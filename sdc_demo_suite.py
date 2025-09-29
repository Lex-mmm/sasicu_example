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
from collections import deque

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB = True
except Exception:
    MATPLOTLIB = False

# Enforce Python version before importing local modules that use match/case
if sys.version_info < (3, 10):
    sys.stderr.write(f"Python 3.10+ is required. Detected {sys.version.split()[0]}.\n"
                     "Please run with the project venv: ./env/bin/python3 sdc_demo_suite.py\n")
    sys.exit(1)

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
    device_id: Optional[str] = None  # allow multiplexing multiple devices on one bus


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


def now_msg(direction: str, mtype: MessageType, payload: Dict[str, Any], corr: Optional[str] = None, device_id: Optional[str] = None) -> SDCMessage:
    ts = time.time()
    return SDCMessage(ts=ts, iso_ts=datetime.fromtimestamp(ts).isoformat(timespec='milliseconds'),
                      direction=direction, type=mtype, payload=payload, correlation_id=corr, device_id=device_id)


# ---------- Digital Twin runtime wrapper ----------

class ModelRuntime:
    """Adapter to run the DigitalTwinModel and expose waveforms/metrics from it."""

    def __init__(self, scenarios_path: Optional[str] = None, seed: int = 42):
        self.model = DigitalTwinModel(patient_id="demo_suite", param_file=self._find_default_params())
        self.model.sleep = True  # use model's internal sleep pacing
        np.random.seed(seed)

        # Alarm module at model layer
        self.alarm = AlarmModule(patient_id="demo_suite")
        self.model.alarmModule = self.alarm

        # Continuous waveform state for patient monitor
        self._ecg_phase = 0.0
        self._ecg_total = 0
        self._pleth_total = 0

        # Thread control delegates to model's start/stop loop
        self._thread = None
        self._paused = threading.Event(); self._paused.clear()

        # Simple scenarios mapped to twin parameter keys
        self.scenarios: Dict[str, Dict[str, float]] = {
            'Baseline': {
                'cardio_control_params.HR_n': 70,
                'cardio_control_params.ABP_n': 90,
                'respiratory_control_params.RR_0': 14,
                'gas_exchange_params.FI_O2': 0.21,
            },
            'Tachycardia': {
                'cardio_control_params.HR_n': 120,
            },
            'Hypotension': {
                'cardio_control_params.ABP_n': 60,
            },
            'Hypoxemia': {
                'gas_exchange_params.FI_O2': 0.18,
            },
        }

    def _find_default_params(self) -> str:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(here, 'healthyFlat.json'),
            os.path.join(os.getcwd(), 'healthyFlat.json'),
            os.path.join(here, 'MDTparameters', 'healthy.json'),
            os.path.join(os.getcwd(), 'MDTparameters', 'healthy.json'),
        ]
        # Also try next to the model file
        try:
            import inspect
            import digital_twin_model as _dtm
            model_dir = os.path.dirname(os.path.abspath(inspect.getfile(_dtm)))
            candidates.append(os.path.join(model_dir, 'healthyFlat.json'))
            candidates.append(os.path.join(model_dir, 'MDTparameters', 'healthy.json'))
        except Exception:
            pass
        # As a last resort, scan MDTparameters for any .json and pick healthy* if found
        mdt_dirs = [
            os.path.join(here, 'MDTparameters'),
            os.path.join(os.getcwd(), 'MDTparameters'),
        ]
        try:
            import glob
            for d in mdt_dirs:
                if os.path.isdir(d):
                    healthy = sorted(glob.glob(os.path.join(d, 'healthy*.json')))
                    candidates.extend(healthy)
                    anyjson = sorted(glob.glob(os.path.join(d, '*.json')))
                    candidates.extend(anyjson)
        except Exception:
            pass
        for c in candidates:
            if os.path.exists(c):
                return c
        # Fallback to relative name (will likely fail but surfaces path)
        return 'healthyFlat.json'

    # Lifecycle
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.model.start_simulation, daemon=True)
        self._thread.start()

    def stop(self):
        try:
            self.model.stop_simulation()
        except Exception:
            pass
        if self._thread:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass

    def pause(self):
        # Model doesn't support pause; emulate via sleep gating
        self._paused.set()
        self.model.sleep = True

    def resume(self):
        self._paused.clear()
        self.model.sleep = True

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def silence_alarms(self, duration_s: int = 60):
        # Placeholder hooks into AlarmModule level if needed
        pass

    def reset_alarms(self):
        # Placeholder
        pass

    # Waveforms and metrics
    def get_waveform_chunk(self, signal: str, fs_target: float = 100.0, seconds: float = 2.0) -> Dict[str, Any]:
        sig = signal.upper()
        # ECG/ABP/Pleth at display rate. ABP is taken from twin buffer; ECG is continuous template; Pleth derived from ABP.
        fs_model = 1.0 / self.model.dt
        if sig == 'ABP':
            arr = np.array(list(self.model.P_store), dtype=float)
            if arr.size == 0:
                return {"signal": 'ABP', "fs": fs_target, "data": []}
            n_needed = int(seconds * fs_model)
            if arr.size > n_needed:
                arr = arr[-n_needed:]
            stride = max(1, int(round(fs_model / fs_target)))
            dec = arr[::stride]
            return {"signal": 'ABP', "fs": fs_model/stride, "data": dec.astype(float).tolist()}
        elif sig == 'ECG':
            # Continuous P-QRS-T template driven by HR
            n = max(1, int(seconds * fs_target))
            dt = 1.0 / fs_target
            hr = float(getattr(self.model, 'HR', 70.0))
            hr = float(np.clip(hr, 30.0, 180.0))
            f_hr = hr / 60.0
            y = np.zeros(n, dtype=float)
            def gauss(x, mu, sigma):
                return np.exp(-0.5 * ((x - mu) / sigma) ** 2)
            for i in range(n):
                self._ecg_phase += 2*np.pi * f_hr * dt
                if self._ecg_phase >= 2*np.pi:
                    self._ecg_phase -= 2*np.pi
                phi = self._ecg_phase / (2*np.pi)
                p = 0.12 * gauss(phi, 0.18, 0.03)
                q = -0.12 * gauss(phi, 0.49, 0.012)
                r = 1.1 * gauss(phi, 0.50, 0.010)
                s = -0.22 * gauss(phi, 0.515, 0.012)
                t = 0.30 * gauss(phi, 0.70, 0.06)
                y[i] = p + q + r + s + t
            self._ecg_total += n
            return {"signal": 'ECG', "fs": fs_target, "data": y.tolist(), "total": self._ecg_total}
        elif sig == 'PLETH':
            # Derive pleth from ABP for cardiovascular consistency
            arr = np.array(list(self.model.P_store), dtype=float)
            if arr.size == 0:
                return {"signal": 'PLETH', "fs": fs_target, "data": [], "total": self._pleth_total}
            n_needed = int(seconds * fs_model)
            if arr.size > n_needed:
                arr = arr[-n_needed:]
            stride = max(1, int(round(fs_model / fs_target)))
            dec = arr[::stride]
            # Normalize to 0..1 and lightly smooth
            lo = np.percentile(dec, 5)
            hi = np.percentile(dec, 95)
            rng = max(1e-3, hi - lo)
            y = (dec - lo) / rng
            # Simple moving average smoothing
            if y.size >= 5:
                k = 5
                kernel = np.ones(k) / k
                y = np.convolve(y, kernel, mode='same')
            y = 0.2 + 0.8 * np.clip(y, 0.0, 1.0)
            self._pleth_total += y.size
            return {"signal": 'PLETH', "fs": fs_model/stride, "data": y.astype(float).tolist(), "total": self._pleth_total}
        else:
            return {"signal": sig, "fs": fs_target, "data": []}

    def get_waveform_since(self, signal: str, last_total: int, fs_target: float = 100.0, max_seconds: float = 1.0) -> Dict[str, Any]:
        # Generate a short slice, maintaining continuity for ECG/PLETH totals
        sig = signal.upper()
        seconds = min(max_seconds, 0.5)
        chunk = self.get_waveform_chunk(sig, fs_target=fs_target, seconds=seconds)
        # Ensure total key is present for UI cursors
        if 'total' not in chunk:
            tot = last_total + len(chunk.get('data', []))
            chunk['total'] = tot
        return chunk

    def get_metrics(self) -> Dict[str, Any]:
        # Pull latest numerics from model
        hr = float(self.model.HR)
        rr = float(self.model.RR)
        spo2 = float(getattr(self, '_spo2_cache', 98.0))
        mapv = float(getattr(self.model, 'recent_MAP', self.model.master_parameters['cardio_control_params.ABP_n']['value']))
        sap = mapv + 20.0
        dap = mapv - 10.0
        etco2 = float(self.model.current_state[17]) if self.model.current_state is not None else 40.0
        temp = 37.0
        return {'HR': hr, 'RR': rr, 'SpO2': spo2, 'MAP': mapv, 'EtCO2': etco2, 'SAP': sap, 'DAP': dap, 'TEMP': temp}

    def set_params(self, params: Dict[str, Any]):
        # Apply directly to the model parameters
        for k, v in params.items():
            try:
                self.model.master_parameters[k]['value'] = float(v)
            except Exception:
                # also try high-level update_param path
                try:
                    self.model.update_param(self.model.patient_id, k.split('.')[-1], v)
                except Exception:
                    pass
        # Re-cache ODE params after changes
        try:
            self.model._cache_ode_parameters()
        except Exception:
            pass


class InfusionPumpRuntime:
    """Simple infusion pump runtime model with rate, VTBI, and alarms."""
    def __init__(self, seed: int = 1):
        self.rate_ml_h = 0.0  # mL/h
        self.vtbi_ml = 0.0    # volume to be infused mL
        self.delivered_ml = 0.0
        self.occlusion = False
        self.running = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_t = None
        self._alarms = {
            'OCCLUSION': False,
            'VTBI_COMPLETE': False
        }

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        # Start background loop but do not auto-run delivery; UI controls it
        self.running = False
        self._last_t = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def prime(self):
        # Reset delivered and alarms
        self.delivered_ml = 0.0
        self._alarms['VTBI_COMPLETE'] = False

    def set_rate(self, rate_ml_h: float):
        self.rate_ml_h = max(0.0, float(rate_ml_h))

    def set_vtbi(self, vtbi_ml: float):
        self.vtbi_ml = max(0.0, float(vtbi_ml))
        # Clear complete if new VTBI set larger than delivered
        if self.vtbi_ml > self.delivered_ml:
            self._alarms['VTBI_COMPLETE'] = False

    def set_occlusion(self, on: bool):
        self.occlusion = bool(on)
        if not self.occlusion:
            self._alarms['OCCLUSION'] = False

    def start_delivery(self):
        self.running = True
        self._last_t = time.time()

    def pause_delivery(self):
        self.running = False

    def _loop(self):
        while not self._stop.is_set():
            now = time.time()
            if self._last_t is None:
                self._last_t = now
            dt = now - self._last_t
            self._last_t = now
            if self.running and not self.occlusion and not self._alarms['VTBI_COMPLETE']:
                ml_per_s = self.rate_ml_h / 3600.0
                self.delivered_ml += ml_per_s * dt
                if self.vtbi_ml > 0 and self.delivered_ml >= self.vtbi_ml:
                    self.delivered_ml = self.vtbi_ml
                    self._alarms['VTBI_COMPLETE'] = True
                    self.running = False
            # Occlusion logic: if occluded and running at non-zero rate, raise alarm
            if self.running and self.occlusion and self.rate_ml_h > 0:
                self._alarms['OCCLUSION'] = True
                self.running = False
            time.sleep(0.05)

    def get_metrics(self) -> Dict[str, Any]:
        remaining = max(0.0, self.vtbi_ml - self.delivered_ml) if self.vtbi_ml > 0 else 0.0
        return {
            'rate_ml_h': float(self.rate_ml_h),
            'vtbi_ml': float(self.vtbi_ml),
            'delivered_ml': float(self.delivered_ml),
            'remaining_ml': float(remaining),
            'running': bool(self.running),
            'occlusion': bool(self.occlusion)
        }

    def get_alarms(self) -> Dict[str, str]:
        # States: INACTIVE/ACTIVE
        return {k: ('ACTIVE' if v else 'INACTIVE') for k, v in self._alarms.items()}


