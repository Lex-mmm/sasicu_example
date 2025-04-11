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
        my_mdib = ProviderMdib.from_mdib_file(os.path.join(BASE_PATH, "mdibmdt.xml"))
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

    dt_model = DigitalTwinModel(patient_id="12345", param_file=os.path.join(BASE_PATH, "MDTparameters/patient_1.json"))
    sampling_interval = 5  # seconds (adjust as needed)
    current_time = dt_model.t   # Initially 0

    # Define alarm thresholds.
    ALARM_THRESHOLD_SaO2 = 95
    HIGH_HEART_RATE_THRESHOLD = 100
    LOW_HEART_RATE_THRESHOLD = 50
    HIGH_BLOOD_PRESSURE_THRESHOLD = 40


    while True:
        sol = solve_ivp(
            fun=dt_model.extended_state_space_equations,
            t_span=[current_time, current_time + sampling_interval],
            y0=dt_model.current_state,
            t_eval=[current_time + sampling_interval],
            method='RK45'
        )

        dt_model.current_state = sol.y[:, -1]
        current_time += sampling_interval
        dt_model.t = current_time

        # --- Compute new metric values (replace with your actual equations) ---
        # For example, assume:
        #   - Heart rate is stored in state index 5
        #   - Blood pressure is stored in state index 6
        new_heart_rate = dt_model.current_state[5]
        new_blood_pressure = dt_model.current_state[6]

        # Optionally simulate changes based on time
        if current_time > 15:
            new_heart_rate -= 10

        # ----- Add random noise spikes -----
        # 5% chance to add noise to heart rate
        if random.random() < 0.05:
            noise = random.uniform(20, 50)  # e.g. spike by 20–50 bpm
            new_heart_rate += noise
            print(f"[{current_time_real}] Injected heart rate spike: +{noise:.1f}")

        # 3% chance to add noise to blood pressure
        if random.random() < 0.03:
            noise = random.uniform(10, 25)
            new_blood_pressure += noise
            print(f"[{current_time_real}] Injected BP spike: +{noise:.1f}")


        current_time_real = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


        # --- Update MDIB metric values ---
        try:
            with my_mdib.metric_state_transaction() as transaction_mgr:
                # Update heart rate metric
                hr_state = transaction_mgr.get_state("heartRate")
                hr_state.MetricValue.Value = Decimal(new_heart_rate)
                
                # Update blood pressure metric
                bp_state = transaction_mgr.get_state("bloodPressure")
                bp_state.MetricValue.Value = Decimal(new_blood_pressure)
        except Exception as e:
            print(f"Warning: Failed to update MDIB metrics (heartRate/bloodPressure): {e}")


        # --- Update alert states based on thresholds ---
        try:
            with my_mdib.alert_state_transaction() as transaction_mgr:
                # Heart Rate Alerts
                if new_heart_rate > HIGH_HEART_RATE_THRESHOLD:
                    # Trigger high heart rate alarm
                    ac_hr_high = transaction_mgr.get_state("ac.hr.high")
                    as_hr_high = transaction_mgr.get_state("as.hr.high")
                    ac_hr_high.Presence = True
                    as_hr_high.Presence = pm_types.AlertSignalPresence.ON
                elif new_heart_rate < LOW_HEART_RATE_THRESHOLD:
                    # Trigger low heart rate alarm
                    ac_hr_low = transaction_mgr.get_state("ac.hr.low")
                    as_hr_low = transaction_mgr.get_state("as.hr.low")
                    ac_hr_low.Presence = True
                    as_hr_low.Presence = pm_types.AlertSignalPresence.ON
                else:
                    # Clear heart rate alarms if within thresholds
                    try:
                        ac_hr_high = transaction_mgr.get_state("ac.hr.high")
                        as_hr_high = transaction_mgr.get_state("as.hr.high")
                        ac_hr_low = transaction_mgr.get_state("ac.hr.low")
                        as_hr_low = transaction_mgr.get_state("as.hr.low")
                        ac_hr_high.Presence = False
                        as_hr_high.Presence = pm_types.AlertSignalPresence.OFF
                        ac_hr_low.Presence = False
                        as_hr_low.Presence = pm_types.AlertSignalPresence.OFF
                    except Exception as clear_e:
                        print(f"Warning: Failed to clear heart rate alarms: {clear_e}")

                # Blood Pressure Alert
                if new_blood_pressure > HIGH_BLOOD_PRESSURE_THRESHOLD:
                    ac_bp_high = transaction_mgr.get_state("ac.bp.high")
                    as_bp_high = transaction_mgr.get_state("as.bp.high")
                    ac_bp_high.Presence = True
                    as_bp_high.Presence = pm_types.AlertSignalPresence.ON
                else:
                    try:
                        ac_bp_high = transaction_mgr.get_state("ac.bp.high")
                        as_bp_high = transaction_mgr.get_state("as.bp.high")
                        ac_bp_high.Presence = False
                        as_bp_high.Presence = pm_types.AlertSignalPresence.OFF
                    except Exception as clear_bp_e:
                        print(f"Warning: Failed to clear blood pressure alarm: {clear_bp_e}")
        except Exception as e:
            print(f"Warning: Failed to update MDIB alert state: {e}")


        time.sleep(sampling_interval)