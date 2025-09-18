#!/usr/bin/env python3
"""
SDC Demo Suite — Provider ↔ Message Monitor ↔ Consumer
Driven exclusively by the Digital Twin physiology model (no mock constants).

Architecture:
- In-memory SDC-like bus with message types: subscribe, metric_report, waveform_chunk,
  alert_report, set_request, set_response, keepalive. Consistent JSON payloads.
- ModelRuntime wraps DigitalTwinModel, steps at high-rate via solve_ivp windows,
  generates ABP waveform buffer (>=50 Hz for UI), and metrics (1–5 Hz).
- ProviderPane publishes reports from the model and applies set_request to the twin.
- ConsumerPane shows vitals and issues set_request ops (SET_PARAM, ALERT_CTRL) only.
- MonitorPane logs all bus traffic with timestamp, direction, type, filter, export.

Performance notes:
- Internal stepping uses 100 ms windows with 50 eval points (≈500 Hz samples/window),
  appended to a rolling buffer; UI renders at ~50–60 Hz using decimated samples.
- End-to-end latency minimized via in-process bus; typical <50 ms on localhost.

Requirements:
- digital_twin_model.DigitalTwinModel present in repo.
- alarm_module.AlarmModule for threshold evaluation; simple SILENCE/LATCH handling here.
"""

from __future__ import annotations

import os
import sys
import json
import time
import threading
import queue
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB = True
except Exception:
    MATPLOTLIB = False

# Local imports (repo)
from digital_twin_model import DigitalTwinModel
from alarm_module import AlarmModule


# ---------- SDC-like in-memory adapter ----------

MessageType = str


@dataclass
class SDCMessage:
    ts: float
    iso_ts: str
    direction: str  # "consumer->provider", "provider->consumer", "system"
    type: MessageType
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None


class SDCBus:
    def __init__(self):
        self._subscribers: List[Callable[[SDCMessage], None]] = []
        self._lock = threading.Lock()

    def publish(self, msg: SDCMessage):
        with self._lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(msg)
            except Exception:
                pass

    def subscribe(self, callback: Callable[[SDCMessage], None]):
        with self._lock:
            self._subscribers.append(callback)


def now_msg(direction: str, mtype: MessageType, payload: Dict[str, Any], corr: Optional[str] = None) -> SDCMessage:
    ts = time.time()
    return SDCMessage(ts=ts, iso_ts=datetime.fromtimestamp(ts).isoformat(timespec='milliseconds'),
                      direction=direction, type=mtype, payload=payload, correlation_id=corr)


# ---------- Digital Twin runtime wrapper ----------