# ---------- UI Panes ----------

class ProviderPane:
    def __init__(self, root: tk.Tk, bus: SDCBus, runtime: ModelRuntime, device_id: str = "MDT"):
        self.runtime = runtime
        self.bus = bus
        self.device_id = device_id
        self.win = tk.Toplevel(root)
        self.win.title("Medical Digital Twin — SDC Provider")
        self.win.geometry("1400x700")
        self._closed = False
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()

        # Subscribe to bus for set_request
        bus.subscribe(self._on_bus)

        # Periodic publishers
        self._tick()

        # Alarm state
        self._silenced_until = None

    def _on_close(self):
        self._closed = True
        try:
            self.win.destroy()
        except Exception:
            pass

    def _build_ui(self):
        # Header with alarm state
        top = tk.Frame(self.win, bg='#222')
        top.pack(fill=tk.X)
        self.status_lbl = tk.Label(top, text="Provider running — remote control enabled", fg='white', bg='#222')
        self.status_lbl.pack(side=tk.LEFT, padx=10, pady=6)
        self._run_btn = tk.Button(top, text="Stop", command=self._toggle_run)
        self._run_btn.pack(side=tk.RIGHT, padx=10)

        alarm_bar = tk.Frame(self.win, bg='#444')
        alarm_bar.pack(fill=tk.X)
        self.alarm_state = tk.Label(alarm_bar, text="INACTIVE", fg='white', bg='#444', font=('Helvetica', 14, 'bold'))
        self.alarm_state.pack(side=tk.LEFT, padx=10, pady=4)
        btns = tk.Frame(alarm_bar, bg='#444')
        btns.pack(side=tk.RIGHT)
        tk.Button(btns, text="Reset", command=lambda: self._alert_ctrl('RESET', 0)).pack(side=tk.RIGHT, padx=6, pady=4)
        tk.Button(btns, text="Silence 60s", command=lambda: self._alert_ctrl('SILENCE', 60)).pack(side=tk.RIGHT, padx=6, pady=4)

        # Content frame
        content = tk.Frame(self.win, bg='black')
        content.pack(fill=tk.BOTH, expand=True)
        left = tk.Frame(content, bg='black')
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = tk.Frame(content, bg='black')
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=16)

        # Plot setup: ECG, Pleth, and Art
        self.canvas = None
        self.axes = {}
        self.lines = {}
        self.plot_window_seconds = 30
        self._ecg_time = time.time()
        self._abp_time = time.time()
        self._pleth_time = time.time()
        self.ecg_x = deque(maxlen=30000)
        self.ecg_y = deque(maxlen=30000)
        self.pleth_x = deque(maxlen=30000)
        self.pleth_y = deque(maxlen=30000)
        self.abp_x = deque(maxlen=30000)
        self.abp_y = deque(maxlen=30000)
        # Waveform cursors (internal total sample counters)
        self._ecg_total_cursor = 0
        self._abp_total_cursor = 0
        self._pleth_total_cursor = 0

        if MATPLOTLIB:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            fig = Figure(figsize=(10, 6), dpi=100, facecolor='black')
            # ECG
            ax1 = fig.add_subplot(3, 1, 1)
            line1, = ax1.plot([], [], color='lime', lw=1)
            ax1.set_ylim(-1.5, 1.5)
            ax1.set_facecolor('black')
            ax1.set_xticks([])
            ax1.set_yticks([])
            for sp in ax1.spines.values():
                sp.set_visible(False)
            ax1.set_title('ECG', color='white', fontsize=10, pad=5, loc='left')
            self.axes['ECG'] = ax1
            self.lines['ECG'] = line1
            # Pleth (SpO2)
            ax2 = fig.add_subplot(3, 1, 2)
            line2, = ax2.plot([], [], color='cyan', lw=1)
            ax2.set_ylim(0.0, 1.2)
            ax2.set_facecolor('black')
            ax2.set_xticks([])
            ax2.set_yticks([])
            for sp in ax2.spines.values():
                sp.set_visible(False)
            ax2.set_title('SpO₂ Pleth', color='white', fontsize=10, pad=5, loc='left')
            self.axes['PLETH'] = ax2
            self.lines['PLETH'] = line2
            # Art (ABP)
            ax3 = fig.add_subplot(3, 1, 3)
            line3, = ax3.plot([], [], color='red', lw=1)
            ax3.set_ylim(50, 160)
            ax3.set_facecolor('black')
            ax3.set_xticks([])
            ax3.set_yticks([])
            for sp in ax3.spines.values():
                sp.set_visible(False)
            ax3.set_title('Art (mmHg)', color='white', fontsize=10, pad=5, loc='left')
            self.axes['ABP'] = ax3
            self.lines['ABP'] = line3

            fig.tight_layout(pad=2)
            self.canvas = FigureCanvasTkAgg(fig, master=left)
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Right side big numerics with inline alarm controls
        self._tile_vars = {}
        self._vital_state_labels: Dict[str, tk.Label] = {}
        def big_label(parent, textvar, color, size):
            return tk.Label(parent, textvariable=textvar, font=('Helvetica', size, 'bold'), fg=color, bg='black', anchor='w', width=6)
        def title_row(parent, text, param_key=None, color='white'):
            fr = tk.Frame(parent, bg='black'); fr.pack(anchor='w', fill=tk.X)
            tk.Label(fr, text=text, font=('Helvetica', 14), fg=color, bg='black', anchor='w').pack(side=tk.LEFT)
            # state indicator dot (alarm state)
            if param_key:
                dot = tk.Label(fr, text='●', fg='green', bg='black')
                dot.pack(side=tk.LEFT, padx=4)
                self._vital_state_labels[param_key] = dot
            return fr

        self.hr_var = tk.StringVar(value="--")
        self.map_var = tk.StringVar(value="--")
        self.map_dia_var = tk.StringVar(value="(--) ")
        self.spo2_var = tk.StringVar(value="--")
        self.rr_var = tk.StringVar(value="--")
        self.etco2_var = tk.StringVar(value="--")
        self.temp_var = tk.StringVar(value="--")

        # HR
        title_row(right, "HR", param_key='HeartRate')
        big_label(right, self.hr_var, 'lime', 48).pack(anchor='w', pady=(0, 8))
        # MAP and SAP/DAP
        title_row(right, "MAP", param_key='BloodPressureMean')
        big_label(right, self.map_var, 'red', 48).pack(anchor='w')
        big_label(right, self.map_dia_var, 'red', 28).pack(anchor='w', pady=(0, 8))
        # SpO2
        title_row(right, "SpO₂", param_key='SpO2')
        big_label(right, self.spo2_var, 'cyan', 48).pack(anchor='w', pady=(0, 8))
        # RR
        title_row(right, "RR", param_key='RespiratoryRate')
        big_label(right, self.rr_var, 'white', 48).pack(anchor='w', pady=(0, 8))
        # EtCO2
        title_row(right, "EtCO₂", param_key='EtCO2')
        big_label(right, self.etco2_var, 'yellow', 48).pack(anchor='w', pady=(0, 8))
        # Temp
        title_row(right, "Temp", param_key='Temperature')
        big_label(right, self.temp_var, 'orange', 48).pack(anchor='w', pady=(0, 8))

        # Controls panel on provider side
        ctl_bar = tk.Frame(right, bg='black')
        ctl_bar.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(ctl_bar, text="Parameters", command=self._open_params_window).pack(side=tk.LEFT, padx=4)
        ttk.Button(ctl_bar, text="Alarm Settings", command=self._open_alarm_window).pack(side=tk.LEFT, padx=4)

        # Provider-side Alarms panel (headline + list)
        alarm_fr = tk.LabelFrame(right, text='Alarms', bg='black', fg='white')
        alarm_fr.pack(fill=tk.X, pady=(12, 0))
        self.alarm_headline_var_provider = tk.StringVar(value='INACTIVE')
        tk.Label(alarm_fr, textvariable=self.alarm_headline_var_provider, fg='red', bg='black').pack(anchor='w', padx=6, pady=(4, 6))
        self.alarm_list_fr_provider = tk.Frame(alarm_fr, bg='black')
        self.alarm_list_fr_provider.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._alarm_rows_provider = []

    def _toggle_run(self):
        if self.runtime.is_paused():
            self.runtime.resume()
            self._run_btn.config(text="Stop")
            self.status_lbl.config(text="Provider running — remote control enabled")
        else:
            self.runtime.pause()
            self._run_btn.config(text="Start")
            self.status_lbl.config(text="Provider paused — remote control enabled")

    def _alert_ctrl(self, action: str, duration: int = 0):
        corr = str(uuid.uuid4())
        req = now_msg("consumer->provider", "set_request",
                      {"op": "ALERT_CTRL", "action": action, "duration_s": duration}, corr)
        self.bus.publish(req)

    def _send_set_param(self, key: str, value: float):
        corr = str(uuid.uuid4())
        self.bus.publish(now_msg("consumer->provider", "set_request", {"op": "SET_PARAM", "params": {key: value}}, corr))

    def _open_params_window(self):
        top = tk.Toplevel(self.win)
        top.title("Provider Parameters")
        top.configure(bg='#2b2b2b')
        scen_fr = tk.LabelFrame(top, text="Scenarios", bg='#2b2b2b', fg='white')
        scen_fr.pack(fill=tk.X, padx=12, pady=8)
        scen_var = tk.StringVar(value=list(self.runtime.scenarios.keys())[0])
        ttk.Combobox(scen_fr, textvariable=scen_var, values=list(self.runtime.scenarios.keys()), state='readonly').pack(side=tk.LEFT, padx=6)
        def apply_scen():
            name = scen_var.get()
            params = self.runtime.scenarios.get(name, {})
            if params:
                corr = str(uuid.uuid4())
                self.bus.publish(now_msg("consumer->provider", "set_request", {"op": "SET_PARAM", "params": params}, corr))
        ttk.Button(scen_fr, text="Apply", command=apply_scen).pack(side=tk.LEFT, padx=6)
        def add_slider(label, key, lo, hi, init):
            fr = tk.Frame(top, bg='#2b2b2b')
            fr.pack(fill=tk.X, padx=12, pady=8)
            tk.Label(fr, text=label, fg='white', bg='#2b2b2b', width=14).pack(side=tk.LEFT)
            var = tk.DoubleVar(value=init)
            sc = tk.Scale(fr, from_=lo, to=hi, orient=tk.HORIZONTAL, resolution=1,
                          length=220, bg='#2b2b2b', fg='white', troughcolor='#444444', highlightbackground='#2b2b2b',
                          variable=var)
            sc.pack(side=tk.LEFT)
            ttk.Button(fr, text="SET", command=lambda k=key, v=var: self._send_set_param(k, v.get())).pack(side=tk.LEFT, padx=6)
        mp = self.runtime.model.master_parameters
        getv = lambda k, d: mp.get(k, {}).get('value', d)
        add_slider("HR_n (bpm)", 'cardio_control_params.HR_n', 40, 150, getv('cardio_control_params.HR_n', 70))
        add_slider("ABP_n (mmHg)", 'cardio_control_params.ABP_n', 50, 130, getv('cardio_control_params.ABP_n', 90))
        add_slider("RR_0 (bpm)", 'respiratory_control_params.RR_0', 8, 40, getv('respiratory_control_params.RR_0', 15))
        add_slider("FiO2 (%)", 'gas_exchange_params.FI_O2', 21, 100, getv('gas_exchange_params.FI_O2', 0.4)*100 if getv('gas_exchange_params.FI_O2', 0.4) <= 1 else getv('gas_exchange_params.FI_O2', 40))
        ttk.Button(top, text="Close", command=top.destroy).pack(pady=8)

    def _open_alarm_window(self):
        top = tk.Toplevel(self.win)
        top.title("Alarm Settings")
        top.configure(bg='#2b2b2b')
        cfg = self.runtime.alarm.get_alarm_config()["alarm_parameters"]
        params = [
            ("HeartRate", "HR"), ("BloodPressureMean", "MAP"), ("SpO2", "SpO₂"),
            ("RespiratoryRate", "RR"), ("EtCO2", "EtCO₂"), ("Temperature", "Temp")
        ]
        entries = {}
        for p_key, label in params:
            section = cfg.get(p_key, {})
            fr = tk.LabelFrame(top, text=label, bg='#2b2b2b', fg='white')
            fr.pack(fill=tk.X, padx=12, pady=6)
            row = tk.Frame(fr, bg='#2b2b2b'); row.pack(fill=tk.X)
            def add_field(parent, t, val):
                lf = tk.Frame(parent, bg='#2b2b2b'); lf.pack(side=tk.LEFT, padx=6)
                tk.Label(lf, text=t, fg='white', bg='#2b2b2b').pack(anchor='w')
                e = ttk.Entry(lf, width=8)
                e.insert(0, "" if val is None else str(val))
                e.pack()
                return e
            e_lo = add_field(row, 'lower', section.get('lower_limit'))
            e_hi = add_field(row, 'upper', section.get('upper_limit'))
            entries[p_key] = (e_lo, e_hi)
        def apply_changes():
            for p_key, (e_lo, e_hi) in entries.items():
                for field, widget in [('lower_limit', e_lo), ('upper_limit', e_hi)]:
                    txt = widget.get().strip()
                    if txt == "":
                        continue
                    try:
                        val = float(txt)
                        self.runtime.alarm.update_alarm_threshold(p_key, field, val)
                    except Exception:
                        pass
        def do_import():
            self.runtime.alarm.load_alarm_config()
            cfg2 = self.runtime.alarm.get_alarm_config()["alarm_parameters"]
            for p_key, (e_lo, e_hi) in entries.items():
                section = cfg2.get(p_key, {})
                for e, key in [(e_lo, 'lower_limit'), (e_hi, 'upper_limit')]:
                    try:
                        e.delete(0, tk.END)
                        val = section.get(key)
                        if val is not None:
                            e.insert(0, str(val))
                    except tk.TclError:
                        pass
        def do_export():
            self.runtime.alarm.save_alarm_config()
        btns = tk.Frame(top, bg='#2b2b2b'); btns.pack(fill=tk.X, pady=8)
        ttk.Button(btns, text='Import', command=do_import).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text='Apply', command=apply_changes).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text='Export', command=do_export).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text='Close', command=top.destroy).pack(side=tk.LEFT, padx=6)

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

    def _smooth(self, y: np.ndarray, win: int = 5) -> np.ndarray:
        if y.size == 0 or win <= 1:
            return y
        win = min(win, int(max(2, y.size//10)))
        k = np.ones(win, dtype=float) / float(win)
        pad = win//2
        yp = np.pad(y, (pad, pad), mode='reflect')
        ys = np.convolve(yp, k, mode='same')[pad:-pad]
        return ys.astype(y.dtype)

    def _tick(self):
        # Publish metrics
        metrics = self.runtime.get_metrics()
        self.bus.publish(now_msg("provider->consumer", "metric_report", metrics, device_id=self.device_id))

        # Publish waveform chunks for ECG, PLETH and ABP
        chunk_ecg = self.runtime.get_waveform_chunk(signal='ECG', fs_target=100.0, seconds=2.0)
        chunk_pleth = self.runtime.get_waveform_chunk(signal='PLETH', fs_target=100.0, seconds=2.0)
        chunk_abp = self.runtime.get_waveform_chunk(signal='ABP', fs_target=100.0, seconds=2.0)
        if chunk_ecg['data']:
            self.bus.publish(now_msg("provider->consumer", "waveform_chunk", chunk_ecg, device_id=self.device_id))
        if chunk_pleth['data']:
            self.bus.publish(now_msg("provider->consumer", "waveform_chunk", chunk_pleth, device_id=self.device_id))
        if chunk_abp['data']:
            self.bus.publish(now_msg("provider->consumer", "waveform_chunk", chunk_abp, device_id=self.device_id))

        # Evaluate alarms and publish
        alarm_data = {
            'HR': metrics['HR'], 'MAP': metrics['MAP'], 'SpO2': metrics['SpO2'], 'TEMP': metrics['TEMP'],
            'RR': metrics['RR'], 'EtCO2': metrics['EtCO2']
        }
        events = self.runtime.alarm.evaluate_alarms(alarm_data)
        states = {}
        silenced = False
        try:
            active_list = self.runtime.alarm.get_active_alarms()
        except Exception:
            active_list = []
        active_params = set(str(a.get('parameter')) for a in active_list if a.get('parameter') is not None)
        for param in active_params:
            if not param:
                continue
            states[param] = 'ACTIVE'
        for ev in events:
            param = ev.get('parameter')
            if not param:
                continue
            pkey = str(param)
            if ev.get('active'):
                states[pkey] = 'SILENCED' if silenced else 'ACTIVE'
            else:
                # no latching in simplified runtime adapter; mark inactive
                states[pkey] = 'INACTIVE'

        any_active = any(s in ('ACTIVE', 'SILENCED') for s in states.values())
        headline = 'SILENCED' if silenced and any_active else ('ACTIVE' if any_active else 'INACTIVE')
        try:
            self.alarm_state.config(text=headline, fg=('orange' if 'SILENCED' in headline else ('red' if 'ACTIVE' in headline else 'green')))
        except tk.TclError:
            return
        self.bus.publish(now_msg("provider->consumer", "alert_report",
                                 {"events": events, "states": states, "headline": headline}, device_id=self.device_id))
        color_map = {'INACTIVE':'green','ACTIVE':'red','SILENCED':'orange','LATCHED':'yellow'}
        for param_key, dot in list(self._vital_state_labels.items()):
            st = states.get(param_key, 'INACTIVE')
            try:
                dot.config(fg=color_map.get(st, 'green'))
            except tk.TclError:
                pass
        try:
            self.alarm_headline_var_provider.set(headline)
        except Exception:
            pass
        for w in getattr(self, '_alarm_rows_provider', []):
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._alarm_rows_provider.clear()
        ev_list = events or []
        if ev_list:
            for ev in ev_list:
                name = ev.get('parameter', '')
                st = states.get(name, 'INACTIVE')
                row = tk.Frame(self.alarm_list_fr_provider, bg='black')
                row.pack(fill=tk.X, anchor='w')
                color = 'red' if 'ACTIVE' in st else ('orange' if 'SILENCED' in st else 'yellow' if 'LATCHED' in st else 'green')
                tk.Label(row, text='●', fg=color, bg='black').pack(side=tk.LEFT, padx=(0, 6))
                tk.Label(row, text=name, bg='black', fg='white').pack(side=tk.LEFT)
                self._alarm_rows_provider.append(row)
        else:
            for name, st in states.items():
                row = tk.Frame(self.alarm_list_fr_provider, bg='black')
                row.pack(fill=tk.X, anchor='w')
                color = 'red' if st == 'ACTIVE' else ('orange' if st == 'SILENCED' else 'yellow' if st == 'LATCHED' else 'green')
                tk.Label(row, text='●', fg=color, bg='black').pack(side=tk.LEFT, padx=(0, 6))
                tk.Label(row, text=name, bg='black', fg='white').pack(side=tk.LEFT)
                self._alarm_rows_provider.append(row)

        # Update big numerics
        hr = metrics.get('HR'); rr = metrics.get('RR'); spo2 = metrics.get('SpO2')
        et = metrics.get('EtCO2'); map_val = metrics.get('MAP'); sap = metrics.get('SAP'); dap = metrics.get('DAP'); temp = metrics.get('TEMP')
        self.hr_var.set(f"{hr:.0f}" if isinstance(hr, (int, float)) else "--")
        self.rr_var.set(f"{rr:.0f}" if isinstance(rr, (int, float)) else "--")
        self.spo2_var.set(f"{spo2:.0f}" if isinstance(spo2, (int, float)) else "--")
        self.etco2_var.set(f"{et:.0f}" if isinstance(et, (int, float)) else "--")
        self.map_var.set(f"{map_val:.0f}" if isinstance(map_val, (int, float)) else "--")
        if isinstance(sap, (int, float)) and isinstance(dap, (int, float)):
            self.map_dia_var.set(f"({sap:.0f}/{dap:.0f})")
        else:
            self.map_dia_var.set("(--)")
        self.temp_var.set(f"{temp:.1f}" if isinstance(temp, (int, float)) else "--")

        # Update waveforms
        if self.canvas is not None:
            wf_e = self.runtime.get_waveform_since(signal='ECG', last_total=self._ecg_total_cursor, fs_target=250.0, max_seconds=2.0)
            y_e = np.asarray(wf_e['data'], dtype=float)
            if y_e.size > 0 and wf_e['fs'] > 0:
                self._ecg_total_cursor = wf_e.get('total', self._ecg_total_cursor)
                y_e = self._smooth(y_e, win=5)
                dt = 1.0 / float(wf_e['fs'])
                new_x = np.linspace(self._ecg_time, self._ecg_time + dt * (y_e.size - 1), y_e.size)
                self._ecg_time = new_x[-1] + dt
                self.ecg_x.extend(new_x)
                self.ecg_y.extend(y_e)
                self.lines['ECG'].set_data(list(self.ecg_x), list(self.ecg_y))
                self.axes['ECG'].set_xlim(self._ecg_time - self.plot_window_seconds, self._ecg_time)
                self.axes['ECG'].set_ylim(-1.5, 1.5)
            wf_p = self.runtime.get_waveform_since(signal='PLETH', last_total=self._pleth_total_cursor, fs_target=100.0, max_seconds=2.0)
            y_p = np.asarray(wf_p['data'], dtype=float)
            if y_p.size > 0 and wf_p['fs'] > 0:
                self._pleth_total_cursor = wf_p.get('total', self._pleth_total_cursor)
                y_p = self._smooth(y_p, win=3)
                dt = 1.0 / float(wf_p['fs'])
                new_x = np.linspace(self._pleth_time, self._pleth_time + dt * (y_p.size - 1), y_p.size)
                self._pleth_time = new_x[-1] + dt
                self.pleth_x.extend(new_x)
                self.pleth_y.extend(y_p)
                self.lines['PLETH'].set_data(list(self.pleth_x), list(self.pleth_y))
                self.axes['PLETH'].set_xlim(self._pleth_time - self.plot_window_seconds, self._pleth_time)
                self.axes['PLETH'].set_ylim(0.0, 1.2)
            wf_a = self.runtime.get_waveform_since(signal='ABP', last_total=self._abp_total_cursor, fs_target=125.0, max_seconds=2.0)
            y_a = np.asarray(wf_a['data'], dtype=float)
            if y_a.size > 0 and wf_a['fs'] > 0:
                self._abp_total_cursor = wf_a.get('total', self._abp_total_cursor)
                y_a = self._smooth(y_a, win=3)
                dt = 1.0 / float(wf_a['fs'])
                new_x = np.linspace(self._abp_time, self._abp_time + dt * (y_a.size - 1), y_a.size)
                self._abp_time = new_x[-1] + dt
                self.abp_x.extend(new_x)
                self.abp_y.extend(y_a)
                self.lines['ABP'].set_data(list(self.abp_x), list(self.abp_y))
                self.axes['ABP'].set_xlim(self._abp_time - self.plot_window_seconds, self._abp_time)
                if len(self.abp_y) > 10:
                    y_arr = np.array(self.abp_y)
                    last_n = int(min(len(y_arr), 1250))
                    y_window = y_arr[-last_n:]
                    ymin, ymax = float(np.min(y_window)), float(np.max(y_window))
                    rng = max(10.0, ymax - ymin)
                    pad = 0.15 * rng
                    lo = max(20.0, ymin - pad)
                    hi = min(220.0, ymax + pad)
                    if hi - lo < 20:
                        hi = lo + 20
                    self.axes['ABP'].set_ylim(lo, hi)
            try:
                self.canvas.draw_idle()
            except tk.TclError:
                pass

        # Keepalive and reschedule
        self.bus.publish(now_msg("provider->consumer", "keepalive", {"ts": time.time()}, device_id=self.device_id))
        try:
            if not self._closed and self.win.winfo_exists():
                self.win.after(50, self._tick)
        except tk.TclError:
            return

class InfusionPumpProviderPane:
    def __init__(self, root: tk.Tk, bus: SDCBus, pump: InfusionPumpRuntime, device_id: str = "PUMP1"):
        self.bus = bus
        self.pump = pump
        self.device_id = device_id
        self.win = tk.Toplevel(root)
        self.win.title(f"Infusion Pump — Provider — {self.device_id}")
        self.win.geometry("820x480")
        self.win.configure(bg='#1e1e1e')
        # ttk style for progress bar
        try:
            style = ttk.Style(self.win)
            try:
                style.theme_use('clam')
            except Exception:
                pass
            style.configure('Pump.Horizontal.TProgressbar', troughcolor='#2a2a2a', background='#2aa198', bordercolor='#2a2a2a', lightcolor='#2aa198', darkcolor='#2aa198')
        except Exception:
            pass
        self._alarm_flash = False
        self._build_ui()
        self.bus.subscribe(self._on_bus)
        self._tick()

    def _build_ui(self):
        # Layout: left canvas (pump visual), right controls/status
        container = tk.Frame(self.win, bg='#1e1e1e')
        container.pack(fill=tk.BOTH, expand=True)

        # Canvas visual
        self.canvas = tk.Canvas(container, width=440, height=440, bg='#1e1e1e', highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, padx=12, pady=12)

        # Pump body and screen
        self._bezel = self.canvas.create_rectangle(20, 20, 420, 420, outline='#3a3a3a', fill='#2b2b2b', width=3)
        self._screen = self.canvas.create_rectangle(40, 40, 400, 150, outline='#0a0a0a', fill='#111111', width=2)
        # Rate display
        self._lcd_rate_text = self.canvas.create_text(220, 80, text="---", fill='#00ffaa', font=('Courier', 32, 'bold'))
        self.canvas.create_text(340, 108, text="mL/h", fill='#66ffd1', font=('Helvetica', 12))
        # VTBI/Delivered small display
        self._lcd_vtbi_text = self.canvas.create_text(220, 138, text="VTBI: -- mL    Del: -- mL", fill='#a0a0a0', font=('Helvetica', 11))

        # LEDs
        self.canvas.create_text(120, 175, text="RUN", fill='#cccccc', font=('Helvetica', 10))
        self._led_run = self.canvas.create_oval(100, 165, 116, 181, outline='#0a0a0a', fill='#333333')
        self.canvas.create_text(325, 175, text="OCCL", fill='#cccccc', font=('Helvetica', 10))
        self._led_occ = self.canvas.create_oval(305, 165, 321, 181, outline='#0a0a0a', fill='#333333')

        # Syringe assembly
        # Barrel coordinates
        self._barrel_x0, self._barrel_y0 = 60, 250
        self._barrel_x1, self._barrel_y1 = 360, 300
        # Barrel glass
        self._barrel = self.canvas.create_rectangle(self._barrel_x0, self._barrel_y0, self._barrel_x1, self._barrel_y1,
                                                    outline='#7da1c4', fill='#e8f1ff', width=2)
        # Barrel left rounded cap and nozzle
        self._barrel_cap = self.canvas.create_oval(self._barrel_x0-18, self._barrel_y0, self._barrel_x0+2, self._barrel_y1,
                                                   outline='#7da1c4', fill='#d8e8ff', width=2)
        # Tapered nozzle tip
        self._nozzle = self.canvas.create_polygon(self._barrel_x0-28, (self._barrel_y0+self._barrel_y1)//2 - 6,
                                                  self._barrel_x0-18, self._barrel_y0+6,
                                                  self._barrel_x0-18, self._barrel_y1-6,
                                                  fill='#8fb2d6', outline='#6e96bd')
        # Tubing from nozzle (L-shaped: horizontal then vertical)
        midy = (self._barrel_y0 + self._barrel_y1) // 2
        self._tube_h = self.canvas.create_line(self._barrel_x0-28, midy, 30, midy, fill='#9ad1ff', width=4)
        self._tube_v = self.canvas.create_line(30, midy, 30, 360, fill='#9ad1ff', width=4)
        # Flow arrows along tubing
        self._flow_phase = 0.0
        self._flow1 = self.canvas.create_polygon(32, 320, 38, 324, 32, 328, fill='#7fe3ff', outline='')
        self._flow2 = self.canvas.create_polygon(32, 340, 38, 344, 32, 348, fill='#7fe3ff', outline='')
        self._flow3 = self.canvas.create_polygon(32, 360, 38, 364, 32, 368, fill='#7fe3ff', outline='')
        # Occlusion clamp near tubing (hidden initially)
        self._clamp_id = self.canvas.create_rectangle(18, 330, 42, 350, outline='#ff3b30', fill='#7a1f1f', width=2, state='hidden')
        self.canvas.create_line(18, 340, 42, 340, fill='#ff635a', width=2)
        # Fluid inside barrel (dynamic)
        self._fluid = self.canvas.create_rectangle(self._barrel_x0+2, self._barrel_y0+2, self._barrel_x0+2, self._barrel_y1-2,
                                                   outline='', fill='#6dd5ed')
        # Plunger stopper inside barrel (moves with volume)
        self._plunger = self.canvas.create_rectangle(self._barrel_x1-14, self._barrel_y0+3, self._barrel_x1-6, self._barrel_y1-3,
                                                     outline='#222222', fill='#444444')
        # Pusher block and rail
        self._rail = self.canvas.create_rectangle(self._barrel_x1+10, self._barrel_y0+12, self._barrel_x1+18, self._barrel_y1-12,
                                                  outline='#666666', fill='#4a4a4a')
        self._pusher = self.canvas.create_rectangle(self._barrel_x1-4, self._barrel_y0-6, self._barrel_x1+26, self._barrel_y1+6,
                                                    outline='#888888', fill='#aaaaaa')
        # Graduated ticks on barrel (0-100%)
        for i in range(0, 11):
            x = self._barrel_x0 + (self._barrel_x1 - self._barrel_x0) * (i / 10.0)
            y0 = self._barrel_y1 + 2
            y1 = y0 + (10 if i % 5 == 0 else 6)
            self.canvas.create_line(x, y0, x, y1, fill='#9bb8d0')
            if i % 5 == 0:
                self.canvas.create_text(x, y1+10, text=f"{i*10}%", fill='#9bb8d0', font=('Helvetica', 8))

        # Right side control panel
        right = tk.Frame(container, bg='#1e1e1e')
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12), pady=12)

        # Status + controls row
        status_row = tk.Frame(right, bg='#1e1e1e')
        status_row.pack(fill=tk.X)
        self.status = tk.StringVar(value="Stopped")
        tk.Label(status_row, textvariable=self.status, fg='#ffffff', bg='#1e1e1e', font=('Helvetica', 12, 'bold')).pack(side=tk.LEFT, padx=6)
        ttk.Button(status_row, text="Start", command=self._start).pack(side=tk.RIGHT, padx=6)
        ttk.Button(status_row, text="Pause", command=self._pause).pack(side=tk.RIGHT, padx=6)

        # Rate control
        ctl = tk.Frame(right, bg='#1e1e1e')
        ctl.pack(fill=tk.X, pady=(8, 0))
        tk.Label(ctl, text="Rate (mL/h)", fg='#cccccc', bg='#1e1e1e').pack(anchor='w', padx=6)
        self.rate_var = tk.DoubleVar(value=50)
        tk.Scale(ctl, from_=0, to=1000, orient=tk.HORIZONTAL, resolution=1, variable=self.rate_var, length=280,
                 bg='#1e1e1e', highlightthickness=0, troughcolor='#3a3a3a', fg='#ffffff', sliderrelief=tk.FLAT).pack(side=tk.LEFT, padx=6)
        ttk.Button(ctl, text="Set", command=lambda: self.pump.set_rate(self.rate_var.get())).pack(side=tk.LEFT, padx=6)

        # VTBI control
        ctl2 = tk.Frame(right, bg='#1e1e1e')
        ctl2.pack(fill=tk.X, pady=(8, 0))
        tk.Label(ctl2, text="VTBI (mL)", fg='#cccccc', bg='#1e1e1e').pack(anchor='w', padx=6)
        self.vtbi_var = tk.DoubleVar(value=100)
        tk.Scale(ctl2, from_=0, to=2000, orient=tk.HORIZONTAL, resolution=1, variable=self.vtbi_var, length=280,
                 bg='#1e1e1e', highlightthickness=0, troughcolor='#3a3a3a', fg='#ffffff', sliderrelief=tk.FLAT).pack(side=tk.LEFT, padx=6)
        ttk.Button(ctl2, text="Set", command=lambda: self.pump.set_vtbi(self.vtbi_var.get())).pack(side=tk.LEFT, padx=6)

        # Occlusion + Prime
        ctl3 = tk.Frame(right, bg='#1e1e1e')
        ctl3.pack(fill=tk.X, pady=(8, 0))
        self.occl_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ctl3, text="Occluded", variable=self.occl_var, command=lambda: self.pump.set_occlusion(self.occl_var.get()),
                       fg='#ffb3b3', bg='#1e1e1e', selectcolor='#662222', activebackground='#1e1e1e').pack(side=tk.LEFT, padx=6)
        ttk.Button(ctl3, text="Prime", command=self.pump.prime).pack(side=tk.LEFT, padx=6)

    # Remaining progress + time to empty
        prog_fr = tk.Frame(right, bg='#1e1e1e')
        prog_fr.pack(fill=tk.X, pady=(12, 0))
        tk.Label(prog_fr, text="Remaining (mL)", fg='#cccccc', bg='#1e1e1e').pack(anchor='w', padx=6)
        self._prog = ttk.Progressbar(prog_fr, orient=tk.HORIZONTAL, length=320, mode='determinate', maximum=100, style='Pump.Horizontal.TProgressbar')
        self._prog.pack(fill=tk.X, padx=6)
        self._eta = tk.StringVar(value="--:--")
        tk.Label(prog_fr, textvariable=self._eta, fg='#a0a0a0', bg='#1e1e1e').pack(anchor='w', padx=6, pady=(4,0))

        # Alarm banner
        self._alarm_banner = tk.Label(right, text="Alarms: INACTIVE", fg='#ffffff', bg='#204020', anchor='w')
        self._alarm_banner.pack(fill=tk.X, padx=6, pady=(12, 0))

    def _start(self):
        self.pump.start_delivery()
        self.status.set("Running")

    def _pause(self):
        self.pump.pause_delivery()
        self.status.set("Paused")

    def _on_bus(self, msg: SDCMessage):
        # Placeholder for handling set_requests if needed in future
        pass

    def _tick(self):
        m = self.pump.get_metrics()
        # Update LCD texts
        try:
            self.canvas.itemconfigure(self._lcd_rate_text, text=f"{m['rate_ml_h']:.0f}")
            self.canvas.itemconfigure(self._lcd_vtbi_text, text=f"VTBI: {m['vtbi_ml']:.0f} mL    Del: {m['delivered_ml']:.1f} mL")
        except tk.TclError:
            return

        # LEDs and status
        run_fill = '#27c93f' if m['running'] and not m['occlusion'] else '#333333'
        occ_fill = '#ff3b30' if m['occlusion'] else '#333333'
        self.canvas.itemconfigure(self._led_run, fill=run_fill)
        self.canvas.itemconfigure(self._led_occ, fill=occ_fill)
        self.status.set("Running" if m['running'] else "Paused")

        # Syringe fluid and plunger position based on remaining fraction
        vtbi = max(0.0, float(m['vtbi_ml']))
        rem = max(0.0, float(m['remaining_ml']))
        frac_rem = 0.0 if vtbi <= 0.0 else max(0.0, min(1.0, rem / vtbi))
        # Barrel geometry
        x0, x1 = self._barrel_x0, self._barrel_x1
        y0, y1 = self._barrel_y0, self._barrel_y1
        length = x1 - x0
        fluid_right = x0 + int(length * frac_rem)
        # Update fluid rectangle (from left nozzle to fluid_right)
        self.canvas.coords(self._fluid, x0+2, y0+2, max(x0+2, fluid_right-1), y1-2)
        # Plunger sits at the fluid right edge
        pl_left = max(x0+6, fluid_right - 8)
        pl_right = pl_left + 8
        self.canvas.coords(self._plunger, pl_left, y0+3, pl_right, y1-3)
        # Pusher block follows slightly to the right
        self.canvas.coords(self._pusher, pl_right-2, y0-6, pl_right+28, y1+6)

        # Progress bar (remaining percent of VTBI)
        pct = 0 if vtbi <= 0.0 else max(0, min(100, int((rem / vtbi) * 100)))
        try:
            self._prog['value'] = pct
        except Exception:
            pass

        # ETA (time to empty) in hh:mm
        rate = max(0.0, float(m['rate_ml_h']))
        if rate > 0 and rem > 0 and m['running'] and not m['occlusion']:
            hours = rem / rate
            minutes = int(hours * 60)
            self._eta.set(f"ETA: {minutes//60:02d}:{minutes%60:02d}")
        else:
            self._eta.set("ETA: --:--")

        # Animate flow arrows along the tubing when running and not occluded
        try:
            if m['running'] and not m['occlusion'] and rate > 0:
                speed = 1.0 + min(4.0, rate / 250.0)
                self._flow_phase = (self._flow_phase + speed) % 40
                base_y = 320
                for i, fid in enumerate([self._flow1, self._flow2, self._flow3]):
                    y = base_y + (i * 18) + (self._flow_phase % 18)
                    self.canvas.coords(fid, 32, y, 38, y+4, 32, y+8)
                    self.canvas.itemconfigure(fid, state='normal', fill='#7fe3ff')
            else:
                for fid in [self._flow1, self._flow2, self._flow3]:
                    self.canvas.itemconfigure(fid, state='hidden')
        except tk.TclError:
            pass

        # Occlusion clamp visibility
        try:
            self.canvas.itemconfigure(self._clamp_id, state='normal' if m['occlusion'] else 'hidden')
        except tk.TclError:
            pass

        # Alarm visuals and banner
        alarms = self.pump.get_alarms()
        headline = "ACTIVE" if any(v == 'ACTIVE' for v in alarms.values()) else "INACTIVE"
        banner_bg = '#5a1f1f' if headline == 'ACTIVE' else ('#4a3c1a' if headline == 'LATCHED' else '#204020')
        try:
            self._alarm_banner.config(text=f"Alarms: {headline}", bg=banner_bg)
        except tk.TclError:
            pass

        # Blink bezel when ACTIVE
        try:
            if headline == 'ACTIVE':
                self._alarm_flash = not self._alarm_flash
                outline = '#7a1f1f' if self._alarm_flash else '#3a3a3a'
                self.canvas.itemconfigure(self._bezel, outline=outline)
            else:
                self.canvas.itemconfigure(self._bezel, outline='#3a3a3a')
        except tk.TclError:
            pass

        # Publish metrics and alarms
        try:
            self.bus.publish(now_msg("provider->consumer", "metric_report", {"device": "INFUSION_PUMP", **m}, device_id=self.device_id))
            self.bus.publish(now_msg("provider->consumer", "alert_report", {"device": "INFUSION_PUMP", "states": alarms, "headline": headline}, device_id=self.device_id))
        except Exception:
            pass

        # Re-schedule
        try:
            self.win.after(100, self._tick)
        except tk.TclError:
            return


