# Sasicu Example

This repository contains an example implementation of an SDC provider and a digital twin model simulation for a medical device context. It demonstrates how to:

- Load and parse device definitions using SDC standards.
- Create an MDIB from an XML specification.
- Simulate physiological state changes using a digital twin model.
- Update metrics and alert states in the MDIB.
- Communicate device states over the SDC provider framework.

## File Structure

- **provider_MDT.py**: Initializes the SDC provider, loads the MDIB, updates metrics, and runs the simulation loop.
- **digital_twin_model.py**: Contains the `DigitalTwinModel` class that encapsulates the extended state-space equations and model parameters.
- Additional folders and configuration files include:
  - **MDTparameters/**: Contains patient-specific parameter files.
  - **ssl/**: Holds SSL certificate files required for secure communication.
  - **mdib.xml**: The XML file from which the local MDIB is created.

## Prerequisites

- Python 3.8 or later.
- Required packages:
  - `sdc11073`
  - `scipy`
  - `numpy`
  - Other dependencies as listed in your project's requirements.

## Getting Started

1. **Setup the Environment**  
   Ensure you have installed the necessary Python packages. If you have a `requirements.txt` file, run:
   ```bash
   pip install -r requirements.txt
   ```

2. **Prepare Configuration Files**  
   - Place the `mdib.xml` file in the repository root.
   - Ensure that the SSL certificates are present in the `ssl/` folder.
   - Check and update `MDTparameters/patient_1.json` as needed.

3. **Run the Provider Script**  
   In your terminal, execute:
   ```bash
   python provider_MDT.py
   ```
   This starts the discovery process, loads the MDIB, and begins the digital twin simulation. The simulation iteratively updates metric values and triggers alarm states based on computed patient values.

## Contributing

Feel free to create issues or pull requests to suggest improvements or report bugs.

## License

This work is provided for non-commercial use only. You are not allowed to commercially use, reproduce, or distribute any part of this repository without obtaining explicit permission from the author. For commercial use inquiries, please contact the repository maintainer.

## References

- SDC Standards documentation.
- Relevant research papers or documentation on digital twin models in medical devices.