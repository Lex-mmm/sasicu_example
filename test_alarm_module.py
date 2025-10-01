#!/usr/bin/env python3
"""Quick test harness for AlarmModule logic transitions.
Run: python test_alarm_module.py
"""
from alarm_module import AlarmModule
import time

am = AlarmModule(patient_id="test")

# Helper to evaluate and print events

def step(val_hr=None, val_map=None, note=""):
    vitals = {}
    if val_hr is not None:
        vitals['HR'] = val_hr
    if val_map is not None:
        vitals['MAP'] = val_map
    ev = am.evaluate_alarms(vitals, force=True)
    if ev:
        for e in ev:
            print(f"EVENT {note}: {e['parameter']} {e['alarm_type']} active={e['active']} value={e['value']} msg={e['message']}")
    else:
        print(f"NOEVENT {note} values={vitals}")

print("=== Baseline within limits ===")
step(val_hr=75, val_map=85, note="baseline")

print("=== Trigger HR high ===")
step(val_hr=130, note="hr_high")
print("=== Back to normal HR (clear) ===")
step(val_hr=90, note="hr_normal")

print("=== Trigger MAP low ===")
step(val_map=50, note="map_low")
print("=== Back to normal MAP (clear) ===")
step(val_map=80, note="map_normal")

print("=== Change HR upper limit lower to provoke new alarm at 95 ===")
am.update_alarm_threshold('HeartRate','upper_limit',92.0)
step(val_hr=95, note="threshold_changed_hr")

print("=== Raise HR upper limit to 110 to clear alarm if active ===")
am.update_alarm_threshold('HeartRate','upper_limit',110.0)
step(val_hr=95, note="threshold_relaxed_hr")

print("=== Done ===")