class ConsumerPane:
    def __init__(self, root: tk.Tk, bus: SDCBus, device_id: str = "MDT"):
        self.bus = bus
        self.device_id = device_id
        self.win = tk.Toplevel(root)
        self.win.title(f"Listener — Consumer — {self.device_id}")
        self.win.geometry("420x420")
        self._build_ui()
        self._alarm_rows: List[tk.Widget] = []
        bus.subscribe(self._on_bus)

    def _build_ui(self):
        body = tk.Frame(self.win)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        # Numerics
        self.hr = tk.StringVar(value="--")
        self.mapv = tk.StringVar(value="--")
        self.spo2 = tk.StringVar(value="--")
        self.rr = tk.StringVar(value="--")
        self.et = tk.StringVar(value="--")
        self.temp = tk.StringVar(value="--")
        for label, var in [("HR", self.hr), ("MAP", self.mapv), ("SpO₂", self.spo2), ("RR", self.rr), ("EtCO₂", self.et), ("Temp", self.temp)]:
            fr = tk.Frame(body); fr.pack(fill=tk.X)
            ttk.Label(fr, text=label, width=8).pack(side=tk.LEFT)
            ttk.Label(fr, textvariable=var).pack(side=tk.LEFT)
        # Alarms
        alarm_fr = tk.LabelFrame(body, text="Alarms")
        alarm_fr.pack(fill=tk.BOTH, expand=True, pady=8)
        self.alarm_head = tk.StringVar(value="INACTIVE")
        ttk.Label(alarm_fr, textvariable=self.alarm_head).pack(anchor='w', padx=6, pady=(4, 6))
        self.alarm_list = tk.Frame(alarm_fr)
        self.alarm_list.pack(fill=tk.X, padx=6, pady=(0, 6))

    def _on_bus(self, msg: SDCMessage):
        if msg.device_id != self.device_id:
            return
        if msg.type == 'metric_report':
            p = msg.payload
            def fmt(v, f):
                return (f % v) if isinstance(v, (int, float)) else "--"
            self.hr.set(fmt(p.get('HR'), "%.0f"))
            self.mapv.set(fmt(p.get('MAP'), "%.0f"))
            self.spo2.set(fmt(p.get('SpO2'), "%.0f"))
            self.rr.set(fmt(p.get('RR'), "%.0f"))
            self.et.set(fmt(p.get('EtCO2'), "%.0f"))
            self.temp.set(fmt(p.get('TEMP'), "%.1f"))
        elif msg.type == 'alert_report':
            headline = msg.payload.get('headline', 'INACTIVE')
            states = msg.payload.get('states', {})
            self.alarm_head.set(headline)
            # rebuild
            for w in list(self._alarm_rows):
                try:
                    w.destroy()
                except tk.TclError:
                    pass
            self._alarm_rows.clear()
            for name, st in states.items():
                row = tk.Frame(self.alarm_list)
                row.pack(fill=tk.X, anchor='w')
                ttk.Label(row, text=f"{name}: {st}").pack(side=tk.LEFT)
                self._alarm_rows.append(row)


