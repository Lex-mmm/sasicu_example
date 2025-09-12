#!/usr/bin/env python3
"""
Modular Alarm System for Digital Twin SDC Provider

Copyright (c) 2025 Dr. L.M. van Loon, UMC Utrecht
This software is licensed for academic and educational use only.
Commercial use is strictly prohibited without explicit written permission from the author.

Based on advanced alarm module architecture with SDC protocol integration.
Supports both threshold-based and algorithm-based alarms with GUI-configurable thresholds.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging

class AlarmModule:
    """
    Modular alarm system with configurable thresholds and SDC integration.
    
    Features:
    - Threshold-based alarms (high/low limits)
    - GUI-configurable alarm thresholds
    - SDC protocol alarm transmission
    - Alarm state management with hysteresis
    - Multiple severity levels (yellow, orange, red)
    - Patient-specific alarm profiles
    """
    
    def __init__(self, patient_id: str, alarm_config_file: str = "alarm_config.json"):
        self.patient_id = patient_id
        self.config_file = alarm_config_file
        
        # Load alarm configuration
        self.load_alarm_config()
        
        # Alarm state tracking
        self.alarm_states = {}
        self.active_alarms = []
        self.alarm_history = []
        
        # Initialize alarm states for all parameters
        self._initialize_alarm_states()
        
        logging.info(f"AlarmModule initialized for patient {patient_id}")
    
    def load_alarm_config(self):
        """Load alarm configuration from file or create default."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.alarm_config = config
            else:
                # Create default configuration
                self.alarm_config = self._create_default_config()
                self.save_alarm_config()
                
        except Exception as e:
            logging.warning(f"Error loading alarm config: {e}. Using defaults.")
            self.alarm_config = self._create_default_config()
    
    def save_alarm_config(self):
        """Save current alarm configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.alarm_config, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving alarm config: {e}")
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default alarm configuration."""
        return {
            "version": "1.0",
            "patient_profile": "adult",
            "alarm_parameters": {
                "SpO2": {
                    "enabled": True,
                    "lower_limit": 95.0,
                    "upper_limit": 100.0,
                    "critical_low": 85.0,
                    "critical_high": None,
                    "hysteresis": 2.0,
                    "message_low": "Low Oxygen Saturation",
                    "message_high": "High Oxygen Saturation",
                    "priority_low": "HIGH",
                    "priority_high": "MEDIUM"
                },
                "HeartRate": {
                    "enabled": True,
                    "lower_limit": 60.0,
                    "upper_limit": 100.0,
                    "critical_low": 40.0,
                    "critical_high": 120.0,
                    "hysteresis": 5.0,
                    "message_low": "Bradycardia",
                    "message_high": "Tachycardia",
                    "priority_low": "HIGH",
                    "priority_high": "HIGH"
                },
                "BloodPressureSystolic": {
                    "enabled": True,
                    "lower_limit": 90.0,
                    "upper_limit": 140.0,
                    "critical_low": 70.0,
                    "critical_high": 180.0,
                    "hysteresis": 10.0,
                    "message_low": "Hypotension",
                    "message_high": "Hypertension",
                    "priority_low": "HIGH",
                    "priority_high": "MEDIUM"
                },
                "BloodPressureDiastolic": {
                    "enabled": True,
                    "lower_limit": 60.0,
                    "upper_limit": 90.0,
                    "critical_low": 40.0,
                    "critical_high": 110.0,
                    "hysteresis": 5.0,
                    "message_low": "Low Diastolic Pressure",
                    "message_high": "High Diastolic Pressure",
                    "priority_low": "MEDIUM",
                    "priority_high": "MEDIUM"
                },
                "BloodPressureMean": {
                    "enabled": True,
                    "lower_limit": 70.0,
                    "upper_limit": 105.0,
                    "critical_low": 50.0,
                    "critical_high": 130.0,
                    "hysteresis": 5.0,
                    "message_low": "Low Mean Arterial Pressure",
                    "message_high": "High Mean Arterial Pressure",
                    "priority_low": "HIGH",
                    "priority_high": "MEDIUM"
                },
                "Temperature": {
                    "enabled": True,
                    "lower_limit": 36.0,
                    "upper_limit": 37.8,
                    "critical_low": 35.0,
                    "critical_high": 40.0,
                    "hysteresis": 0.3,
                    "message_low": "Hypothermia",
                    "message_high": "Hyperthermia",
                    "priority_low": "MEDIUM",
                    "priority_high": "MEDIUM"
                },
                "RespiratoryRate": {
                    "enabled": True,
                    "lower_limit": 12.0,
                    "upper_limit": 20.0,
                    "critical_low": 8.0,
                    "critical_high": 30.0,
                    "hysteresis": 2.0,
                    "message_low": "Bradypnea",
                    "message_high": "Tachypnea",
                    "priority_low": "MEDIUM",
                    "priority_high": "MEDIUM"
                },
                "EtCO2": {
                    "enabled": True,
                    "lower_limit": 30.0,
                    "upper_limit": 45.0,
                    "critical_low": 25.0,
                    "critical_high": 50.0,
                    "hysteresis": 2.0,
                    "message_low": "Hypocapnia",
                    "message_high": "Hypercapnia",
                    "priority_low": "MEDIUM",
                    "priority_high": "MEDIUM"
                }
            }
        }
    
    def _initialize_alarm_states(self):
        """Initialize alarm states for all parameters."""
        for param_name in self.alarm_config["alarm_parameters"]:
            self.alarm_states[param_name] = {
                "alarm_low": False,
                "alarm_high": False,
                "alarm_critical_low": False,
                "alarm_critical_high": False,
                "last_value": None,
                "last_check": None
            }
    
    def update_alarm_threshold(self, parameter: str, threshold_type: str, value: float):
        """
        Update alarm threshold from GUI.
        
        Args:
            parameter: Parameter name (SpO2, HeartRate, etc.)
            threshold_type: Type of threshold (lower_limit, upper_limit, critical_low, critical_high)
            value: New threshold value
        """
        if parameter in self.alarm_config["alarm_parameters"]:
            if threshold_type in self.alarm_config["alarm_parameters"][parameter]:
                old_value = self.alarm_config["alarm_parameters"][parameter][threshold_type]
                self.alarm_config["alarm_parameters"][parameter][threshold_type] = value
                self.save_alarm_config()
                
                logging.info(f"Updated {parameter} {threshold_type}: {old_value} → {value}")
                return True
        return False
    
    def evaluate_alarms(self, vital_signs: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Evaluate all alarm conditions for current vital signs.
        
        Args:
            vital_signs: Dictionary with current vital sign values
            
        Returns:
            List of alarm events (triggered or resolved)
        """
        alarm_events = []
        current_time = datetime.now()
        
        # Map vital signs to alarm parameter names
        param_mapping = {
            "SaO2": "SpO2",
            "HR": "HeartRate", 
            "SAP": "BloodPressureSystolic",
            "DAP": "BloodPressureDiastolic",
            "MAP": "BloodPressureMean",
            "TEMP": "Temperature",
            "RR": "RespiratoryRate",
            "EtCO2": "EtCO2"
        }
        
        for vital_key, param_name in param_mapping.items():
            if vital_key in vital_signs and param_name in self.alarm_config["alarm_parameters"]:
                param_config = self.alarm_config["alarm_parameters"][param_name]
                
                if param_config["enabled"]:
                    value = vital_signs[vital_key]
                    events = self._check_parameter_alarms(param_name, value, current_time)
                    alarm_events.extend(events)
        
        return alarm_events
    
    def _check_parameter_alarms(self, parameter: str, value: float, timestamp: datetime) -> List[Dict[str, Any]]:
        """Check alarms for a specific parameter."""
        config = self.alarm_config["alarm_parameters"][parameter]
        state = self.alarm_states[parameter]
        events = []
        
        # Get thresholds
        lower_limit = config.get("lower_limit")
        upper_limit = config.get("upper_limit") 
        critical_low = config.get("critical_low")
        critical_high = config.get("critical_high")
        hysteresis = config.get("hysteresis", 0)
        
        # Check critical alarms first (highest priority)
        if critical_low is not None:
            # Trigger when strictly below the limit; clear when above/equal to limit + hysteresis
            if (value < critical_low) and not state["alarm_critical_low"]:
                event = self._create_alarm_event(parameter, "CRITICAL_LOW", True, value, timestamp, config)
                events.append(event)
                state["alarm_critical_low"] = True
            elif (value >= (critical_low + hysteresis)) and state["alarm_critical_low"]:
                event = self._create_alarm_event(parameter, "CRITICAL_LOW", False, value, timestamp, config)
                events.append(event)
                state["alarm_critical_low"] = False

        if critical_high is not None:
            # Trigger when strictly above the limit; clear when below/equal to limit - hysteresis
            if (value > critical_high) and not state["alarm_critical_high"]:
                event = self._create_alarm_event(parameter, "CRITICAL_HIGH", True, value, timestamp, config)
                events.append(event)
                state["alarm_critical_high"] = True
            elif (value <= (critical_high - hysteresis)) and state["alarm_critical_high"]:
                event = self._create_alarm_event(parameter, "CRITICAL_HIGH", False, value, timestamp, config)
                events.append(event)
                state["alarm_critical_high"] = False

        # Check normal threshold alarms (if not in critical state)
        if not (state["alarm_critical_low"] or state["alarm_critical_high"]):
            if lower_limit is not None:
                # Trigger when strictly below the limit; clear when above/equal to limit + hysteresis
                if (value < lower_limit) and not state["alarm_low"]:
                    event = self._create_alarm_event(parameter, "LOW", True, value, timestamp, config)
                    events.append(event)
                    state["alarm_low"] = True
                elif (value >= (lower_limit + hysteresis)) and state["alarm_low"]:
                    event = self._create_alarm_event(parameter, "LOW", False, value, timestamp, config)
                    events.append(event)
                    state["alarm_low"] = False

            if upper_limit is not None:
                # Trigger when strictly above the limit; clear when below/equal to limit - hysteresis
                if (value > upper_limit) and not state["alarm_high"]:
                    event = self._create_alarm_event(parameter, "HIGH", True, value, timestamp, config)
                    events.append(event)
                    state["alarm_high"] = True
                elif (value <= (upper_limit - hysteresis)) and state["alarm_high"]:
                    event = self._create_alarm_event(parameter, "HIGH", False, value, timestamp, config)
                    events.append(event)
                    state["alarm_high"] = False
        
        # Update last check
        state["last_value"] = value
        state["last_check"] = timestamp
        
        return events
    
    def _create_alarm_event(self, parameter: str, alarm_type: str, active: bool, 
                          value: float, timestamp: datetime, config: Dict) -> Dict[str, Any]:
        """Create an alarm event dictionary."""
        
        # Determine message and priority
        if alarm_type == "LOW":
            message = config["message_low"]
            priority = config["priority_low"]
        elif alarm_type == "HIGH":
            message = config["message_high"] 
            priority = config["priority_high"]
        elif alarm_type == "CRITICAL_LOW":
            message = f"CRITICAL {config['message_low']}"
            priority = "CRITICAL"
        elif alarm_type == "CRITICAL_HIGH":
            message = f"CRITICAL {config['message_high']}"
            priority = "CRITICAL"
        else:
            message = f"Unknown alarm type {alarm_type}"
            priority = "MEDIUM"
        
        event = {
            "patient_id": self.patient_id,
            "parameter": parameter,
            "alarm_type": alarm_type,
            "active": active,
            "value": value,
            "timestamp": timestamp.isoformat(),
            "message": message,
            "priority": priority,
            "alarm_id": f"{parameter}_{alarm_type}_{timestamp.isoformat()}"
        }
        
        # Add to history
        self.alarm_history.append(event)
        
        # Manage active alarms list
        alarm_key = f"{parameter}_{alarm_type}"
        if active:
            if alarm_key not in [a["key"] for a in self.active_alarms]:
                self.active_alarms.append({
                    "key": alarm_key,
                    "event": event
                })
        else:
            self.active_alarms = [a for a in self.active_alarms if a["key"] != alarm_key]
        
        logging.info(f"Alarm {'TRIGGERED' if active else 'RESOLVED'}: {parameter} {alarm_type} = {value} ({message})")
        
        return event
    
    def get_active_alarms(self) -> List[Dict[str, Any]]:
        """Get list of currently active alarms."""
        return [a["event"] for a in self.active_alarms]
    
    def get_alarm_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alarm history (most recent first)."""
        return self.alarm_history[-limit:][::-1]
    
    def get_alarm_config(self) -> Dict[str, Any]:
        """Get current alarm configuration."""
        return self.alarm_config.copy()
    
    def set_patient_profile(self, profile: str):
        """Set patient profile (adult, pediatric, neonatal) with appropriate thresholds."""
        if profile == "neonatal":
            # Update thresholds for neonatal patients
            updates = {
                "HeartRate": {"lower_limit": 100.0, "upper_limit": 160.0, "critical_low": 80.0, "critical_high": 180.0},
                "BloodPressureSystolic": {"lower_limit": 60.0, "upper_limit": 90.0, "critical_low": 45.0, "critical_high": 110.0},
                "BloodPressureMean": {"lower_limit": 35.0, "upper_limit": 60.0, "critical_low": 25.0, "critical_high": 75.0},
                "RespiratoryRate": {"lower_limit": 30.0, "upper_limit": 50.0, "critical_low": 20.0, "critical_high": 70.0}
            }
        elif profile == "pediatric":
            # Update thresholds for pediatric patients  
            updates = {
                "HeartRate": {"lower_limit": 80.0, "upper_limit": 120.0, "critical_low": 60.0, "critical_high": 150.0},
                "BloodPressureSystolic": {"lower_limit": 80.0, "upper_limit": 120.0, "critical_low": 65.0, "critical_high": 140.0},
                "RespiratoryRate": {"lower_limit": 15.0, "upper_limit": 25.0, "critical_low": 10.0, "critical_high": 35.0}
            }
        else:  # adult (default)
            updates = {}
        
        # Apply updates
        for param, thresholds in updates.items():
            if param in self.alarm_config["alarm_parameters"]:
                self.alarm_config["alarm_parameters"][param].update(thresholds)
        
        self.alarm_config["patient_profile"] = profile
        self.save_alarm_config()
        logging.info(f"Updated alarm thresholds for {profile} patient profile")
    
    def get_current_alarm_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get current alarm status for all parameters.
        
        Returns:
            Dictionary with current alarm status for each parameter
        """
        status = {}
        
        for param_name, state in self.alarm_states.items():
            # Determine the highest priority active alarm
            if state["alarm_critical_high"]:
                alarm_type = "CRITICAL_HIGH"
                active = True
                config = self.alarm_config["alarm_parameters"][param_name]
                message = f"CRITICAL {config['message_high']}"
                priority = "CRITICAL"
            elif state["alarm_critical_low"]:
                alarm_type = "CRITICAL_LOW"
                active = True
                config = self.alarm_config["alarm_parameters"][param_name]
                message = f"CRITICAL {config['message_low']}"
                priority = "CRITICAL"
            elif state["alarm_high"]:
                alarm_type = "HIGH"
                active = True
                config = self.alarm_config["alarm_parameters"][param_name]
                message = config["message_high"]
                priority = config["priority_high"]
            elif state["alarm_low"]:
                alarm_type = "LOW"
                active = True
                config = self.alarm_config["alarm_parameters"][param_name]
                message = config["message_low"]
                priority = config["priority_low"]
            else:
                alarm_type = "NORMAL"
                active = False
                message = "Normal"
                priority = "NONE"
            
            status[param_name] = {
                "active": active,
                "alarm_type": alarm_type,
                "message": message,
                "priority": priority,
                "last_value": state["last_value"],
                "last_check": state["last_check"]
            }
        
        return status
    
    def has_active_alarms(self) -> bool:
        """Check if any alarms are currently active."""
        for state in self.alarm_states.values():
            if (state["alarm_low"] or state["alarm_high"] or 
                state["alarm_critical_low"] or state["alarm_critical_high"]):
                return True
        return False
    
    def get_active_alarm_count(self) -> int:
        """Get count of currently active alarms."""
        count = 0
        for state in self.alarm_states.values():
            if (state["alarm_low"] or state["alarm_high"] or 
                state["alarm_critical_low"] or state["alarm_critical_high"]):
                count += 1
        return count
