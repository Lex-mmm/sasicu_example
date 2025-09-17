#!/usr/bin/env python3
"""
Alarm System Test and Demonstration

Copyright (c) 2025 Dr. L.M. van Loon. All Rights Reserved.

This software is for academic research and educational purposes only.
Commercial use is strictly prohibited without explicit written permission
from Dr. L.M. van Loon.

Demonstrates the complete modular alarm system functionality.
"""

from alarm_module import AlarmModule
from sdc_alarm_manager import SDCAlarmManager
import time

def test_alarm_system():
    """Test the complete alarm system functionality."""
    
    print("=" * 60)
    print("SDC Digital Twin - Modular Alarm System Test")
    print("=" * 60)
    
    # Initialize alarm module
    print("\n1. Initializing alarm module...")
    alarm_module = AlarmModule(patient_id="test_patient")
    print("✓ Alarm module initialized")
    
    # Show default configuration
    config = alarm_module.get_alarm_config()
    print(f"✓ Patient profile: {config['patient_profile']}")
    print(f"✓ Available parameters: {list(config['alarm_parameters'].keys())}")
    
    # Test threshold modification
    print("\n2. Testing threshold modification...")
    old_hr_high = config['alarm_parameters']['HeartRate']['upper_limit']
    alarm_module.update_alarm_threshold('HeartRate', 'upper_limit', 120.0)
    print(f"✓ HR upper threshold changed: {old_hr_high} → 120")
    
    # Test normal vital signs (no alarms)
    print("\n3. Testing normal vital signs...")
    normal_vitals = {
        'HR': 75,      # Normal
        'MAP': 85,     # Normal  
        'SaO2': 98,    # Normal
        'TEMP': 37.0,  # Normal
        'RR': 16       # Normal
    }
    
    alarms = alarm_module.evaluate_alarms(normal_vitals)
    print(f"Normal vitals: {normal_vitals}")
    print(f"Alarms triggered: {len(alarms)} (expected: 0)")
    
    # Test abnormal vital signs (should trigger alarms)
    print("\n4. Testing abnormal vital signs...")
    abnormal_vitals = {
        'HR': 140,     # Too high (> 120 after our change)
        'MAP': 45,     # Too low (< 70)
        'SaO2': 80,    # Too low (< 95)
        'TEMP': 39.5,  # Too high (> 37.8)
        'RR': 35       # Too high (> 20)
    }
    
    alarms = alarm_module.evaluate_alarms(abnormal_vitals)
    print(f"Abnormal vitals: {abnormal_vitals}")
    print(f"Alarms triggered: {len(alarms)}")
    
    for alarm in alarms:
        if alarm['active']:
            print(f"  🚨 {alarm['parameter']} {alarm['alarm_type']}: {alarm['value']} - {alarm['message']}")
    
    # Test patient profile change
    print("\n5. Testing patient profile change...")
    alarm_module.set_patient_profile('neonatal')
    config_neo = alarm_module.get_alarm_config()
    hr_limits_neo = config_neo['alarm_parameters']['HeartRate']
    print(f"✓ Switched to neonatal profile")
    print(f"  HR limits: {hr_limits_neo['lower_limit']}-{hr_limits_neo['upper_limit']} (neonatal)")
    
    # Test neonatal vitals that would be normal for neonate but abnormal for adult
    neonatal_vitals = {
        'HR': 140,     # Normal for neonate, high for adult
        'MAP': 45,     # Normal for neonate, low for adult
        'SaO2': 95,    # Normal
        'TEMP': 37.0,  # Normal
        'RR': 25       # Normal for neonate
    }
    
    alarms_neo = alarm_module.evaluate_alarms(neonatal_vitals)
    print(f"Neonatal vitals: {neonatal_vitals}")
    print(f"Alarms with neonatal profile: {len(alarms_neo)}")
    
    for alarm in alarms_neo:
        if alarm['active']:
            print(f"  🚨 {alarm['parameter']} {alarm['alarm_type']}: {alarm['value']} - {alarm['message']}")
    
    # Show active alarms
    print("\n6. Active alarms summary...")
    active_alarms = alarm_module.get_active_alarms()
    print(f"Total active alarms: {len(active_alarms)}")
    
    # Show alarm history
    history = alarm_module.get_alarm_history(limit=10)
    print(f"Recent alarm events: {len(history)}")
    
    print("\n" + "=" * 60)
    print("✓ Alarm system test completed successfully!")
    print("✓ Ready for integration with SDC provider and GUI")
    print("=" * 60)

if __name__ == "__main__":
    test_alarm_system()