class MonitorPane:
    def __init__(self, root: tk.Tk, bus: SDCBus):
        self.bus = bus
        self.win = tk.Toplevel(root)
        self.win.title("Message Monitor")
        self.win.geometry("900x420")
        self._msgs: List[SDCMessage] = []
        self._row_to_msg: Dict[str, SDCMessage] = {}
        self._max_rows = 1000
        self._build_ui()
        bus.subscribe(self._on_bus)

    def _build_ui(self):
        top = tk.Frame(self.win)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Type:").pack(side=tk.LEFT, padx=(6, 2))
        self.type_var = tk.StringVar(value="All")
        ttk.Combobox(top, textvariable=self.type_var, values=["All","metric_report","waveform_chunk","alert_report","set_request","set_response","keepalive"], width=14, state='readonly').pack(side=tk.LEFT)
        ttk.Label(top, text="Direction:").pack(side=tk.LEFT, padx=(10, 2))
        self.dir_var = tk.StringVar(value="All")
        ttk.Combobox(top, textvariable=self.dir_var, values=["All","provider->consumer","consumer->provider","system"], width=18, state='readonly').pack(side=tk.LEFT)
        ttk.Label(top, text="Device:").pack(side=tk.LEFT, padx=(10, 2))
        self.dev_var = tk.StringVar(value="All")
        self.dev_box = ttk.Combobox(top, textvariable=self.dev_var, values=["All"], width=12, state='readonly')
        self.dev_box.pack(side=tk.LEFT)
        ttk.Button(top, text="Export NDJSON", command=self._export).pack(side=tk.RIGHT, padx=6)

        cols = ("Time","Direction","Device","Type","Preview")
        self.tree = ttk.Treeview(self.win, columns=cols, show='headings')
        for c, w in [("Time",160),("Direction",160),("Device",100),("Type",140),("Preview",320)]:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, stretch=(c=="Preview"))
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<Double-1>', self._show_payload)

    def _passes_filters(self, m: SDCMessage) -> bool:
        if self.type_var.get() != 'All' and m.type != self.type_var.get():
            return False
        if self.dir_var.get() != 'All' and m.direction != self.dir_var.get():
            return False
        if self.dev_var.get() != 'All' and (m.device_id or '') != self.dev_var.get():
            return False
        return True

    def _on_bus(self, msg: SDCMessage):
        self._msgs.append(msg)
        # keep device list fresh
        devs = {"All"} | {m.device_id for m in self._msgs if m.device_id}
        cur = list(sorted([d for d in devs if d != "All"]))
        self.dev_box['values'] = ["All"] + cur
        if self._passes_filters(msg):
            preview = json.dumps(msg.payload, separators=(',',':'))
            if len(preview) > 120:
                preview = preview[:117] + '...'
            row = (msg.iso_ts, msg.direction, msg.device_id or '', msg.type, preview)
            iid = self.tree.insert('', 'end', values=row)
            self._row_to_msg[iid] = msg
            # cap rows
            n = len(self.tree.get_children(''))
            if n > self._max_rows:
                oldest = self.tree.get_children('')[0]
                try:
                    del self._row_to_msg[oldest]
                except KeyError:
                    pass
                self.tree.delete(oldest)

    def _show_payload(self, event=None):
        sel = self.tree.focus()
        if not sel:
            return
        msg = self._row_to_msg.get(sel)
        if not msg:
            return
        top = tk.Toplevel(self.win)
        top.title(f"Payload — {msg.type} — {msg.device_id or ''}")
        txt = tk.Text(top, wrap='word', width=100, height=30)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert('1.0', json.dumps(msg.payload, indent=2))
        txt.config(state=tk.DISABLED)

    def _export(self):
        try:
            path = filedialog.asksaveasfilename(defaultextension='.ndjson', filetypes=[('NDJSON', '*.ndjson'), ('All files', '*.*')])
            if not path:
                return
            with open(path, 'w') as f:
                for m in self._msgs:
                    f.write(json.dumps({
                        'ts': m.ts, 'iso_ts': m.iso_ts, 'direction': m.direction, 'type': m.type,
                        'payload': m.payload, 'correlation_id': m.correlation_id, 'device_id': m.device_id
                    }) + '\n')
        except Exception:
            pass


