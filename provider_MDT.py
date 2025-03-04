from __future__ import annotations

import sys
import os
import argparse  # <-- new import

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
        my_mdib = ProviderMdib.from_mdib_file(os.path.join(BASE_PATH, "mdib.xml"))
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

        p_a_O2 = dt_model.current_state[18]
        CaO2 = (dt_model.params['K_O2'] *
                np.power((1 - np.exp(-dt_model.params['k_O2'] * min(p_a_O2, 700))), 2)) * 100
        Sa_O2 = ((CaO2 - p_a_O2 * 0.003 / 100) /
                 (dt_model.misc_constants['Hgb'] * 1.34)) * 100

        if current_time > 15:
            Sa_O2 -= 20

        current_time_real = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            with my_mdib.metric_state_transaction() as transaction_mgr:
                spoO2_state = transaction_mgr.get_state("SpO2.Measuredvalue.2F.44A5")
                spoO2_state.MetricValue.Value = Decimal(Sa_O2)
        except Exception as e:
            print(f"Warning: Failed to update MDIB metric (SpO2): {e}")

        if Sa_O2 < ALARM_THRESHOLD_SaO2:
            try:
                with my_mdib.alert_state_transaction() as transaction_mgr:
                    ac_state = transaction_mgr.get_state("Limit.DESAT.SpO2.Measuredvalue.2F.44A5.39663")
                    as_state = transaction_mgr.get_state("AS.Vis.NORMALPRIOCOLORLATCHED.Limit.DESAT.SpO2.Measuredvalue.2F.44A5.39663.11566")
                    ac_state.Presence = True
                    as_state.Presence = pm_types.AlertSignalPresence.ON
            except Exception as e:
                print(f"Warning: Failed to update MDIB alert state: {e}")

        time.sleep(sampling_interval)