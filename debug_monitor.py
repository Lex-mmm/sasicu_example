#!/usr/bin/env python3
"""
Debug Monitor - Simple SDC data reader
"""

import sys
import os
import time
from datetime import datetime

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from sdc11073.consumer import SdcConsumer
    from sdc11073.wsdiscovery import WSDiscoverySingleAdapter
    from sdc11073 import certloader
    print("✓ SDC libraries loaded")
except ImportError as e:
    print(f"✗ Failed to import SDC libraries: {e}")
    sys.exit(1)

def connect_and_monitor():
    print("Initializing SDC connection...")
    
    try:
        # Initialize discovery
        discovery = WSDiscoverySingleAdapter("en0")
        discovery.start()
        print("✓ Discovery started")
        
        # Search for services
        services = discovery.search_services(timeout=10)
        if not services:
            print("✗ No services found")
            return
            
        print(f"✓ Found {len(services)} service(s)")
        
        # Connect to first service
        service = services[0]
        ssl_context = certloader.mk_ssl_contexts_from_folder(
            ca_folder=os.path.join(os.getcwd(), "ssl/"),
            ssl_passwd='dummypass'
        )
        
        consumer = SdcConsumer.from_wsd_service(service, ssl_context_container=ssl_context)
        consumer.start_all()
        print("✓ Consumer connected")
        
        # Wait for MDIB to be available
        print("Waiting for MDIB...")
        max_wait = 30  # 30 seconds max wait
        wait_count = 0
        
        while not consumer.mdib and wait_count < max_wait:
            time.sleep(1)
            wait_count += 1
            print(f"  Waiting... {wait_count}s")
            
        if not consumer.mdib:
            print("✗ MDIB not available after 30 seconds")
            return
            
        print("✓ MDIB available!")
        
        # Target metrics we want to monitor
        target_handles = ['hr', 'map', 'sap', 'dap', 'temperature', 'sao2', 'rr', 'etco2']
        
        print("\nStarting monitoring loop...")
        print("=" * 80)
        
        while True:
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                values = {}
                
                # Get all metric states
                for state in consumer.mdib.states.objects:
                    if hasattr(state, 'DescriptorHandle') and state.DescriptorHandle in target_handles:
                        if hasattr(state, 'MetricValue') and state.MetricValue and state.MetricValue.Value is not None:
                            values[state.DescriptorHandle] = float(state.MetricValue.Value)
                
                # Display values
                if values:
                    print(f"[{timestamp}] ", end="")
                    for handle in target_handles:
                        if handle in values:
                            if handle == 'temperature':
                                print(f"{handle.upper()}: {values[handle]:.1f}°C  ", end="")
                            else:
                                print(f"{handle.upper()}: {values[handle]:.0f}  ", end="")
                        else:
                            print(f"{handle.upper()}: --  ", end="")
                    print()  # New line
                else:
                    print(f"[{timestamp}] No data available")
                
                time.sleep(2)  # Update every 2 seconds
                
            except KeyboardInterrupt:
                print("\nStopping monitor...")
                break
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(1)
                
        consumer.stop_all()
        discovery.stop()
        print("✓ Disconnected")
        
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    connect_and_monitor()