class InfusionPumpConsumerPane:
    def __init__(self, root: tk.Tk, bus: SDCBus, device_id: str = "PUMP1"):
        self.bus = bus
        self.device_id = device_id
        self.win = tk.Toplevel(root)
        self.win.title(f"Infusion Pump — Consumer — {self.device_id}")
        self.win.geometry("420x360")
        self._build_ui()
        bus.subscribe(self._on_bus)

    def _build_ui(self):
        body = tk.Frame(self.win)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.v_rate = tk.StringVar(value="--")
        self.v_vtbi = tk.StringVar(value="--")
        self.v_del = tk.StringVar(value="--")
        self.v_rem = tk.StringVar(value="--")
        self.v_run = tk.StringVar(value="--")
        self.v_occ = tk.StringVar(value="--")
        for label, var in [("Rate", self.v_rate),("VTBI", self.v_vtbi),("Delivered", self.v_del),("Remaining", self.v_rem),("Running", self.v_run),("Occlusion", self.v_occ)]:
            fr = tk.Frame(body); fr.pack(fill=tk.X)
            ttk.Label(fr, text=label, width=10).pack(side=tk.LEFT)
            ttk.Label(fr, textvariable=var).pack(side=tk.LEFT)
        self.al_head = tk.StringVar(value="INACTIVE")
        tk.Label(body, textvariable=self.al_head).pack(anchor='w', pady=(8,2))
        self.al_list = tk.Frame(body); self.al_list.pack(fill=tk.BOTH, expand=True)
        self._al_rows: List[tk.Widget] = []

    def _on_bus(self, msg: SDCMessage):
        if msg.device_id != self.device_id:
            return
        if msg.type == 'metric_report':
            p = msg.payload
            self.v_rate.set(f"{p.get('rate_ml_h', 0):.0f} mL/h")
            self.v_vtbi.set(f"{p.get('vtbi_ml', 0):.0f} mL")
            self.v_del.set(f"{p.get('delivered_ml', 0):.1f} mL")
            self.v_rem.set(f"{p.get('remaining_ml', 0):.1f} mL")
            self.v_run.set(str(p.get('running')))
            self.v_occ.set(str(p.get('occlusion')))
        elif msg.type == 'alert_report':
            self.al_head.set(msg.payload.get('headline', 'INACTIVE'))
            for w in list(self._al_rows):
                try:
                    w.destroy()
                except tk.TclError:
                    pass
            self._al_rows.clear()
            for name, st in msg.payload.get('states', {}).items():
                row = tk.Frame(self.al_list); row.pack(anchor='w')
                ttk.Label(row, text=f"{name}: {st}").pack(side=tk.LEFT)
                self._al_rows.append(row)


