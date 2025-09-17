#!/usr/bin/env python3
"""
SDC Provider for Medical Device Testing
Provides physiological data via Service-oriented Device Connectivity (SDC).

Copyright (c) 2025 Dr. L.M. van Loon. All Rights Reserved.

This software is for academic research and educational purposes only.
Commercial use is strictly prohibited without explicit written permission
from Dr. L.M. van Loon.

For commercial licensing inquiries, contact Dr. L.M. van Loon.
"""

from __future__ import annotations

import sys
print("Python executable:", sys.executable)
import sys
import os
import argparse  # <-- new import
import netifaces  # Add this import with your other imports
import random

# Use the current working directory as the base path instead of a hardcoded one
BASE_PATH = os.getcwd()
sys.path.append(BASE_PATH)

# Define the network adapter for discovery
NETWORK_ADAPTER = "en0"

# Global baseline body temperature (controllable from GUI)
BASELINE_TEMPERATURE = 37.0  # Normal body temperature in Celsius

# Directly import the DigitalTwinModel class
sys.path.append(BASE_PATH)
from digital_twin_model import DigitalTwinModel
from alarm_module import AlarmModule

import logging
import time
import uuid
from decimal import Decimal
from datetime import datetime

from sdc11073.location import SdcLocation
from sdc11073.loghelper import basic_logging_setup
from sdc11073.mdib import ProviderMdib
from sdc11073.mdib import mdibbase
from sdc11073.provider import SdcProvider
from sdc11073.provider.components import SdcProviderComponents
from sdc11073.roles.product import ExtendedProduct
from sdc11073.wsdiscovery import WSDiscoverySingleAdapter
from sdc11073.xml_types import pm_qnames as pm
from sdc11073.xml_types import pm_types
from sdc11073.xml_types.dpws_types import ThisDeviceType
from sdc11073.xml_types.dpws_types import ThisModelType
from sdc11073 import certloader
from sdc11073.xml_types.pm_types import AlertSignalPresence



# Added by LM van Loon on 20241106
from scipy.integrate import solve_ivp
import numpy as np
# ------------- Original SDC Provider Setup -------------
# The provider’s UUID is created from a base.
base_uuid = uuid.UUID('{cc013678-79f6-403c-998f-3cc0cc050230}')
my_uuid = uuid.uuid5(base_uuid, "12345")

