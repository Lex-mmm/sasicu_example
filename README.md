# 🏥 Digital Twin Physiological Monitoring System

A real-time physiological simulation and monitoring system with interactive parameter adjustment capabilities. Perfect for medical research, education, and cardiovascular/respiratory system modeling.

## 📄 License & Usage Rights

**© 2025 Dr. L.M. van Loon. All Rights Reserved.**

This software is provided for **academic research and educational purposes only**. 

### ✅ Permitted Uses:
- Academic research and study
- Educational purposes in medical/engineering curricula
- Non-commercial scientific investigations
- Personal learning and experimentation

### ❌ Prohibited Uses:
- Commercial use or distribution
- Integration into commercial products or services
- Resale or licensing to third parties
- Any profit-generating activities

### 📧 Commercial Licensing:
For commercial use, licensing, or any questions regarding usage rights, please contact:
**Dr. L.M. van Loon** - [Contact information to be provided]

*By using this software, you agree to these terms and acknowledge the intellectual property rights of Dr. L.M. van Loon.*

## 📋 Table of Contents
- [🚀 Quick Start](#-quick-start)
- [📦 Installation](#-installation)
- [🎯 Basic Usage](#-basic-usage)
- [🔧 Advanced Features](#-advanced-features)
- [👥 Patient Types](#-patient-types)
- [📊 Parameter Adjustment](#-parameter-adjustment)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [📚 Technical Details](#-technical-details)

---

## 🚀 Quick Start

Ready to see some physiological magic? Here's the fastest way to get started:

1. **Check your system (optional but recommended):**
   ```bash
   python3 system_check.py
   ```
   This will verify everything is working properly! ✅

2. **Run the launcher:**
   ```bash
   python3 launcher.py
   ```

3. **Select a patient type** from the dropdown menu

4. **Click "Start Monitor"** 

5. **Watch real-time physiological data!** 📊

6. **Experiment with parameters** using the adjustment panel

That's it! You're now monitoring a digital human! 🤖

---

## 📦 Installation

### Prerequisites
- **Python 3.8 or higher** (check with `python3 --version`)
- **macOS, Linux, or Windows**

### Required Libraries
```bash
pip install numpy scipy matplotlib tkinter
```

### File Structure
Make sure you have these files:
```
📁 Your Project Folder/
├── 📄 launcher.py          # Main launcher application
├── 📄 direct_monitor.py    # Real-time monitor
├── 📄 digital_twin_model.py # Physiological model
├── 📄 list_patients.py     # Patient list utility
├── 📄 healthyFlat.json     # Healthy patient parameters
├── 📄 heartfailureFlat.json # Heart failure patient
├── 📄 hypotensionFlat.json # Hypotension patient
└── 📁 MDTparameters/       # Additional patient files
    ├── patient_1.json
    ├── patient_2.json
    └── patient_3.json
```

---

## 🎯 Basic Usage

### Method 1: Using the Launcher (Recommended)

1. **Start the Launcher**
   ```bash
   python3 launcher.py
   ```

2. **Select Patient Type**
   - Choose from dropdown: Healthy, Heart Failure, Hypotension, etc.
   - Each patient has different baseline physiological parameters

3. **Start Monitoring**
   - Click **"Start Monitor"** button
   - A new window opens showing real-time data

4. **View Real-time Data**
   - 8 parameter cards showing live values
   - Trend indicators (↗ ↙ →) showing changes
   - Event log with system messages

### Method 2: Direct Command Line

```bash
# Monitor healthy patient
python3 direct_monitor.py --patient healthyFlat.json

# Monitor heart failure patient  
python3 direct_monitor.py --patient heartfailureFlat.json

# Monitor hypotension patient
python3 direct_monitor.py --patient hypotensionFlat.json
```

---

## 🔧 Advanced Features

### Real-time Parameter Adjustment

The monitor includes a **Parameter Adjustment Panel** that lets you modify physiological parameters while the simulation is running!

#### Available Parameters:
1. **Total Blood Volume (TBV)**: 3000-8000 mL
   - *Effect*: Higher volume → Higher blood pressure
   
2. **Nominal Heart Rate**: 40-150 bpm
   - *Effect*: Direct control of heart rate baseline
   
3. **Pressure Setpoint**: 60-140 mmHg
   - *Effect*: Target blood pressure for regulation
   
4. **Baseline Respiratory Rate**: 8-30 bpm
   - *Effect*: Controls breathing pattern and gas exchange

#### How to Adjust Parameters:
1. **Find the Parameter Panel** (below the data cards)
2. **Use the Sliders** to adjust values
3. **Watch Real-time Changes** in the parameter cards above
4. **Check Event Log** for confirmation of changes

#### Example Experiments:
- **Blood Volume Study**: Increase TBV from 4000→6000 mL, observe blood pressure changes
- **Heart Rate Response**: Adjust HR from 70→100 bpm, see cardiovascular adaptation  
- **Respiratory Analysis**: Change RR from 12→20 bpm, monitor SpO2 and EtCO2

### Control Buttons

- **Start/Stop Simulation**: Pause or resume the physiological simulation
- **Reset**: Return to initial patient parameters and restart
- **▼/▶ Show/Hide Controls**: Toggle parameter adjustment panel

---

## 👥 Patient Types

### Available Patients

| Patient Type | File | Description |
|-------------|------|-------------|
| **Healthy Patient** | `healthyFlat.json` | Normal physiological parameters |
| **Heart Failure** | `heartfailureFlat.json` | Reduced cardiac function |
| **Hypotension** | `hypotensionFlat.json` | Low blood pressure condition |
| **Patient 1-3** | `MDTparameters/patient_*.json` | Additional parameter sets |

### Physiological Differences

**Healthy Patient:**
- HR: ~70 bpm, BP: ~120/80 mmHg, SpO2: ~98%

**Heart Failure Patient:**
- Reduced ejection fraction, compensatory tachycardia
- Lower cardiac output, potential fluid retention

**Hypotension Patient:**
- Consistently lower blood pressure values
- Potential compensatory mechanisms active

### Adding New Patients

1. **Create JSON file** with patient parameters
2. **Name it** with "Flat" in filename (e.g., `diabeticFlat.json`)
3. **Place in main folder** or `MDTparameters/` folder
4. **Restart launcher** - it will auto-detect the new patient

---

## 📊 Parameter Adjustment

### Understanding Parameter Effects

#### Total Blood Volume (TBV)
- **Normal Range**: 4000-6000 mL
- **Low Volume (3000 mL)**: Hypotension, tachycardia
- **High Volume (7000+ mL)**: Hypertension, possible edema

#### Heart Rate (HR_n)
- **Normal**: 60-100 bpm
- **Bradycardia (<60)**: Potential low cardiac output
- **Tachycardia (>100)**: Increased oxygen demand

#### Pressure Setpoint (Pset)
- **Normal**: 90-110 mmHg (MAP target)
- **Low Setpoint**: Hypotensive state simulation
- **High Setpoint**: Hypertensive condition modeling

#### Respiratory Rate (RR_0)
- **Normal**: 12-20 bpm
- **Low Rate**: Potential CO2 retention
- **High Rate**: Hyperventilation, low CO2

### Real-time Monitoring Tips

1. **Make Small Changes**: Adjust parameters gradually
2. **Observe Trends**: Look for ↗↙→ indicators on cards
3. **Check Event Log**: Confirms parameter changes
4. **Wait for Stabilization**: Allow 10-20 seconds between changes

---

## 🛠️ Troubleshooting

### Common Issues

#### "Digital twin model not found"
**Solution:**
```bash
# Check if file exists
ls digital_twin_model.py

# Make sure you're in the right directory
pwd
```

#### "No patient files found"
**Solution:**
```bash
# List available patients
python3 list_patients.py

# Check if JSON files exist
ls *.json
```

#### Monitor window won't open
**Solution:**
1. Check Python version: `python3 --version` (need 3.8+)
2. Install required packages: `pip install numpy scipy matplotlib tkinter`
3. Try direct command: `python3 direct_monitor.py`

#### Parameter changes not working
**Solution:**
1. Make sure simulation is **running** (not stopped)
2. Check that parameter panel is **visible** (click ▼ to expand)
3. Look for error messages in event log

### Performance Tips

- **Close unused monitors** - each patient runs separately
- **Adjust sampling interval** if system is slow
- **Use reset button** if simulation becomes unstable

---

## 📚 Technical Details

### System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Launcher      │───▶│  Direct Monitor  │───▶│ Digital Twin    │
│   (Patient      │    │  (GUI + Control) │    │ Model (Math)    │
│   Selection)    │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Monitored Parameters

| Parameter | Unit | Description | Typical Range |
|-----------|------|-------------|---------------|
| **Heart Rate** | bpm | Beats per minute | 60-100 |
| **Mean ABP** | mmHg | Mean arterial pressure | 70-110 |
| **Systolic BP** | mmHg | Peak arterial pressure | 100-140 |
| **Diastolic BP** | mmHg | Minimum arterial pressure | 60-90 |
| **Temperature** | °C | Body temperature | 36.5-37.5 |
| **SpO2** | % | Oxygen saturation | 95-100 |
| **Resp. Rate** | bpm | Breaths per minute | 12-20 |
| **EtCO2** | mmHg | End-tidal CO2 | 35-45 |

### Simulation Details

- **Integration Method**: LSODA (adaptive solver)
- **Time Step**: 2 seconds
- **Update Frequency**: Real-time
- **Pressure Calculation**: Rolling window average
- **Temperature Model**: Circadian + random variation

### File Formats

**Patient Parameter Files (JSON):**
```json
{
  "cardio_control_params.HR_n": {"value": 70},
  "misc_constants.TBV": {"value": 5000},
  "initial_conditions.Pset": {"value": 90},
  "respiratory_control_params.RR_0": {"value": 12}
}
```

---

## 🆘 Need Help?

### Quick Commands Reference

```bash
# Start everything (easiest)
python3 launcher.py

# Monitor specific patient
python3 direct_monitor.py --patient healthyFlat.json

# List all available patients
python3 list_patients.py

# Check system status
python3 -c "import numpy, scipy, tkinter; print('✓ All libraries OK')"
```

### Contact & Support

- Check the event log in the monitor for error messages
- Make sure all `.json` files are in the correct location
- Verify Python 3.8+ is installed
- Try restarting the launcher if issues persist

---

## 🎉 You're Ready to Go!

1. **Run**: `python3 launcher.py`
2. **Select**: A patient type
3. **Start**: The monitor
4. **Experiment**: With parameter adjustments
5. **Observe**: Real-time physiological responses

**Happy monitoring!** 🏥✨

---

*This system is designed for research and educational purposes. Always validate results with clinical data when appropriate.*

---

## 📄 Copyright & License

**© 2025 Dr. L.M. van Loon. All Rights Reserved.**

This Digital Twin Physiological Monitoring System is protected by copyright law. Commercial use is strictly prohibited without explicit written permission from Dr. L.M. van Loon. 

For licensing inquiries or commercial use requests, please contact Dr. L.M. van Loon directly.

**Academic and educational use is encouraged and permitted under these terms.**