class VentilatorRuntime:
    """Simple volume-controlled ventilator simulation producing Paw, Flow, Volume.
    Parameters (units):
      - RR (breaths/min), VT_ml (mL), Ti (s), PEEP (cmH2O),
      - C_ml_per_cmH2O (mL/cmH2O), R_cmH2O_per_Lps (cmH2O/(L/s)).
    """
    def __init__(self):
        # Params
        self.RR = 15.0
        self.VT_ml = 500.0
        self.Ti = 1.0
        self.PEEP = 5.0
        self.C_ml_per_cmH2O = 50.0
        self.R_cmH2O_per_Lps = 10.0
        # State
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fs_internal = 200.0  # Hz
        self._dt = 1.0 / self._fs_internal
        self._buf_secs = 20
        self._buf_max = int(self._buf_secs * self._fs_internal)
        self._paw_buffer = np.zeros(self._buf_max, dtype=np.float32)
        self._flow_buffer = np.zeros(self._buf_max, dtype=np.float32)  # L/s
        self._vol_buffer = np.zeros(self._buf_max, dtype=np.float32)   # mL
        self._paw_len = 0
        self._flow_len = 0
        self._vol_len = 0
        self._paw_total = 0
        self._flow_total = 0
        self._vol_total = 0
        # Breath cycle
        self._t_in_breath = 0.0
        self._last_vt_ml = self.VT_ml
        self._last_pip = self.PEEP

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def set_params(self, **kw):
        for k, v in kw.items():
            if hasattr(self, k):
                try:
                    setattr(self, k, float(v))
                except Exception:
                    pass

    # --- Waveform APIs ---
    def _append(self, buf: np.ndarray, cur_len: int, src: np.ndarray) -> int:
        n = src.size
        if n <= 0:
            return cur_len
        if n >= self._buf_max:
            buf[:self._buf_max] = src[-self._buf_max:]
            return self._buf_max
        free = self._buf_max - cur_len
        if n > free:
            shift = n - free
            buf[:cur_len - shift] = buf[shift:cur_len]
            cur_len -= shift
        buf[cur_len:cur_len+n] = src
        return cur_len + n

    def get_waveform_chunk(self, signal: str, fs_target: float = 100.0, seconds: float = 2.0) -> Dict[str, Any]:
        sig = signal.upper()
        n_needed = int(seconds * self._fs_internal)
        if sig == 'PAW':
            n_av = self._paw_len; data = self._paw_buffer[max(0, n_av-n_needed):n_av]
        elif sig == 'FLOW':
            n_av = self._flow_len; data = self._flow_buffer[max(0, n_av-n_needed):n_av]
        else:
            n_av = self._vol_len; data = self._vol_buffer[max(0, n_av-n_needed):n_av]
        if data.size == 0:
            return {"signal": sig, "fs": fs_target, "data": []}
        stride = max(1, int(round(self._fs_internal / fs_target)))
        dec = data[::stride]
        return {"signal": sig, "fs": self._fs_internal / stride, "data": dec.astype(float).tolist()}

    def get_waveform_since(self, signal: str, last_total: int, fs_target: float = 100.0, max_seconds: float = 1.0) -> Dict[str, Any]:
        sig = signal.upper()
        cap = int(max_seconds * self._fs_internal)
        if sig == 'PAW':
            current_total = self._paw_total; n_new = max(0, min(current_total - last_total, cap))
            if n_new <= 0: return {"signal": 'PAW', "fs": fs_target, "data": [], "total": current_total}
            n = min(n_new, self._paw_len); data = self._paw_buffer[self._paw_len-n:self._paw_len]
        elif sig == 'FLOW':
            current_total = self._flow_total; n_new = max(0, min(current_total - last_total, cap))
            if n_new <= 0: return {"signal": 'FLOW', "fs": fs_target, "data": [], "total": current_total}
            n = min(n_new, self._flow_len); data = self._flow_buffer[self._flow_len-n:self._flow_len]
        else:
            current_total = self._vol_total; n_new = max(0, min(current_total - last_total, cap))
            if n_new <= 0: return {"signal": 'VOL', "fs": fs_target, "data": [], "total": current_total}
            n = min(n_new, self._vol_len); data = self._vol_buffer[self._vol_len-n:self._vol_len]
        stride = max(1, int(round(self._fs_internal / fs_target)))
        dec = data[::stride]
        return {"signal": sig, "fs": self._fs_internal / stride, "data": dec.astype(float).tolist(), "total": current_total}

    def get_metrics(self) -> Dict[str, Any]:
        Ttot = max(0.2, 60.0 / max(1e-3, self.RR))
        ie_ratio = (Ttot - self.Ti) / max(1e-3, self.Ti)
        return {
            'RR': self.RR,
            'VT_ml': self._last_vt_ml,
            'MV_L_min': (self.RR * self._last_vt_ml) / 1000.0,
            'PIP': self._last_pip,
            'PEEP': self.PEEP,
            'IE': ie_ratio,
        }

    def get_alarms(self) -> Dict[str, str]:
        states = {
            'HIGH_PRESSURE': 'ACTIVE' if self._last_pip > 35.0 else 'INACTIVE',
            'LOW_TIDAL': 'ACTIVE' if self._last_vt_ml < 200.0 else 'INACTIVE',
        }
        return states

    def _run(self):
        last = time.perf_counter()
        vol_ml = 0.0
        pip_cycle = self.PEEP
        vt_cycle = 0.0
        while not self._stop.is_set():
            now = time.perf_counter()
            dt = now - last
            if dt < self._dt:
                time.sleep(self._dt - dt)
                now = time.perf_counter()
                dt = now - last
            last = now

            # Breath timing
            RR = max(1e-3, self.RR)
            Ttot = max(0.2, 60.0 / RR)
            Ti = min(max(0.2, self.Ti), Ttot - 0.1)
            self._t_in_breath += dt
            if self._t_in_breath >= Ttot:
                # End of breath: finalize metrics
                self._last_vt_ml = vt_cycle
                self._last_pip = pip_cycle
                vt_cycle = 0.0
                pip_cycle = self.PEEP
                self._t_in_breath -= Ttot

            in_insp = self._t_in_breath < Ti

            # Lung mechanics
            C = max(5.0, self.C_ml_per_cmH2O)            # mL/cmH2O
            R = max(1.0, self.R_cmH2O_per_Lps)           # cmH2O/(L/s)
            PEEP = max(0.0, self.PEEP)

            if in_insp:
                flow_ml_s = self.VT_ml / Ti
                vol_ml += flow_ml_s * dt
                vol_ml = min(vol_ml, self.VT_ml)
            else:
                tau = (R * (C / 1000.0))  # seconds
                if tau < 0.05:
                    tau = 0.05
                # Exponential decay towards zero volume
                dvol = -(vol_ml / tau) * dt
                vol_ml += dvol
                if vol_ml < 0:
                    vol_ml = 0.0
                flow_ml_s = dvol / dt if dt > 0 else -vol_ml / tau

            flow_L_s = flow_ml_s / 1000.0
            paw = PEEP + (vol_ml / C) + (R * flow_L_s)
            pip_cycle = max(pip_cycle, paw)
            vt_cycle = max(vt_cycle, vol_ml)

            # Append to buffers
            paw_val = np.array([paw], dtype=np.float32)
            flow_val = np.array([flow_L_s], dtype=np.float32)
            vol_val = np.array([vol_ml], dtype=np.float32)
            self._paw_len = self._append(self._paw_buffer, self._paw_len, paw_val)
            self._flow_len = self._append(self._flow_buffer, self._flow_len, flow_val)
            self._vol_len = self._append(self._vol_buffer, self._vol_len, vol_val)
            self._paw_total += 1; self._flow_total += 1; self._vol_total += 1