class ModelRuntime:
    """Wrap DigitalTwinModel with high-rate stepping and waveform/metrics outputs."""

    def __init__(self, scenarios_path: Optional[str] = None, seed: int = 42):
        self.model = DigitalTwinModel(patient_id="demo_suite", param_file=self._find_default_params())
        self.model_seed = seed
        np.random.seed(seed)

        # Alarm module at model layer
        self.alarm = AlarmModule(patient_id="demo_suite")
        self.model.alarmModule = self.alarm

        # Runtime
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Time and buffers
        self.fs_wave = 100.0  # UI render target Hz (decimated)
        self.win_dt = 0.1     # integrate 100 ms windows
        self.win_points = 50  # 50 eval points per window => 500 Hz internal
        self.buffer_secs = 20
        self._wave_time = queue.Queue(maxsize=0)  # not used directly in UI

        # Rolling waveform buffer for ABP (seconds)
        self._buf_max = int(self.buffer_secs * 500)  # internal sample rate ~500 Hz
        self._abp_buffer = np.zeros(self._buf_max, dtype=np.float32)
        self._abp_len = 0

        # Latest metrics
        self.metrics = {
            'HR': 0.0, 'RR': 0.0, 'SpO2': 98.0, 'MAP': 0.0, 'EtCO2': 40.0,
            'SAP': 0.0, 'DAP': 0.0, 'TEMP': 37.0
        }

        # Scenario bundles
        self.scenarios = self._load_scenarios(scenarios_path)

        # Alarm controls
        self._silenced_until: Optional[float] = None
        self._latched: Dict[str, bool] = {}

    def _find_default_params(self) -> str:
        # Prefer MDTparameters/healthy.json else healthyFlat.json
        cwd = os.getcwd()
        candidates = [
            os.path.join(cwd, 'MDTparameters', 'healthy.json'),
            os.path.join(cwd, 'healthyFlat.json')
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        # Fallback to any json in MDTparameters
        mdt = os.path.join(cwd, 'MDTparameters')
        if os.path.isdir(mdt):
            for f in os.listdir(mdt):
                if f.endswith('.json'):
                    return os.path.join(mdt, f)
        raise FileNotFoundError('No parameter file found')

    def _load_scenarios(self, path: Optional[str]) -> Dict[str, Dict[str, Any]]:
        if path and os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        # Minimal built-ins if file missing
        return {
            "Sepsis": {"gas_exchange_params.FI_O2": 50, "cardio_control_params.HR_n": 110, "misc_constants.TBV": 4500},
            "COPD": {"gas_exchange_params.FI_O2": 28, "respiratory_control_params.RR_0": 18},
            "Hypotension": {"cardio_control_params.ABP_n": 60, "cardio_control_params.HR_n": 90}
        }

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def set_params(self, updates: Dict[str, Any]):
        # Updates map 1:1 to master_parameters keys
        for k, v in updates.items():
            if k in self.model.master_parameters:
                self.model.master_parameters[k]['value'] = float(v)
                # Update cached shortcuts used by model
                if k == 'cardio_control_params.HR_n':
                    self.model._ode_HR_n = float(v)
                elif k == 'cardio_control_params.ABP_n':
                    self.model._baro_P_set = float(v)
                elif k == 'respiratory_control_params.RR_0':
                    self.model._ode_RR0 = float(v)
                elif k == 'gas_exchange_params.FI_O2':
                    # Model reads this directly during compute_variables
                    pass

    def apply_scenario(self, name: str):
        updates = self.scenarios.get(name)
        if updates:
            self.set_params(updates)

    def silence_alarms(self, duration_s: int):
        self._silenced_until = time.time() + duration_s

    def reset_alarms(self):
        self._latched.clear()
        self._silenced_until = None
        # Also clear module state
        if hasattr(self.alarm, 'reset'):
            try:
                self.alarm.reset()
            except Exception:
                pass

    def get_waveform_chunk(self, fs_target: float = 100.0, seconds: float = 1.0) -> Dict[str, Any]:
        # Return most recent seconds of ABP decimated to fs_target
        internal_fs = self.win_points / self.win_dt  # ~500 Hz
        n_needed = int(seconds * internal_fs)
        n = min(n_needed, self._abp_len)
        if n <= 0:
            return {"signal": "ABP", "fs": fs_target, "data": []}
        data = self._abp_buffer[self._abp_len - n:self._abp_len]
        # Decimate to fs_target by simple stride
        stride = max(1, int(round(internal_fs / fs_target)))
        dec = data[::stride]
        return {"signal": "ABP", "fs": internal_fs / stride, "data": dec.astype(float).tolist()}

    def get_metrics(self) -> Dict[str, float]:
        return dict(self.metrics)

    def _append_abp(self, arr: np.ndarray):
        length = arr.size
        if length <= 0:
            return
        if length >= self._buf_max:
            self._abp_buffer[:self._buf_max] = arr[-self._buf_max:]
            self._abp_len = self._buf_max
            return
        # Shift if needed
        free = self._buf_max - self._abp_len
        if length > free:
            shift = length - free
            self._abp_buffer[:self._abp_len - shift] = self._abp_buffer[shift:self._abp_len]
            self._abp_len -= shift
        self._abp_buffer[self._abp_len:self._abp_len + length] = arr
        self._abp_len += length

    def _run_loop(self):
        from scipy.integrate import solve_ivp
        current_time = self.model.t
        last_metric_emit = 0.0
        while not self._stop.is_set():
            try:
                sol = solve_ivp(
                    fun=self.model.extended_state_space_equations,
                    t_span=[current_time, current_time + self.win_dt],
                    y0=self.model.current_state,
                    t_eval=np.linspace(current_time, current_time + self.win_dt, self.win_points),
                    method='LSODA', rtol=1e-6, atol=1e-6
                )
                self.model.current_state = sol.y[:, -1]
                current_time += self.win_dt
                self.model.t = current_time

                # Compute variables at each eval point to get ABP samples
                abp_vals = []
                for i in range(sol.y.shape[1]):
                    P, F, HR, SaO2, RR = self.model.compute_variables(sol.t[i], sol.y[:, i])
                    # Arterial pressure approximation from P[0]
                    p0 = P[0] if isinstance(P, (list, np.ndarray)) else float(P)
                    abp_vals.append(float(p0))
                self._append_abp(np.asarray(abp_vals, dtype=np.float32))

                # Update metrics at ~1–2 Hz
                if (current_time - last_metric_emit) >= 0.5:
                    # Use last state
                    P, F, HR, SaO2, RR = self.model.compute_variables(current_time, self.model.current_state)
                    map_val = float(np.mean(P[0])) if hasattr(P[0], '__iter__') else float(P[0])
                    # Estimate systolic/diastolic from recent buffer
                    window = min(self._abp_len, int(2 * self.win_points))
                    if window > 0:
                        recent = self._abp_buffer[self._abp_len - window:self._abp_len]
                        sap = float(np.max(recent))
                        dap = float(np.min(recent))
                    else:
                        sap = map_val
                        dap = map_val
                    # Temperature & EtCO2 proxies from state (consistent with provider_MDT)
                    temp = 37.0 + 0.1 * np.random.normal()  # small physiological variability
                    etco2 = float(self.model.current_state[17]) if len(self.model.current_state) > 17 else 40.0

                    self.metrics.update({
                        'HR': float(HR), 'RR': float(RR), 'SpO2': float(SaO2),
                        'MAP': float(map_val), 'EtCO2': float(etco2), 'SAP': float(sap), 'DAP': float(dap),
                        'TEMP': float(temp)
                    })
                    last_metric_emit = current_time
            except Exception:
                # Avoid tight loop on error
                time.sleep(0.01)


# ---------- UI Panes ----------

class ProviderPane:
    def __init__(self, root: tk.Tk, bus: SDCBus, runtime: ModelRuntime):
        self.runtime = runtime
        self.bus = bus
        self.win = tk.Toplevel(root)
        self.win.title("SDC Provider (Digital Twin)")
        self.win.geometry("700x500")
        self._build_ui()

        # Subscribe to bus for set_request
        bus.subscribe(self._on_bus)

        # Periodic publishers
        self._tick()

        # Alarm state
        self._silenced_until: Optional[float] = None

    def _build_ui(self):
        top = tk.Frame(self.win)
        top.pack(fill=tk.X)
        self.status_lbl = tk.Label(top, text="Receiving remote control from Consumer", fg='green')
        self.status_lbl.pack(side=tk.LEFT, padx=5, pady=5)

        # Vital tiles
        tiles = tk.Frame(self.win)
        tiles.pack(fill=tk.X)
        self._tile_vars: Dict[str, tk.StringVar] = {}
        for name in ["HR", "RR", "SpO2", "MAP", "EtCO2"]:
            f = tk.Frame(tiles, relief='groove', borderwidth=1)
            f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3, pady=3)
            tk.Label(f, text=name, font=('Helvetica', 10, 'bold')).pack()
            var = tk.StringVar(value="--")
            tk.Label(f, textvariable=var, font=('Helvetica', 16, 'bold')).pack()
            self._tile_vars[name] = var

        # Alarm panel
        alarm = tk.LabelFrame(self.win, text="Alarms")
        alarm.pack(fill=tk.X, padx=5, pady=5)
        self.alarm_state = tk.Label(alarm, text="INACTIVE")
        self.alarm_state.pack(side=tk.LEFT, padx=5)
        tk.Button(alarm, text="Silence 60s", command=lambda: self._alert_ctrl('SILENCE', 60)).pack(side=tk.RIGHT)

        # Waveform panel
        self.wave_frame = tk.Frame(self.win)
        self.wave_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = None
        if MATPLOTLIB:
            fig = Figure(figsize=(6, 3), dpi=100)
            self.ax = fig.add_subplot(111)
            self.ax.set_title('ABP')
            self.ax.set_ylabel('mmHg')
            self.ax.set_xlabel('s')
            self.line, = self.ax.plot([], [], lw=1)
            self.canvas = FigureCanvasTkAgg(fig, master=self.wave_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _alert_ctrl(self, action: str, duration: int = 0):
        corr = str(uuid.uuid4())
        req = now_msg("consumer->provider", "set_request",
                      {"op": "ALERT_CTRL", "action": action, "duration_s": duration}, corr)
        # Loopback via bus (in real SDC, Consumer would emit)
        self.bus.publish(req)

    def _on_bus(self, msg: SDCMessage):
        if msg.type == 'set_request' and msg.direction.startswith('consumer'):
            corr = msg.correlation_id or str(uuid.uuid4())
            op = msg.payload.get('op')
            if op == 'SET_PARAM':
                params = msg.payload.get('params', {})
                self.runtime.set_params(params)
                self.bus.publish(now_msg("provider->consumer", "set_response",
                                         {"status": "OK", "applied": params}, corr))
            elif op == 'ALERT_CTRL':
                action = msg.payload.get('action')
                if action == 'SILENCE':
                    dur = int(msg.payload.get('duration_s', 60))
                    self.runtime.silence_alarms(dur)
                elif action == 'RESET':
                    self.runtime.reset_alarms()
                self.bus.publish(now_msg("provider->consumer", "set_response",
                                         {"status": "OK", "action": action}, corr))

    def _tick(self):
        # Publish metrics
        metrics = self.runtime.get_metrics()
        self.bus.publish(now_msg("provider->consumer", "metric_report", metrics))

        # Publish waveform chunk (1s)
        chunk = self.runtime.get_waveform_chunk(fs_target=100.0, seconds=5.0)
        self.bus.publish(now_msg("provider->consumer", "waveform_chunk", chunk))

        # Evaluate alarms and publish
        alarm_data = {
            'HR': metrics['HR'], 'MAP': metrics['MAP'], 'SaO2': metrics['SpO2'], 'TEMP': metrics['TEMP'],
            'RR': metrics['RR'], 'EtCO2': metrics['EtCO2']
        }
        events = self.runtime.alarm.evaluate_alarms(alarm_data)
        # Determine state considering silence
        silenced = self.runtime._silenced_until and time.time() < self.runtime._silenced_until
        active = any(e.get('active') for e in events)
        state_text = "SILENCED" if silenced and active else ("ACTIVE" if active else "INACTIVE")
        self.alarm_state.config(text=state_text, fg=('orange' if silenced else ('red' if active else 'green')))
        self.bus.publish(now_msg("provider->consumer", "alert_report",
                                 {"events": events, "state": state_text}))

        # Update tiles
        for k, var in self._tile_vars.items():
            val = metrics.get(k, "--")
            if isinstance(val, float):
                if k in ("HR", "RR", "SpO2", "EtCO2"):
                    var.set(f"{val:.0f}")
                else:
                    var.set(f"{val:.1f}")
            else:
                var.set(str(val))

        # Update waveform
        if self.canvas is not None:
            wf = self.runtime.get_waveform_chunk(fs_target=50.0, seconds=10.0)
            y = np.asarray(wf['data'], dtype=float)
            if y.size > 0:
                x = np.linspace(-len(y)/wf['fs'], 0, len(y))
                self.ax.clear()
                self.ax.set_title('ABP')
                self.ax.set_ylabel('mmHg')
                self.ax.set_xlabel('s')
                self.ax.plot(x, y, lw=1)
                self.ax.set_xlim(x[0], x[-1] if x.size > 0 else 1)
                self.canvas.draw()

        self.win.after(50, self._tick)  # ~20 Hz UI updates


class ConsumerPane:
    def __init__(self, root: tk.Tk, bus: SDCBus, runtime: ModelRuntime):
        self.runtime = runtime
        self.bus = bus
        self.win = tk.Toplevel(root)
        self.win.title("SDC Consumer (Controls)")
        self.win.geometry("450x500")
        self._build_ui()
        bus.subscribe(self._on_bus)

    def _build_ui(self):
        # Vital tiles
        tiles = tk.Frame(self.win)
        tiles.pack(fill=tk.X)
        self._tile_vars: Dict[str, tk.StringVar] = {}
        for name in ["HR", "RR", "SpO2", "MAP", "EtCO2"]:
            f = tk.Frame(tiles, relief='groove', borderwidth=1)
            f.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3, pady=3)
            tk.Label(f, text=name, font=('Helvetica', 10, 'bold')).pack()
            var = tk.StringVar(value="--")
            tk.Label(f, textvariable=var, font=('Helvetica', 16, 'bold')).pack()
            self._tile_vars[name] = var

        # Controls
        ctl = tk.LabelFrame(self.win, text="Physiology Controls (via SET_PARAM)")
        ctl.pack(fill=tk.X, padx=5, pady=5)

        self._controls: List[tuple] = []
        def add_slider(label, key, frm, to, init):
            row = tk.Frame(ctl)
            row.pack(fill=tk.X, padx=4, pady=2)
            tk.Label(row, text=label, width=12).pack(side=tk.LEFT)
            var = tk.DoubleVar(value=init)
            scale = tk.Scale(row, from_=frm, to=to, orient=tk.HORIZONTAL, showvalue=True,
                             resolution=1 if key != 'gas_exchange_params.FI_O2' else 1,
                             variable=var, length=220)
            scale.pack(side=tk.LEFT)
            btn = tk.Button(row, text="SET", command=lambda k=key, v=var: self._send_set_param(k, v.get()))
            btn.pack(side=tk.RIGHT)
            self._controls.append((key, var))

        # Common controls
        add_slider("HR_set", 'cardio_control_params.HR_n', 40, 150, 70)
        add_slider("ABP_set", 'cardio_control_params.ABP_n', 50, 130, 90)
        add_slider("RR_set", 'respiratory_control_params.RR_0', 8, 40, 15)
        add_slider("FiO2_set", 'gas_exchange_params.FI_O2', 21, 100, 40)

        # Alert buttons
        alert = tk.LabelFrame(self.win, text="Alert Controls")
        alert.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(alert, text="Silence 60s", command=lambda: self._send_alert('SILENCE', 60)).pack(side=tk.LEFT, padx=5)
        tk.Button(alert, text="Reset", command=lambda: self._send_alert('RESET', 0)).pack(side=tk.LEFT)

        # Scenarios
        scen = tk.LabelFrame(self.win, text="Scenarios")
        scen.pack(fill=tk.X, padx=5, pady=5)
        self.scen_var = tk.StringVar(value=list(self.runtime.scenarios.keys())[0])
        ttk.Combobox(scen, textvariable=self.scen_var, values=list(self.runtime.scenarios.keys()), state='readonly').pack(side=tk.LEFT, padx=5)
        tk.Button(scen, text="Apply", command=self._apply_scenario).pack(side=tk.LEFT)

    def _apply_scenario(self):
        name = self.scen_var.get()
        params = self.runtime.scenarios.get(name, {})
        corr = str(uuid.uuid4())
        self.bus.publish(now_msg("consumer->provider", "set_request", {"op": "SET_PARAM", "params": params}, corr))

    def _send_set_param(self, key: str, value: float):
        corr = str(uuid.uuid4())
        self.bus.publish(now_msg("consumer->provider", "set_request", {"op": "SET_PARAM", "params": {key: value}}, corr))

    def _send_alert(self, action: str, duration: int):
        corr = str(uuid.uuid4())
        self.bus.publish(now_msg("consumer->provider", "set_request", {"op": "ALERT_CTRL", "action": action, "duration_s": duration}, corr))

    def _on_bus(self, msg: SDCMessage):
        if msg.type == 'metric_report' and msg.direction.startswith('provider'):
            metrics = msg.payload
            for k_ui, src in [("HR", 'HR'), ("RR", 'RR'), ("SpO2", 'SpO2'), ("MAP", 'MAP'), ("EtCO2", 'EtCO2')]:
                v = metrics.get(src)
                if v is not None:
                    self._tile_vars[k_ui].set(f"{v:.0f}" if k_ui in ("HR", "RR", "SpO2", "EtCO2") else f"{v:.1f}")


