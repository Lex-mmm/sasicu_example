#!/usr/bin/env python3
"""
Digital Twin Launcher
Launch both the provider and monitoring GUI for the digital twin system.

Copyright (c) 2025 Dr. L.M. van Loon. All Rights Reserved.

This software is for academic research and educational purposes only.
Commercial use is strictly prohibited without explicit written permission
from Dr. L.M. van Loon.

For commercial licensing inquiries, contact Dr. L.M. van Loon.
"""

import sys
import os
import subprocess
import argparse
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import glob

class DigitalTwinLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("Digital Twin System Launcher - © Dr. L.M. van Loon")
        self.root.geometry("800x700")  # Made taller for patient selection
        
        # Process tracking
        self.provider_process = None
        self.direct_process = None
        
        # Get available patients
        self.available_patients = self.get_available_patients()
        
        # Create GUI
        self.create_widgets()
        
    def get_available_patients(self):
        """Get list of available patient parameter files."""
        patients = []
        
        # Add all JSON files containing "Flat" from main folder
        main_folder = os.getcwd()
        flat_files = glob.glob(os.path.join(main_folder, "*Flat*.json"))
        for file_path in sorted(flat_files):
            filename = os.path.basename(file_path)
            # Create a nice display name
            display_name = filename.replace('.json', '').replace('Flat', '').replace('flat', '')
            
            # Handle specific cases for better readability
            if 'healthy' in display_name.lower():
                display_name = "Healthy Patient (Default)"
            elif 'heartfailure' in display_name.lower():
                display_name = "Heart Failure Patient"
            elif 'hypotension' in display_name.lower():
                display_name = "Hypotension Patient"
            else:
                # General case: capitalize and clean up
                display_name = display_name.replace('_', ' ').title()
                if not display_name.startswith('Patient'):
                    display_name = f"Patient {display_name}"
            
            patients.append((display_name, filename))
        
        # Add all JSON files containing "Flat" from MDTparameters folder
        mdt_folder = os.path.join(os.getcwd(), "MDTparameters")
        if os.path.exists(mdt_folder):
            flat_files = glob.glob(os.path.join(mdt_folder, "*Flat*.json"))
            for file_path in sorted(flat_files):
                filename = os.path.basename(file_path)
                # Create a nice display name
                display_name = filename.replace('.json', '').replace('_', ' ').title()
                if not display_name.startswith('Patient'):
                    display_name = f"Patient {display_name}"
                relative_path = os.path.join("MDTparameters", filename)
                patients.append((display_name, relative_path))
        
        # Add other patients from MDTparameters folder (non-Flat files)
        if os.path.exists(mdt_folder):
            other_files = glob.glob(os.path.join(mdt_folder, "*.json"))
            for file_path in sorted(other_files):
                filename = os.path.basename(file_path)
                # Skip if already added (contains Flat)
                if "Flat" in filename:
                    continue
                # Create a nice display name
                display_name = filename.replace('.json', '').replace('_', ' ').title()
                if not display_name.startswith('Patient'):
                    display_name = f"Patient {display_name}"
                relative_path = os.path.join("MDTparameters", filename)
                patients.append((display_name, relative_path))
        
        # If no files found, add default fallback
        if not patients:
            patients.append(("Healthy Patient (Default)", "healthyFlat.json"))
        
        return patients
        
    def create_widgets(self):
        """Create the launcher GUI widgets."""
        # Title
        title_frame = tk.Frame(self.root, bg='#34495e', height=60)
        title_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(title_frame, text="Digital Twin System Launcher", 
                              font=('Arial', 18, 'bold'), 
                              fg='white', bg='#34495e')
        title_label.pack(expand=True)
        
        # Main content frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Provider section
        provider_frame = tk.LabelFrame(main_frame, text="SDC Provider (Digital Twin)", 
                                      font=('Arial', 12, 'bold'), padx=10, pady=10)
        provider_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(provider_frame, text="Starts the digital twin simulation and SDC provider", 
                font=('Arial', 10)).pack(anchor=tk.W)
        
        provider_button_frame = tk.Frame(provider_frame)
        provider_button_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.provider_button = tk.Button(provider_button_frame, text="Start Provider", 
                                        command=self.toggle_provider,
                                        bg='#27ae60', fg='white', font=('Arial', 11),
                                        relief=tk.FLAT, padx=20, pady=5)
        self.provider_button.pack(side=tk.LEFT)
        
        self.provider_status = tk.Label(provider_button_frame, text="Stopped", 
                                       fg='red', font=('Arial', 10))
        self.provider_status.pack(side=tk.LEFT, padx=(20, 0))
        
        # Monitor section
        monitor_frame = tk.LabelFrame(main_frame, text="Digital Twin Monitor", 
                                     font=('Arial', 12, 'bold'), padx=10, pady=10)
        monitor_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(monitor_frame, text="Real-time visualization of digital twin physiological data", 
                font=('Arial', 10)).pack(anchor=tk.W)
        tk.Label(monitor_frame, text="• Direct access to digital twin model (no SDC required)", 
                font=('Arial', 9), fg='gray').pack(anchor=tk.W, padx=20)
        tk.Label(monitor_frame, text="• Displays all parameters: HR, ABP, Temperature, SpO2, RR, EtCO2", 
                font=('Arial', 9), fg='gray').pack(anchor=tk.W, padx=20)
        tk.Label(monitor_frame, text="• Real-time parameter adjustment: TBV, HR, Pressure, Respiratory Rate", 
                font=('Arial', 9), fg='gray').pack(anchor=tk.W, padx=20)
        
        # Patient selection
        patient_selection_frame = tk.Frame(monitor_frame)
        patient_selection_frame.pack(fill=tk.X, pady=(10, 5))
        
        tk.Label(patient_selection_frame, text="Patient:", 
                font=('Arial', 11, 'bold')).pack(side=tk.LEFT)
        
        self.patient_var = tk.StringVar()
        patient_options = [display_name for display_name, _ in self.available_patients]
        
        self.patient_dropdown = ttk.Combobox(patient_selection_frame, textvariable=self.patient_var,
                                           values=patient_options, state="readonly",
                                           font=('Arial', 10), width=35)
        self.patient_dropdown.pack(side=tk.LEFT, padx=(10, 0))
        
        # Set default selection
        if patient_options:
            self.patient_dropdown.set(patient_options[0])
        
        # Patient info display
        self.patient_info_label = tk.Label(patient_selection_frame, text="", 
                                          font=('Arial', 9), 
                                          fg='#7f8c8d')
        self.patient_info_label.pack(side=tk.LEFT, padx=(15, 0))
        
        monitor_button_frame = tk.Frame(monitor_frame)
        monitor_button_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.direct_button = tk.Button(monitor_button_frame, text="Start Monitor", 
                                      command=self.toggle_direct_monitor,
                                      bg='#27ae60', fg='white', font=('Arial', 11),
                                      relief=tk.FLAT, padx=20, pady=5)
        self.direct_button.pack(side=tk.LEFT)
        
        self.direct_status = tk.Label(monitor_button_frame, text="Stopped", 
                                     fg='red', font=('Arial', 10))
        self.direct_status.pack(side=tk.LEFT, padx=(20, 0))
        
        # Network adapter selection
        network_frame = tk.LabelFrame(main_frame, text="Network Configuration", 
                                     font=('Arial', 12, 'bold'), padx=10, pady=10)
        network_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(network_frame, text="Network Adapter:", 
                font=('Arial', 10)).pack(side=tk.LEFT)
        
        self.adapter_var = tk.StringVar(value="en0")
        adapter_entry = tk.Entry(network_frame, textvariable=self.adapter_var, 
                                font=('Arial', 10), width=10)
        adapter_entry.pack(side=tk.LEFT, padx=(10, 0))
        
        tk.Label(network_frame, text="(e.g., en0, eth0, wlan0)", 
                font=('Arial', 9), fg='gray').pack(side=tk.LEFT, padx=(10, 0))
        
        # Quick start section
        quick_frame = tk.LabelFrame(main_frame, text="Quick Start", 
                                   font=('Arial', 12, 'bold'), padx=10, pady=10)
        quick_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Button(quick_frame, text="Start Provider + Monitor", 
                 command=self.start_both,
                 bg='#e67e22', fg='white', font=('Arial', 12, 'bold'),
                 relief=tk.FLAT, padx=30, pady=8).pack(side=tk.LEFT)
        
        tk.Button(quick_frame, text="Monitor Only", 
                 command=self.start_monitor_only,
                 bg='#27ae60', fg='white', font=('Arial', 12, 'bold'),
                 relief=tk.FLAT, padx=30, pady=8).pack(side=tk.LEFT, padx=(10, 0))
        
        tk.Button(quick_frame, text="Stop All", 
                 command=self.stop_all,
                 bg='#e74c3c', fg='white', font=('Arial', 12),
                 relief=tk.FLAT, padx=30, pady=8).pack(side=tk.RIGHT)
        
        # Log output
        log_frame = tk.LabelFrame(main_frame, text="System Log", 
                                 font=('Arial', 12, 'bold'), padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Copyright footer
        footer_frame = tk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, pady=(5, 0))
        
        tk.Label(footer_frame, text="© 2025 Dr. L.M. van Loon - Academic/Educational Use Only", 
                font=('Arial', 8), fg='gray').pack()
        
        # Add initial log message
        self.log("Digital Twin System Launcher initialized")
        self.log("Ready to start provider and monitor")
        
    def log(self, message):
        """Add a message to the log output."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        
    def toggle_provider(self):
        """Toggle the provider process."""
        if self.provider_process is None:
            self.start_provider()
        else:
            self.stop_provider()
            
    def start_provider(self):
        """Start the SDC provider process."""
        try:
            adapter = self.adapter_var.get()
            cmd = [sys.executable, "provider_MDT.py", "--adapter", adapter]
            
            self.log(f"Starting provider with adapter: {adapter}")
            self.provider_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                cwd=os.getcwd()
            )
            
            self.provider_button.config(text="Stop Provider", bg='#e74c3c')
            self.provider_status.config(text="Running", fg='green')
            self.log("Provider started successfully")
            
            # Start monitoring provider output
            threading.Thread(target=self.monitor_provider_output, daemon=True).start()
            
        except Exception as e:
            self.log(f"Error starting provider: {e}")
            messagebox.showerror("Error", f"Failed to start provider: {e}")
            
    def stop_provider(self):
        """Stop the SDC provider process."""
        if self.provider_process:
            try:
                self.provider_process.terminate()
                self.provider_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.provider_process.kill()
            except Exception as e:
                self.log(f"Error stopping provider: {e}")
            
            self.provider_process = None
            self.provider_button.config(text="Start Provider", bg='#27ae60')
            self.provider_status.config(text="Stopped", fg='red')
            self.log("Provider stopped")
            
    def monitor_provider_output(self):
        """Monitor and log provider output."""
        try:
            while self.provider_process and self.provider_process.poll() is None:
                if self.provider_process.stdout:
                    line = self.provider_process.stdout.readline()
                    if line:
                        self.log(f"Provider: {line.strip()}")
                else:
                    time.sleep(0.1)
        except Exception as e:
            self.log(f"Error monitoring provider: {e}")
            
    def toggle_direct_monitor(self):
        """Toggle the direct monitor process."""
        if self.direct_process is None:
            self.start_direct_monitor()
        else:
            self.stop_direct_monitor()
            
    def start_direct_monitor(self):
        """Start the direct data monitor GUI."""
        try:
            # Get selected patient file
            selected_display_name = self.patient_var.get()
            selected_file = None
            for display_name, file_path in self.available_patients:
                if display_name == selected_display_name:
                    selected_file = file_path
                    break
            
            if not selected_file:
                messagebox.showerror("Error", "Please select a patient file")
                return
            
            cmd = [sys.executable, "direct_monitor.py", "--patient", selected_file]
            
            self.log(f"Starting direct monitor with patient: {selected_display_name}")
            self.log(f"Using parameter file: {selected_file}")
            self.direct_process = subprocess.Popen(
                cmd,
                cwd=os.getcwd()
            )
            
            self.direct_button.config(text="Stop Monitor", bg='#e74c3c')
            self.direct_status.config(text="Running", fg='green')
            self.log("Direct monitor started successfully")
            
            # Check if direct monitor is still running
            threading.Thread(target=self.check_direct_monitor_status, daemon=True).start()
            
        except Exception as e:
            self.log(f"Error starting direct monitor: {e}")
            messagebox.showerror("Error", f"Failed to start direct monitor: {e}")
            
    def stop_direct_monitor(self):
        """Stop the direct data monitor GUI."""
        if self.direct_process:
            try:
                self.direct_process.terminate()
                self.direct_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.direct_process.kill()
            except Exception as e:
                self.log(f"Error stopping direct monitor: {e}")
            
            self.direct_process = None
            self.direct_button.config(text="Start Monitor", bg='#27ae60')
            self.direct_status.config(text="Stopped", fg='red')
            self.log("Direct monitor stopped")
            
    def check_direct_monitor_status(self):
        """Check if direct monitor process is still running."""
        while self.direct_process:
            if self.direct_process.poll() is not None:
                # Process has terminated
                self.direct_process = None
                self.root.after(0, lambda: self.direct_button.config(text="Start Monitor", bg='#27ae60'))
                self.root.after(0, lambda: self.direct_status.config(text="Stopped", fg='red'))
                self.root.after(0, lambda: self.log("Direct monitor process ended"))
                break
            time.sleep(1)
            
    def start_monitor_only(self):
        """Start only the direct monitor (no provider needed)."""
        if self.direct_process is None:
            self.start_direct_monitor()
            
    def start_both(self):
        """Start both provider and direct monitor."""
        if self.provider_process is None:
            self.start_provider()
            
        # Wait a moment for provider to start
        time.sleep(2)
        
        if self.direct_process is None:
            self.start_direct_monitor()
            
    def stop_all(self):
        """Stop all processes."""
        self.stop_provider()
        self.stop_direct_monitor()
        self.log("All processes stopped")
        
    def on_closing(self):
        """Handle application closing."""
        self.stop_all()
        self.root.quit()
        self.root.destroy()

def main():
    """Main function to run the launcher."""
    parser = argparse.ArgumentParser(description="Digital Twin System Launcher")
    args = parser.parse_args()
    
    root = tk.Tk()
    app = DigitalTwinLauncher(root)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_closing()

if __name__ == "__main__":
    main()
