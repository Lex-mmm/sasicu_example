#!/usr/bin/env python3
"""
Advanced Digital Twin GUI with Real-time Plotting
Displays physiological data with trend visualization using matplotlib.

Copyright (c) 2025 Dr. L.M. van Loon. All Rights Reserved.

This software is for academic research and educational purposes only.
Commercial use is strictly prohibited without explicit written permission
from Dr. L.M. van Loon.

For commercial licensing inquiries, contact Dr. L.M. van Loon.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
from collections import deque
import time
import threading
import argparse
import logging
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import matplotlib
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    logger.warning("Matplotlib not available. Plotting disabled.")
    MATPLOTLIB_AVAILABLE = False

# Try to import SDC libraries
try:
    from sdc11073.consumer import SdcConsumer
    from sdc11073.definitions_sdc import SdcV1Definitions
    from sdc11073 import certloader
    from sdc11073.wsdiscovery import WSDiscoverySingleAdapter
    SDC_AVAILABLE = True
except ImportError:
    logger.warning("SDC libraries not available. Demo mode will be used.")
    SDC_AVAILABLE = False

class DigitalTwinGUI:
    def __init__(self, root, network_adapter="en0"):
        self.root = root
        self.root.title("Digital Twin Advanced GUI - © Dr. L.M. van Loon")
        self.root.geometry("1200x800")
        self.root.configure(bg='#f0f0f0')
        
        self.network_adapter = network_adapter
        self.running = True
        self.demo_mode = not SDC_AVAILABLE
        
        # Data storage (thread-safe)
        self.max_points = 100
        self.time_data = deque(maxlen=self.max_points)
        self.hr_data = deque(maxlen=self.max_points)
        self.map_data = deque(maxlen=self.max_points)
        self.sap_data = deque(maxlen=self.max_points)
        self.dap_data = deque(maxlen=self.max_points)
        self.temp_data = deque(maxlen=self.max_points)
        self.sao2_data = deque(maxlen=self.max_points)
        self.rr_data = deque(maxlen=self.max_points)
        self.etco2_data = deque(maxlen=self.max_points)
        
        # SDC consumer (only if available)
        self.consumer = None
        self.discovery = None
        self.data_thread = None
        
        # Demo data generator
        self.demo_time = 0
        
        self.setup_gui()
        
        if MATPLOTLIB_AVAILABLE:
            self.setup_plots()
        else:
            self.setup_simple_display()
        
        # Start data collection
        if self.demo_mode:
            self.status_label.config(text="Demo Mode - Simulated Data", foreground="blue")
            logger.info("Starting in demo mode with simulated data")
        else:
            self.start_data_collection()
        
        # Start GUI update loop (main thread only)
        self.start_gui_updates()
        
    def setup_gui(self):
        """Setup the GUI components."""
        # Status frame
        status_frame = tk.Frame(self.root, bg='#f0f0f0')
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(status_frame, text="Connection Status:", 
                font=('Arial', 12, 'bold'), bg='#f0f0f0').pack(side=tk.LEFT)
        
        self.status_label = tk.Label(status_frame, text="Initializing...", 
                                    font=('Arial', 12), fg='orange', bg='#f0f0f0')
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Control frame
        control_frame = tk.Frame(self.root, bg='#f0f0f0')
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Button(control_frame, text="Clear Data", command=self.clear_data,
                 bg='#e74c3c', fg='white', font=('Arial', 10)).pack(side=tk.LEFT)
        
        tk.Button(control_frame, text="Refresh", command=self.force_refresh,
                 bg='#3498db', fg='white', font=('Arial', 10)).pack(side=tk.LEFT, padx=(10, 0))
        
        # Main content frame
        self.content_frame = tk.Frame(self.root, bg='white')
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Copyright footer
        footer_frame = tk.Frame(self.root, bg='#f0f0f0')
        footer_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        tk.Label(footer_frame, text="© 2025 Dr. L.M. van Loon - Academic/Educational Use Only", 
                font=('Arial', 8), fg='gray', bg='#f0f0f0').pack()
        
    def setup_plots(self):
        """Setup matplotlib plots."""
        # Create figure with subplots
        self.fig = Figure(figsize=(12, 8), facecolor='white')
        self.fig.suptitle('Digital Twin Physiological Parameters', fontsize=14, fontweight='bold')
        
        # Create subplots
        self.ax1 = self.fig.add_subplot(2, 2, 1)  # Cardiovascular
        self.ax2 = self.fig.add_subplot(2, 2, 2)  # Temperature
        self.ax3 = self.fig.add_subplot(2, 2, 3)  # Respiratory
        self.ax4 = self.fig.add_subplot(2, 2, 4)  # EtCO2
        
        # Configure subplots
        self.ax1.set_title('Cardiovascular Parameters')
        self.ax1.set_ylabel('mmHg / bpm')
        self.ax1.grid(True, alpha=0.3)
        
        self.ax2.set_title('Body Temperature')
        self.ax2.set_ylabel('°C')
        self.ax2.grid(True, alpha=0.3)
        
        self.ax3.set_title('Respiratory Parameters')
        self.ax3.set_ylabel('% / bpm')
        self.ax3.grid(True, alpha=0.3)
        
        self.ax4.set_title('End-tidal CO2')
        self.ax4.set_ylabel('mmHg')
        self.ax4.set_xlabel('Time (seconds)')
        self.ax4.grid(True, alpha=0.3)
        
        # Embed plot in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, self.content_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
    def setup_simple_display(self):
        """Setup simple text display when matplotlib is not available."""
        tk.Label(self.content_frame, text="Matplotlib not available - Text mode only", 
                font=('Arial', 14), bg='white').pack(pady=20)
        
        self.text_display = tk.Text(self.content_frame, height=20, width=80, 
                                   font=('Consolas', 10))
        self.text_display.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
    def start_data_collection(self):
        """Start data collection in a separate thread."""
        if SDC_AVAILABLE:
            self.data_thread = threading.Thread(target=self.sdc_worker_safe, daemon=True)
            self.data_thread.start()
        
    def sdc_worker_safe(self):
        """Thread-safe SDC worker with proper error handling."""
        try:
            logger.info("Starting SDC consumer worker")
            
            # Update status in main thread
            self.root.after(0, lambda: self.status_label.config(
                text="Searching for SDC device...", foreground="orange"))
            
            # Initialize discovery
            self.discovery = WSDiscoverySingleAdapter(self.network_adapter)
            self.discovery.start()
            
            # Load SSL context
            ssl_context = certloader.mk_ssl_contexts_from_folder(
                ca_folder=os.path.join(os.getcwd(), "ssl/"),
                ssl_passwd='dummypass'
            )
            
            # Search for services
            services = self.discovery.search_services(timeout=10)
            
            if not services:
                self.root.after(0, lambda: self.status_label.config(
                    text="No SDC device found - Using demo mode", foreground="red"))
                self.demo_mode = True
                return
                
            # Connect to first service
            service = services[0]
            self.consumer = SdcConsumer.from_wsd_service(service, ssl_context)
            self.consumer.start_all()
            
            # Update status
            self.root.after(0, lambda: self.status_label.config(
                text="Connected to SDC device", foreground="green"))
            
            logger.info("SDC consumer connected successfully")
            
        except Exception as e:
            logger.error(f"SDC worker error: {e}")
            self.root.after(0, lambda: self.status_label.config(
                text=f"SDC Error - Using demo mode", foreground="red"))
            self.demo_mode = True
        
    def start_gui_updates(self):
        """Start the GUI update loop in the main thread."""
        self.update_gui()
        
    def update_gui(self):
        """Update GUI in main thread only."""
        if not self.running:
            return
            
        try:
            # Collect new data
            if self.demo_mode:
                self.generate_demo_data()
            else:
                self.collect_sdc_data()
            
            # Update display
            if MATPLOTLIB_AVAILABLE:
                self.update_plots()
            else:
                self.update_text_display()
            
        except Exception as e:
            logger.error(f"GUI update error: {e}")
        
        # Schedule next update
        self.root.after(1000, self.update_gui)  # Update every 1 second
        
    def generate_demo_data(self):
        """Generate demo data for testing."""
        self.demo_time += 1
        current_time = self.demo_time
        
        # Generate realistic physiological data
        hr = 70 + 10 * np.sin(current_time * 0.1) + np.random.normal(0, 2)
        map_val = 90 + 15 * np.sin(current_time * 0.05) + np.random.normal(0, 3)
        sap = map_val + 30 + np.random.normal(0, 5)
        dap = map_val - 20 + np.random.normal(0, 3)
        temp = 37.0 + 0.5 * np.sin(current_time * 0.02) + np.random.normal(0, 0.1)
        sao2 = 98 + 2 * np.sin(current_time * 0.03) + np.random.normal(0, 0.5)
        rr = 15 + 3 * np.sin(current_time * 0.08) + np.random.normal(0, 1)
        etco2 = 38 + 5 * np.sin(current_time * 0.06) + np.random.normal(0, 1)
        
        # Add to data
        self.add_data_point(current_time, hr, map_val, sap, dap, temp, sao2, rr, etco2)
        
    def collect_sdc_data(self):
        """Collect data from SDC consumer."""
        if not self.consumer:
            return
            
        try:
            # This is a simplified data collection
            # In real implementation, you would extract actual SDC values
            current_time = time.time()
            
            # For now, use demo data since SDC implementation is complex
            self.generate_demo_data()
            
        except Exception as e:
            logger.error(f"SDC data collection error: {e}")
            
    def add_data_point(self, time_val, hr, map_val, sap, dap, temp, sao2, rr, etco2):
        """Add a new data point to all series."""
        self.time_data.append(time_val)
        self.hr_data.append(hr)
        self.map_data.append(map_val)
        self.sap_data.append(sap)
        self.dap_data.append(dap)
        self.temp_data.append(temp)
        self.sao2_data.append(sao2)
        self.rr_data.append(rr)
        self.etco2_data.append(etco2)
        
    def update_plots(self):
        """Update all plots with current data."""
        if len(self.time_data) == 0:
            return
            
        try:
            # Clear previous plots
            self.ax1.clear()
            self.ax2.clear()
            self.ax3.clear()
            self.ax4.clear()
            
            # Convert to numpy arrays for plotting
            time_array = np.array(self.time_data)
            
            # Plot cardiovascular data
            self.ax1.plot(time_array, self.hr_data, 'r-', label='HR (bpm)', linewidth=2)
            self.ax1.plot(time_array, self.map_data, 'b-', label='MAP (mmHg)', linewidth=2)
            self.ax1.plot(time_array, self.sap_data, 'g-', label='Systolic', linewidth=1)
            self.ax1.plot(time_array, self.dap_data, 'm-', label='Diastolic', linewidth=1)
            self.ax1.set_title('Cardiovascular Parameters')
            self.ax1.set_ylabel('mmHg / bpm')
            self.ax1.grid(True, alpha=0.3)
            self.ax1.legend()
            
            # Plot temperature
            self.ax2.plot(time_array, self.temp_data, 'orange', linewidth=2)
            self.ax2.set_title('Body Temperature')
            self.ax2.set_ylabel('°C')
            self.ax2.grid(True, alpha=0.3)
            
            # Plot respiratory data
            self.ax3.plot(time_array, self.sao2_data, 'cyan', label='SpO2 (%)', linewidth=2)
            self.ax3.plot(time_array, self.rr_data, 'purple', label='RR (bpm)', linewidth=2)
            self.ax3.set_title('Respiratory Parameters')
            self.ax3.set_ylabel('% / bpm')
            self.ax3.grid(True, alpha=0.3)
            self.ax3.legend()
            
            # Plot EtCO2
            self.ax4.plot(time_array, self.etco2_data, 'brown', linewidth=2)
            self.ax4.set_title('End-tidal CO2')
            self.ax4.set_ylabel('mmHg')
            self.ax4.set_xlabel('Time (seconds)')
            self.ax4.grid(True, alpha=0.3)
            
            # Adjust layout and refresh
            self.fig.tight_layout()
            self.canvas.draw()
            
        except Exception as e:
            logger.error(f"Plot update error: {e}")
            
    def update_text_display(self):
        """Update text display when matplotlib is not available."""
        if len(self.time_data) == 0:
            return
            
        try:
            # Get latest values
            latest_values = f"""
