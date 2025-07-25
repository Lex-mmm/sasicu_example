# Digital Twin GUI System

This directory contains a comprehensive GUI system for monitoring the digital twin physiological data in real-time.

## Components

### 1. Simple Monitor (`simple_monitor.py`)
A lightweight, user-friendly monitoring interface that displays real-time physiological parameters from the digital twin.

**Features:**
- Real-time display of 8 physiological parameters
- Visual cards with color-coded parameter values
- Automatic connection to SDC provider
- Demo mode when SDC libraries are not available
- Clean, intuitive interface

**Parameters Monitored:**
- Heart Rate (HR) - bpm
- Mean Arterial Blood Pressure (MAP) - mmHg
- Systolic Blood Pressure (SAP) - mmHg  
- Diastolic Blood Pressure (DAP) - mmHg
- Body Temperature - °C
- Oxygen Saturation (SpO2) - %
- Respiratory Rate (RR) - bpm
- End-tidal CO2 (EtCO2) - mmHg

### 2. Advanced GUI (`digital_twin_gui.py`)
A more sophisticated interface with real-time plotting capabilities.

**Features:**
- Real-time matplotlib plots for trend visualization
- Multiple plot panels for different parameter groups
- Data history tracking (last 100 points)
- Advanced SDC consumer integration

### 3. System Launcher (`launcher.py`)
A control center for managing both the provider and monitoring applications.

**Features:**
- Start/stop the digital twin provider
- Launch monitoring GUI
- Network adapter configuration
- System log output
- Quick start options

## Installation

1. **Install Required Dependencies:**
```bash
pip install -r requirements.txt
```

2. **Ensure SSL Certificates:**
Make sure the `ssl/` directory contains the required certificates:
- `cacert.pem`
- `usercert.pem` 
- `userkey.pem`

## Usage

### Option 1: Using the System Launcher (Recommended)
```bash
python launcher.py
```

This provides a graphical interface to:
1. Start the digital twin provider
2. Launch the monitoring GUI
3. View system logs
4. Configure network settings

### Option 2: Manual Start

1. **Start the Digital Twin Provider:**
```bash
python provider_MDT.py --adapter en0
```

2. **Start the Simple Monitor (in a new terminal):**
```bash
python simple_monitor.py --adapter en0
```

3. **Or start the Advanced GUI:**
```bash
python digital_twin_gui.py --adapter en0
```

### Option 3: Demo Mode
If SDC libraries are not available, the simple monitor will automatically run in demo mode with simulated data.

## Network Configuration

Both applications support network adapter specification:
- macOS: typically `en0` (WiFi) or `en1` (Ethernet)
- Linux: typically `eth0` (Ethernet) or `wlan0` (WiFi)
- Windows: use the adapter name from `ipconfig`

## GUI Features

### Simple Monitor Interface
- **Parameter Cards**: Visual cards showing current values with color coding
- **Real-time Updates**: Values update every second
- **Connection Status**: Shows connection state to SDC provider
- **Manual Refresh**: Force data refresh
- **Auto-reconnect**: Automatically attempts to reconnect if connection is lost

### Advanced GUI Interface  
- **Cardiovascular Plot**: HR, MAP, Systolic, and Diastolic BP trends
- **Temperature Plot**: Body temperature over time
- **Respiratory Plot**: SpO2 and respiratory rate trends
- **EtCO2 Plot**: End-tidal CO2 levels
- **Data Export**: Historical data can be analyzed
- **Zoom/Pan**: Interactive plot navigation

## Troubleshooting

### Connection Issues
1. **Check Network Adapter**: Ensure the correct adapter is specified
2. **Provider Running**: Make sure `provider_MDT.py` is running first
3. **Firewall**: Check that firewall allows SDC communication
4. **SSL Certificates**: Verify SSL certificates are present and valid

### Performance Issues
1. **Update Frequency**: Reduce update frequency if system is slow
2. **Data History**: Reduce the number of stored data points
3. **Plot Complexity**: Use simple monitor for better performance

### Demo Mode
If SDC libraries are missing:
1. The simple monitor will automatically run in demo mode
2. Install SDC dependencies: `pip install sdc11073`
3. Restart the application

## Data Visualization

The GUIs provide different visualization approaches:

### Current Values Display
- Large, easy-to-read numerical displays
- Color-coded parameter categories
- Unit labels for each measurement
- Status indicators for connection and data quality

### Trend Analysis
- Time-series plots showing parameter evolution
- Multiple parameters on single plots for correlation analysis
- Adjustable time windows
- Real-time scrolling displays

## Integration with Digital Twin

The GUI system integrates with the digital twin model through:

1. **SDC Consumer**: Connects to the SDC provider running the digital twin
2. **Real-time Data**: Receives live physiological parameter updates
3. **Alarm Integration**: Can display alert states from the provider
4. **Parameter Mapping**: Maps digital twin outputs to clinical parameters

## Customization

### Adding New Parameters
1. Update the parameter definitions in the GUI files
2. Add corresponding handles in the SDC consumer logic
3. Ensure the provider exposes the new parameters

### Modifying Display
1. **Colors**: Update color codes in parameter definitions
2. **Layout**: Modify grid layouts and widget arrangements  
3. **Update Rates**: Change timing parameters for different refresh rates

### Plot Customization
1. **Plot Types**: Add new plot types (histograms, scatter plots)
2. **Styling**: Modify matplotlib styling and themes
3. **Data Processing**: Add filtering, smoothing, or analysis functions

## API Reference

### SimpleDigitalTwinMonitor Class
- `connect_to_device()`: Establish SDC connection
- `collect_data()`: Retrieve current parameter values
- `update_display()`: Refresh GUI elements
- `generate_demo_data()`: Create simulated data

### DigitalTwinGUI Class
- `setup_plots()`: Initialize matplotlib figures
- `update_plots()`: Refresh plot data
- `collect_data()`: Get SDC data
- `clear_data()`: Reset data history

## Security Notes

- The system uses SSL/TLS for SDC communication
- Certificates should be properly managed and updated
- Network traffic is encrypted between provider and consumer
- Consider firewall rules for production deployment