if __name__ == '__main__':
    # Parse command-line arguments for network adapter and patient file
    parser = argparse.ArgumentParser(description="Start SDC Provider")
    parser.add_argument('--adapter', default='en0', help="Network adapter to use (default: en0)")
    parser.add_argument('--patient-file', default=None, help="Patient parameter file to use (.json)")
    args = parser.parse_args()
    NETWORK_ADAPTER = args.adapter

    # Initialize loop counter for periodic alarm status output
    loop_counter = 0

    # Start discovery on the specified network adapter
    my_discovery = WSDiscoverySingleAdapter(NETWORK_ADAPTER)
    my_discovery.start()

    # Create the local MDIB from an XML file.
    try:
        my_mdib = ProviderMdib.from_mdib_file(os.path.join(BASE_PATH, "ExtendedDevice.xml"))
    except Exception as e:
        print("Error reading mdib.xml:", e)
        sys.exit(1)
    print("My UUID is {}".format(my_uuid))

    # Set the location context for discovery.
    my_location = SdcLocation(fac='UMCU', poc='ICU_3', bed='01')  # Facility, Department, Bed

    # Set model information for discovery.
    dpws_model = ThisModelType(
        manufacturer='Draeger',
        manufacturer_url='www.draeger.com',
        model_name='TestDevice',
        model_number='1.0',
        model_url='www.draeger.com/model',
        presentation_url='www.draeger.com/model/presentation'
    )
    dpws_device = ThisDeviceType(
        friendly_name='TestDevice',
        firmware_version='Version1',
        serial_number='12345'
    )

    # Load SSL context.
    my_ssl_context = certloader.mk_ssl_contexts_from_folder(
        ca_folder=os.path.join(BASE_PATH, "ssl/"),
        ssl_passwd='dummypass'
    )

    # Create the SDC provider device.
    specific_components = SdcProviderComponents(role_provider_class=ExtendedProduct)
    sdc_provider = SdcProvider(
        ws_discovery=my_discovery,
        epr=my_uuid,
        this_model=dpws_model,
        this_device=dpws_device,
        device_mdib_container=my_mdib,
        specific_components=specific_components,
        ssl_context_container=my_ssl_context
    )
    sdc_provider.start_all()
    sdc_provider.set_location(my_location)

    # ------------- Original MDIB Metric Update -------------
    all_metric_descrs = [c for c in my_mdib.descriptions.objects if c.NODETYPE == pm.NumericMetricDescriptor]
    with my_mdib.metric_state_transaction() as transaction_mgr:
        for metric_descr in all_metric_descrs:
            st = transaction_mgr.get_state(metric_descr.Handle)
            st.mk_metric_value()
            st.MetricValue.Value = Decimal(1.0)
            st.MetricValue.ActiveDeterminationPeriod = 1494554822450
            st.MetricValue.Validity = pm_types.MeasurementValidity.VALID
            st.ActivationState = pm_types.ComponentActivation.ON
            

    # ------------- Digital Twin Model Simulation -------------
    from digital_twin_model import DigitalTwinModel

    # Determine which parameter file to use
    if args.patient_file:
        # Use the file specified by the GUI
        param_file_path = args.patient_file
        print(f"Using patient file specified by GUI: {param_file_path}")
    else:
        # Use healthy.json as default for healthy adult simulation
        param_file_path = os.path.join(BASE_PATH, "MDTparameters", "healthy.json")
        if not os.path.exists(param_file_path):
            # Fallback to neonate.json if healthy.json doesn't exist
            param_file_path = os.path.join(BASE_PATH, "MDTparameters", "neonate.json")
        print(f"Using default parameter file: {param_file_path}")
    
    if not os.path.exists(param_file_path):
        print(f"Error: Parameter file not found: {param_file_path}")
        sys.exit(1)
    
    dt_model = DigitalTwinModel(patient_id="Dummy", param_file=param_file_path)
    
    # Initialize the alarm module
    alarm_module = AlarmModule(patient_id="Dummy")
    dt_model.alarmModule = alarm_module  # Connect to digital twin
    print("✓ Alarm module initialized and connected to digital twin")
    
    sampling_interval = 2 # seconds (adjust as needed)
    current_time = dt_model.t   # Initially 0
    
    # Adjust baseline temperature based on patient profile
    if "pneumonia" in param_file_path.lower():
        BASELINE_TEMPERATURE = 38.8  # Fever from pneumonia
        print(f"Pneumonia patient detected - baseline temperature set to {BASELINE_TEMPERATURE}°C")
    elif "heartfailure" in param_file_path.lower() or "copd" in param_file_path.lower():
        BASELINE_TEMPERATURE = 37.0  # Normal temperature for other conditions
        print(f"Patient profile detected - baseline temperature set to {BASELINE_TEMPERATURE}°C")
    else:
        BASELINE_TEMPERATURE = 37.0  # Default normal temperature
        print(f"Default baseline temperature set to {BASELINE_TEMPERATURE}°C")

    # Parameter update file for communication with GUI
    param_update_file = os.path.join(BASE_PATH, "param_updates.tmp")
    
    def trigger_ecg_lead_off_alarm(enable):
        """Trigger or clear the ECG lead off technical alarm"""
        try:
            with my_mdib.alert_state_transaction() as transaction_mgr:
                # Get the ECG lead off alert condition and signals
                alert_condition = transaction_mgr.get_state("tech.moni.1")
                vis_signal = transaction_mgr.get_state("signal.tech.moni.1.visible")
                aud_signal = transaction_mgr.get_state("signal.tech.moni.1.audible")
                
                if enable:
                    # Activate the alarm
                    alert_condition.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
                else:
                    # Clear the alarm
                    alert_condition.Presence = False
                    vis_signal.Presence = pm_types.AlertSignalPresence.OFF
                    aud_signal.Presence = pm_types.AlertSignalPresence.OFF
                    
        except Exception as e:
            print(f"Warning: Failed to update ECG lead off alarm: {e}")
    
    def check_parameter_updates():
        """Check for parameter updates from GUI and apply them"""
        if os.path.exists(param_update_file):
            try:
                with open(param_update_file, 'r') as f:
                    lines = f.readlines()
                
                # Process each parameter update
                for line in lines:
                    line = line.strip()
                    if '=' in line:
                        param, value = line.split('=', 1)
                        param = param.strip()
                        value = float(value.strip())
                        
                        # Map GUI parameter names to digital twin parameter names
                        param_mapping = {
                            'hr_setpoint': 'cardio_control_params.HR_n',
                            'map_setpoint': 'cardio_control_params.ABP_n',
                            'rr_setpoint': 'respiratory_control_params.RR_0',
                            'fio2': 'gas_exchange_params.FI_O2',
                            'blood_volume': 'misc_constants.TBV',
                            'temperature': 'baseline_temperature',  # Custom temperature parameter
                            'baroreflex': 'use_baroreflex',
                            'chemoreceptor': 'use_chemoreceptor',
                            'ecg_lead_off': 'ecg_lead_status'  # ECG disconnection alarm trigger
                        }
                        
                        if param in param_mapping:
                            dt_param = param_mapping[param]
                            
                            # Handle reflex toggles separately
                            if param == 'baroreflex':
                                dt_model.use_baroreflex = bool(value)
                                print(f"Updated baroreflex to {dt_model.use_baroreflex}")
                            elif param == 'chemoreceptor':
                                dt_model.use_chemoreceptor = bool(value)
                                print(f"Updated chemoreceptor to {dt_model.use_chemoreceptor}")
                            elif param == 'temperature':
                                # Handle temperature change
                                global BASELINE_TEMPERATURE
                                BASELINE_TEMPERATURE = value
                                print(f"Updated baseline temperature to {BASELINE_TEMPERATURE:.1f}°C")
                            elif param == 'ecg_lead_off':
                                # Handle ECG lead off alarm trigger
                                trigger_ecg_lead_off_alarm(bool(value))
                                print(f"ECG lead off alarm {'triggered' if value else 'cleared'}")
                            elif dt_param in dt_model.master_parameters:
                                # Update the parameter in the digital twin model
                                dt_model.master_parameters[dt_param]['value'] = value
                                print(f"Updated parameter {dt_param} to {value}")
                                
                                # Update internal variables that cache these values
                                if dt_param == 'cardio_control_params.HR_n':
                                    dt_model._ode_HR_n = value
                                elif dt_param == 'cardio_control_params.ABP_n':
                                    dt_model._baro_P_set = value
                                elif dt_param == 'respiratory_control_params.RR_0':
                                    dt_model._ode_RR0 = value
                
                # Remove the file after processing
                os.remove(param_update_file)
                
            except Exception as e:
                print(f"Error processing parameter updates: {e}")
                try:
                    os.remove(param_update_file)
                except:
                    pass

    def evaluate_and_trigger_alarms(current_data):
        """Evaluate physiological data using alarm module and trigger SDC alarms"""
        if not hasattr(dt_model, 'alarmModule') or dt_model.alarmModule is None:
            return
        
        # Format data for alarm module (using expected parameter names)
        alarm_data = {
            'HR': current_data.get('heart_rate', 0),
            'SAP': current_data.get('systolic_pressure', 0),
            'DAP': current_data.get('diastolic_pressure', 0),
            'MAP': current_data.get('blood_pressure', 0),
            'SaO2': current_data.get('sao2', 0),
            'TEMP': current_data.get('temperature', 37.0),
            'RR': current_data.get('rr', 0),
            'EtCO2': current_data.get('etco2', 0)
        }
        
        # Evaluate alarms using the alarm module
        alarm_events = dt_model.alarmModule.evaluate_alarms(alarm_data)
        
        # Process each alarm event
        for event in alarm_events:
            if event['active']:
                trigger_sdc_alarm(event)
            else:
                clear_sdc_alarm(event)

    def output_current_alarm_status():
        """Output current alarm status for GUI parsing (called periodically)"""
        if not hasattr(dt_model, 'alarmModule') or dt_model.alarmModule is None:
            return
        
        try:
            # Get current alarm status for all parameters
            alarm_status = dt_model.alarmModule.get_current_alarm_status()
            
            # Output status for each parameter that has an active alarm
            for param_name, status in alarm_status.items():
                if status['active']:
                    # Output active alarm status
                    alarm_type = status['alarm_type'].lower().replace('_', ' ')
                    print(f"🟨 CURRENT ALARM STATUS: {param_name} {alarm_type} - {status['message']}")
                
        except Exception as e:
            print(f"Warning: Failed to output alarm status: {e}")

    def trigger_sdc_alarm(alarm_event):
        """Trigger an SDC alarm based on alarm module event"""
        try:
            param_name = alarm_event['parameter']
            alarm_type = alarm_event['alarm_type'].lower()  # 'high', 'low', 'critical_high', 'critical_low'
            
            # Map alarm parameters to SDC alarm handles
            sdc_mapping = {
                'HeartRate': 'hr',
                'BloodPressureMean': 'map',
                'BloodPressureSystolic': 'sap',  # Updated mapping
                'BloodPressureDiastolic': 'dap',  # Updated mapping
                'Temperature': 'temperature',
                'SpO2': 'sao2',
                'RespiratoryRate': 'rr',
                'EtCO2': 'etco2'
            }
            
            # Convert alarm type to upper/lower
            if 'high' in alarm_type:
                sdc_alarm_type = 'upper'
            elif 'low' in alarm_type:
                sdc_alarm_type = 'lower'
            else:
                return  # Unknown alarm type
            
            if param_name in sdc_mapping:
                sdc_param = sdc_mapping[param_name]
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state(f"limit.{sdc_param}.{sdc_alarm_type}")
                    vis_signal = transaction_mgr.get_state(f"signal.{sdc_param}.{sdc_alarm_type}.visible")
                    aud_signal = transaction_mgr.get_state(f"signal.{sdc_param}.{sdc_alarm_type}.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
                    
                print(f"✓ Triggered SDC alarm: {param_name} {alarm_type} - {alarm_event['message']}")
        except Exception as e:
            print(f"Warning: Failed to trigger SDC alarm for {alarm_event['parameter']}: {e}")

    def clear_sdc_alarm(alarm_event):
        """Clear an SDC alarm based on alarm module event"""
        try:
            param_name = alarm_event['parameter']
            alarm_type = alarm_event['alarm_type'].lower()
            
            sdc_mapping = {
                'HeartRate': 'hr',
                'BloodPressureMean': 'map',
                'BloodPressureSystolic': 'sap',
                'BloodPressureDiastolic': 'dap',
                'Temperature': 'temperature',
                'SpO2': 'sao2',
                'RespiratoryRate': 'rr',
                'EtCO2': 'etco2'
            }
            
            # Convert alarm type to upper/lower
            if 'high' in alarm_type:
                sdc_alarm_type = 'upper'
            elif 'low' in alarm_type:
                sdc_alarm_type = 'lower'
            else:
                return  # Unknown alarm type
            
            if param_name in sdc_mapping:
                sdc_param = sdc_mapping[param_name]
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state(f"limit.{sdc_param}.{sdc_alarm_type}")
                    vis_signal = transaction_mgr.get_state(f"signal.{sdc_param}.{sdc_alarm_type}.visible")
                    aud_signal = transaction_mgr.get_state(f"signal.{sdc_param}.{sdc_alarm_type}.audible")

                    cond_state.Presence = False
                    vis_signal.Presence = pm_types.AlertSignalPresence.OFF
                    aud_signal.Presence = pm_types.AlertSignalPresence.OFF
                    
                print(f"✓ Cleared SDC alarm: {param_name} {alarm_type}")
        except Exception as e:
            print(f"Warning: Failed to clear SDC alarm for {alarm_event['parameter']}: {e}")

    # Storage for pressure values during integration
    pressure_values = []
    
    # Storage for systolic and diastolic pressure tracking
    pressure_buffer = []
    max_pressure_window = 50  # Track max/min over recent samples

    def pressure_callback(t, y):
        """Callback to collect pressure values during integration"""
        # Convert volumes to pressures using the same logic as compute_variables
        V = y[:10]
        Pmus = y[25]
        
        # Get elastances for current time
        ela, elv, era, erv = dt_model.get_inputs(t)
        UV_c = dt_model.master_parameters['cardio_control_params.UV_n']['value'] + y[28]
        
        # Calculate pressures
        P = np.zeros(10)
        P[0] = dt_model.elastance[0, 0] * (V[0] - dt_model.uvolume[0]) + Pmus
        P[1] = dt_model.elastance[0, 1] * (V[1] - dt_model.uvolume[1])
        P[2] = dt_model.elastance[0, 2] * (V[2] - dt_model.uvolume[2] * UV_c)
        P[3] = dt_model.elastance[0, 3] * (V[3] - dt_model.uvolume[3] * UV_c) + Pmus
        P[4] = era * (V[4] - dt_model.uvolume[4]) + Pmus
        P[5] = erv * (V[5] - dt_model.uvolume[5]) + Pmus
        P[6] = dt_model.elastance[0, 6] * (V[6] - dt_model.uvolume[6]) + Pmus
        P[7] = dt_model.elastance[0, 7] * (V[7] - dt_model.uvolume[7]) + Pmus
        P[8] = ela * (V[8] - dt_model.uvolume[8]) + Pmus
        P[9] = elv * (V[9] - dt_model.uvolume[9]) + Pmus
        
        # Store the arterial pressure (P[0])
        pressure_values.append(P[0])
        return 0  # Continue integration

    # Main simulation loop
    while True:
        # Check for parameter updates from GUI
        check_parameter_updates()
        
        # Clear pressure values for this integration
        pressure_values = []
        
        sol = solve_ivp(
            fun=dt_model.extended_state_space_equations,
            t_span=[current_time, current_time + sampling_interval],
            y0=dt_model.current_state,
            t_eval=np.linspace(current_time, current_time + sampling_interval, 50),  # Dense output for averaging
            method='LSODA',
            rtol=1e-6,
            atol=1e-6,
            events=pressure_callback
        )

        dt_model.current_state = sol.y[:, -1]
        current_time += sampling_interval
        dt_model.t = current_time

        # --- Compute physiological variables using the digital twin model ---
        P, F, HR, SaO2, RR = dt_model.compute_variables(current_time, dt_model.current_state)
        
        # Calculate average blood pressure over the sampling interval
        if len(sol.t) > 1:
            # Compute pressure for each time point in the solution
            avg_pressure_values = []
            for i in range(len(sol.t)):
                t_point = sol.t[i]
                y_point = sol.y[:, i]
                
                # Same pressure calculation as in callback
                V = y_point[:10]
                Pmus = y_point[25]
                ela, elv, era, erv = dt_model.get_inputs(t_point)
                UV_c = dt_model.master_parameters['cardio_control_params.UV_n']['value'] + y_point[28]
                
                P_temp = np.zeros(10)
                P_temp[0] = dt_model.elastance[0, 0] * (V[0] - dt_model.uvolume[0]) + Pmus
                avg_pressure_values.append(P_temp[0])
            
            averaged_blood_pressure = np.mean(avg_pressure_values)
            
            # Calculate systolic and diastolic pressures
            pressure_buffer.extend(avg_pressure_values)
            if len(pressure_buffer) > max_pressure_window:
                pressure_buffer = pressure_buffer[-max_pressure_window:]
            
            # Find systolic (max) and diastolic (min) from recent pressure values
            systolic_pressure = np.max(pressure_buffer) if pressure_buffer else P[0]
            diastolic_pressure = np.min(pressure_buffer) if pressure_buffer else P[0]
        else:
            averaged_blood_pressure = P[0]
            systolic_pressure = P[0]
            diastolic_pressure = P[0]
        
        # Calculate body temperature (simplified model - controllable baseline with small variations)
        # Add small physiological variations and potential fever response
        baseline_temp = BASELINE_TEMPERATURE  # Controllable body temperature baseline from GUI
        temp_variation = 0.2 * np.sin(current_time / 3600) + 0.1 * np.random.normal(0, 0.1)  # Daily variation + noise
        body_temperature = baseline_temp + temp_variation
        
        # Extract values for SDC updates
        new_heart_rate = HR
        new_blood_pressure = averaged_blood_pressure  # Use averaged pressure (MAP)
        new_systolic_pressure = systolic_pressure
        new_diastolic_pressure = diastolic_pressure
        new_temperature = body_temperature
        new_SaO2 = SaO2
        new_RR = RR
        new_etCO2 = dt_model.current_state[17]

        current_time_real = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            with my_mdib.metric_state_transaction() as transaction_mgr:
                # Update heart rate
                hr_state = transaction_mgr.get_state("hr")
                hr_state.MetricValue.Value = Decimal(float(new_heart_rate))

                # Update mean arterial pressure (now averaged)
                map_state = transaction_mgr.get_state("map")
                map_state.MetricValue.Value = Decimal(float(new_blood_pressure))
                
                # Update systolic arterial pressure (ABPsys)
                sap_state = transaction_mgr.get_state("sap")
                sap_state.MetricValue.Value = Decimal(float(new_systolic_pressure))
                
                # Update diastolic arterial pressure (ABPdias)
                dap_state = transaction_mgr.get_state("dap")
                dap_state.MetricValue.Value = Decimal(float(new_diastolic_pressure))
                
                # Update body temperature
                temp_state = transaction_mgr.get_state("temperature")
                temp_state.MetricValue.Value = Decimal(float(new_temperature))
                
                # Update oxygen saturation
                sao2_state = transaction_mgr.get_state("sao2")
                sao2_state.MetricValue.Value = Decimal(float(new_SaO2))
                
                # Update respiratory rate
                rr_state = transaction_mgr.get_state("rr")
                rr_state.MetricValue.Value = Decimal(float(new_RR))
                
                # Update end-tidal CO2
                etco2_state = transaction_mgr.get_state("etco2")
                etco2_state.MetricValue.Value = Decimal(float(new_etCO2))
                
        except Exception as e:
            print(f"Warning: Failed to update MDIB metrics: {e}")

        # Print current values for debugging
        print(f"[{current_time_real}] HR: {new_heart_rate:.1f}, MAP (avg): {new_blood_pressure:.1f}, "
              f"SYS: {new_systolic_pressure:.1f}, DIA: {new_diastolic_pressure:.1f}, "
              f"TEMP: {new_temperature:.1f}°C, SaO2: {new_SaO2:.1f}, RR: {new_RR:.1f}, etCO2: {new_etCO2:.1f}", flush=True)

        # Evaluate and trigger alarms using the alarm module
        current_data = {
            'heart_rate': new_heart_rate,
            'blood_pressure': new_blood_pressure,
            'systolic_pressure': new_systolic_pressure,
            'diastolic_pressure': new_diastolic_pressure,
            'temperature': new_temperature,
            'sao2': new_SaO2,
            'rr': new_RR,
            'etco2': new_etCO2
        }
        evaluate_and_trigger_alarms(current_data)
        
        # Output current alarm status every 5 cycles (for GUI persistence)
        loop_counter += 1
        
        if loop_counter % 5 == 0:  # Every 5 iterations (~10 seconds)
            output_current_alarm_status()

        time.sleep(sampling_interval)