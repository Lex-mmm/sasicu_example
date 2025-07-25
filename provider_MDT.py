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

# Directly import the DigitalTwinModel class
sys.path.append(BASE_PATH)
from digital_twin_model import DigitalTwinModel

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
    # Parse command-line arguments for network adapter
    parser = argparse.ArgumentParser(description="Start SDC Provider")
    parser.add_argument('--adapter', default='en0', help="Network adapter to use (default: en0)")
    args = parser.parse_args()
    NETWORK_ADAPTER = args.adapter

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

    dt_model = DigitalTwinModel(patient_id="12345", param_file=os.path.join(BASE_PATH, "healthyFlat.json"))
    sampling_interval = 5  # seconds (adjust as needed)
    current_time = dt_model.t   # Initially 0

    # Define alarm thresholds.
    ALARM_THRESHOLD_SaO2 = 95
    HIGH_HEART_RATE_THRESHOLD = 100
    LOW_HEART_RATE_THRESHOLD = 50
    HIGH_BLOOD_PRESSURE_THRESHOLD = 40
    HIGH_SYSTOLIC_THRESHOLD = 180
    LOW_SYSTOLIC_THRESHOLD = 90
    HIGH_DIASTOLIC_THRESHOLD = 110
    LOW_DIASTOLIC_THRESHOLD = 60
    HIGH_TEMPERATURE_THRESHOLD = 38.5
    LOW_TEMPERATURE_THRESHOLD = 35.0

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

    while True:
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
        
        # Calculate body temperature (simplified model - normally 37°C with small variations)
        # Add small physiological variations and potential fever response
        baseline_temp = 37.0  # Normal body temperature in Celsius
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
              f"TEMP: {new_temperature:.1f}°C, SaO2: {new_SaO2:.1f}, RR: {new_RR:.1f}, etCO2: {new_etCO2:.1f}")

        # Activate alerts based on thresholds
        try:
            if new_heart_rate > HIGH_HEART_RATE_THRESHOLD:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state("limit.hr.upper")
                    vis_signal = transaction_mgr.get_state("signal.hr.upper.visible")
                    aud_signal = transaction_mgr.get_state("signal.hr.upper.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
        except Exception as e:
            print(f"Warning: Failed to update HR alert: {e}")

        try:
            if new_blood_pressure > HIGH_BLOOD_PRESSURE_THRESHOLD:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state("limit.map.upper")
                    vis_signal = transaction_mgr.get_state("signal.map.upper.visible")
                    aud_signal = transaction_mgr.get_state("signal.map.upper.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
        except Exception as e:
            print(f"Warning: Failed to update MAP alert: {e}")

        # New alerts for systolic pressure
        try:
            if new_systolic_pressure > HIGH_SYSTOLIC_THRESHOLD:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state("limit.sap.upper")
                    vis_signal = transaction_mgr.get_state("signal.sap.upper.visible")
                    aud_signal = transaction_mgr.get_state("signal.sap.upper.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
            elif new_systolic_pressure < LOW_SYSTOLIC_THRESHOLD:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state("limit.sap.lower")
                    vis_signal = transaction_mgr.get_state("signal.sap.lower.visible")
                    aud_signal = transaction_mgr.get_state("signal.sap.lower.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
        except Exception as e:
            print(f"Warning: Failed to update SAP alert: {e}")

        # New alerts for diastolic pressure
        try:
            if new_diastolic_pressure > HIGH_DIASTOLIC_THRESHOLD:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state("limit.dap.upper")
                    vis_signal = transaction_mgr.get_state("signal.dap.upper.visible")
                    aud_signal = transaction_mgr.get_state("signal.dap.upper.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
            elif new_diastolic_pressure < LOW_DIASTOLIC_THRESHOLD:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state("limit.dap.lower")
                    vis_signal = transaction_mgr.get_state("signal.dap.lower.visible")
                    aud_signal = transaction_mgr.get_state("signal.dap.lower.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
        except Exception as e:
            print(f"Warning: Failed to update DAP alert: {e}")

        # New alerts for temperature
        try:
            if new_temperature > HIGH_TEMPERATURE_THRESHOLD:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state("limit.temperature.upper")
                    vis_signal = transaction_mgr.get_state("signal.temperature.upper.visible")
                    aud_signal = transaction_mgr.get_state("signal.temperature.upper.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
            elif new_temperature < LOW_TEMPERATURE_THRESHOLD:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    cond_state = transaction_mgr.get_state("limit.temperature.lower")
                    vis_signal = transaction_mgr.get_state("signal.temperature.lower.visible")
                    aud_signal = transaction_mgr.get_state("signal.temperature.lower.audible")

                    cond_state.Presence = True
                    vis_signal.Presence = pm_types.AlertSignalPresence.ON
                    aud_signal.Presence = pm_types.AlertSignalPresence.ON
        except Exception as e:
            print(f"Warning: Failed to update temperature alert: {e}")





        time.sleep(sampling_interval)