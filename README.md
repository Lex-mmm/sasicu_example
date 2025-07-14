# SDC Medical Device Provider Example

This repository demonstrates a Service-oriented Device Connectivity (SDC) provider implementation with a digital twin model simulation for medical devices. The example showcases SDC standards integration with physiological modeling for simulating patient vital signs.

## Overview

This implementation creates a medical device provider that simulates a patient monitor using a physiological digital twin model. The digital twin simulates cardiovascular and respiratory systems to generate realistic vital signs data (heart rate, blood pressure, oxygen saturation, etc.) that are transmitted through SDC protocols.

## Features

- SDC-compliant provider implementation following IEEE 11073 standards
- Digital twin model for physiological state simulation with:
  - Cardiovascular system modeling
  - Respiratory system modeling
  - Baroreflex and chemoreceptor control mechanisms
- Real-time metric updates with physiologically realistic values
- Simulated alert state management for clinical alarm conditions
- Secure communication with SSL/TLS support
- Configurable patient parameters for different clinical scenarios

## Repository Structure

```
sasicu_example/
├── provider_MDT.py         # Main provider implementation with SDC integration
├── consumer.py             # Example SDC consumer that connects to the provider
├── digital_twin_model.py   # Digital twin physiological simulation model
├── ExtendedDevice.xml      # Medical Device Information Base (MDIB) definition
├── healthyFlat.json        # Default parameter configuration for healthy patient
├── ssl/                    # SSL certificates for secure communication
└── README.md               # This documentation file
```

## Prerequisites

- Python 3.8+
- Network interface with IPv4 support
- SSL certificates for secure communication

### Required Python Packages
```bash
pip install sdc11073 scipy numpy netifaces
```

## Usage

### Starting the Provider

```bash
python provider_MDT.py --adapter <network_interface>
```

Options:
- `--adapter`: Network interface to use (default: en0)

### Starting the Consumer

```bash
python consumer.py --interface <network_interface>
```

Options:
- `--interface`: Network interface to use (default: en0)
- `--ssl-passwd`: SSL certificate password (default: dummypass)

## How It Works

1. The provider initializes the SDC framework and loads the MDIB definition from `ExtendedDevice.xml`
2. A digital twin model simulates a patient's physiological state using parameters from `healthyFlat.json`
3. The provider periodically updates the SDC metrics with values from the simulation including:
   - Heart Rate (HR)
   - Mean Arterial Pressure (MAP) - averaged over sampling interval
   - Oxygen Saturation (SaO2)
   - Respiratory Rate (RR)
   - End-tidal CO2 (etCO2)
4. Alert conditions are triggered based on physiological thresholds
5. Consumers can discover and connect to the provider via SDC protocols

## Configuration

### Patient Parameters

Patient parameters are configured in `healthyFlat.json`. These include:
- Cardiovascular parameters (heart rate, blood pressure, elastance)
- Respiratory parameters (respiratory rate, gas exchange)
- Metabolic parameters (O2 consumption, CO2 production)
- Baroreflex and chemoreceptor control parameters

### MDIB Configuration

The `ExtendedDevice.xml` file defines the structure of the medical device information, including:
- Available metrics (HR, MAP, SAP, DAP, RR, SaO2, etCO2, etc.)
- Alert conditions and thresholds for each metric
- Device metadata and capabilities
- Both monitoring and ventilation device definitions

## Digital Twin Model Features

The physiological simulation includes:
- **Cardiovascular System**: 10-compartment lumped parameter model with elastances and resistances
- **Respiratory System**: Mechanical ventilation with gas exchange modeling
- **Control Systems**: Baroreflex and chemoreceptor feedback loops
- **Real-time Integration**: Continuous ODE solving with physiologically realistic dynamics

## Security

- All communications are secured using SSL/TLS
- Certificates must be properly configured in the `ssl/` directory
- Default SSL password can be overridden via command line

## License

For non-commercial use only. Commercial usage requires explicit permission from L.M. van Loon (l.m.vanloon@utwente.nl).

## Contact

For questions or commercial inquiries:
- **Author**: L.M. van Loon
- **Email**: l.m.vanloon@utwente.nl