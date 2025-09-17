#!/usr/bin/env python3
"""
Direct Digital Twin Monitor
Displays real-time data directly from the digital twin model without SDC.

Copyright (c) 2025 Dr. L.M. van Loon. All Rights Reserved.

This software is for academic research and educational purposes only.
Commercial use is strictly prohibited without explicit written permission
from Dr. L.M. van Loon.

For commercial licensing inquiries, contact Dr. L.M. van Loon.
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
import numpy as np
from scipy.integrate import solve_ivp
import random

# Add current directory to path for imports
sys.path.append(os.getcwd())

try:
    from digital_twin_model import DigitalTwinModel
    print("✓ Digital twin model imported successfully")
except ImportError as e:
    print(f"✗ Failed to import digital twin model: {e}")
    sys.exit(1)

class DirectDigitalTwinMonitor:
    def __init__(self, root, patient_file="healthyFlat.json"):
        self.root = root
        self.root.title("Direct Digital Twin Monitor - © Dr. L.M. van Loon")
        self.root.geometry("1000x650")  # Made shorter since no patient selection
        self.root.configure(bg='#f0f0f0')
        
        # Initialize digital twin model
        self.dt_model = None
        self.current_time = 0
        self.sampling_interval = 2  # seconds
        self.current_patient_file = patient_file  # Use provided patient file
        
        # Get patient display name for title
        self.patient_display_name = self.get_patient_display_name(patient_file)
        
        # Data storage for recent values
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
        
        # Pressure tracking
        self.pressure_buffer = []
        self.max_pressure_window = 50
        
        # Control flags
        self.running = False
        self.simulation_thread = None
        
        # Parameter adjustment variables
        self.parameter_vars = {}
        self.adjustable_parameters = {
            'misc_constants.TBV': {'label': 'Total Blood Volume (mL)', 'min': 3000, 'max': 8000, 'default': 5000},
            'cardio_control_params.HR_n': {'label': 'Nominal Heart Rate (bpm)', 'min': 40, 'max': 150, 'default': 70},
            'initial_conditions.Pset': {'label': 'Pressure Setpoint (mmHg)', 'min': 60, 'max': 140, 'default': 100},
            'respiratory_control_params.RR_0': {'label': 'Baseline Resp. Rate (bpm)', 'min': 8, 'max': 30, 'default': 16}
        }
        
        # Create GUI
        self.create_widgets()
        
        # Initialize digital twin
        self.initialize_digital_twin()
    
    def get_patient_display_name(self, patient_file):
        """Get a nice display name for the patient file."""
        filename = os.path.basename(patient_file)
        display_name = filename.replace('.json', '').replace('Flat', '').replace('flat', '')
        
        # Handle specific cases for better readability
        if 'healthy' in display_name.lower():
            return "Healthy Patient (Default)"
        elif 'heartfailure' in display_name.lower():
            return "Heart Failure Patient"
        elif 'hypotension' in display_name.lower():
            return "Hypotension Patient"
        else:
            # General case: capitalize and clean up
            display_name = display_name.replace('_', ' ').title()
            if not display_name.startswith('Patient'):
                display_name = f"Patient {display_name}"
            return display_name
    
    def update_patient_info(self):
        """Update the patient info display with key parameters."""
        if not self.dt_model:
            return
            
        try:
            # Get some key patient parameters to display
            hr_baseline = self.dt_model.master_parameters.get('cardio_control_params.HR_n', {}).get('value', 'N/A')
            abp_baseline = self.dt_model.master_parameters.get('cardio_control_params.ABP_n', {}).get('value', 'N/A')
            rr_baseline = self.dt_model.master_parameters.get('respiratory_control_params.RR_0', {}).get('value', 'N/A')
            
            self.log_event(f"✓ Patient baseline parameters: HR={hr_baseline}, ABP={abp_baseline}, RR={rr_baseline}")
            
        except Exception as e:
            self.log_event(f"Note: Could not display patient baseline parameters: {e}")
        
    def create_widgets(self):
        """Create the main GUI widgets."""
        # Title
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=70)
        title_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(title_frame, text=f"Direct Digital Twin Monitor - {self.patient_display_name}", 
                              font=('Arial', 18, 'bold'), 
                              fg='white', bg='#2c3e50')
        title_label.pack(expand=True)
        
        subtitle_label = tk.Label(title_frame, text="Real-time physiological simulation data", 
                                 font=('Arial', 12), 
                                 fg='#ecf0f1', bg='#2c3e50')
        subtitle_label.pack()
        
        # Status and control frame
        control_frame = tk.Frame(self.root, bg='#f0f0f0')
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Status
        tk.Label(control_frame, text="Status:", font=('Arial', 12, 'bold'), 
                bg='#f0f0f0').pack(side=tk.LEFT)
        
        self.status_label = tk.Label(control_frame, text="Initializing...", 
                                    font=('Arial', 12), 
                                    fg="orange", bg='#f0f0f0')
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Time info
        self.time_label = tk.Label(control_frame, text="", 
                                  font=('Arial', 10), 
                                  fg="gray", bg='#f0f0f0')
        self.time_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # Simulation time
        self.sim_time_label = tk.Label(control_frame, text="Sim: 0s", 
                                      font=('Arial', 10), 
                                      fg="blue", bg='#f0f0f0')
        self.sim_time_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # Control buttons
        self.start_button = tk.Button(control_frame, text="Start Simulation", 
                                     command=self.toggle_simulation,
                                     font=('Arial', 12), 
                                     bg='#27ae60', fg='white',
                                     relief=tk.FLAT, padx=20, pady=5)
        self.start_button.pack(side=tk.RIGHT, padx=(10, 0))
        
        tk.Button(control_frame, text="Reset", 
                 command=self.reset_simulation,
                 font=('Arial', 12), 
                 bg='#f39c12', fg='white',
                 relief=tk.FLAT, padx=20, pady=5).pack(side=tk.RIGHT)
        
        # Main data frame
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Create parameter cards
        self.create_parameter_cards(main_frame)
        
        # Parameter adjustment frame
        self.create_parameter_adjustment_panel()
        
        # Events frame
        events_frame = tk.LabelFrame(self.root, text="System Events", 
                                    font=('Arial', 10, 'bold'), 
                                    bg='#f0f0f0', padx=10, pady=5)
        events_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.events_text = tk.Text(events_frame, height=6, font=('Consolas', 9), 
                                  bg='#2c3e50', fg='#ecf0f1', 
                                  insertbackground='white')
        scrollbar = tk.Scrollbar(events_frame, command=self.events_text.yview)
        self.events_text.configure(yscrollcommand=scrollbar.set)
        
        self.events_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add initial message
        self.log_event("Digital Twin Monitor initialized")
        
        # Copyright footer
        footer_frame = tk.Frame(self.root, bg='#f0f0f0')
        footer_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        tk.Label(footer_frame, text="© 2025 Dr. L.M. van Loon - Academic/Educational Use Only", 
                font=('Arial', 8), fg='gray', bg='#f0f0f0').pack()
        
    def create_parameter_cards(self, parent):
        """Create cards for each physiological parameter."""
        # Parameter definitions with colors and icons
        parameters = [
            ('Heart Rate', 'hr', 'bpm', '#e74c3c', '♥'),
            ('Mean ABP', 'map', 'mmHg', '#3498db', '📈'),
            ('Systolic BP', 'sap', 'mmHg', '#27ae60', '⬆️'),
            ('Diastolic BP', 'dap', 'mmHg', '#f39c12', '⬇️'),
            ('Temperature', 'temperature', '°C', '#9b59b6', '🌡️'),
            ('SpO2', 'sao2', '%', '#1abc9c', '💨'),
            ('Resp. Rate', 'rr', 'bpm', '#34495e', '🫁'),
            ('EtCO2', 'etco2', 'mmHg', '#e67e22', '💨')
        ]
        
        # Create grid layout
        self.parameter_cards = {}
        for i, (name, key, unit, color, icon) in enumerate(parameters):
            row = i // 4
            col = i % 4
            
            # Card frame
            card_frame = tk.Frame(parent, bg='white', relief=tk.RAISED, bd=2)
            card_frame.grid(row=row, column=col, padx=8, pady=8, sticky='nsew')
            
            # Configure grid weights
            parent.grid_rowconfigure(row, weight=1)
            parent.grid_columnconfigure(col, weight=1)
            
            # Header with icon and name
            header_frame = tk.Frame(card_frame, bg=color, height=45)
            header_frame.pack(fill=tk.X)
            header_frame.pack_propagate(False)
            
            tk.Label(header_frame, text=f"{icon} {name}", 
                    font=('Arial', 11, 'bold'), 
                    fg='white', bg=color).pack(expand=True)
            
            # Value display
            value_frame = tk.Frame(card_frame, bg='white', height=90)
            value_frame.pack(fill=tk.BOTH, expand=True)
            value_frame.pack_propagate(False)
            
            value_label = tk.Label(value_frame, text="--", 
                                  font=('Arial', 26, 'bold'), 
                                  fg=color, bg='white')
            value_label.pack(expand=True)
            
            unit_label = tk.Label(value_frame, text=unit, 
                                 font=('Arial', 11), 
                                 fg='gray', bg='white')
            unit_label.pack()
            
            # Trend indicator
            trend_label = tk.Label(value_frame, text="", 
                                  font=('Arial', 14), 
                                  fg='gray', bg='white')
            trend_label.pack()
            
            self.parameter_cards[key] = {
                'value_label': value_label,
                'unit_label': unit_label,
                'trend_label': trend_label,
                'color': color,
                'previous_value': 0
            }
    
    def create_parameter_adjustment_panel(self):
        """Create the parameter adjustment panel."""
        # Parameter adjustment frame (collapsible)
        self.param_frame = tk.LabelFrame(self.root, text="🔧 Real-time Parameter Adjustment", 
                                        font=('Arial', 11, 'bold'), 
                                        bg='#f8f9fa', padx=10, pady=5)
        self.param_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        # Toggle button for collapsing/expanding
        toggle_frame = tk.Frame(self.param_frame, bg='#f8f9fa')
        toggle_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.param_visible = tk.BooleanVar(value=True)
        self.toggle_button = tk.Button(toggle_frame, text="▼ Show Controls", 
                                      command=self.toggle_parameter_panel,
                                      font=('Arial', 9), 
                                      bg='#e9ecef', relief=tk.FLAT,
                                      padx=10, pady=2)
        self.toggle_button.pack(side=tk.LEFT)
        
        tk.Label(toggle_frame, text="Adjust parameters while simulation is running", 
                font=('Arial', 9), fg='#6c757d', bg='#f8f9fa').pack(side=tk.LEFT, padx=(10, 0))
        
        # Controls container
        self.param_controls_frame = tk.Frame(self.param_frame, bg='#f8f9fa')
        self.param_controls_frame.pack(fill=tk.X, pady=5)
        
        # Create parameter controls
        for i, (param_key, config) in enumerate(self.adjustable_parameters.items()):
            row = i // 2
            col = i % 2
            
            # Parameter control frame
            control_frame = tk.Frame(self.param_controls_frame, bg='#ffffff', relief=tk.RIDGE, bd=1)
            control_frame.grid(row=row, column=col, padx=5, pady=3, sticky='ew')
            
            # Configure grid weights
            self.param_controls_frame.grid_columnconfigure(col, weight=1)
            
            # Parameter label
            label_frame = tk.Frame(control_frame, bg='#ffffff')
            label_frame.pack(fill=tk.X, padx=8, pady=5)
            
            tk.Label(label_frame, text=config['label'], 
                    font=('Arial', 10, 'bold'), bg='#ffffff').pack(side=tk.LEFT)
            
            # Current value display
            current_var = tk.StringVar(value="Loading...")
            self.parameter_vars[f"{param_key}_current"] = current_var
            tk.Label(label_frame, textvariable=current_var, 
                    font=('Arial', 9), fg='#007bff', bg='#ffffff').pack(side=tk.RIGHT)
            
            # Scale control
            scale_frame = tk.Frame(control_frame, bg='#ffffff')
            scale_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
            
            scale_var = tk.DoubleVar(value=config['default'])
            self.parameter_vars[param_key] = scale_var
            
            scale = tk.Scale(scale_frame, from_=config['min'], to=config['max'], 
                           orient=tk.HORIZONTAL, variable=scale_var,
                           resolution=100 if 'TBV' in param_key else 1,
                           command=lambda val, key=param_key: self.on_parameter_change(key, val),
                           font=('Arial', 8), bg='#ffffff',
                           highlightthickness=0, bd=0)
            scale.pack(fill=tk.X)
            
            # Min/Max labels
            minmax_frame = tk.Frame(control_frame, bg='#ffffff')
            minmax_frame.pack(fill=tk.X, padx=8, pady=(0, 5))
            
            tk.Label(minmax_frame, text=f"Min: {config['min']}", 
                    font=('Arial', 8), fg='#6c757d', bg='#ffffff').pack(side=tk.LEFT)
            tk.Label(minmax_frame, text=f"Max: {config['max']}", 
                    font=('Arial', 8), fg='#6c757d', bg='#ffffff').pack(side=tk.RIGHT)
    
    def toggle_parameter_panel(self):
        """Toggle the visibility of the parameter adjustment panel."""
        if self.param_visible.get():
            self.param_controls_frame.pack_forget()
            self.toggle_button.config(text="▶ Show Controls")
            self.param_visible.set(False)
        else:
            self.param_controls_frame.pack(fill=tk.X, pady=5)
            self.toggle_button.config(text="▼ Hide Controls")
            self.param_visible.set(True)
    
    def on_parameter_change(self, param_key, value):
        """Handle parameter value changes."""
        try:
            if not self.dt_model:
                return
                
            new_value = float(value)
            
            # Update the parameter in the digital twin model
            if param_key in self.dt_model.master_parameters:
                old_value = self.dt_model.master_parameters[param_key]['value']
                self.dt_model.master_parameters[param_key]['value'] = new_value
                
                # Log the change
                self.log_event(f"🔧 {param_key}: {old_value:.1f} → {new_value:.1f}")
                
                # Update current value display
                current_var_key = f"{param_key}_current"
                if current_var_key in self.parameter_vars:
                    unit = ""
                    if 'TBV' in param_key:
                        unit = " mL"
                    elif 'HR' in param_key or 'RR' in param_key:
                        unit = " bpm"
                    elif 'Pset' in param_key:
                        unit = " mmHg"
                    
                    self.parameter_vars[current_var_key].set(f"Current: {new_value:.0f}{unit}")
            else:
                self.log_event(f"⚠️ Parameter {param_key} not found in model")
                
        except Exception as e:
            self.log_event(f"✗ Error updating parameter {param_key}: {e}")
    
    def update_parameter_displays(self):
        """Update the current parameter value displays."""
        if not self.dt_model:
            return
            
        try:
            for param_key in self.adjustable_parameters:
                if param_key in self.dt_model.master_parameters:
                    current_value = self.dt_model.master_parameters[param_key]['value']
                    
                    # Update the scale
                    if param_key in self.parameter_vars:
                        self.parameter_vars[param_key].set(current_value)
                    
                    # Update current value display
                    current_var_key = f"{param_key}_current"
                    if current_var_key in self.parameter_vars:
                        unit = ""
                        if 'TBV' in param_key:
                            unit = " mL"
                        elif 'HR' in param_key or 'RR' in param_key:
                            unit = " bpm"
                        elif 'Pset' in param_key:
                            unit = " mmHg"
                        
                        self.parameter_vars[current_var_key].set(f"Current: {current_value:.0f}{unit}")
        except Exception as e:
            self.log_event(f"Note: Could not update parameter displays: {e}")
    
    def initialize_digital_twin(self):
        """Initialize the digital twin model."""
        try:
            self.dt_model = DigitalTwinModel(
                patient_id="GUI_Monitor", 
                param_file=os.path.join(os.getcwd(), self.current_patient_file)
            )
            self.current_time = self.dt_model.t
            self.status_label.config(text="Digital twin loaded", fg="green")
            self.log_event("✓ Digital twin model initialized successfully")
            self.log_event(f"✓ Using parameter file: {self.current_patient_file}")
            self.log_event(f"✓ Initial simulation time: {self.current_time}s")
            
            # Update patient info display
            self.update_patient_info()
            
            # Update parameter displays
            self.update_parameter_displays()
            
            # Show initial values immediately
            self.show_initial_values()
            
            # Auto-start simulation after a short delay
            self.root.after(1000, self.auto_start_simulation)
            
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)[:30]}...", fg="red")
            self.log_event(f"✗ Failed to initialize digital twin: {e}")
            messagebox.showerror("Error", f"Failed to initialize digital twin:\n{e}")
    
    def show_initial_values(self):
        """Show initial physiological values."""
        if not self.dt_model:
            self.log_event("✗ No digital twin model available")
            return
            
        try:
            # Get initial physiological state
            P, F, HR, SaO2, RR = self.dt_model.compute_variables(self.current_time, self.dt_model.current_state)
            
            # Set initial values
            self.current_values['hr'] = float(HR)
            self.current_values['map'] = float(P[0])  # Initial pressure
            self.current_values['sap'] = float(P[0] + 20)  # Estimated systolic
            self.current_values['dap'] = float(P[0] - 20)  # Estimated diastolic  
            self.current_values['temperature'] = 37.0
            self.current_values['sao2'] = float(SaO2)
            self.current_values['rr'] = float(RR)
            self.current_values['etco2'] = float(self.dt_model.current_state[17])
            
            # Update display immediately
            self.update_display()
            self.log_event(f"✓ Initial values: HR={HR:.1f}, MAP={P[0]:.1f}, SaO2={SaO2:.1f}")
            
        except Exception as e:
            self.log_event(f"✗ Error showing initial values: {e}")
    
    def auto_start_simulation(self):
        """Automatically start the simulation."""
        if not self.running and self.dt_model:
            self.log_event("🚀 Auto-starting simulation...")
            self.start_simulation()
    
    def toggle_simulation(self):
        """Start or stop the simulation."""
        if not self.running:
            self.start_simulation()
        else:
            self.stop_simulation()
    
    def start_simulation(self):
        """Start the digital twin simulation."""
        if not self.dt_model:
            messagebox.showerror("Error", "Digital twin not initialized")
            return
            
        self.running = True
        self.start_button.config(text="Stop Simulation", bg='#e74c3c')
        self.status_label.config(text="Running simulation", fg="green")
        self.log_event("🚀 Simulation started")
        
        # Start simulation in background thread
        self.simulation_thread = threading.Thread(target=self.simulation_loop, daemon=True)
        self.simulation_thread.start()
    
    def stop_simulation(self):
        """Stop the digital twin simulation."""
        self.running = False
        self.start_button.config(text="Start Simulation", bg='#27ae60')
        self.status_label.config(text="Simulation stopped", fg="orange")
        self.log_event("⏹️ Simulation stopped")
    
    def reset_simulation(self):
        """Reset the simulation to initial state."""
        was_running = self.running
        if self.running:
            self.stop_simulation()
            
        try:
            self.dt_model = DigitalTwinModel(
                patient_id="GUI_Monitor", 
                param_file=os.path.join(os.getcwd(), self.current_patient_file)
            )
            self.current_time = self.dt_model.t
            self.pressure_buffer = []
            
            # Update parameter displays
            self.update_parameter_displays()
            
            # Reset display values
            for key in self.current_values:
                self.current_values[key] = 0
            self.update_display()
            
            self.log_event("🔄 Simulation reset to initial state")
            
            if was_running:
                self.start_simulation()
                
        except Exception as e:
            self.log_event(f"✗ Reset failed: {e}")
            messagebox.showerror("Error", f"Failed to reset simulation:\n{e}")
    
    def simulation_loop(self):
        """Main simulation loop running in background thread."""
        while self.running and self.dt_model:
            try:
                # Run one simulation step
                self.run_simulation_step()
                
                # Update GUI (must be done in main thread)
                self.root.after(0, self.update_display)
                
                # Sleep for the sampling interval
                time.sleep(self.sampling_interval)
                
            except Exception as e:
                self.root.after(0, lambda: self.log_event(f"✗ Simulation error: {e}"))
                time.sleep(1)
    
    def run_simulation_step(self):
        """Run one step of the digital twin simulation."""
        if not self.dt_model:
            self.root.after(0, lambda: self.log_event("✗ No digital twin model available"))
            return
            
        # This is the same logic as in provider_MDT.py
        try:
            # Solve the differential equations
            sol = solve_ivp(
                fun=self.dt_model.extended_state_space_equations,
                t_span=[self.current_time, self.current_time + self.sampling_interval],
                y0=self.dt_model.current_state,
                t_eval=np.linspace(self.current_time, self.current_time + self.sampling_interval, 20),
                method='LSODA',
                rtol=1e-6,
                atol=1e-6
            )
            
            # Update model state
            self.dt_model.current_state = sol.y[:, -1]
            self.current_time += self.sampling_interval
            self.dt_model.t = self.current_time
            
            # Compute physiological variables
            P, F, HR, SaO2, RR = self.dt_model.compute_variables(self.current_time, self.dt_model.current_state)
            
            # Calculate blood pressures like in provider_MDT.py
            if len(sol.t) > 1:
                avg_pressure_values = []
                for i in range(len(sol.t)):
                    t_point = sol.t[i]
                    y_point = sol.y[:, i]
                    
                    V = y_point[:10]
                    Pmus = y_point[25]
                    ela, elv, era, erv = self.dt_model.get_inputs(t_point)
                    UV_c = self.dt_model.master_parameters['cardio_control_params.UV_n']['value'] + y_point[28]
                    
                    P_temp = np.zeros(10)
                    P_temp[0] = self.dt_model.elastance[0, 0] * (V[0] - self.dt_model.uvolume[0]) + Pmus
                    avg_pressure_values.append(P_temp[0])
                
                averaged_blood_pressure = np.mean(avg_pressure_values)
                
                # Calculate systolic and diastolic pressures
                self.pressure_buffer.extend(avg_pressure_values)
                if len(self.pressure_buffer) > self.max_pressure_window:
                    self.pressure_buffer = self.pressure_buffer[-self.max_pressure_window:]
                
                systolic_pressure = np.max(self.pressure_buffer) if self.pressure_buffer else P[0]
                diastolic_pressure = np.min(self.pressure_buffer) if self.pressure_buffer else P[0]
            else:
                averaged_blood_pressure = P[0]
                systolic_pressure = P[0]
                diastolic_pressure = P[0]
            
            # Calculate temperature with variations
            baseline_temp = 37.0
            temp_variation = 0.2 * np.sin(self.current_time / 3600) + 0.1 * np.random.normal(0, 0.1)
            body_temperature = baseline_temp + temp_variation
            
            # Store previous values for trend calculation
            previous_values = self.current_values.copy()
            
            # Update current values
            self.current_values['hr'] = float(HR)
            self.current_values['map'] = float(averaged_blood_pressure)
            self.current_values['sap'] = float(systolic_pressure)
            self.current_values['dap'] = float(diastolic_pressure)
            self.current_values['temperature'] = float(body_temperature)
            self.current_values['sao2'] = float(SaO2)
            self.current_values['rr'] = float(RR)
            self.current_values['etco2'] = float(self.dt_model.current_state[17])
            
            # Update trend indicators
            for key in self.current_values:
                if key in previous_values:
                    diff = self.current_values[key] - previous_values[key]
                    if key in self.parameter_cards:
                        self.parameter_cards[key]['trend_diff'] = diff
                        
            # Log simulation step progress
            if int(self.current_time) % 10 == 0:  # Every 10 seconds
                self.root.after(0, lambda: self.log_event(f"📊 Sim step: HR={HR:.1f}, MAP={averaged_blood_pressure:.1f}, T={body_temperature:.1f}°C"))
                        
        except Exception as e:
            self.root.after(0, lambda: self.log_event(f"✗ Simulation step error: {e}"))
    
    def update_display(self):
        """Update the GUI display with current values."""
        # Update parameter cards
        for key, card in self.parameter_cards.items():
            value = self.current_values[key]
            previous = card['previous_value']
            
            # Format value
            if key == 'temperature':
                display_value = f"{value:.1f}"
            else:
                display_value = f"{value:.0f}"
            
            card['value_label'].config(text=display_value)
            
            # Update trend indicator
            if value > previous:
                trend = "↗"
                trend_color = "#27ae60"
            elif value < previous:
                trend = "↙"
                trend_color = "#e74c3c"
            else:
                trend = "→"
                trend_color = "#95a5a6"
                
            card['trend_label'].config(text=trend, fg=trend_color)
            card['previous_value'] = value
        
        # Update time displays
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.config(text=f"Real time: {current_time}")
        self.sim_time_label.config(text=f"Sim: {self.current_time:.0f}s")
    
    def log_event(self, message):
        """Add an event to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.events_text.see(tk.END)
    
    def on_closing(self):
        """Handle application closing."""
        self.running = False
        if self.simulation_thread and self.simulation_thread.is_alive():
            self.simulation_thread.join(timeout=1)
        self.root.quit()
        self.root.destroy()

def main():
    """Main function to run the direct monitor application."""
    parser = argparse.ArgumentParser(description="Direct Digital Twin Monitor")
    parser.add_argument("--patient", "-p", type=str, default="healthyFlat.json",
                       help="Patient parameter file to use (default: healthyFlat.json)")
    args = parser.parse_args()
    
    root = tk.Tk()
    app = DirectDigitalTwinMonitor(root, patient_file=args.patient)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_closing()

if __name__ == "__main__":
    main()
