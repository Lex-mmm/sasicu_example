#!/usr/bin/env python3
"""
SDC Consumer for Medical Device Testing
Consumes physiological data via Service-oriented Device Connectivity (SDC).

Copyright (c) 2025 Dr. L.M. van Loon. All Rights Reserved.

This software is for academic research and educational purposes only.
Commercial use is strictly prohibited without explicit written permission
from Dr. L.M. van Loon.

For commercial licensing inquiries, contact Dr. L.M. van Loon.
"""

import logging
import time
import uuid
import argparse
import os
import netifaces
import ipaddress
from sdc11073.xml_types import pm_types, msg_types
from sdc11073.xml_types import pm_qnames as pm
from sdc11073.xml_types.actions import periodic_actions
from sdc11073.wsdiscovery import WSDiscovery  # Remove NetworkingThreadPosix import
from sdc11073.definitions_sdc import SdcV1Definitions
from sdc11073.consumer import SdcConsumer
from sdc11073.mdib import ConsumerMdib
from sdc11073 import observableproperties
from sdc11073.loghelper import basic_logging_setup
from sdc11073 import certloader
import socket


# Define the patched socket creation for unicast
def patched_create_unicast_in_socket(self, addr, port):
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except Exception as e:
        print("Warning: SO_REUSEPORT could not be set:", e)
    try:
        # Bind to same IP, but let OS choose a free port instead of 3702
        sock.bind((addr, 0))  # <-- this is the fix
    except OSError as e:
        raise RuntimeError(f"Socket bind failed on {addr}: {e}")
    return sock


# Assuming your `NetworkingThreadPosix` was used for networking tasks.
# The patch is being applied here for the unicast socket function.
# If you still have reference to it in your code, removing it will allow everything to work.

# Main entry, will start to scan for the known provider and connect
baseUUID = uuid.UUID('{cc013678-79f6-403c-998f-3cc0cc050230}')
device_A_UUID = uuid.uuid5(baseUUID, "12345")


def on_metric_update(metrics_by_handle: dict):
    # This callback will be called when metrics are updated from the provider
    print(f"Got update on: {list(metrics_by_handle.keys())}")
    
    # Print the actual metric values
    for handle, metric_state in metrics_by_handle.items():
        if hasattr(metric_state, 'MetricValue') and metric_state.MetricValue is not None:
            value = metric_state.MetricValue.Value
            print(f"  {handle}: {value}")
        else:
            print(f"  {handle}: No value available")


def on_alarm_update(alert_by_handle: dict):
    # This callback will be called when alarms are updated from the provider
    print(f"Got alarm update on: {list(alert_by_handle.keys())}")
    
    # Print detailed alarm information
    for handle, alert_state in alert_by_handle.items():
        print(f"  Alert {handle}:")
        
        # Check if it's a limit alert condition
        if hasattr(alert_state, 'Presence') and alert_state.Presence is not None:
            print(f"    Presence: {alert_state.Presence}")
            
        # Print limit information if available
        if hasattr(alert_state, 'Limits') and alert_state.Limits is not None:
            limits = alert_state.Limits
            if hasattr(limits, 'Upper') and limits.Upper is not None:
                print(f"    Upper Limit: {limits.Upper}")
            if hasattr(limits, 'Lower') and limits.Lower is not None:
                print(f"    Lower Limit: {limits.Lower}")
                
        # Print the source metric and its current value if available
        if hasattr(alert_state, 'Source') and alert_state.Source is not None:
            source_handle = alert_state.Source
            print(f"    Source Metric: {source_handle}")
            
            # Try to get the current value of the source metric
            try:
                if hasattr(my_mdib, 'states') and source_handle in my_mdib.states:
                    source_state = my_mdib.states[source_handle]
                    if hasattr(source_state, 'MetricValue') and source_state.MetricValue is not None:
                        current_value = source_state.MetricValue.Value
                        print(f"    Current Value: {current_value}")
            except:
                print(f"    Current Value: Unable to retrieve")


def set_ensemble_context(mdib: ConsumerMdib, sdc_consumer: SdcConsumer) -> None:
    print("Trying to set ensemble context of device A")
    ensemble_descriptor_container = mdib.descriptions.NODETYPE.get_one(pm.EnsembleContextDescriptor)
    context_client = sdc_consumer.context_service_client

    # Iterating over matching operation descriptors
    operation_handle = None
    for op_descr in mdib.descriptions.NODETYPE.get(pm.SetContextStateOperationDescriptor, []):
        if op_descr.OperationTarget == ensemble_descriptor_container.Handle:
            operation_handle = op_descr.Handle

    # Creating new ensemble context object
    new_ensemble_context = context_client.mk_proposed_context_object(ensemble_descriptor_container.Handle)
    new_ensemble_context.ContextAssociation = pm_types.ContextAssociation.ASSOCIATED
    new_ensemble_context.Identification = [
        pm_types.InstanceIdentifier(root="1.2.3", extension_string="SupervisorSuperEnsemble")]
    
    # Set the context state remotely
    response = context_client.set_context_state(operation_handle, [new_ensemble_context])
    result: msg_types.OperationInvokedReportPart = response.result()
    
    if result.InvocationInfo.InvocationState not in (msg_types.InvocationState.FINISHED, msg_types.InvocationState.FINISHED_MOD):
        print(f'set ensemble context state failed state = {result.InvocationInfo.InvocationState}, '
              f'error = {result.InvocationInfo.InvocationError}, msg = {result.InvocationInfo.InvocationErrorMessage}')
    else:
        print(f'set ensemble context was successful.')


# main entry, will start to scan for the known provider and connect
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start SDC Consumer with specified network interface")
    parser.add_argument('--interface', default='en0', help="Network interface to use (default: en0)")
    parser.add_argument('--ssl-passwd', default="dummypass", help="SSL password for cert loading (default: dummypass)")
    args = parser.parse_args()

    # Determine the IP address based on interface
    try:
        ipaddress.IPv4Address(args.interface)
        network_ip = args.interface
    except ipaddress.AddressValueError:
        iface_data = netifaces.ifaddresses(args.interface)
        network_ip = iface_data[netifaces.AF_INET][0]['addr']

    current_dir = os.path.dirname(os.path.abspath(__file__))
    ssl_folder = os.path.join(current_dir, 'ssl')
    
    # Set up logging and discovery
    basic_logging_setup(level=logging.INFO)
    my_discovery = WSDiscovery(network_ip)
    my_discovery.start()
    
    # Search for the provider and connect
    found_device = False
    while not found_device:
        print('searching for SDC providers')
        services = my_discovery.search_services(types=SdcV1Definitions.MedicalDeviceTypesFilter)
        
        for one_service in services:
            print(f"Got service: {one_service.epr}")
            if one_service.epr == device_A_UUID.urn:
                print(f"Found a match: {one_service}")
                my_ssl_context_container = certloader.mk_ssl_contexts_from_folder(
                    ca_folder=ssl_folder,
                    ssl_passwd=args.ssl_passwd
                )
                my_client = SdcConsumer.from_wsd_service(one_service, ssl_context_container=my_ssl_context_container)
                my_client.start_all(not_subscribed_actions=periodic_actions)
                my_mdib = ConsumerMdib(my_client)
                my_mdib.init_mdib()
                observableproperties.bind(my_mdib, metrics_by_handle=on_metric_update)
                observableproperties.bind(my_mdib, alert_by_handle=on_alarm_update)
                found_device = True
                set_ensemble_context(my_mdib, my_client)

    while True:
        time.sleep(1)