class VentilatorTwinAdapter:
    """Adapter that exposes ventilator waveforms/metrics from the DigitalTwinModel.
    It uses the running ModelRuntime.model instance and does not simulate separately."""
    def __init__(self, model: DigitalTwinModel):
        self.model = model
        # Ensure ventilator mode is enabled
        try:
            self.model.set_ventilator_settings(enabled=True)
        except Exception:
            # fallback: flip MV flag directly
            try:
                self.model._ode_MV_mode = 1
                self.model.master_parameters['misc_constants.MV']['value'] = 1
            except Exception:
                pass

    # Convenience properties for UI defaults/labels
    @property
    def RR(self) -> float:
        try:
            return float(self.model.vent_rr)
        except Exception:
            return float(getattr(self.model, 'RR', 14.0))

    @property
    def PEEP(self) -> float:
        try:
            return float(self.model.vent_peep_cmH2O)
        except Exception:
            return 5.0

    @property
    def Ti(self) -> float:
        try:
            ti = getattr(self.model, 'vent_ti', None)
            if ti is not None:
                return float(ti)
            RR = max(1e-3, float(self.model.vent_rr))
            T = 60.0 / RR
            IE = float(getattr(self.model, 'vent_ie_ratio', 1.0))
            return T * (1.0 / (1.0 + max(0.1, IE)))
        except Exception:
            return 1.0

    @property
    def VT_ml(self) -> float:
        try:
            m = self.model.vent_get_metrics()
            vt = float(m.get('VT_ml', 500.0))
            return vt if vt > 0 else 500.0
        except Exception:
            return 500.0

    def start(self):
        # Model is already running via ModelRuntime
        pass

    def set_params(self, **kw):
        # Map VentilatorProviderPane sliders to model settings
        rr = kw.get('RR', None)
        vt_ml = kw.get('VT_ml', None)  # Currently not directly used by model; keep for future
        ti = kw.get('Ti', None)
        peep = kw.get('PEEP', None)
        # Use deltaP as surrogate for VT target pressure increment if provided
        deltaP = kw.get('deltaP', None)
        self.model.set_ventilator_settings(RR=rr, PEEP=peep, Ti=ti, deltaP=deltaP, enabled=True)

    def get_waveform_chunk(self, signal: str, fs_target: float = 100.0, seconds: float = 2.0) -> Dict[str, Any]:
        return self.model.vent_get_waveform_chunk(signal, fs_target=fs_target, seconds=seconds)

    def get_metrics(self) -> Dict[str, Any]:
        return self.model.vent_get_metrics()

    def get_alarms(self) -> Dict[str, str]:
        m = self.get_metrics()
        states = {
            'HIGH_PRESSURE': 'ACTIVE' if m.get('PIP', 0) > 35.0 else 'INACTIVE',
            'LOW_TIDAL': 'ACTIVE' if m.get('VT_ml', 0) < 200.0 else 'INACTIVE',
        }
        return states

    def stop(self):
        # No separate thread to stop; model handled elsewhere
        pass

class VentilatorProviderPane:
    def __init__(self, root: tk.Tk, bus: SDCBus, vent: Any, device_id: str = "VENT1"):
        self.bus = bus
        self.vent = vent
        self.device_id = device_id
        self.win = tk.Toplevel(root)
        self.win.title(f"Ventilator — Provider — {self.device_id}")
        self.win.geometry("980x520")
        self._closed = False
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        bus.subscribe(self._on_bus)
        self._tick()

    def _on_close(self):
        self._closed = True
        try:
            self.win.destroy()
        except Exception:
            pass

    def _build_ui(self):
        container = tk.Frame(self.win)
        container.pack(fill=tk.BOTH, expand=True)
        left = tk.Frame(container)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        right = tk.Frame(container)
        right.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        # Waveform figure
        if MATPLOTLIB:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            fig = Figure(figsize=(6.8, 4.2), dpi=100, facecolor='#111111')
            self.axes = {
                'PAW': fig.add_subplot(311),
                'FLOW': fig.add_subplot(312),
                'VOL': fig.add_subplot(313),
            }
            # Determine an initial VT for scaling
            try:
                m0 = self.vent.get_metrics()
                vt_init = float(m0.get('VT_ml', 500.0))
                if vt_init <= 0:
                    vt_init = 500.0
            except Exception:
                vt_init = 500.0

            for name, ax in self.axes.items():
                ax.set_facecolor('#000000')
                ax.grid(color='#202020')
                ax.tick_params(colors='#a0a0a0')
                ax.spines['bottom'].set_color('#808080')
                ax.spines['top'].set_color('#808080')
                ax.spines['left'].set_color('#808080')
                ax.spines['right'].set_color('#808080')
                if name == 'PAW':
                    ax.set_ylabel('Paw (cmH2O)', color='#a0ffa0')
                    ax.set_ylim(0, 40)
                elif name == 'FLOW':
                    ax.set_ylabel('Flow (L/s)', color='#a0ffa0')
                    ax.set_ylim(-1.5, 1.5)
                else:
                    ax.set_ylabel('Vol (mL)', color='#a0ffa0')
                    ax.set_ylim(0, max(800, vt_init * 1.2))
            self.lines = {
                'PAW': self.axes['PAW'].plot([], [], color='#7fe3ff', lw=1.2)[0],
                'FLOW': self.axes['FLOW'].plot([], [], color='#ffd37f', lw=1.2)[0],
                'VOL': self.axes['VOL'].plot([], [], color='#66ff99', lw=1.2)[0],
            }
            self.canvas = FigureCanvasTkAgg(fig, master=left)
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            tk.Label(left, text='Matplotlib not available').pack()

        # Controls and numerics
        self.status = tk.StringVar(value='Running')
        sr = tk.Frame(right); sr.pack(fill=tk.X)
        ttk.Label(sr, textvariable=self.status).pack(side=tk.LEFT)
        ttk.Button(sr, text='Pause', command=self._pause).pack(side=tk.RIGHT, padx=4)
        ttk.Button(sr, text='Start', command=self._start).pack(side=tk.RIGHT, padx=4)

        # Param controls
        ctl = tk.LabelFrame(right, text='Settings')
        ctl.pack(fill=tk.X, pady=(6, 0))
        # Seed control defaults safely from adapter/metrics
        m0 = None
        try:
            rr0 = float(self.vent.RR)
        except Exception:
            rr0 = 14.0
        try:
            if m0 is None:
                m0 = self.vent.get_metrics()
            vt0 = float(m0.get('VT_ml', 500.0))
            if vt0 <= 0:
                vt0 = 500.0
        except Exception:
            vt0 = 500.0
        try:
            ti0 = float(self.vent.Ti)
        except Exception:
            ti0 = 1.0
        try:
            peep0 = float(self.vent.PEEP)
        except Exception:
            peep0 = 5.0

        self._rr = tk.DoubleVar(value=rr0)
        self._vt = tk.DoubleVar(value=vt0)
        self._ti = tk.DoubleVar(value=ti0)
        self._peep = tk.DoubleVar(value=peep0)
        for label, var, fr, to, res in [
            ("RR (bpm)", self._rr, 5, 35, 1),
            ("VT (mL)", self._vt, 100, 800, 10),
            ("Ti (s)", self._ti, 0.4, 2.5, 0.1),
            ("PEEP (cmH2O)", self._peep, 0, 20, 1),
        ]:
            row = tk.Frame(ctl); row.pack(fill=tk.X)
            tk.Label(row, text=label, width=14, anchor='w').pack(side=tk.LEFT)
            tk.Scale(row, from_=fr, to=to, orient=tk.HORIZONTAL, resolution=res, variable=var, length=220).pack(side=tk.LEFT, padx=6)
        ttk.Button(ctl, text='Apply', command=self._apply).pack(anchor='e', padx=6, pady=4)

        # Numerics
        nums = tk.LabelFrame(right, text='Numerics')
        nums.pack(fill=tk.X, pady=(8, 0))
        self.v_pip = tk.StringVar(value='--')
        self.v_peep = tk.StringVar(value='--')
        self.v_rr = tk.StringVar(value='--')
        self.v_vt = tk.StringVar(value='--')
        self.v_mv = tk.StringVar(value='--')
        self.v_ie = tk.StringVar(value='--')
        for label, var in [("PIP", self.v_pip),("PEEP", self.v_peep),("RR", self.v_rr),("VT", self.v_vt),("MV", self.v_mv),("I:E", self.v_ie)]:
            r = tk.Frame(nums); r.pack(fill=tk.X)
            ttk.Label(r, text=label, width=6).pack(side=tk.LEFT)
            ttk.Label(r, textvariable=var).pack(side=tk.LEFT)

        # Alarms
        self._alarm_banner = tk.Label(right, text='Alarms: INACTIVE', bg='#204020', fg='#ffffff', anchor='w')
        self._alarm_banner.pack(fill=tk.X, pady=(8, 0))

    def _apply(self):
        # Also pass deltaP derived from VT slider as a simple mapping (optional)
        self.vent.set_params(RR=self._rr.get(), VT_ml=self._vt.get(), Ti=self._ti.get(), PEEP=self._peep.get(), deltaP=max(5.0, min(30.0, (self._vt.get()/50.0))))

    def _start(self):
        self.status.set('Running')
        # nothing else, simulation always runs

    def _pause(self):
        self.status.set('Running')  # placeholder; runtime runs continuously

    def _on_bus(self, msg: SDCMessage):
        pass

    def _tick(self):
        # Update plots
        if MATPLOTLIB:
            for sig in ('PAW','FLOW','VOL'):
                try:
                    chunk = self.vent.get_waveform_chunk(sig, fs_target=100.0, seconds=3.0)
                    y = chunk['data']
                    if len(y) == 0:
                        continue
                    n = len(y)
                    x = np.linspace(-3.0, 0.0, n)
                    self.lines[sig].set_data(x, y)
                    self.axes[sig].set_xlim(-3.0, 0.0)
                except Exception:
                    pass
            try:
                self.canvas.draw_idle()
            except Exception:
                pass

        # Update numerics and alarms
        m = self.vent.get_metrics()
        self.v_pip.set(f"{m['PIP']:.1f} cmH2O")
        self.v_peep.set(f"{m['PEEP']:.1f} cmH2O")
        self.v_rr.set(f"{m['RR']:.0f} bpm")
        self.v_vt.set(f"{m['VT_ml']:.0f} mL")
        self.v_mv.set(f"{m['MV_L_min']:.1f} L/min")
        self.v_ie.set(f"1:{m['IE']:.1f}")

        alarms = self.vent.get_alarms()
        headline = 'ACTIVE' if any(v == 'ACTIVE' for v in alarms.values()) else 'INACTIVE'
        try:
            self._alarm_banner.config(text=f"Alarms: {headline}", bg=('#5a1f1f' if headline=='ACTIVE' else '#204020'))
        except Exception:
            pass

        # Publish bus messages
        self.bus.publish(now_msg("provider->consumer", "metric_report", {"device": "VENTILATOR", **m}, device_id=self.device_id))
        self.bus.publish(now_msg("provider->consumer", "alert_report", {"device": "VENTILATOR", "states": alarms, "headline": headline}, device_id=self.device_id))
        for sig in ('PAW','FLOW','VOL'):
            chunk = self.vent.get_waveform_chunk(sig, fs_target=100.0, seconds=0.5)
            self.bus.publish(now_msg("provider->consumer", "waveform_chunk", {"signal": sig, **chunk}, device_id=self.device_id))

        try:
            if not self._closed and self.win.winfo_exists():
                self.win.after(100, self._tick)
        except tk.TclError:
            return


