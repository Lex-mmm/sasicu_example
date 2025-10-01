# 🏥 SDC Digital Twin Medical Monitoring System
A professional-grade medical device simulation system using the **SDC11073** protocol for real-time physiological monitoring and parameter control. Features advanced pathophysiological modeling, dynamic GUI interfaces, and comprehensive alarm management.
High‑fidelity physiological digital twin + SDC (ISO/IEEE 11073) provider + professional monitor GUI. Real‑time vitals, configurable alarms, emergency toggles, and live parameter control for research & education.
## 📄 License (Summary)
**© 2025 Dr. L.M. van Loon. All Rights Reserved.** Academic & educational use only. No clinical or commercial deployment. For licensing inquiries contact the author. Full details: `docs/DETAILS.md`.
## 📋 Contents
1. Quick Start  
2. Core Features  
3. Alarm Summary  
4. Patient Profiles (Brief)  
5. Emergency & Parameter Controls  
6. Troubleshooting (Core)  
7. Extended Docs → `docs/DETAILS.md`
## 🚀 Quick Start
```bash
python3 system_check.py                 # verify environment & files
python3 provider_MDT.py --adapter en0   # start SDC provider (terminal 1)
python3 sdc_monitor_control.py          # start monitor GUI (terminal 2)
```
Select patient in GUI → observe real‑time vitals & alarms.
## 🧩 Core Features
- Real‑time SDC metrics (HR, MAP/SAP/DAP, Temp, SpO2, RR, EtCO2)
- Physiologic ODE digital twin (cardio‑respiratory + reflexes)
- Configurable alarm engine (thresholds, hysteresis, synthetic clears)
- Profile‑aware limits (adult, neonate, pediatric, disease states)
- Emergency toggles: ECG Lead Off (HR not measurable), Blood Sampling (forces arterial pressures)
- Live parameter control: FiO2 (percent→fraction), blood volume (smoothed), hemodynamic setpoints
- Dark, responsive GUI with scalable vital tiles
Extended architecture diagram & deep dive: `docs/DETAILS.md`.
## 📦 Install (Minimal)
```bash
pip install -r requirements.txt   # includes sdc11073, numpy, scipy, etc.
python3 system_check.py           # verify env & certs
```
Expected in `ssl/`: `cacert.pem usercert.pem userkey.pem`
## 🚨 Alarm Summary
Adult defaults (modifiable):
| Param | Low | High | Crit Low | Crit High |
|-------|-----|------|----------|-----------|
| HR | 60 | 100 | 40 | 120 |
| MAP | 65 | 110 | 50 | 130 |
| SpO2 | 90 | 100 | 85 | — |
| Temp °C | 36.0 | 38.5 | 35.0 | 40.0 |
| RR | 12 | 25 | 8 | 30 |
| EtCO2 | 30 | 50 | 25 | 50 |

Behavior: hysteresis to reduce chatter; limit edits push to SDC LimitAlertCondition (Range Lower/Upper); clearing logic emits synthetic resolves; ECG Lead Off sets HR validity NA with technical alarm.
## 🧪 Patient Profiles (Brief)
JSON baselines: `healthy`, `heartfailure`, `COPD`, `pneumonia`, `neonate`. Selecting a profile adjusts model baselines + suggested limits.
## ⚙️ Parameter & Emergency Controls
- FiO2 (0–100%) → fraction inside model
- Total Blood Volume (smoothed transition)
- HR / MAP / RR setpoints (influences reflex behavior)
- Temperature override
- Reflex toggles: baroreflex & chemoreflex
- Emergency: ECG Lead Off (suppress HR metric), Blood Sampling (MAP/SAP/DAP=300 while active)
## 🆘 Troubleshooting (Core)
| Issue | Quick Action |
|-------|--------------|
| No provider found | Confirm provider terminal running; adapter flag; network iface |
| GUI disconnected | Check provider still streaming; <30s timeout |
| Threshold change not visible | Click Apply; force change (e.g. HR 101 → 100) to export |
| HR limit mismatch | Same as above; watch provider log for `limit.hr.upper` update |
| FiO2 change inert | Ensure Apply; provider log shows cached FiO2 update |
Extended guide: `docs/DETAILS.md`.
## 🔗 Demo Suite
End‑to‑end provider + monitor + consumer + logging:
```bash
./env/bin/python3 sdc_demo_suite.py
```
**© 2025 Dr. L.M. van Loon. Academic & educational use only.** Extended documentation in `docs/DETAILS.md`.
# 🏥 SDC Digital Twin Medical Monitoring System

