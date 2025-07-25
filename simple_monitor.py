#!/usr/bin/env python3
"""
Simple Digital Twin Data Monitor
A lightweight monitor that displays real-time data from the digital twin.
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import argparse
from datetime import datetime
from collections import deque

# Add current directory to path for imports
sys.path.append(os.getcwd())

try:
    # SDC Consumer imports
    from sdc11073.consumer import SdcConsumer
    from sdc11073.wsdiscovery import WSDiscoverySingleAdapter
    from sdc11073 import certloader
    SDC_AVAILABLE = True
except ImportError:
    SDC_AVAILABLE = False
    print("Warning: SDC libraries not available. Running in demo mode.")

class SimpleDigitalTwinMonitor:
    def __init__(self, root, network_adapter='en0'):
        self.root = root
        self.root.title("Digital Twin Data Monitor")
        self.root.geometry("800x600")
        self.root.configure(bg='#f0f0f0')
        
        # Network adapter for discovery
        self.network_adapter = network_adapter
        
        # Data storage
        self.current_values = {
            'hr': 70.0,
            'map': 80.0,
            'sap': 120.0,
            'dap': 80.0,
            'temperature': 37.0,
            'sao2': 98.0,
            'rr': 16.0,
            'etco2': 35.0
        }
        
        # Connection status
        self.consumer = None
        self.discovery = None
        self.device_found = False
        self.running = False
        self.monitoring_active = False
        
        # Create GUI
        self.create_widgets()
        
        # Auto-start if SDC is available
        if SDC_AVAILABLE:
            self.auto_connect()
        else:
            self.start_demo_mode()
        
    def create_widgets(self):
        """Create the main GUI widgets."""
        # Title
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=60)
        title_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(title_frame, text="Digital Twin Patient Monitor", 
                              font=('Arial', 18, 'bold'), 
                              fg='white', bg='#2c3e50')
        title_label.pack(expand=True)
        
        # Status frame
        status_frame = tk.Frame(self.root, bg='#f0f0f0')
        status_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(status_frame, text="Status:", font=('Arial', 12, 'bold'), 
                bg='#f0f0f0').pack(side=tk.LEFT)
        
        self.status_label = tk.Label(status_frame, text="Initializing...", 
                                    font=('Arial', 12), 
                                    fg="orange", bg='#f0f0f0')
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Last update time
        self.time_label = tk.Label(status_frame, text="", 
                                  font=('Arial', 10), 
                                  fg="gray", bg='#f0f0f0')
        self.time_label.pack(side=tk.RIGHT)
        
        # Main data frame
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Create parameter cards
        self.create_parameter_cards(main_frame)
        
        # Control buttons
        control_frame = tk.Frame(self.root, bg='#f0f0f0')
        control_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.connect_button = tk.Button(control_frame, text="Connect to Device", 
                                       command=self.toggle_connection,
                                       font=('Arial', 12), 
                                       bg='#3498db', fg='white',
                                       relief=tk.FLAT, padx=20, pady=5)
        self.connect_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.refresh_button = tk.Button(control_frame, text="Refresh Data", 
                                       command=self.manual_refresh,
                                       font=('Arial', 12), 
                                       bg='#27ae60', fg='white',
                                       relief=tk.FLAT, padx=20, pady=5)
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(control_frame, text="Exit", 
                 command=self.on_closing,
                 font=('Arial', 12), 
                 bg='#e74c3c', fg='white',
                 relief=tk.FLAT, padx=20, pady=5).pack(side=tk.RIGHT)
        
    def create_parameter_cards(self, parent):
        """Create cards for each physiological parameter."""
        # Parameter definitions
        parameters = [
            ('Heart Rate', 'hr', 'bpm', '#e74c3c', '♥'),
            ('Mean ABP', 'map', 'mmHg', '#3498db', '📊'),
            ('Systolic BP', 'sap', 'mmHg', '#27ae60', '⬆'),
            ('Diastolic BP', 'dap', 'mmHg', '#f39c12', '⬇'),
            ('Temperature', 'temperature', '°C', '#9b59b6', '🌡'),
            ('SpO2', 'sao2', '%', '#1abc9c', '💨'),
            ('Resp. Rate', 'rr', 'bpm', '#34495e', '👃'),
            ('EtCO2', 'etco2', 'mmHg', '#e67e22', '💨')
        ]
        
        # Create grid layout
        self.parameter_cards = {}
        for i, (name, key, unit, color, icon) in enumerate(parameters):
            row = i // 4
            col = i % 4
            
            # Card frame
            card_frame = tk.Frame(parent, bg='white', relief=tk.RAISED, bd=2)
            card_frame.grid(row=row, column=col, padx=10, pady=10, sticky='nsew')
            
            # Configure grid weights
            parent.grid_rowconfigure(row, weight=1)
            parent.grid_columnconfigure(col, weight=1)
            
            # Icon and name
            header_frame = tk.Frame(card_frame, bg=color, height=40)
            header_frame.pack(fill=tk.X)
            header_frame.pack_propagate(False)
            
            tk.Label(header_frame, text=f"{icon} {name}", 
                    font=('Arial', 12, 'bold'), 
                    fg='white', bg=color).pack(expand=True)
            
            # Value display
            value_frame = tk.Frame(card_frame, bg='white', height=80)
            value_frame.pack(fill=tk.BOTH, expand=True)
            value_frame.pack_propagate(False)
            
            value_label = tk.Label(value_frame, text="--", 
                                  font=('Arial', 24, 'bold'), 
                                  fg=color, bg='white')
            value_label.pack(expand=True)
            
            unit_label = tk.Label(value_frame, text=unit, 
                                 font=('Arial', 12), 
                                 fg='gray', bg='white')
            unit_label.pack()
            
            self.parameter_cards[key] = {
                'value_label': value_label,
                'unit_label': unit_label,
                'color': color
            }
    
    def auto_connect(self):
        """Automatically attempt to connect to SDC device."""
        self.connection_thread = threading.Thread(target=self.connect_to_device, daemon=True)
        self.connection_thread.start()
        
    def connect_to_device(self):
        """Connect to SDC device in background thread."""
        try:
            self.root.after(0, lambda: self.status_label.config(text="Searching for device...", fg="orange"))
            
            # Initialize discovery
            self.discovery = WSDiscoverySingleAdapter(self.network_adapter)
            self.discovery.start()
            
            # Load SSL context
            ssl_context = certloader.mk_ssl_contexts_from_folder(
                ca_folder=os.path.join(os.getcwd(), "ssl/"),
                ssl_passwd='dummypass'
            )
            
            # Search for devices
            services = self.discovery.search_services(timeout=10)
            
            if not services:
                self.root.after(0, lambda: self.status_label.config(text="No device found", fg="red"))
                self.root.after(0, lambda: self.connect_button.config(text="Retry Connection"))
                return
            
            # Connect to first found service
            service = services[0]
            self.root.after(0, lambda: self.status_label.config(text="Connecting...", fg="orange"))
            
            # Create consumer
            self.consumer = SdcConsumer.from_wsd_service(service, ssl_context_container=ssl_context)
            self.consumer.start_all()
            
            self.device_found = True
            self.running = True
            self.monitoring_active = True
            
            self.root.after(0, lambda: self.status_label.config(text="Connected - Monitoring", fg="green"))
            self.root.after(0, lambda: self.connect_button.config(text="Disconnect"))
            
            # Start monitoring loop
            self.monitor_data()
            
        except Exception as e:
            error_msg = f"Connection failed: {str(e)[:30]}..."
            self.root.after(0, lambda: self.status_label.config(text=error_msg, fg="red"))
            self.root.after(0, lambda: self.connect_button.config(text="Retry Connection"))
            
    def monitor_data(self):
        """Continuously monitor data from the device."""
        while self.running and self.monitoring_active:
            try:
                self.collect_data()
                time.sleep(1)  # Update every second
            except Exception as e:
                print(f"Monitoring error: {e}")
                time.sleep(5)  # Wait before retrying
                
    def collect_data(self):
        """Collect data from the SDC consumer."""
        if not self.consumer or not hasattr(self.consumer, 'mdib') or not self.consumer.mdib:
            return
            
        try:
            mdib = self.consumer.mdib
            
            # Mapping of our keys to SDC handles
            metrics = {
                'hr': 'hr',
                'map': 'map', 
                'sap': 'sap',
                'dap': 'dap',
                'temperature': 'temperature',
                'sao2': 'sao2',
                'rr': 'rr',
                'etco2': 'etco2'
            }
            
            new_values = {}
            for key, handle in metrics.items():
                try:
                    # Try to get the metric state
                    states = [s for s in mdib.states.objects if hasattr(s, 'DescriptorHandle') and s.DescriptorHandle == handle]
                    if states:
                        state = states[0]
                        if hasattr(state, 'MetricValue') and state.MetricValue and state.MetricValue.Value is not None:
                            new_values[key] = float(state.MetricValue.Value)
                        else:
                            new_values[key] = self.current_values[key]
                    else:
                        new_values[key] = self.current_values[key]
                except Exception as e:
                    print(f"Error getting {key}: {e}")
                    new_values[key] = self.current_values[key]
            
            # Update current values and GUI
            self.current_values.update(new_values)
            self.root.after(0, self.update_display)
            
        except Exception as e:
            print(f"Error collecting data: {e}")
            
    def update_display(self):
        """Update the GUI display with current values."""
        # Update parameter cards
        for key, card in self.parameter_cards.items():
            value = self.current_values[key]
            if key == 'temperature':
                display_value = f"{value:.1f}"
            else:
                display_value = f"{value:.0f}"
            card['value_label'].config(text=display_value)
        
        # Update timestamp
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.config(text=f"Last update: {current_time}")
        
    def start_demo_mode(self):
        """Start demo mode with simulated data."""
        self.status_label.config(text="Demo Mode - No SDC libraries", fg="blue")
        self.connect_button.config(text="Demo Mode", state='disabled')
        self.monitoring_active = True
        
        # Start demo data generation
        self.demo_thread = threading.Thread(target=self.generate_demo_data, daemon=True)
        self.demo_thread.start()
        
    def generate_demo_data(self):
        """Generate demo data for testing."""
        import random
        import math
        
        time_counter = 0
        while self.monitoring_active:
            try:
                # Generate realistic simulated data
                time_counter += 1
                
                # Heart rate with some variation
                self.current_values['hr'] = 70 + 10 * math.sin(time_counter * 0.1) + random.uniform(-5, 5)
                
                # Blood pressures
                base_systolic = 120 + 15 * math.sin(time_counter * 0.05)
                self.current_values['sap'] = base_systolic + random.uniform(-10, 10)
                self.current_values['dap'] = base_systolic * 0.67 + random.uniform(-5, 5)
                self.current_values['map'] = (self.current_values['sap'] + 2 * self.current_values['dap']) / 3
                
                # Temperature with small variations
                self.current_values['temperature'] = 37.0 + 0.5 * math.sin(time_counter * 0.02) + random.uniform(-0.2, 0.2)
                
                # SpO2
                self.current_values['sao2'] = 98 + 2 * math.sin(time_counter * 0.03) + random.uniform(-1, 1)
                
                # Respiratory rate
                self.current_values['rr'] = 16 + 3 * math.sin(time_counter * 0.08) + random.uniform(-2, 2)
                
                # EtCO2
                self.current_values['etco2'] = 35 + 5 * math.sin(time_counter * 0.06) + random.uniform(-2, 2)
                
                # Update display
                self.root.after(0, self.update_display)
                
                time.sleep(1)
                
            except Exception as e:
                print(f"Demo data error: {e}")
                time.sleep(1)
                
    def toggle_connection(self):
        """Toggle connection to device."""
        if not self.device_found:
            if SDC_AVAILABLE:
                self.auto_connect()
            else:
                messagebox.showinfo("Info", "SDC libraries not available. Running in demo mode.")
        else:
            self.disconnect_device()
            
    def disconnect_device(self):
        """Disconnect from device."""
        self.running = False
        self.monitoring_active = False
        self.device_found = False
        
        if self.consumer:
            try:
                self.consumer.stop_all()
            except:
                pass
        
        if self.discovery:
            try:
                self.discovery.stop()
            except:
                pass
                
        self.status_label.config(text="Disconnected", fg="red")
        self.connect_button.config(text="Connect to Device")
        
    def manual_refresh(self):
        """Manually refresh data."""
        if self.device_found:
            threading.Thread(target=self.collect_data, daemon=True).start()
        
    def on_closing(self):
        """Handle application closing."""
        self.monitoring_active = False
        self.running = False
        
        if self.consumer:
            try:
                self.consumer.stop_all()
            except:
                pass
                
        if self.discovery:
            try:
                self.discovery.stop()
            except:
                pass
                
        self.root.quit()
        self.root.destroy()

def main():
    """Main function to run the monitor application."""
    parser = argparse.ArgumentParser(description="Digital Twin Data Monitor")
    parser.add_argument('--adapter', default='en0', help="Network adapter to use (default: en0)")
    args = parser.parse_args()
    
    root = tk.Tk()
    app = SimpleDigitalTwinMonitor(root, network_adapter=args.adapter)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_closing()

if __name__ == "__main__":
    main()
