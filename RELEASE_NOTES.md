# Release Notes — 2025-09-12

This document summarizes parameters and alarms added since the last synced Git version.

## Added Parameters
- EtCO2 (End‑tidal CO₂, mmHg)
  - Provider now generates EtCO2 metrics.
  - GUI displays EtCO2 in the vitals panel.
  - Alarm module evaluates EtCO2 against configured thresholds.

## Added Alarms
- EtCO2 alarms:
  - Hypocapnia (EtCO2 low)
  - Hypercapnia (EtCO2 high)
- Critical severity levels across parameters (new):
  - CRITICAL_LOW and CRITICAL_HIGH added for: HeartRate, BloodPressureMean (MAP), SpO2, RespiratoryRate, Temperature, and EtCO2.
- Symmetric hysteresis added to all threshold-based alarms to reduce chatter.

## Default Threshold Highlights (Adult)
- EtCO2: lower 25 mmHg, critical_low 20 mmHg (upper/critical_high follow config if enabled)
- HeartRate: widened startup upper limit; see `alarm_config.json`
- MAP, SpO2, RR, Temperature: thresholds standardized and include critical levels

## Implementation Notes
- Files updated:
  - `alarm_module.py` — added EtCO2 handling; critical levels; hysteresis; persistent state
  - `alarm_config.json` — added EtCO2 limits; widened adult defaults; added critical limits
  - `provider_MDT.py` — emits EtCO2 and periodic CURRENT ALARM STATUS summaries
  - `sdc_monitor_control.py` — displays EtCO2; renders persistent alarm status

If you want a diff against a specific tag or commit, I can generate a scoped comparison and refine this list accordingly.
