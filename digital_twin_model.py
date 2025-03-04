# digital_twin_model.py

import numpy as np
import json
import time
from scipy.integrate import solve_ivp

class DigitalTwinModel:
    def __init__(self, patient_id, param_file="/Users/l.m.vanloon/Library/CloudStorage/OneDrive-UMCUtrecht/SDC/sasicu_example/MDTparameters/patient_1.json", data_callback=None):
        self.patient_id = patient_id
        self.data_callback = data_callback
        self.t = 0  # simulation time

        # Load and process parameters from JSON
        self._load_parameters(param_file)
        self.process_parameter_expressions()

        # Initialize model parameters and state
        self.initialize_model_parameters()
        self.current_state = self.initialize_state()

    def _load_parameters(self, param_file):
        """
        Load parameters from a JSON configuration file.
        Raises exceptions with detailed messages for missing or invalid files.
        """
        try:
            print(f"Loading parameter file: {param_file}")
            with open(param_file, "r") as file:
                config = json.load(file)
            self.params = config.get("params", {})
            self.initial_conditions = config.get("initial_conditions", {})
            self.bloodflows = config.get("bloodflows", {})
            self.cardio_constants = config.get("cardio_constants", {})
            self.cardio_parameters = config.get("cardio_parameters", {})
            self.gas_exchange_params = config.get("gas_exchange_params", {})
            self.derived_gas_exchange_params = config.get("derived_gas_exchange_params", {})
            self.respiratory_control_params = config.get("respiratory_control_params", {})
            self.cardio_control_params = config.get("cardio_control_params", {})
            self.misc_constants = config.get("misc_constants", {})
            print(f"Successfully loaded parameters for patient {self.patient_id}.")
        except FileNotFoundError:
            raise FileNotFoundError(f"Parameter file '{param_file}' not found. Please verify the file path.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Parameter file '{param_file}' is not a valid JSON file: {e}")

    def process_parameter_expressions(self):
        """
        Evaluate any string expressions in the parameter dictionaries.
        """
        # Create a context for evaluation
        context = {"np": np, "exp": np.exp, "min": min, "max": max}

        # Combine all parameter dictionaries into one
        all_parameters = {}
        parameter_dicts = [
            self.params,
            self.initial_conditions,
            self.bloodflows,
            self.cardio_constants,
            self.cardio_parameters,
            self.gas_exchange_params,
            self.derived_gas_exchange_params,
            self.respiratory_control_params,
            self.cardio_control_params,
            self.misc_constants,
        ]
        for param_dict in parameter_dicts:
            all_parameters.update(param_dict)

        # Keep track of unresolved parameters
        unresolved = set(all_parameters.keys())
        resolved = set()
        max_iterations = 10  # Prevent infinite loops
        for iteration in range(max_iterations):
            progress_made = False
            for key in list(unresolved):
                value = all_parameters[key]
                if isinstance(value, str):
                    try:
                        # Attempt to evaluate the expression
                        evaluated_value = eval(value, context)
                        all_parameters[key] = evaluated_value
                        context[key] = evaluated_value
                        unresolved.remove(key)
                        resolved.add(key)
                        progress_made = True
                    except Exception:
                        # Dependency might not be resolved yet
                        continue
                else:
                    context[key] = value
                    unresolved.remove(key)
                    resolved.add(key)
                    progress_made = True
            if not progress_made:
                break  # No further progress can be made

        if unresolved:
            print(f"Could not resolve the following parameters after {iteration + 1} iterations:")
            for key in unresolved:
                print(f" - {key}")
            raise ValueError("Parameter evaluation failed due to unresolved dependencies.")
        else:
            print("All parameters resolved successfully.")

        # Update each dictionary with the evaluated parameters
        for param_dict in parameter_dicts:
            for key in param_dict.keys():
                param_dict[key] = all_parameters[key]

        # Ensure that 't_eval' is defined in misc_constants
        if 't_eval' not in self.misc_constants:
            self.misc_constants['t_eval'] = np.arange(
                self.misc_constants['tmin'],
                self.misc_constants['tmax'] + self.misc_constants['T'],
                self.misc_constants['T']
            )

    def initialize_model_parameters(self):
        """Initialize model parameters such as elastance, resistance, and unstressed volumes."""
        elastance_list = self.cardio_parameters['elastance']
        resistance_list = self.cardio_parameters['resistance']
        uvolume_list = self.cardio_parameters['uvolume']

        # Convert lists to numpy arrays
        self.elastance = np.array(elastance_list, dtype=np.float64)
        self.resistance = np.array(resistance_list, dtype=np.float64)
        self.uvolume = np.array(uvolume_list, dtype=np.float64)

        # Lung model mechanical parameters
        self.C_cw = 0.2445  # l/cmH2O
        self.A_mechanical = np.array([
            [
                -1 / (self.cardio_constants['C_l'] * self.cardio_constants['R_ml'])
                - 1 / (self.cardio_constants['R_lt'] * self.cardio_constants['C_l']),
                1 / (self.cardio_constants['R_lt'] * self.cardio_constants['C_l']),
                0, 0, 0
            ],
            [
                1 / (self.cardio_constants['R_lt'] * self.cardio_constants['C_tr']),
                -1 / (self.cardio_constants['C_tr'] * self.cardio_constants['R_lt'])
                - 1 / (self.cardio_constants['R_tb'] * self.cardio_constants['C_tr']),
                1 / (self.cardio_constants['R_tb'] * self.cardio_constants['C_tr']),
                0, 0
            ],
            [
                0,
                1 / (self.cardio_constants['R_tb'] * self.cardio_constants['C_b']),
                -1 / (self.cardio_constants['C_b'] * self.cardio_constants['R_tb'])
                - 1 / (self.cardio_constants['R_bA'] * self.cardio_constants['C_b']),
                1 / (self.cardio_constants['R_bA'] * self.cardio_constants['C_b']),
                0
            ],
            [
                0, 0,
                1 / (self.cardio_constants['R_bA'] * self.cardio_constants['C_A']),
                -1 / (self.cardio_constants['C_A'] * self.cardio_constants['R_bA']),
                0
            ],
            [
                1 / (self.cardio_constants['R_lt'] * self.C_cw),
                -1 / (self.C_cw * self.cardio_constants['R_lt']),
                0, 0, 0
            ]
        ])
        self.B_mechanical = np.array([
            [1 / (self.cardio_constants['R_ml'] * self.cardio_constants['C_l']), 0, 0],
            [0, 1, 0],
            [0, 1, 0],
            [0, 1, 0],
            [0, 0, 1]
        ])

        # Initialize heart period parameters based on HR
        self.HR = self.misc_constants.get('HR', 75)
        self.update_heart_period(self.HR)

        # Initialize buffers for storing simulation data
        self.dt = self.misc_constants.get('T', 0.01)
        window_duration = 20  # seconds
        self.window_size = int(window_duration / self.dt)
        self.P_store = np.zeros((10, self.window_size))
        self.F_store = np.zeros((10, self.window_size))
        self.HR_store = np.zeros(self.window_size)
        self.buffer_index = 0

    def initialize_state(self):
        """Set initial state variables for the combined model."""
        state = np.zeros(29)  # Total number of state variables
        TBV = self.misc_constants.get('TBV', 5000)
        state[:10] = TBV * (self.uvolume / np.sum(self.uvolume))
        # Adjust a few initial volumes if needed
        state[0] += 200
        state[1] += 100
        state[2] += 100

        # Mechanical states (indices 10 to 14)
        state[10:15] = np.zeros(5)

        # Other states: gas exchange and control variables
        state[15] = 157 / 731       # FD_O2
        state[16] = 7 / 731         # FD_CO2
        state[17] = self.initial_conditions.get('p_a_CO2', 40)
        state[18] = self.initial_conditions.get('p_a_O2', 95)
        state[19] = self.initial_conditions.get('c_Stis_CO2', 0.5)
        state[20] = self.initial_conditions.get('c_Scap_CO2', 0.5)
        state[21] = self.initial_conditions.get('c_Stis_O2', 0.2)
        state[22] = self.initial_conditions.get('c_Scap_O2', 0.2)
        state[23] = self.respiratory_control_params.get('Delta_RR_c', 0)
        state[24] = self.respiratory_control_params.get('Delta_Pmus_c', 0)
        state[25] = -2              # Pmus
        state[26] = 0               # Delta_HR_c
        state[27] = 0               # Delta_R_c
        state[28] = 0               # Delta_UV_c
        return state

    def update_heart_period(self, HR):
        """Calculate and update heart period parameters based on HR."""
        self.HR = HR
        self.HP = 60 / HR
        self.Tas = 0.03 + 0.09 * self.HP
        self.Tav = 0.01
        self.Tvs = 0.16 + 0.2 * self.HP

    def calculate_elastances(self, t):
        """Calculate heart elastances at time t."""
        T = self.misc_constants['T']
        ncc = (t % self.HP) / T

        if ncc <= round(self.Tas / T):
            aaf = np.sin(np.pi * ncc / (self.Tas / T))
        else:
            aaf = 0

        ela = self.elastance[0, 8] + (self.elastance[1, 8] - self.elastance[0, 8]) * aaf
        era = self.elastance[0, 4] + (self.elastance[1, 4] - self.elastance[0, 4]) * aaf

        if ncc <= round((self.Tas + self.Tav) / T):
            vaf = 0
        elif ncc <= round((self.Tas + self.Tav + self.Tvs) / T):
            vaf = np.sin(np.pi * (ncc - (self.Tas + self.Tav) / T) / (self.Tvs / T))
        else:
            vaf = 0

        elv = self.elastance[0, 9] + (self.elastance[1, 9] - self.elastance[0, 9]) * vaf
        erv = self.elastance[0, 5] + (self.elastance[1, 5] - self.elastance[0, 5]) * vaf

        return ela, era, elv, erv

    def get_inputs(self, t):
        """Return the current inputs for the cardiovascular system."""
        # Update heart period parameters (if HR changes externally)
        self.update_heart_period(self.HR)
        ela, era, elv, erv = self.calculate_elastances(t)
        # Return an array with [ela, elv, era, erv]
        return np.array([ela, elv, era, erv])

    def ventilator_pressure(self, t):
        """Return a simple square‐wave ventilator pressure as a function of time."""
        RR = self.respiratory_control_params['RR_0']  # breaths per minute
        PEEP = 5  # cmH2O
        T = 60 / RR
        IEratio = 1
        TI = T * IEratio / (1 + IEratio)
        cycle_time = t % T
        mode = 'VCV'
        if mode == 'VCV':
            if 0 <= cycle_time <= TI:
                return (PEEP + 15) * 0.735  # Inhalation phase
            else:
                return PEEP * 0.735        # Exhalation phase
        elif mode == 'PCV':
            return 20 if cycle_time < 0.5 else PEEP

    def input_function(self, t, RR, Pmus_min, IEratio=1.0):
        """Compute the derivative of Pmus (muscle pressure) as a function of time."""
        T = 60 / RR
        TI = T * IEratio / (1 + IEratio)
        TE = T - TI
        exp_time = TE / 5
        cycle_time = t % T

        if 0 <= cycle_time <= TI:
            dPmus_dt = 2 * (-Pmus_min / (TI * TE)) * cycle_time + (Pmus_min * T) / (TI * TE)
        else:
            dPmus_dt = -Pmus_min / (exp_time * (1 - np.exp(-TE / exp_time))) * np.exp(-(cycle_time - TI) / exp_time)
        return np.array([0, dPmus_dt])

    def extended_state_space_equations(self, t, x):
        """
        Define the combined system of differential equations.
        x is a 29-element state vector.
        """
        # Split state vector
        V = x[:10]                      # Cardiovascular volumes
        mechanical_states = x[10:15]    # Mechanical states
        FD_O2, FD_CO2, p_a_CO2, p_a_O2 = x[15], x[16], x[17], x[18]
        c_Stis_CO2, c_Scap_CO2, c_Stis_O2, c_Scap_O2 = x[19:23]
        Delta_RR_c = x[23]
        Delta_Pmus_c = x[24]
        Pmus = x[25]
        Delta_HR_c = x[26]
        Delta_R_c = x[27]
        Delta_UV_c = x[28]

        # Obtain inputs (elastances etc.)
        inputs = self.get_inputs(t)
        ela, elv, era, erv = inputs  # Note: ordering here matches how they are used later

        # Compute control-dependent parameters
        HR = self.cardio_control_params['HR_n'] - Delta_HR_c
        R_c = self.cardio_control_params['R_n'] - Delta_R_c
        UV_c = self.cardio_control_params['UV_n'] + Delta_UV_c

        # Update heart period parameters based on HR
        self.update_heart_period(HR)

        if self.misc_constants['MV'] == 0:
            P_ao = 0
            self.RR = self.respiratory_control_params['RR_0'] + Delta_RR_c
            Pmus_min = self.respiratory_control_params['Pmus_0'] + Delta_Pmus_c
            driver = self.input_function(t, self.RR, Pmus_min)
            Pmus_dt = driver[1]
            FI_O2 = self.gas_exchange_params['FI_O2']
            FI_CO2 = self.gas_exchange_params['FI_CO2']
        else:
            P_ao = self.ventilator_pressure(t)
            driver = np.array([P_ao, 0])
            FI_O2 = self.gas_exchange_params['FI_O2']
            FI_CO2 = self.gas_exchange_params['FI_CO2']
            Pmus_dt = 0

        # Calculate pressures for the cardiovascular model
        P = np.zeros(10)
        P[0] = self.elastance[0, 0] * (V[0] - self.uvolume[0]) + mechanical_states[4]
        P[1] = self.elastance[0, 1] * (V[1] - self.uvolume[1])
        P[2] = self.elastance[0, 2] * (V[2] - self.uvolume[2] * UV_c)
        P[3] = self.elastance[0, 3] * (V[3] - self.uvolume[3] * UV_c) + mechanical_states[4]
        P[4] = era * (V[4] - self.uvolume[4]) + mechanical_states[4]
        P[5] = erv * (V[5] - self.uvolume[5]) + mechanical_states[4]
        P[6] = self.elastance[0, 6] * (V[6] - self.uvolume[6]) + mechanical_states[4]
        P[7] = self.elastance[0, 7] * (V[7] - self.uvolume[7]) + mechanical_states[4]
        P[8] = ela * (V[8] - self.uvolume[8]) + mechanical_states[4]
        P[9] = elv * (V[9] - self.uvolume[9]) + mechanical_states[4]

        # Calculate flows using Ohm's law-like relationships
        F = np.zeros(10)
        F[0] = (P[0] - P[1]) / (self.resistance[0] * R_c)
        F[1] = (P[1] - P[2]) / (self.resistance[1] * R_c)
        F[2] = (P[2] - P[3]) / (self.resistance[2] * R_c)
        F[3] = (P[3] - P[4]) / self.resistance[3] if P[3] - P[4] > 0 else (P[3] - P[4]) / (10 * self.resistance[3])
        F[4] = (P[4] - P[5]) / self.resistance[4] if P[4] - P[5] > 0 else 0
        F[5] = (P[5] - P[6]) / self.resistance[5] if P[5] - P[6] > 0 else 0
        F[6] = (P[6] - P[7]) / self.resistance[6]
        F[7] = (P[7] - P[8]) / self.resistance[7] if P[7] - P[8] > 0 else (P[7] - P[8]) / (10 * self.resistance[7])
        F[8] = (P[8] - P[9]) / self.resistance[8] if P[8] - P[9] > 0 else 0
        F[9] = (P[9] - P[0]) / self.resistance[9] if P[9] - P[0] > 0 else 0

        # Compute the derivatives of the volumes
        dVdt = np.zeros(10)
        dVdt[0] = F[9] - F[0]
        dVdt[1] = F[0] - F[1]
        dVdt[2] = F[1] - F[2]
        dVdt[3] = F[2] - F[3]
        dVdt[4] = F[3] - F[4]
        dVdt[5] = F[4] - F[5]
        dVdt[6] = F[5] - F[6]
        dVdt[7] = F[6] - F[7]
        dVdt[8] = F[7] - F[8]
        dVdt[9] = F[8] - F[9]

        # Lung and gas exchange related computations
        CO = self.bloodflows['CO']
        q_p = CO
        sh = 0.02  # shunt fraction
        q_S = 0.8 * CO

        Pmus_dt = driver[1]
        Ppl_dt = (mechanical_states[0] / (self.cardio_constants['R_lt'] * self.C_cw)) - \
                 (mechanical_states[1] / (self.C_cw * self.cardio_constants['R_lt'])) + Pmus_dt
        dxdt_mechanical = np.dot(self.A_mechanical, mechanical_states) + \
                          np.dot(self.B_mechanical, [P_ao, Ppl_dt, Pmus_dt])

        Vdot_l = (P_ao - mechanical_states[0]) / self.cardio_constants['R_ml']
        Vdot_A = (mechanical_states[2] - mechanical_states[3]) / self.cardio_constants['R_bA']

        p_D_CO2 = FD_CO2 * 713
        p_D_O2 = FD_O2 * 713
        FA_CO2 = p_a_CO2 / 713
        FA_O2 = p_a_O2 / 713

        # If p_a_O2 is huge, clamp now:
        p_a_O2 = max(0.0, min(p_a_O2, 700.0))

        c_a_CO2 = self.params['K_CO2'] * p_a_CO2 + self.params['k_CO2']

        # Now safe from overflow:
        c_a_O2 = self.params['K_O2'] * np.power((1 - np.exp(-self.params['k_O2'] * p_a_O2)), 2)

        # For simplicity, let the venous concentrations equal the capillary values
        c_v_CO2 = c_Scap_CO2
        c_v_O2 = c_Scap_O2

        # Determine whether the system is in inspiration or expiration
        if (self.misc_constants['MV'] == 1 and P_ao > 6 * 0.735) or \
           (self.misc_constants['MV'] == 0 and mechanical_states[0] < 0):
            dFD_O2_dt = Vdot_l * 1000 * (FI_O2 - FD_O2) / (self.gas_exchange_params['V_D'] * 1000)
            dFD_CO2_dt = Vdot_l * 1000 * (FI_CO2 - FD_CO2) / (self.gas_exchange_params['V_D'] * 1000)
            dp_a_CO2 = (863 * q_p * (1 - sh) * (c_v_CO2 - c_a_CO2) + Vdot_A * 1000 * (p_D_CO2 - p_a_CO2)) / \
                       (self.gas_exchange_params['V_A'] * 1000)
            dp_a_O2 = (863 * q_p * (1 - sh) * (c_v_O2 - c_a_O2) + Vdot_A * 1000 * (p_D_O2 - p_a_O2)) / \
                      (self.gas_exchange_params['V_A'] * 1000)
        else:
            dFD_O2_dt = Vdot_A * 1000 * (FD_O2 - FA_O2) / (self.gas_exchange_params['V_D'] * 1000)
            dFD_CO2_dt = Vdot_A * 1000 * (FD_CO2 - FA_CO2) / (self.gas_exchange_params['V_D'] * 1000)
            dp_a_CO2 = 863 * q_p * (1 - self.bloodflows.get('sh', sh)) * (c_v_CO2 - c_a_CO2) / \
                       (self.gas_exchange_params['V_A'] * 1000)
            dp_a_O2 = 863 * q_p * (1 - self.bloodflows.get('sh', sh)) * (c_v_O2 - c_a_O2) / \
                      (self.gas_exchange_params['V_A'] * 1000)

        dc_Stis_CO2 = (self.params['M_S_CO2'] - self.gas_exchange_params['D_S_CO2'] * (c_Stis_CO2 - c_Scap_CO2)) / \
                      self.params['V_Stis_CO2']
        dc_Scap_CO2 = (q_S * (c_a_CO2 - c_Scap_CO2) + self.gas_exchange_params['D_S_CO2'] * (c_Stis_CO2 - c_Scap_CO2)) / \
                      self.params['V_Scap_CO2']
        dc_Stis_O2 = (self.params['M_S_O2'] - self.gas_exchange_params['D_S_O2'] * (c_Stis_O2 - c_Scap_O2)) / \
                     self.params['V_Stis_O2']
        dc_Scap_O2 = (q_S * (c_a_O2 - c_Scap_O2) + self.gas_exchange_params['D_S_O2'] * (c_Stis_O2 - c_Scap_O2)) / \
                     self.params['V_Scap_O2']

        # Central control dynamics
        u_c = p_a_CO2 - self.respiratory_control_params['PaCO2_n']
        hr_c = P[0] - self.cardio_control_params['ABP_n']
        dDelta_Pmus_c = (-Delta_Pmus_c + self.respiratory_control_params['Gc_A'] * u_c) / \
                         self.respiratory_control_params['tau_c_A']
        dDelta_RR_c = (-Delta_RR_c + self.respiratory_control_params['Gc_f'] * u_c) / \
                      self.respiratory_control_params['tau_p_f']
        dDelta_HR_c = (-Delta_HR_c + self.cardio_control_params['Gc_hr'] * hr_c) / \
                      self.cardio_control_params['tau_hr']
        dDelta_R_c = (-Delta_R_c + self.cardio_control_params['Gc_r'] * hr_c) / \
                     self.cardio_control_params['tau_r']
        dDelta_UV_c = (-Delta_UV_c + self.cardio_control_params['Gc_uv'] * hr_c) / \
                      self.cardio_control_params['tau_uv']

        # Combine all derivatives into one state derivative vector
        dxdt = np.concatenate([
            dVdt,
            dxdt_mechanical,
            [
                dFD_O2_dt,
                dFD_CO2_dt,
                dp_a_CO2,
                dp_a_O2,
                dc_Stis_CO2,
                dc_Scap_CO2,
                dc_Stis_O2,
                dc_Scap_O2,
                dDelta_RR_c,
                dDelta_Pmus_c,
                Pmus_dt,
                dDelta_HR_c,
                dDelta_R_c,
                dDelta_UV_c
            ]
        ])
        return dxdt
