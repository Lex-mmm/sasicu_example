# SDC Medical Device Provider Example

This repository demonstrates a Service-oriented Device Connectivity (SDC) provider implementation with a digital twin model simulation for medical devices. The example showcases SDC standards integration with physiological modeling.

## Features

- SDC-compliant provider implementation
- Digital twin model for physiological state simulation
- Real-time metric updates and alert state management
- Secure communication with SSL/TLS support
- Configurable patient parameters

## Repository Structure

```
sasicu_example/
├── provider_MDT.py         # Main provider implementation
├── digital_twin_model.py   # Digital twin model simulation
├── MDTparameters/         # Patient parameter configurations
│   └── patient_1.json
├── ssl/                   # SSL certificates
└── mdib.xml              # Base MDIB definition
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
python provider_MDT.py --interface en0
```

Options:
- `--interface`: Network interface (default: en0)
- `--ssl-password`: SSL certificate password (default: dummypass)

### Starting the Consumer

```bash
python consumer_MDT.py --interface en0
```

## Configuration

1. Place your MDIB definition in `mdib.xml`
2. Update SSL certificates in the `ssl/` directory
3. Configure patient parameters in `MDTparameters/patient_1.json`

## Security

- All communications are secured using SSL/TLS
- Certificates must be properly configured before running the provider
- Default SSL password can be overridden via command line

## License

For non-commercial use only. Commercial usage requires explicit permission from L.M. van Loon (l.m.vanloon@utwente.nl).

## Contact

For questions or commercial inquiries:
- **Author**: L.M. van Loon
- **Email**: l.m.vanloon@utwente.nl