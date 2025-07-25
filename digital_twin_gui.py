#!/usr/bin/env python3
"""
Digital Twin Monitoring GUI
Real-time visualization of physiological parameters from the SDC provider.
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import numpy as np
from collections import deque
from datetime import datetime, timedelta
import threading
import time
import argparse

# SDC Consumer imports
from sdc11073.consumer import SdcConsumer
from sdc11073.wsdiscovery import WSDiscoverySingleAdapter
from sdc11073 import certloader

class DigitalTwinGUI:
    def __init__(self, root, network_adapter='en0'):
        self.root = root
        self.root.title("Digital Twin Monitoring Dashboard")
        self.root.geometry("1400x900")
        
        # Network adapter for discovery
        self.network_adapter = network_adapter
        
        # Data storage for plotting (last 100 data points)
        self.max_points = 100
        self.timestamps = deque(maxlen=self.max_points)
        self.hr_data = deque(maxlen=self.max_points)
        self.map_data = deque(maxlen=self.max_points)
        self.sap_data = deque(maxlen=self.max_points)
        self.dap_data = deque(maxlen=self.max_points)
        self.temp_data = deque(maxlen=self.max_points)
        self.sao2_data = deque(maxlen=self.max_points)
        self.rr_data = deque(maxlen=self.max_points)
        self.etco2_data = deque(maxlen=self.max_points)
        
        # Current values for display
        self.current_values = {
            'hr': 0.0,
            'map': 0.0,
            'sap': 0.0,
            'dap': 0.0,
            'temperature': 37.0,
            'sao2': 98.0,
            'rr': 16.0,
            'etco2': 35.0
        }
        
        # SDC Consumer
        self.consumer = None
        self.device_found = False
        self.running = False
        
        # Create GUI
        self.create_widgets()
        self.setup_plots()
        
        # Start data collection
        self.start_data_collection()
        
    def create_widgets(self):
        """Create the main GUI widgets."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Digital Twin Monitoring Dashboard", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 10))
        
        # Status frame
        status_frame = ttk.LabelFrame(main_frame, text="Connection Status", padding="5")
        status_frame.grid(row=0, column=2, sticky="wen", padx=(10, 0))
        
        self.status_label = ttk.Label(status_frame, text="Searching for device...", 
                                     foreground="orange")
        self.status_label.pack()
        
        # Current values frame
        values_frame = ttk.LabelFrame(main_frame, text="Current Values", padding="10")
        values_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        
        # Create value display labels
        self.value_labels = {}
        parameters = [
            ('Heart Rate', 'hr', 'bpm'),
            ('Mean ABP', 'map', 'mmHg'),
            ('Systolic BP', 'sap', 'mmHg'),
            ('Diastolic BP', 'dap', 'mmHg'),
            ('Temperature', 'temperature', '°C'),
            ('SpO2', 'sao2', '%'),
            ('Resp. Rate', 'rr', 'bpm'),
            ('EtCO2', 'etco2', 'mmHg')
        ]
        
        for i, (label, key, unit) in enumerate(parameters):
            # Parameter name
            ttk.Label(values_frame, text=f"{label}:", font=('Arial', 10, 'bold')).grid(
                row=i, column=0, sticky=tk.W, pady=2)
            
            # Value label
            value_label = ttk.Label(values_frame, text=f"-- {unit}", 
                                   font=('Arial', 12), foreground="blue")
            value_label.grid(row=i, column=1, sticky=tk.W, padx=(10, 0), pady=2)
            self.value_labels[key] = (value_label, unit)
        
        # Plots frame
        plots_frame = ttk.Frame(main_frame)
        plots_frame.grid(row=1, column=1, columnspan=2, sticky="nsew")
        plots_frame.columnconfigure(0, weight=1)
        plots_frame.rowconfigure(0, weight=1)
        
        # Create matplotlib figure
        self.fig, self.axes = plt.subplots(2, 2, figsize=(12, 8))
        self.fig.suptitle('Real-time Physiological Monitoring', fontsize=14, fontweight='bold')
        
        # Embed plots in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, plots_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        
        # Control buttons frame
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, columnspan=3, pady=(10, 0))
        
        self.start_button = ttk.Button(control_frame, text="Start Monitoring", 
                                      command=self.toggle_monitoring)
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(control_frame, text="Clear Data", 
                  command=self.clear_data).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(control_frame, text="Exit", 
                  command=self.on_closing).pack(side=tk.LEFT)
        
    def setup_plots(self):
        """Setup the matplotlib plots."""
        # Cardiovascular parameters (top-left)
        self.axes[0, 0].set_title('Cardiovascular Parameters')
        self.axes[0, 0].set_ylabel('Pressure (mmHg) / HR (bpm)')
        self.hr_line, = self.axes[0, 0].plot([], [], 'r-', label='Heart Rate', linewidth=2)
        self.map_line, = self.axes[0, 0].plot([], [], 'b-', label='Mean ABP', linewidth=2)
        self.sap_line, = self.axes[0, 0].plot([], [], 'g-', label='Systolic BP', linewidth=2)
        self.dap_line, = self.axes[0, 0].plot([], [], 'm-', label='Diastolic BP', linewidth=2)
        self.axes[0, 0].legend(loc='upper right', fontsize=8)
        self.axes[0, 0].grid(True, alpha=0.3)
        
        # Temperature (top-right)
        self.axes[0, 1].set_title('Body Temperature')
        self.axes[0, 1].set_ylabel('Temperature (°C)')
        self.temp_line, = self.axes[0, 1].plot([], [], 'orange', linewidth=2)
        self.axes[0, 1].grid(True, alpha=0.3)
        self.axes[0, 1].set_ylim(35, 42)
        
        # Respiratory parameters (bottom-left)
        self.axes[1, 0].set_title('Respiratory Parameters')
        self.axes[1, 0].set_ylabel('SpO2 (%) / RR (bpm)')
        self.axes[1, 0].set_xlabel('Time')
        self.sao2_line, = self.axes[1, 0].plot([], [], 'c-', label='SpO2', linewidth=2)
        self.rr_line, = self.axes[1, 0].plot([], [], 'brown', label='Resp Rate', linewidth=2)
        self.axes[1, 0].legend(loc='upper right', fontsize=8)
        self.axes[1, 0].grid(True, alpha=0.3)
        
        # EtCO2 (bottom-right)
        self.axes[1, 1].set_title('End-tidal CO2')
        self.axes[1, 1].set_ylabel('EtCO2 (mmHg)')
        self.axes[1, 1].set_xlabel('Time')
        self.etco2_line, = self.axes[1, 1].plot([], [], 'purple', linewidth=2)
        self.axes[1, 1].grid(True, alpha=0.3)
        self.axes[1, 1].set_ylim(20, 60)
        
        # Adjust layout
        self.fig.tight_layout()
        
        # Start animation
        self.animation = FuncAnimation(self.fig, self.update_plots, interval=1000, blit=False)
        
    def start_data_collection(self):
        """Start the SDC consumer in a separate thread."""
        self.data_thread = threading.Thread(target=self.sdc_consumer_worker, daemon=True)
        self.data_thread.start()
        
    def sdc_consumer_worker(self):
        """Worker function to handle SDC consumer operations."""
        try:
            # Initialize discovery
            self.discovery = WSDiscoverySingleAdapter(self.network_adapter)
            self.discovery.start()
            
            # Load SSL context
            ssl_context = certloader.mk_ssl_contexts_from_folder(
                ca_folder=os.path.join(os.getcwd(), "ssl/"),
                ssl_passwd='dummypass'
            )
            
            # Search for devices
            self.root.after(0, lambda: self.status_label.config(text="Searching for SDC device...", 
                                                               foreground="orange"))
            
            services = self.discovery.search_services(timeout=10)
            
            if not services:
                self.root.after(0, lambda: self.status_label.config(text="No SDC device found", 
                                                                   foreground="red"))
                return
            
            # Connect to first found service
            service = services[0]
            self.root.after(0, lambda: self.status_label.config(text="Connecting to device...", 
                                                               foreground="orange"))
            
            # Create consumer
            self.consumer = SdcConsumer.from_wsd_service(service, ssl_context_container=ssl_context)
            self.consumer.start_all()
            
            self.device_found = True
            self.running = True
            
            self.root.after(0, lambda: self.status_label.config(text="Connected - Monitoring", 
                                                               foreground="green"))
            
            # Start monitoring loop
            while self.running:
                try:
                    self.collect_data()
                    time.sleep(1)  # Update every second
                except Exception as e:
                    print(f"Data collection error: {e}")
                    time.sleep(5)  # Wait before retrying
                    
        except Exception as e:
            print(f"SDC Consumer error: {e}")
            self.root.after(0, lambda: self.status_label.config(text=f"Connection error: {str(e)[:30]}...", 
                                                               foreground="red"))
            
    def collect_data(self):
        """Collect data from the SDC consumer."""
        if not self.consumer or not self.consumer.mdib:
            return
            
        try:
            # Get current MDIB
            mdib = self.consumer.mdib
            
            # Extract metric values
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
                    # Get metric state using the handle
                    states = mdib.states.handle.get(handle, [])
                    if states:
                        state = states[0]  # Get first state
                        if hasattr(state, 'MetricValue') and state.MetricValue and state.MetricValue.Value is not None:
                            new_values[key] = float(state.MetricValue.Value)
                        else:
                            new_values[key] = self.current_values[key]  # Keep previous value
                    else:
                        new_values[key] = self.current_values[key]  # Keep previous value
                except Exception as e:
                    print(f"Error getting {key}: {e}")
                    new_values[key] = self.current_values[key]  # Keep previous value
            
            # Update data storage
            current_time = datetime.now()
            self.timestamps.append(current_time)
            self.hr_data.append(new_values['hr'])
            self.map_data.append(new_values['map'])
            self.sap_data.append(new_values['sap'])
            self.dap_data.append(new_values['dap'])
            self.temp_data.append(new_values['temperature'])
            self.sao2_data.append(new_values['sao2'])
            self.rr_data.append(new_values['rr'])
            self.etco2_data.append(new_values['etco2'])
            
            # Update current values
            self.current_values.update(new_values)
            
            # Update GUI labels
            self.root.after(0, self.update_value_labels)
            
        except Exception as e:
            print(f"Error collecting data: {e}")
            
    def update_value_labels(self):
        """Update the current value labels."""
        for key, (label, unit) in self.value_labels.items():
            value = self.current_values[key]
            if key == 'temperature':
                label.config(text=f"{value:.1f} {unit}")
            else:
                label.config(text=f"{value:.0f} {unit}")
                
    def update_plots(self, frame):
        """Update the matplotlib plots with new data."""
        if len(self.timestamps) < 2:
            return
            
        # Convert timestamps to relative time in minutes
        start_time = self.timestamps[0]
        x_data = [(t - start_time).total_seconds() / 60 for t in self.timestamps]
        
        # Update cardiovascular plot
        self.hr_line.set_data(x_data, list(self.hr_data))
        self.map_line.set_data(x_data, list(self.map_data))
        self.sap_line.set_data(x_data, list(self.sap_data))
        self.dap_line.set_data(x_data, list(self.dap_data))
        
        # Update temperature plot
        self.temp_line.set_data(x_data, list(self.temp_data))
        
        # Update respiratory plot
        self.sao2_line.set_data(x_data, list(self.sao2_data))
        self.rr_line.set_data(x_data, list(self.rr_data))
        
        # Update EtCO2 plot
        self.etco2_line.set_data(x_data, list(self.etco2_data))
        
        # Auto-scale axes
        for ax in self.axes.flat:
            if len(x_data) > 1:
                ax.set_xlim(min(x_data), max(x_data))
                ax.relim()
                ax.autoscale_view(scalex=False)
        
        # Update x-axis labels to show time
        for ax in [self.axes[1, 0], self.axes[1, 1]]:
            ax.set_xlabel(f'Time (minutes from {start_time.strftime("%H:%M:%S")})')
            
        self.canvas.draw_idle()
        
    def toggle_monitoring(self):
        """Toggle monitoring on/off."""
        if self.running:
            self.running = False
            self.start_button.config(text="Start Monitoring")
        else:
            self.running = True
            self.start_button.config(text="Stop Monitoring")
            
    def clear_data(self):
        """Clear all collected data."""
        self.timestamps.clear()
        self.hr_data.clear()
        self.map_data.clear()
        self.sap_data.clear()
        self.dap_data.clear()
        self.temp_data.clear()
        self.sao2_data.clear()
        self.rr_data.clear()
        self.etco2_data.clear()
        
        # Clear plots
        for ax in self.axes.flat:
            ax.clear()
        self.setup_plots()
        
    def on_closing(self):
        """Handle application closing."""
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
    """Main function to run the GUI application."""
    parser = argparse.ArgumentParser(description="Digital Twin Monitoring GUI")
    parser.add_argument('--adapter', default='en0', help="Network adapter to use (default: en0)")
    args = parser.parse_args()
    
    root = tk.Tk()
    app = DigitalTwinGUI(root, network_adapter=args.adapter)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_closing()

if __name__ == "__main__":
    main()