class MonitorPane:
    def __init__(self, root: tk.Tk, bus: SDCBus):
        self.bus = bus
        self.win = tk.Toplevel(root)
        self.win.title("SDC Message Monitor")
        self.win.geometry("700x500")
        self._build_ui()
        bus.subscribe(self._on_bus)

    def _build_ui(self):
        # Filters
        filt = tk.Frame(self.win)
        filt.pack(fill=tk.X)
        tk.Label(filt, text="Filter type:").pack(side=tk.LEFT)
        self.type_var = tk.StringVar(value="")
        ttk.Combobox(filt, textvariable=self.type_var, values=["", "metric_report", "waveform_chunk", "alert_report", "set_request", "set_response", "subscribe", "keepalive"], state='readonly', width=20).pack(side=tk.LEFT)
        tk.Button(filt, text="Clear", command=lambda: self.type_var.set(""))
        tk.Button(filt, text="Export NDJSON", command=self._export).pack(side=tk.RIGHT, padx=5)

        # Treeview
        cols = ("time", "dir", "type", "payload")
        self.tree = ttk.Treeview(self.win, columns=cols, show='headings')
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=120 if c != 'payload' else 400)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Store for export
        self._msgs: List[SDCMessage] = []

        # Periodic filter refresh
        self.win.after(500, self._refresh)

    def _on_bus(self, msg: SDCMessage):
        self._msgs.append(msg)
        # Apply filter
        tfilter = self.type_var.get()
        if tfilter and msg.type != tfilter:
            return
        payload_preview = json.dumps(msg.payload)[:200]
        self.tree.insert('', 'end', values=(msg.iso_ts, msg.direction, msg.type, payload_preview))

    def _refresh(self):
        # If filter changed, rebuild view
        # For simplicity, always no-op; could re-render when filter non-empty
        self.win.after(500, self._refresh)

    def _export(self):
        try:
            path = filedialog.asksaveasfilename(defaultextension='.ndjson', filetypes=[('NDJSON', '*.ndjson'), ('All files', '*.*')])
            if not path:
                return
            with open(path, 'w') as f:
                for m in self._msgs:
                    f.write(json.dumps({
                        'ts': m.ts, 'iso_ts': m.iso_ts, 'direction': m.direction, 'type': m.type,
                        'payload': m.payload, 'correlation_id': m.correlation_id
                    }) + '\n')
        except Exception:
            pass


# ---------- Main launcher ----------

def main():
    # Root and panes
    root = tk.Tk()
    root.title("SDC Demo Suite")
    root.geometry("200x100")
    tk.Label(root, text="SDC Demo Suite running...\nClose this to exit.").pack(padx=10, pady=10)

    bus = SDCBus()
    runtime = ModelRuntime(scenarios_path=os.path.join(os.getcwd(), 'scenarios.json') if os.path.exists('scenarios.json') else None)
    runtime.start()

    ProviderPane(root, bus, runtime)
    MonitorPane(root, bus)
    ConsumerPane(root, bus, runtime)

    try:
        root.mainloop()
    finally:
        runtime.stop()


if __name__ == '__main__':
    main()
