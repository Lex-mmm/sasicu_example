#!/usr/bin/env python3
"""
Quick SDC Connection Test
Test if we can connect to the running provider.
"""

import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from sdc11073.consumer import SdcConsumer
    from sdc11073.wsdiscovery import WSDiscoverySingleAdapter
    from sdc11073 import certloader
    print("✓ SDC libraries imported successfully")
except ImportError as e:
    print(f"✗ Failed to import SDC libraries: {e}")
    sys.exit(1)

def test_connection():
    print("Starting SDC discovery test...")
    
    try:
        # Initialize discovery
        discovery = WSDiscoverySingleAdapter("en0")
        discovery.start()
        print("✓ Discovery started")
        
        # Search for services
        print("Searching for SDC services (timeout: 10s)...")
        services = discovery.search_services(timeout=10)
        print(f"Found {len(services)} services")
        
        if not services:
            print("✗ No SDC services found")
            print("Make sure provider_MDT.py is running")
            return False
            
        for i, service in enumerate(services):
            print(f"Service {i}: {service}")
            
        # Try to connect to first service
        service = services[0]
        print(f"Attempting to connect to: {service}")
        
        # Load SSL context
        ssl_context = certloader.mk_ssl_contexts_from_folder(
            ca_folder=os.path.join(os.getcwd(), "ssl/"),
            ssl_passwd='dummypass'
        )
        print("✓ SSL context loaded")
        
        # Create consumer
        consumer = SdcConsumer.from_wsd_service(service, ssl_context_container=ssl_context)
        consumer.start_all()
        print("✓ Consumer started")
        
        # Check MDIB
        if consumer.mdib:
            print("✓ MDIB available")
            
            # List available metrics
            metrics = [s for s in consumer.mdib.states.objects if hasattr(s, 'DescriptorHandle')]
            print(f"Found {len(metrics)} metric states")
            
            # Check for our specific metrics
            target_handles = ['hr', 'map', 'sap', 'dap', 'temperature', 'sao2', 'rr', 'etco2']
            found_handles = []
            
            for metric in metrics:
                if hasattr(metric, 'DescriptorHandle') and metric.DescriptorHandle in target_handles:
                    found_handles.append(metric.DescriptorHandle)
                    if hasattr(metric, 'MetricValue') and metric.MetricValue:
                        print(f"  {metric.DescriptorHandle}: {metric.MetricValue.Value}")
                    
            print(f"Found target metrics: {found_handles}")
            missing = set(target_handles) - set(found_handles)
            if missing:
                print(f"Missing metrics: {missing}")
        else:
            print("✗ No MDIB available")
            
        consumer.stop_all()
        discovery.stop()
        print("✓ Connection test completed successfully")
        return True
        
    except Exception as e:
        print(f"✗ Connection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    if success:
        print("\n🎉 SDC connection working! The monitor should be able to connect.")
    else:
        print("\n❌ SDC connection failed. Check the provider and try again.")
