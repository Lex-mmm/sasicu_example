#!/usr/bin/env python3
"""
Test script to verify the digital twin model is working correctly.
"""

import sys
import os
import numpy as np
from scipy.integrate import solve_ivp

# Add current directory to path for imports
sys.path.append(os.getcwd())

try:
    from digital_twin_model import DigitalTwinModel
    print("✓ Digital twin model imported successfully")
except ImportError as e:
    print(f"✗ Failed to import digital twin model: {e}")
    sys.exit(1)

def test_digital_twin():
    """Test the digital twin model functionality."""
    print("🔬 Testing Digital Twin Model...")
    
    try:
        # Initialize model
        dt_model = DigitalTwinModel(
            patient_id="Test_Patient", 
            param_file=os.path.join(os.getcwd(), "healthyFlat.json")
        )
        print(f"✓ Model initialized, initial time: {dt_model.t}s")
        
        # Get initial state
        initial_state = dt_model.current_state.copy()
        print(f"✓ Initial state vector length: {len(initial_state)}")
        
        # Test compute_variables
        P, F, HR, SaO2, RR = dt_model.compute_variables(dt_model.t, dt_model.current_state)
        print(f"✓ Initial values:")
        print(f"  - Heart Rate: {HR:.1f} bpm")
        print(f"  - Mean ABP: {P[0]:.1f} mmHg")
        print(f"  - SpO2: {SaO2:.1f} %")
        print(f"  - Respiratory Rate: {RR:.1f} bpm")
        print(f"  - EtCO2: {dt_model.current_state[17]:.1f} mmHg")
        
        # Test simulation step
        print("\n🔄 Running simulation step...")
        current_time = dt_model.t
        sampling_interval = 2.0
        
        sol = solve_ivp(
            fun=dt_model.extended_state_space_equations,
            t_span=[current_time, current_time + sampling_interval],
            y0=dt_model.current_state,
            t_eval=np.linspace(current_time, current_time + sampling_interval, 10),
            method='LSODA',
            rtol=1e-6,
            atol=1e-6
        )
        
        print(f"✓ Simulation solved, solution points: {len(sol.t)}")
        
        # Update state
        dt_model.current_state = sol.y[:, -1]
        dt_model.t = current_time + sampling_interval
        
        # Get new values
        P_new, F_new, HR_new, SaO2_new, RR_new = dt_model.compute_variables(dt_model.t, dt_model.current_state)
        print(f"✓ Updated values after {sampling_interval}s:")
        print(f"  - Heart Rate: {HR_new:.1f} bpm")
        print(f"  - Mean ABP: {P_new[0]:.1f} mmHg")
        print(f"  - SpO2: {SaO2_new:.1f} %")
        print(f"  - Respiratory Rate: {RR_new:.1f} bpm")
        print(f"  - EtCO2: {dt_model.current_state[17]:.1f} mmHg")
        
        # Test pressure calculations
        print("\n🩺 Testing pressure calculations...")
        avg_pressure_values = []
        for i in range(len(sol.t)):
            t_point = sol.t[i]
            y_point = sol.y[:, i]
            
            V = y_point[:10]
            Pmus = y_point[25]
            ela, elv, era, erv = dt_model.get_inputs(t_point)
            
            P_temp = np.zeros(10)
            P_temp[0] = dt_model.elastance[0, 0] * (V[0] - dt_model.uvolume[0]) + Pmus
            avg_pressure_values.append(P_temp[0])
        
        averaged_blood_pressure = np.mean(avg_pressure_values)
        systolic_pressure = np.max(avg_pressure_values)
        diastolic_pressure = np.min(avg_pressure_values)
        
        print(f"✓ Pressure analysis:")
        print(f"  - Mean ABP: {averaged_blood_pressure:.1f} mmHg")
        print(f"  - Systolic BP: {systolic_pressure:.1f} mmHg")
        print(f"  - Diastolic BP: {diastolic_pressure:.1f} mmHg")
        
        print("\n🎉 Digital twin model test completed successfully!")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_digital_twin()
    sys.exit(0 if success else 1)
