from __future__ import annotations

import importlib.util
import sys

# load the digital twin model from the compiled module
pyc_path = "/Users/l.m.vanloon/Library/CloudStorage/OneDrive-UMCUtrecht/SDC/sasicu_example/__pycache__/digital_twin_model.cpython-39.pyc"
spec = importlib.util.spec_from_file_location("digital_twin_model", pyc_path)
digital_twin_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digital_twin_module)
DigitalTwinModel = digital_twin_module.DigitalTwinModel

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

# The provider’s UUID is created from a base.
base_uuid = uuid.UUID('{cc013678-79f6-403c-998f-3cc0cc050230}')
my_uuid = uuid.uuid5(base_uuid, "12345")

if __name__ == '__main__':
    # Start discovery on a specific network adapter ("en0", "Ethernet", etc.)
    my_discovery = WSDiscoverySingleAdapter("en0")
    my_discovery.start()

    # Create the local MDIB from an XML file.
    my_mdib = ProviderMdib.from_mdib_file("mdib.xml")
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

    # Added by LM van Loon on 20241106: load SSL context.
    my_ssl_context = certloader.mk_ssl_contexts_from_folder(
        ca_folder='/Users/l.m.vanloon/Library/CloudStorage/OneDrive-UMCUtrecht/SDC/sasicu_example/ssl/',
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

    # Create local numeric metric values (for example, one numeric metric).
    all_metric_descrs = [c for c in my_mdib.descriptions.objects if c.NODETYPE == pm.NumericMetricDescriptor]
    with my_mdib.metric_state_transaction() as transaction_mgr:
        for metric_descr in all_metric_descrs:
            st = transaction_mgr.get_state(metric_descr.Handle)
            st.mk_metric_value()
            st.MetricValue.Value = Decimal(1.0)
            st.MetricValue.ActiveDeterminationPeriod = 1494554822450
            st.MetricValue.Validity = pm_types.MeasurementValidity.VALID
            st.ActivationState = pm_types.ComponentActivation.ON

    # Create an instance of the digital twin model.
    # (Make sure the parameter file "parameters.json" exists and includes all required keys.)
    dt_model = DigitalTwinModel(patient_id="12345", param_file="/Users/l.m.vanloon/Library/CloudStorage/OneDrive-UMCUtrecht/SDC/sasicu_example/MDTparameters/patient_1.json")

    # Use the digital twin model for simulation updates.
    sampling_interval = 10  # seconds (adjust as needed)
    current_time = dt_model.t   # Initially 0

    # Define alarm thresholds.
    ALARM_THRESHOLD_SaO2 = 95

    # Main simulation loop.
    while True:
        # Use solve_ivp to integrate the digital twin's ODEs over the interval.
        sol = solve_ivp(
            fun=dt_model.extended_state_space_equations,
            t_span=[current_time, current_time + sampling_interval],
            y0=dt_model.current_state,
            t_eval=[current_time + sampling_interval],
            method='RK45'
        )

        # Update the digital twin model's state and simulation time.
        dt_model.current_state = sol.y[:, -1]
        current_time += sampling_interval
        dt_model.t = current_time  # Keep the internal time updated

        # For example, extract the arterial oxygen partial pressure (p_a_O2) from the state.
        p_a_O2 = dt_model.current_state[18]
        # Compute CaO2 and SaO2 using parameters from the digital twin model.
        CaO2 = (dt_model.params['K_O2'] *
                np.power((1 - np.exp(-dt_model.params['k_O2'] * min(p_a_O2, 700))), 2)) * 100
        Sa_O2 = ((CaO2 - p_a_O2 * 0.003 / 100) /
                 (dt_model.misc_constants['Hgb'] * 1.34)) * 100

        # Optionally, adjust SaO2 after a certain simulation time.
        if current_time > 15:
            Sa_O2 -= 20

        current_time_real = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Update the MDIB metric value.
        with my_mdib.metric_state_transaction() as transaction_mgr:
            spoO2_state = transaction_mgr.get_state("SpO2.Measuredvalue.2F.44A5")
            spoO2_state.MetricValue.Value = Decimal(Sa_O2)
            # Uncomment the line below to print debug information:
            # print(f"Time: {current_time_real} | t={current_time}s | SaO2: {Sa_O2}")

        # Check the alarm condition.
        if Sa_O2 < ALARM_THRESHOLD_SaO2:
            with my_mdib.alert_state_transaction() as transaction_mgr:
                ac_state = transaction_mgr.get_state("Limit.DESAT.SpO2.Measuredvalue.2F.44A5.39663")
                as_state = transaction_mgr.get_state("AS.Vis.NORMALPRIOCOLORLATCHED.Limit.DESAT.SpO2.Measuredvalue.2F.44A5.39663.11566")
                ac_state.Presence = True
                as_state.Presence = pm_types.AlertSignalPresence.ON

        # Wait for the next update.
        time.sleep(sampling_interval)