A professional-grade medical device simulation system using the **SDC11073** protocol for real-time physiological monitoring and parameter control. Features advanced pathophysiological modeling, dynamic GUI interfaces, and comprehensive alarm management.

## 📄 License & Usage Rights 

**© 2025 Dr. L.M. van Loon. All Rights Reserved.**

This software is provided for **academic research and educational purposes only**. 

### ✅ Permitted Uses:
- Academic research and medical education
- Non-commercial scientific investigations  
- Medical device protocol development
- Physiological modeling research

### ❌ Prohibited Uses:
- Commercial use or distribution
- Clinical patient monitoring (research only)
- Integration into commercial medical products

### 📧 Commercial Licensing:
For commercial use or licensing inquiries, contact **Dr. L.M. van Loon**.

---

## 📋 Table of Contents
- [🚀 Quick Start](#-quick-start)
- [🏥 System Architecture](#-system-architecture)
- [📦 Installation](#-installation)
- [🎮 Professional GUI](#-professional-gui)
- [👥 Disease-Specific Patients](#-disease-specific-patients)
- [⚠️ Alarm System](#️-alarm-system)
- [🔧 Advanced Parameter Control](#-advanced-parameter-control)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [📚 Technical Reference](#-technical-reference)

---

## 🚀 Quick Start

### Fastest Way to Start:

1. **System Check:**
   ```bash
   python3 system_check.py
   ```

2. **Launch Main Monitor:**
   ```bash
   python3 sdc_monitor_control.py
   ```

3. **Start Digital Twin Provider (new terminal):**
   ```bash
   python3 provider_MDT.py --adapter en0
   ```

4. **Select Patient & Watch Real-time Data!** 🏥

---

## 🏥 System Architecture

```
┌─────────────────────┐    SDC11073     ┌─────────────────────┐
│   Professional     │◄─────────────────►│   Digital Twin      │
│   Monitor GUI       │    Protocol     │   Provider          │
│ (sdc_monitor_control)│                 │ (provider_MDT.py)   │
└─────────────────────┘                 └─────────────────────┘
          │                                        │
          ▼                                        ▼
┌─────────────────────┐                 ┌─────────────────────┐
│   Alarm System     │                 │  Physiological      │
│   Management        │                 │  Digital Twin       │
└─────────────────────┘                 │  Engine             │
                                        └─────────────────────┘
```

### **Core Components:**
- **`sdc_monitor_control.py`** - Professional medical device GUI with dynamic scaling
- **`provider_MDT.py`** - SDC provider with advanced physiological simulation
- **`digital_twin_model.py`** - Cardiovascular/respiratory mathematical model
- **`alarm_module.py`** - Clinical-grade alarm management system

---

## 📦 Installation

### Prerequisites:
- **Python 3.8+**
- **macOS/Linux** (Windows with WSL)

### SDC11073 Dependencies:
```bash
pip install sdc11073 lxml numpy scipy matplotlib
```

### Complete Installation:
```bash
# Clone or download the project
cd sasicu_example

# Install all dependencies
pip install -r requirements.txt

# Verify SSL certificates exist
ls ssl/
# Should show: cacert.pem, usercert.pem, userkey.pem

# Run system check
python3 system_check.py
```

---

## 🎮 Professional GUI

### Main Interface: `sdc_monitor_control.py`

**Features:**
- 🎨 **Professional medical device styling** with dark theme
- 📏 **Dynamic font scaling** - vital signs auto-scale to box size
- 📊 **Real-time SDC data streaming** from medical device protocol
- ⚠️ **Comprehensive alarm system** with visual/audio alerts
- 🔧 **Advanced parameter controls** with apply buttons
- 📈 **Connection status monitoring** with timeout detection

**Monitored Parameters:**
- Heart Rate (HR) - bpm
- Mean/Systolic/Diastolic Blood Pressure - mmHg  
- Body Temperature - °C
- Oxygen Saturation (SpO2) - %
- Respiratory Rate (RR) - bpm
- End-tidal CO2 (EtCO2) - mmHg

### Key Interface Elements:

#### 🔴 **Vital Signs Display**
- Large, color-coded parameter cards
- Dynamic font sizing based on window size
- Trend indicators (↗ ↙ →)
- Real-time value updates

#### 🚨 **Alarm Status Panel**
- Parameter-specific alarm indicators
- Visual alarm status overview
- Configurable alarm thresholds
- Patient profile-specific limits

#### ⚙️ **Parameter Control Panel**
- FiO2 control (0-100%)
- Blood volume adjustment
- Heart rate/pressure setpoints
- Temperature control
- Baroreflex/Chemoreceptor toggles

---

## 👥 Disease-Specific Patients

### Available Patient Profiles:

#### 🫀 **Heart Failure (heartfailure.json)**
- **Pathophysiology**: Reduced ventricular contractility
- **Key Changes**: 44-45% reduction in elastance values
- **Expected Signs**: ↓ MAP, ↑ HR (compensatory), reduced stroke volume

#### 🫁 **COPD (COPD.json)** 
- **Pathophysiology**: Increased airway resistance
- **Key Changes**: 150-175% increase in airway resistances
- **Expected Signs**: ↑ RR, ↑ EtCO2, air trapping, possible hypoxemia

#### 🦠 **Pneumonia (pneumonia.json)**
- **Pathophysiology**: Fever + impaired gas exchange
- **Key Changes**: Temperature → 38.8°C, 34% reduction in O2 diffusion
- **Expected Signs**: ↑ Temp, ↓ SpO2, ↑ RR, ↑ HR, increased O2 consumption

#### 👶 **Neonate (neonate.json)**
- **Pathophysiology**: Immature physiological systems
- **Key Changes**: Adjusted ranges for neonatal physiology
- **Expected Signs**: Higher baseline HR, different pressure ranges

#### ✅ **Healthy (healthy.json)**
- **Baseline**: Normal adult physiological parameters
- **Reference**: Standard values for comparison

### Patient Selection:
- Choose patient profile in GUI dropdown
- Provider automatically adjusts baseline parameters
- Temperature defaults loaded from patient file
- Alarm thresholds adapt to patient type

---

## ⚠️ Alarm System

### Clinical-Grade Alarm Management:

#### **Alarm Parameters:**
- Heart Rate: Bradycardia/Tachycardia detection
- Blood Pressure: Hypotension/Hypertension monitoring  
- SpO2: Hypoxemia detection
- Temperature: Hypothermia/Hyperthermia alerts
- Respiratory Rate: Apnea/Tachypnea detection
- EtCO2: Hypo/Hypercapnia monitoring

#### **Alarm Behavior Enhancements:**
The `AlarmModule` provides threshold and critical alarms with hysteresis. Recent enhancements:

- Threshold updates now flag parameters for forced re-evaluation next cycle.
- Crossing a threshold emits an activation event; returning within limits (considering hysteresis) emits a resolution event.
- Changing a limit that brings a value back to normal triggers synthetic clearance events so stale alarms are removed immediately.
- `evaluate_alarms(vitals, force=True)` can be called to force evaluation (used by test harness).

Minimal test harness: run `./env/bin/python test_alarm_module.py` to see activation and resolution for HeartRate and MAP.
#### **Patient Profile Adaptation:**
- **Adult**: HR 60-100, MAP 65-110, SpO2 >90%
- **Neonatal**: HR 100-180, MAP 35-60, SpO2 >85%
- **Pediatric**: HR 80-140, MAP 50-90, customized ranges

#### **Alarm Features:**
- Visual status indicators with color coding
- Configurable thresholds per parameter
- Enable/disable individual alarms
- Real-time alarm evaluation
- Event logging with timestamps

---

## 🔧 Advanced Parameter Control

### Real-Time Parameter Adjustment:

#### **FiO2 Control**
- **Range**: 0-100% (including hypoxic conditions)
- **Application**: Research scenarios, altitude simulation
- **Controls**: Slider + Apply button for precise control

#### **Hemodynamic Parameters**
- **Blood Volume**: 3000-6000 mL
- **HR Setpoint**: 40-150 bpm
- **MAP Setpoint**: 50-130 mmHg
- **Effects**: Real-time cardiovascular changes

#### **Temperature Control**
- **Range**: 35.0-42.0°C
- **Patient-Specific**: Defaults from patient profiles
- **Features**: Fever simulation, hypothermia studies

#### **Physiological Reflex Controls**

**Baroreflex Toggle:**
- **ON**: Normal cardiovascular pressure regulation
- **OFF**: Removes pressure feedback (research mode)
- **Applications**: Study isolated cardiovascular responses

**Chemoreceptor Toggle:**
- **ON**: Normal respiratory gas regulation  
- **OFF**: Removes O2/CO2 feedback (research mode)
- **Applications**: Study breathing pattern changes

### Usage Workflow:
1. Adjust slider to desired value
2. Observe real-time preview
3. Click **Apply** to implement change
4. Monitor physiological response
5. Check event log for confirmation

---

## 🛠️ Troubleshooting

### Common Issues:

#### **"No SDC Provider Found"**
```bash
# Check if provider is running
ps aux | grep provider_MDT

# Restart provider with correct adapter
python3 provider_MDT.py --adapter en0

# Check network adapter
ifconfig
```

#### **"GUI Shows Disconnected"**
- Verify provider is outputting data
- Check 30-second timeout hasn't occurred
- Restart both provider and GUI
- Verify SSL certificates in ssl/ folder

#### **"Parameter Changes Not Working"**
- Ensure provider is running
- Check parameter update file permissions
- Verify Apply button is clicked (not just slider)
- Monitor event log for error messages

#### **"Alarm System Not Working"**
- Check alarm configuration file: `alarm_config.json`
- Verify patient profile selection
- Ensure alarm parameters are enabled
- Check threshold values are reasonable

### Debug Tools:
```bash
# Test SDC connection
python3 test_connection.py

# Console monitor for debugging
python3 console_monitor.py

# Direct value testing
python3 test_direct_values.py
```

---

## 📚 Technical Reference

### File Structure:
```
📁 sasicu_example/
├── 🏥 Core Applications
│   ├── sdc_monitor_control.py    # Main professional GUI
│   ├── provider_MDT.py          # SDC provider
│   └── digital_twin_model.py    # Physiological engine
├── 👥 Patient Profiles  
│   └── MDTparameters/
│       ├── healthy.json         # Normal physiology
│       ├── heartfailure.json    # Heart failure
│       ├── COPD.json           # COPD simulation
│       ├── pneumonia.json      # Pneumonia + fever
│       └── neonate.json        # Neonatal parameters
├── ⚠️ Alarm System
│   ├── alarm_module.py         # Alarm logic
│   ├── alarm_config.json       # Configuration
│   └── sdc_alarm_manager.py    # SDC integration
└── 🔧 Development Tools
    ├── debug_monitor.py        # Simple data reader
    ├── console_monitor.py      # Terminal monitor
    └── test_*.py              # Testing utilities
```

### Protocol Details:
- **SDC11073**: ISO/IEEE 11073 Service-oriented Device Connectivity
- **Discovery**: WS-Discovery for automatic provider detection
- **Security**: TLS with mutual authentication
- **Data Format**: Real-time metric streaming

### Physiological Model:
- **Cardiovascular**: Multi-compartment pressure-volume relationships
- **Respiratory**: Gas exchange with diffusion limitations  
- **Control Systems**: Baroreflex, chemoreceptor feedback
- **Pathophysiology**: Disease-specific parameter modifications

### Performance:
- **Update Rate**: Real-time (1-2 second intervals)
- **Connection Monitoring**: 30-second timeout detection
- **Resource Usage**: Low CPU, minimal memory footprint
- **Scalability**: Multiple simultaneous connections supported

---

## 🆘 Support & Contact

### Quick Reference Commands:
```bash
# Start system
python3 sdc_monitor_control.py

# Start provider
python3 provider_MDT.py --adapter en0

# System check
python3 system_check.py

# Debug connection
python3 test_connection.py
```

### Research Applications:
- Medical device protocol development
- Physiological simulation and modeling
- Medical education and training
- Alarm system validation
- Pathophysiology research

---

**© 2025 Dr. L.M. van Loon. Academic and educational use permitted.**

*This system is designed for research and educational purposes. Always validate results with clinical data when appropriate.*

---

## 🔗 SDC Demo Suite (Provider ↔ Monitor ↔ Consumer)

The file `sdc_demo_suite.py` runs a complete end-to-end SDC-style workflow, entirely driven by the Digital Twin model:

- Provider window: publishes model-derived metrics and an ABP waveform; shows alarm state and accepts set_request operations.
- Message Monitor: logs all messages with timestamps, direction, type (metric_report, waveform_chunk, alert_report, set_request/response, keepalive) and allows export to NDJSON.
- Consumer window: mirrors vitals and offers controls for HR_set, ABP_set, RR_set, FiO2_set; also Alarm Silence/Reset via ALERT_CTRL.

Run locally:

```bash
./env/bin/python3 sdc_demo_suite.py
```

Scenarios can be selected in the Consumer window and are applied as parameter bundles to the model (no UI constants). You can customize scenarios in an optional `scenarios.json` at the project root. All alarms and thresholds are evaluated by the model/alarm module.
