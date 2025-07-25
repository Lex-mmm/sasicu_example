#!/usr/bin/env python3
"""
Console Digital Twin Monitor
Shows real-time data in terminal for debugging purposes.
"""

import sys
import os
import time
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

class ConsoleDigitalTwinMonitor:
    def __init__(self):
        # Initialize digital twin model
        self.dt_model = DigitalTwinModel(
            patient_id="Console_Monitor", 
            param_file=os.path.join(os.getcwd(), "healthyFlat.json")
        )
        self.current_time = self.dt_model.t
        self.sampling_interval = 2  # seconds
        
        # Pressure tracking
        self.pressure_buffer = []
        self.max_pressure_window = 50
        
        print("✓ Digital twin model initialized")
        print(f"✓ Initial simulation time: {self.current_time}s")
        
    def run_simulation_step(self):
        """Run one step of the digital twin simulation."""
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
            
            # Calculate blood pressures
            if len(sol.t) > 1:
                avg_pressure_values = []
                for i in range(len(sol.t)):
                    t_point = sol.t[i]
                    y_point = sol.y[:, i]
                    
                    V = y_point[:10]
                    Pmus = y_point[25]
                    ela, elv, era, erv = self.dt_model.get_inputs(t_point)
                    
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
            
            # Add random noise spikes
            hr_display = HR
            map_display = averaged_blood_pressure
            sap_display = systolic_pressure
            temp_display = body_temperature
            
            if random.random() < 0.05:  # 5% chance
                noise = random.uniform(20, 50)
                hr_display += noise
                print(f"  🔥 Heart rate spike: +{noise:.1f} bpm")
                
            if random.random() < 0.03:  # 3% chance
                noise = random.uniform(10, 25)
                map_display += noise
                sap_display += noise
                print(f"  🔥 Blood pressure spike: +{noise:.1f} mmHg")
                
            if random.random() < 0.02:  # 2% chance
                fever_spike = random.uniform(1.0, 3.0)
                temp_display += fever_spike
                print(f"  🔥 Temperature spike: +{fever_spike:.1f}°C")
            
            return {
                'hr': hr_display,
                'map': map_display,
                'sap': sap_display,
                'dap': diastolic_pressure,
                'temperature': temp_display,
                'sao2': SaO2,
                'rr': RR,
                'etco2': self.dt_model.current_state[17]
            }
            
        except Exception as e:
            print(f"✗ Simulation step error: {e}")
            return None
    
    def run_monitor(self):
        """Run the console monitor."""
        print("\n🚀 Starting console digital twin monitor...")
        print("Press Ctrl+C to stop\n")
        
        step_count = 0
        try:
            while True:
                values = self.run_simulation_step()
                if values:
                    step_count += 1
                    
                    # Clear screen and display values
                    os.system('clear' if os.name == 'posix' else 'cls')
                    
                    print("=" * 60)
                    print(f"   DIGITAL TWIN MONITOR - Step {step_count}")
                    print(f"   Simulation Time: {self.current_time:.1f}s")
                    print("=" * 60)
                    print()
                    
                    print(f"♥  Heart Rate:     {values['hr']:.1f} bpm")
                    print(f"📈 Mean ABP:       {values['map']:.1f} mmHg")
                    print(f"⬆️  Systolic BP:    {values['sap']:.1f} mmHg")
                    print(f"⬇️  Diastolic BP:   {values['dap']:.1f} mmHg")
                    print(f"🌡️  Temperature:    {values['temperature']:.1f} °C")
                    print(f"💨 SpO2:           {values['sao2']:.1f} %")
                    print(f"🫁 Resp. Rate:     {values['rr']:.1f} bpm")
                    print(f"💨 EtCO2:          {values['etco2']:.1f} mmHg")
                    
                    print()
                    print(f"Next update in {self.sampling_interval} seconds...")
                
                time.sleep(self.sampling_interval)
                
        except KeyboardInterrupt:
            print("\n\n⏹️  Monitor stopped by user")
            print("Thank you for using the Digital Twin Monitor!")

def main():
    """Main function."""
    monitor = ConsoleDigitalTwinMonitor()
    monitor.run_monitor()

if __name__ == "__main__":
    main()