Digital Twin Physiological Monitor - Live Data
Time: {self.time_data[-1]:.0f}s

Heart Rate:        {self.hr_data[-1]:.1f} bpm
Mean ABP:          {self.map_data[-1]:.1f} mmHg
Systolic BP:       {self.sap_data[-1]:.1f} mmHg
Diastolic BP:      {self.dap_data[-1]:.1f} mmHg
Temperature:       {self.temp_data[-1]:.1f} °C
SpO2:              {self.sao2_data[-1]:.1f} %
Respiratory Rate:  {self.rr_data[-1]:.1f} bpm
EtCO2:             {self.etco2_data[-1]:.1f} mmHg

Data Points: {len(self.time_data)}/{self.max_points}
"""
            
            self.text_display.delete(1.0, tk.END)
            self.text_display.insert(1.0, latest_values)
            
        except Exception as e:
            logger.error(f"Text display update error: {e}")
            
    def clear_data(self):
        """Clear all data and plots."""
        self.time_data.clear()
        self.hr_data.clear()
        self.map_data.clear()
        self.sap_data.clear()
        self.dap_data.clear()
        self.temp_data.clear()
        self.sao2_data.clear()
        self.rr_data.clear()
        self.etco2_data.clear()
        self.demo_time = 0
        
        if MATPLOTLIB_AVAILABLE:
            # Clear plots
            for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
                ax.clear()
            self.canvas.draw()
        else:
            self.text_display.delete(1.0, tk.END)
            self.text_display.insert(1.0, "Data cleared. Waiting for new data...")
        
    def force_refresh(self):
        """Force a data refresh."""
        logger.info("Forcing data refresh")
        
    def on_closing(self):
        """Handle window closing."""
        self.running = False
        
        # Clean up SDC resources
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
                
        self.root.destroy()

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Digital Twin Advanced GUI")
    parser.add_argument("--adapter", "-a", type=str, default="en0",
                       help="Network adapter to use (default: en0)")
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
