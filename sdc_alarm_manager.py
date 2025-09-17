#!/usr/bin/env python3
"""
SDC Alarm Manager - Handles alarm transmission via SDC protocol

Copyright (c) 2025 Dr. L.M. van Loon, UMC Utrecht
This software is licensed for academic and educational use only.
Commercial use is strictly prohibited without explicit written permission from the author.

Integrates the modular alarm system with SDC protocol for proper alarm transmission.
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime

class SDCAlarmManager:
    """
    Manages alarm transmission via SDC protocol.
    
    Features:
    - SDC alert state management
    - Priority-based alarm handling
    - Alert condition lifecycle management
    - Proper SDC alarm semantics
    """
    
    def __init__(self, sdc_device):
        self.sdc_device = sdc_device
        self.active_sdc_alarms = {}  # Track active SDC alarm states
        
        # SDC priority mapping
        self.sdc_priority_map = {
            "CRITICAL": "Hi",
            "HIGH": "Hi", 
            "MEDIUM": "Me",
            "LOW": "Lo"
        }
        
        logging.info("SDCAlarmManager initialized")
    
    def process_alarm_events(self, alarm_events: List[Dict[str, Any]]):
        """
        Process alarm events and update SDC alert states.
        
        Args:
            alarm_events: List of alarm events from alarm module
        """
        for event in alarm_events:
            try:
                self._update_sdc_alarm_state(event)
            except Exception as e:
                logging.error(f"Error processing alarm event: {e}")
    
    def _update_sdc_alarm_state(self, event: Dict[str, Any]):
        """Update SDC alarm state for a single event."""
        parameter = event["parameter"]
        alarm_type = event["alarm_type"]
        active = event["active"]
        
        # Create unique alarm identifier
        alarm_id = f"{parameter}_{alarm_type}"
        
        try:
            if active:
                self._activate_sdc_alarm(alarm_id, event)
            else:
                self._deactivate_sdc_alarm(alarm_id, event)
                
        except Exception as e:
            logging.error(f"Error updating SDC alarm state for {alarm_id}: {e}")
    
    def _activate_sdc_alarm(self, alarm_id: str, event: Dict[str, Any]):
        """Activate an SDC alarm."""
        if not hasattr(self.sdc_device, 'transaction_manager'):
            logging.warning("SDC device not properly initialized for alarms")
            return
            
        try:
            transaction_mgr = self.sdc_device.transaction_manager
            
            # Find the alert condition (or create if needed)
            alert_condition = self._get_or_create_alert_condition(alarm_id, event)
            
            if alert_condition:
                # Update alert condition to active state
                with transaction_mgr.transaction() as transaction:
                    alert_state = transaction.get_state(alert_condition.Handle)
                    
                    # Set alarm properties
                    alert_state.ActivationState = "On"  # SDC alarm activation
                    alert_state.ActualConditionGenerationDelay = Decimal("0")
                    alert_state.ActualPriority = self.sdc_priority_map.get(event["priority"], "Me")
                    
                    # Set alert message
                    if hasattr(alert_state, 'AlertMessage'):
                        alert_state.AlertMessage = event["message"]
                    
                    # Update timestamp
                    alert_state.StateVersion = alert_state.StateVersion + 1 if alert_state.StateVersion else 1
                
                self.active_sdc_alarms[alarm_id] = {
                    "handle": alert_condition.Handle,
                    "event": event,
                    "activated_at": datetime.now()
                }
                
                logging.info(f"SDC alarm activated: {alarm_id} - {event['message']}")
                
        except Exception as e:
            logging.error(f"Error activating SDC alarm {alarm_id}: {e}")
    
    def _deactivate_sdc_alarm(self, alarm_id: str, event: Dict[str, Any]):
        """Deactivate an SDC alarm.""" 
        if alarm_id not in self.active_sdc_alarms:
            return  # Alarm not active in SDC
            
        try:
            transaction_mgr = self.sdc_device.transaction_manager
            alarm_info = self.active_sdc_alarms[alarm_id]
            
            # Update alert condition to inactive state
            with transaction_mgr.transaction() as transaction:
                alert_state = transaction.get_state(alarm_info["handle"])
                
                # Deactivate alarm
                alert_state.ActivationState = "Off"  # SDC alarm deactivation
                alert_state.StateVersion = alert_state.StateVersion + 1 if alert_state.StateVersion else 1
            
            # Remove from active alarms
            del self.active_sdc_alarms[alarm_id]
            
            logging.info(f"SDC alarm deactivated: {alarm_id}")
            
        except Exception as e:
            logging.error(f"Error deactivating SDC alarm {alarm_id}: {e}")
    
    def _get_or_create_alert_condition(self, alarm_id: str, event: Dict[str, Any]):
        """Get existing or create new alert condition for alarm."""
        try:
            # For now, we'll use a simplified approach and find existing alert conditions
            # In a full implementation, you might want to create dynamic alert conditions
            
            if hasattr(self.sdc_device, 'device_mdib_container'):
                mdib = self.sdc_device.device_mdib_container.mdib
                
                # Look for existing alert conditions that match our parameter
                for alert_condition in mdib.alert_conditions:
                    if hasattr(alert_condition, 'Source') and event["parameter"] in str(alert_condition.Source):
                        return alert_condition
                
                # For demonstration, return the first available alert condition
                # In production, you'd want to map specific conditions to specific parameters
                alert_conditions = list(mdib.alert_conditions)
                if alert_conditions:
                    return alert_conditions[0]
                    
        except Exception as e:
            logging.error(f"Error finding alert condition for {alarm_id}: {e}")
            
        return None
    
    def get_active_sdc_alarms(self) -> Dict[str, Any]:
        """Get currently active SDC alarms."""
        return self.active_sdc_alarms.copy()
    
    def clear_all_alarms(self):
        """Clear all active SDC alarms (emergency reset)."""
        for alarm_id in list(self.active_sdc_alarms.keys()):
            try:
                # Create dummy deactivation event
                dummy_event = {"active": False}
                self._deactivate_sdc_alarm(alarm_id, dummy_event)
            except Exception as e:
                logging.error(f"Error clearing alarm {alarm_id}: {e}")
        
        self.active_sdc_alarms.clear()
        logging.info("All SDC alarms cleared")