class VentilatorConsumerPane:
    def __init__(self, root: tk.Tk, bus: SDCBus, device_id: str = 'VENT1'):
        self.bus = bus
        self.device_id = device_id
        self.win = tk.Toplevel(root)
        self.win.title(f"Ventilator — Consumer — {self.device_id}")
        self.win.geometry("420x320")
        self._build_ui()
        bus.subscribe(self._on_bus)

    def _build_ui(self):
        body = tk.Frame(self.win); body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.v_pip = tk.StringVar(value='--')
        self.v_peep = tk.StringVar(value='--')
        self.v_rr = tk.StringVar(value='--')
        self.v_vt = tk.StringVar(value='--')
        self.v_mv = tk.StringVar(value='--')
        self.v_ie = tk.StringVar(value='--')
        for label, var in [("PIP", self.v_pip),("PEEP", self.v_peep),("RR", self.v_rr),("VT", self.v_vt),("MV", self.v_mv),("I:E", self.v_ie)]:
            r = tk.Frame(body); r.pack(fill=tk.X)
            ttk.Label(r, text=label, width=6).pack(side=tk.LEFT)
            ttk.Label(r, textvariable=var).pack(side=tk.LEFT)

        self.al_head = tk.StringVar(value='INACTIVE')
        tk.Label(body, textvariable=self.al_head).pack(anchor='w', pady=(8,2))
        self.al_list = tk.Frame(body); self.al_list.pack(fill=tk.BOTH, expand=True)
        self._al_rows: List[tk.Widget] = []

    def _on_bus(self, msg: SDCMessage):
        if msg.device_id != self.device_id:
            return
        if msg.type == 'metric_report' and msg.payload.get('device') == 'VENTILATOR':
            p = msg.payload
            self.v_pip.set(f"{p.get('PIP', 0):.1f} cmH2O")
            self.v_peep.set(f"{p.get('PEEP', 0):.1f} cmH2O")
            self.v_rr.set(f"{p.get('RR', 0):.0f} bpm")
            self.v_vt.set(f"{p.get('VT_ml', 0):.0f} mL")
            self.v_mv.set(f"{p.get('MV_L_min', 0):.1f} L/min")
            self.v_ie.set(f"1:{p.get('IE', 0):.1f}")
        elif msg.type == 'alert_report' and msg.payload.get('device') == 'VENTILATOR':
            self.al_head.set(msg.payload.get('headline', 'INACTIVE'))
            for w in list(self._al_rows):
                try:
                    w.destroy()
                except tk.TclError:
                    pass
            self._al_rows.clear()
            for name, st in msg.payload.get('states', {}).items():
                row = tk.Frame(self.al_list); row.pack(anchor='w')
                ttk.Label(row, text=f"{name}: {st}").pack(side=tk.LEFT)
                self._al_rows.append(row)

class DeviceLauncher:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.title("Select Devices to Start")
        self.win.geometry("380x260")
        self.win.grab_set()
        self._result = None

        body = tk.Frame(self.win)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # MDT device option
        self.use_mdt = tk.BooleanVar(value=True)
        mdt_fr = tk.LabelFrame(body, text="Medical Digital Twin (MDT)")
        mdt_fr.pack(fill=tk.X, pady=6)
        tk.Checkbutton(mdt_fr, text="Start MDT", variable=self.use_mdt).pack(side=tk.LEFT, padx=6, pady=6)
        tk.Label(mdt_fr, text="Device ID:").pack(side=tk.LEFT)
        self.mdt_id = tk.StringVar(value="MDT")
        ttk.Entry(mdt_fr, textvariable=self.mdt_id, width=12).pack(side=tk.LEFT, padx=6)

        # Pump device option
        self.use_pump = tk.BooleanVar(value=True)
        pump_fr = tk.LabelFrame(body, text="Infusion Pump")
        pump_fr.pack(fill=tk.X, pady=6)
        tk.Checkbutton(pump_fr, text="Start Pump", variable=self.use_pump).pack(side=tk.LEFT, padx=6, pady=6)
        tk.Label(pump_fr, text="Device ID:").pack(side=tk.LEFT)
        self.pump_id = tk.StringVar(value="PUMP1")
        ttk.Entry(pump_fr, textvariable=self.pump_id, width=12).pack(side=tk.LEFT, padx=6)

        # Ventilator device option
        self.use_vent = tk.BooleanVar(value=False)
        vent_fr = tk.LabelFrame(body, text="Mechanical Ventilator")
        vent_fr.pack(fill=tk.X, pady=6)
        tk.Checkbutton(vent_fr, text="Start Ventilator", variable=self.use_vent).pack(side=tk.LEFT, padx=6, pady=6)
        tk.Label(vent_fr, text="Device ID:").pack(side=tk.LEFT)
        self.vent_id = tk.StringVar(value="VENT1")
        ttk.Entry(vent_fr, textvariable=self.vent_id, width=12).pack(side=tk.LEFT, padx=6)

        # Monitor toggle
        self.use_monitor = tk.BooleanVar(value=True)
        mon_fr = tk.Frame(body)
        mon_fr.pack(fill=tk.X, pady=6)
        tk.Checkbutton(mon_fr, text="Open Message Monitor", variable=self.use_monitor).pack(anchor='w', padx=6)

        # Buttons
        btns = tk.Frame(self.win)
        btns.pack(fill=tk.X, pady=8)
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side=tk.RIGHT, padx=6)
        ttk.Button(btns, text="Start", command=self._start).pack(side=tk.RIGHT, padx=6)

        self.win.protocol("WM_DELETE_WINDOW", self._cancel)

    def _start(self):
        # Require at least one device
        if not (self.use_mdt.get() or self.use_pump.get() or self.use_vent.get()):
            messagebox.showwarning("Nothing selected", "Please select at least one device to start.")
            return
        # Validate IDs are not empty
        if self.use_mdt.get() and not self.mdt_id.get().strip():
            messagebox.showwarning("Missing ID", "Please provide a device ID for MDT.")
            return
        if self.use_pump.get() and not self.pump_id.get().strip():
            messagebox.showwarning("Missing ID", "Please provide a device ID for Infusion Pump.")
            return
        if self.use_vent.get() and not self.vent_id.get().strip():
            messagebox.showwarning("Missing ID", "Please provide a device ID for Ventilator.")
            return
        self._result = {
            'mdt': self.use_mdt.get(),
            'mdt_id': self.mdt_id.get().strip(),
            'pump': self.use_pump.get(),
            'pump_id': self.pump_id.get().strip(),
            'vent': self.use_vent.get(),
            'vent_id': self.vent_id.get().strip(),
            'monitor': self.use_monitor.get(),
        }
        self.win.destroy()

    def _cancel(self):
        self._result = None
        self.win.destroy()

    def result(self):
        return self._result


# ---------- Main launcher ----------

def main():
    # Root and panes
    root = tk.Tk()
    root.title("SDC Demo Suite — Launcher")
    root.geometry("300x120")
    tk.Label(root, text="Select devices to start...\nClose main to exit.").pack(padx=10, pady=10)

    # Show launcher
    launcher = DeviceLauncher(root)
    # Wait for launcher to close
    root.wait_window(launcher.win)
    cfg = launcher.result()
    if not cfg:
        # cancelled
        root.destroy()
        return

    bus = SDCBus()
    runtime = None
    pump = None
    vent = None

    # Launch panes
    import traceback
    if cfg['mdt']:
        try:
            print("[Launcher] Starting MDT ...")
            runtime = ModelRuntime(scenarios_path=os.path.join(os.getcwd(), 'scenarios.json') if os.path.exists('scenarios.json') else None)
            runtime.start()
            ProviderPane(root, bus, runtime, device_id=cfg['mdt_id'])
            ConsumerPane(root, bus, device_id=cfg['mdt_id'])
            print("[Launcher] MDT started.")
        except Exception:
            tb = traceback.format_exc()
            print("[Launcher] MDT failed to start:\n", tb)
            try:
                messagebox.showerror("MDT start failed", tb)
            except Exception:
                pass
    if cfg['pump']:
        try:
            print("[Launcher] Starting Pump ...")
            pump = InfusionPumpRuntime()
            pump.start()
            InfusionPumpProviderPane(root, bus, pump, device_id=cfg['pump_id'])
            InfusionPumpConsumerPane(root, bus, device_id=cfg['pump_id'])
            print("[Launcher] Pump started.")
        except Exception:
            tb = traceback.format_exc()
            print("[Launcher] Pump failed to start:\n", tb)
            try:
                messagebox.showerror("Pump start failed", tb)
            except Exception:
                pass
    if cfg.get('vent'):
        try:
            print("[Launcher] Starting Ventilator ...")
            # Ensure a model runtime exists and is running
            if runtime is None:
                runtime = ModelRuntime(scenarios_path=os.path.join(os.getcwd(), 'scenarios.json') if os.path.exists('scenarios.json') else None)
                runtime.start()
            vent = VentilatorTwinAdapter(runtime.model)
            VentilatorProviderPane(root, bus, vent, device_id=cfg['vent_id'])
            VentilatorConsumerPane(root, bus, device_id=cfg['vent_id'])
            print("[Launcher] Ventilator started.")
        except Exception:
            tb = traceback.format_exc()
            print("[Launcher] Ventilator failed to start:\n", tb)
            try:
                messagebox.showerror("Ventilator start failed", tb)
            except Exception:
                pass
    if cfg['monitor']:
        MonitorPane(root, bus)

    try:
        root.mainloop()
    finally:
        try:
            if runtime:
                runtime.stop()
        except Exception:
            pass
        try:
            if pump:
                pump.stop()
        except Exception:
            pass
        try:
            if vent:
                vent.stop()
        except Exception:
            pass


if __name__ == '__main__':
    main()
