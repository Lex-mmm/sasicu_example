#!/usr/bin/env python3
"""
SDC Digital Twin Monitor with Integrated Control Panel (Fixed)
Monitors SDC data AND provides control over the virtual patient parameters.

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
import subprocess
import json
import glob
import queue
try:
    import numpy as np
except ImportError:
    print("\n[ERROR] numpy is not installed in the current interpreter.")
    print("Hint: Activate the bundled virtualenv or install requirements:")
    print("  source env/bin/activate  # (macOS/Linux) OR .\\env\\Scripts\\activate (Windows)")
    print("  pip install -r requirements.txt")
    print("Or run using the embedded interpreter:")
    print("  ./env/bin/python sdc_monitor_control.py")
    raise
from alarm_module import AlarmModule
from sdc_alarm_manager import SDCAlarmManager

# Add current directory to path for imports
sys.path.append(os.getcwd())

# SDC Consumer imports
try:
    from sdc11073.consumer import SdcConsumer
    from sdc11073.wsdiscovery import WSDiscoverySingleAdapter
    from sdc11073 import certloader
    SDC_AVAILABLE = True
    print("✓ SDC libraries available")
except ImportError as e:
    print(f"✗ SDC libraries not available: {e}")
    SDC_AVAILABLE = False

# Digital Twin Model for control
try:
    from digital_twin_model import DigitalTwinModel
    DT_MODEL_AVAILABLE = True
    print("✓ Digital twin model imported successfully")
except ImportError as e:
    DigitalTwinModel = None
    DT_MODEL_AVAILABLE = False
    print(f"✗ Failed to import digital twin model: {e}")

class SDCDigitalTwinMonitor:
    def __init__(self, root, network_adapter="en0"):
        self.root = root
        self.root.title("SDC Digital Twin Monitor & Control - © Dr. L.M. van Loon")
        self.root.geometry("1000x600")  # Even more compact
        self.root.configure(bg='#2c3e50')  # Dark blue background for better contrast
        
        self.network_adapter = network_adapter
        
        # SDC Consumer
        self.consumer = None
        self.discovery = None
        self.connected = False
        self.last_data_time = 0  # Track when we last received data
        
        # Thread-safe communication
        self.data_queue = queue.Queue()
        self.log_queue = queue.Queue()
        self.sdc_messages_queue = queue.Queue()  # New queue for SDC messages
        
        # Provider process (we'll start our own)
        self.provider_process = None
        
        # Consumer process (we'll use the working consumer.py)
        self.consumer_process = None
        self.consumer_running = False  # Track consumer state (default OFF)
        
        # Digital Twin Control (for parameter adjustment only)
        self.dt_model = None
        # Cross-platform default patient file path (avoids hardcoded separators/backslashes)
        self.current_patient = os.path.join("MDTparameters", "healthy.json")
        
        # Initialize alarm system (will be properly initialized when connecting to provider)
        self.alarm_module = None
        self.sdc_alarm_manager = None
        self.alarm_status_labels = {}
        
        # DON'T initialize digital twin model here - we want to connect to provider instead
        # self.initialize_digital_twin()
        
        # Data storage for display
        self.current_values = {
            'hr': 0,
            'map': 0,
            'sap': 0,
            'dap': 0,
            'temperature': 37.0,
            'sao2': 98,
            'rr': 15,
            'etco2': 40
        }
        
        # Create GUI
        self.create_theme()
        self.create_widgets()
        
        # Initialize display to show waiting for provider data
        self.initialize_display()
        
        # Start queue processing
        self.process_queues()
        
        # Consumer is default OFF - user needs to start manually via button
        self.log_queue.put("📡 SDC Consumer: Default OFF - use control button to start")
        # Placeholder attributes for applied labels (initialized later in parameter slider creation)
        self.fio2_applied_label = None
        self.blood_volume_applied_label = None
        # Start live parameter reflection (FiO2 / TBV) if/when model becomes available
        self.root.after(1500, self.start_live_param_monitoring)

    def _resolve_python_interpreter(self):
        """Robust cross-platform Python interpreter resolution.

        Preference order:
          1. Current process interpreter (if it has numpy installed)
          2. Local virtual environment (env/bin/python or env/Scripts/python.exe)
          3. shutil.which lookups: python, python3, py
        """
        import shutil

        # 1. Current interpreter
        cur = sys.executable
        if cur:
            return cur

        # 2. Local venv conventional locations
        candidates = [
            os.path.join(os.getcwd(), 'env', 'bin', 'python'),
            os.path.join(os.getcwd(), 'env', 'bin', 'python3'),
            os.path.join(os.getcwd(), 'env', 'Scripts', 'python.exe'),
            os.path.join(os.getcwd(), 'env', 'Scripts', 'python')
        ]
        for c in candidates:
            if os.path.exists(c):
                return c

        # 3. PATH lookups
        for name in ('python3', 'python', 'py'):
            found = shutil.which(name)
            if found:
                return found
        return 'python'

    def create_theme(self):
        """Configure a consistent, modern ttk theme and widget styles."""
        try:
            style = ttk.Style(self.root)
            # Use a theme that allows color customization
            try:
                style.theme_use('clam')
            except Exception:
                pass

            # Base palette
            bg = '#1a252f'
            panel = '#2d3748'
            text = '#e5e7eb'
            subtle = '#a0aec0'

            self.root.configure(bg=bg)

            # Buttons
            style.configure('TButton',
                            font=('Helvetica', 9, 'bold'),
                            padding=(10, 6),
                            background='#374151',
                            foreground=text,
                            borderwidth=0)
            style.map('TButton',
                      background=[('active', '#4b5563'), ('pressed', '#4b5563')])

            style.configure('Accent.TButton', background='#10b981', foreground='#0b141a')
            style.map('Accent.TButton', background=[('active', '#059669'), ('pressed', '#059669')])

            style.configure('Secondary.TButton', background='#14b8a6', foreground='#0b141a')
            style.map('Secondary.TButton', background=[('active', '#0d9488'), ('pressed', '#0d9488')])

            style.configure('Danger.TButton', background='#ef4444', foreground='#0b141a')
            style.map('Danger.TButton', background=[('active', '#dc2626'), ('pressed', '#dc2626')])

            style.configure('Warning.TButton', background='#f59e0b', foreground='#0b141a')
            style.map('Warning.TButton', background=[('active', '#d97706'), ('pressed', '#d97706')])

            style.configure('Info.TButton', background='#8b5cf6', foreground='#0b141a')
            style.map('Info.TButton', background=[('active', '#7c3aed'), ('pressed', '#7c3aed')])

            # Compact button for inline actions
            style.configure('AccentMini.TButton',
                            background='#10b981', foreground='#0b141a',
                            font=('Helvetica', 9, 'bold'), padding=(8, 4))
            style.map('AccentMini.TButton', background=[('active', '#059669'), ('pressed', '#059669')])

            style.configure('DangerMini.TButton',
                            background='#ef4444', foreground='#0b141a',
                            font=('Helvetica', 9, 'bold'), padding=(8, 4))
            style.map('DangerMini.TButton', background=[('active', '#dc2626'), ('pressed', '#dc2626')])

            style.configure('SecondaryMini.TButton',
                            background='#14b8a6', foreground='#0b141a',
                            font=('Helvetica', 9, 'bold'), padding=(8, 4))
            style.map('SecondaryMini.TButton', background=[('active', '#0d9488'), ('pressed', '#0d9488')])

            # Combobox
            style.configure('TCombobox',
                            fieldbackground=panel,
                            background=panel,
                            foreground=text,
                            arrowcolor=subtle,
                            borderwidth=0)
        except Exception:
            # Styling is best-effort; ignore if platform rejects some options
            pass
        
    def start_consumer_process(self):
        """Start the working consumer.py process."""
        if not SDC_AVAILABLE:
            self.log_queue.put("✗ SDC libraries not available for consumer")
            self.sdc_messages_queue.put("SDC Monitor: SDC libraries not available")
            if hasattr(self, 'consumer_status_label'):
                self.consumer_status_label.config(text="N/A", fg="#808080")
            return
            
        try:
            # Check if consumer file exists
            if not os.path.exists("consumer.py"):
                self.log_queue.put("✗ consumer.py not found!")
                self.sdc_messages_queue.put("SDC Consumer: consumer.py not found!")
                if hasattr(self, 'consumer_status_label'):
                    self.consumer_status_label.config(text="N/A", fg="#808080")
                return
                
            self.log_queue.put("🔍 Starting SDC consumer...")
            self.sdc_messages_queue.put("SDC Consumer: Starting consumer process...")
            
            # Start consumer process (use venv python if available)
            python_cmd = self._resolve_python_interpreter()
            cmd = [python_cmd, "-u", "consumer.py", "--interface", self.network_adapter]
            self.log_queue.put(f"Consumer Command: {' '.join(cmd)}")
            
            self.consumer_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,  # Line buffering
                cwd=os.getcwd()
            )
            
            self.log_queue.put(f"✓ Consumer started on interface {self.network_adapter}")
            self.log_queue.put(f"Consumer PID: {self.consumer_process.pid}")
            self.sdc_messages_queue.put(f"SDC Consumer: Started on interface {self.network_adapter}")
            
            # Update consumer state
            self.consumer_running = True
            if hasattr(self, 'consumer_status_label'):
                self.consumer_status_label.config(text="ON", fg="#00ff88")
            
            # Start monitoring consumer output immediately to capture early failures
            self.monitor_consumer_output()

            # Check if process started successfully
            time.sleep(0.5)
            if self.consumer_process.poll() is not None:
                self.log_queue.put(f"✗ Consumer process exited with code: {self.consumer_process.returncode}")
                self.sdc_messages_queue.put(f"SDC Consumer: Process failed with code {self.consumer_process.returncode}")
                self.consumer_running = False
                if hasattr(self, 'consumer_status_label'):
                    self.consumer_status_label.config(text="ERROR", fg="#e53e3e")
                return

            
        except Exception as e:
            error_msg = f"✗ Failed to start consumer: {e}"
            self.log_queue.put(error_msg)
            self.sdc_messages_queue.put(f"SDC Consumer: {error_msg}")
            self.consumer_running = False
            if hasattr(self, 'consumer_status_label'):
                self.consumer_status_label.config(text="ERROR", fg="#e53e3e")
            
    def monitor_consumer_output(self):
        """Monitor consumer output in background thread."""
        def read_consumer_output():
            try:
                while self.consumer_process and self.consumer_process.poll() is None:
                    if self.consumer_process.stdout:
                        line = self.consumer_process.stdout.readline()
                        if line:
                            line_stripped = line.strip()
                            # Put consumer output into SDC messages queue
                            self.sdc_messages_queue.put(f"Consumer: {line_stripped}")
                            # Also log important messages
                            if any(keyword in line_stripped.lower() for keyword in ['got update', 'got alarm', 'hr:', 'map:', 'temp:', 'found a match', 'successful']):
                                self.log_queue.put(f"Consumer: {line_stripped}")
                                
                            # Parse metric updates and put in data queue
                            self.parse_consumer_output(line_stripped)
                        else:
                            time.sleep(0.1)
                    else:
                        time.sleep(0.5)
            except Exception as e:
                self.log_queue.put(f"Consumer output monitoring error: {e}")
        
        # Start monitoring in background thread
        output_thread = threading.Thread(target=read_consumer_output, daemon=True)
        output_thread.start()
        
    def parse_consumer_output(self, line):
        """Parse consumer output to extract metric values."""
        try:
            # Look for metric updates in the format "  hr: 70.0"
            if ': ' in line and any(metric in line.lower() for metric in ['hr:', 'map:', 'sap:', 'dap:', 'temperature:', 'sao2:', 'rr:', 'etco2:']):
                parts = line.split(': ')
                if len(parts) >= 2:
                    metric_name = parts[0].strip().lower()
                    value_str = parts[1].strip()
                    
                    try:
                        value = float(value_str)
                        # Create data update
                        data_update = {metric_name: value}
                        self.data_queue.put(data_update)
                        self.sdc_messages_queue.put(f"SDC Metric Parsed: {metric_name} = {value}")
                        
                        # Mark as connected when we receive valid data and update timestamp
                        import time
                        self.last_data_time = time.time()
                        if not self.connected:
                            self.connected = True
                            self.log_queue.put("✓ SDC connection detected - receiving data")
                            
                    except ValueError:
                        pass  # Not a numeric value
                        
        except Exception as e:
            self.sdc_messages_queue.put(f"Consumer parse error: {e}")
            
    def initialize_digital_twin(self):
        """Initialize the digital twin model."""
        try:
            if not DT_MODEL_AVAILABLE or DigitalTwinModel is None:
                self.log_queue.put("✗ Digital twin model not available")
                self.dt_model = None
                return
                
            self.dt_model = DigitalTwinModel(
                patient_id="monitor_patient",
                param_file=self.current_patient,
                sleep=False  # Don't sleep in the model
            )
            self.log_queue.put("✓ Digital twin model initialized")
        except Exception as e:
            self.log_queue.put(f"✗ Failed to initialize digital twin: {e}")
            self.dt_model = None
            
    def create_widgets(self):
        """Create modern GUI with professional medical device styling."""
        # Set modern background for root window
        self.root.configure(bg='#0f1419')
        
        # Create main container with modern layout
        main_container = tk.Frame(self.root, bg='#0f1419')
        main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # Left side: Vital signs display
        left_frame = tk.Frame(main_container, bg='#0f1419')
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Modern title header
        title_frame = tk.Frame(left_frame, bg='#1a252f', height=40)
        title_frame.pack(fill=tk.X, pady=(0, 5))
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="● SDC DIGITAL TWIN MONITOR", 
                font=('Helvetica', 14, 'bold'), bg='#1a252f', fg='#00ff88').pack(pady=8)
        
        # Modern connection status
        status_section = tk.Frame(left_frame, bg='#1a252f')
        status_section.pack(fill=tk.X, pady=(0, 3))
        
        status_container = tk.Frame(status_section, bg='#2d3748')
        status_container.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(status_container, text="STATUS:", font=('Helvetica', 10, 'bold'), 
                bg='#2d3748', fg='#a0aec0').pack(side=tk.LEFT, padx=5)
        
        self.status_label = tk.Label(status_container, text="DISCONNECTED", 
                                     font=('Helvetica', 10, 'bold'), fg='#e53e3e', bg='#2d3748')
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(status_container, text="RECONNECT", command=self.reconnect_sdc,
                   style='Secondary.TButton').pack(side=tk.RIGHT, padx=5)
        
        # Modern provider controls
        provider_section = tk.Frame(left_frame, bg='#1a252f')
        provider_section.pack(fill=tk.X, pady=(0, 3))
        
        provider_container = tk.Frame(provider_section, bg='#2d3748')
        provider_container.pack(fill=tk.X, padx=5, pady=5)
        
        # First row: Provider label and main controls
        provider_main_row = tk.Frame(provider_container, bg='#2d3748')
        provider_main_row.pack(fill=tk.X, pady=(0, 2))
        
        tk.Label(provider_main_row, text="PROVIDER:", font=('Helvetica', 10, 'bold'), 
                 bg='#2d3748', fg='#a0aec0').pack(side=tk.LEFT, padx=5)
        
        ttk.Button(provider_main_row, text="START", command=self.start_provider,
                   style='Accent.TButton').pack(side=tk.LEFT, padx=2)
        
        ttk.Button(provider_main_row, text="STOP", command=self.stop_provider,
                   style='Danger.TButton').pack(side=tk.LEFT, padx=2)
        
        ttk.Button(provider_main_row, text="SDC MSGS", command=self.open_sdc_messages_window,
                   style='Info.TButton').pack(side=tk.RIGHT, padx=5)
        
        self.provider_status = tk.Label(provider_main_row, text="STOPPED", 
                                      font=('Helvetica', 9, 'bold'), fg='#e53e3e', bg='#2d3748')
        self.provider_status.pack(side=tk.RIGHT, padx=(5, 15))
        
        # Second row: Network adapter selection
        adapter_row = tk.Frame(provider_container, bg='#2d3748')
        adapter_row.pack(fill=tk.X, pady=(2, 0))
        
        tk.Label(adapter_row, text="Network Adapter:", font=('Helvetica', 9), 
                 bg='#2d3748', fg='#a0aec0').pack(side=tk.LEFT, padx=5)
        
        # Get available network adapters
        self.network_adapters = self.get_available_adapters()
        self.selected_adapter = tk.StringVar(value=self.network_adapter)
        
        adapter_combo = ttk.Combobox(adapter_row, textvariable=self.selected_adapter,
                                   values=self.network_adapters, state="readonly",
                                   width=8, font=('Helvetica', 9))
        adapter_combo.pack(side=tk.LEFT, padx=(5, 2))
        adapter_combo.bind('<<ComboboxSelected>>', self.on_adapter_change)
        
        # Current adapter indicator
        self.adapter_status = tk.Label(adapter_row, text=f"Current: {self.network_adapter}", 
                                     font=('Helvetica', 8), fg='#63b3ed', bg='#2d3748')
        self.adapter_status.pack(side=tk.LEFT, padx=(10, 5))
        
        # Compact vital signs display
        self.create_vital_signs_display(left_frame)
        
        # Log area (compact)
        self.create_log_area(left_frame)
        
        # Right side: Modern scrollable control panel
        right_frame = tk.Frame(main_container, bg='#0f1419', width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_frame.pack_propagate(False)  # Maintain fixed width
        
        # Create modern scrollable control panel
        self.create_scrollable_control_panel(right_frame)
        
        # Bind window resize events for dynamic font scaling
        self.root.bind('<Configure>', self.on_window_resize)
    
    def create_vital_signs_display(self, parent):
        """Create professional vital signs monitoring display with improved visuals."""
        # Main container with subtle gradient-like background
        vital_frame = tk.Frame(parent, bg='#1a252f', relief='flat', borderwidth=0)
        vital_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 3))
        
        # Title header with modern styling
        title_frame = tk.Frame(vital_frame, bg='#1a252f', height=30)
        title_frame.pack(fill=tk.X, padx=5, pady=3)
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="● PATIENT VITALS", 
                font=('Helvetica', 11, 'bold'), bg='#1a252f', fg='#00ff88').pack(anchor='w')
        
        # Professional medical device color scheme - subtle and readable
        params = [
            ('HR', 'hr', 'bpm', '#2d3748', '#00ff88'),      # Dark bg, bright green
            ('MAP', 'map', 'mmHg', '#2d3748', '#4fd1c7'),    # Dark bg, cyan
            ('SAP', 'sap', 'mmHg', '#2d3748', '#63b3ed'),    # Dark bg, light blue  
            ('DAP', 'dap', 'mmHg', '#2d3748', '#90cdf4'),    # Dark bg, sky blue
            ('Temp', 'temperature', '°C', '#2d3748', '#f687b3'),   # Dark bg, pink
            ('SpO2', 'sao2', '%', '#2d3748', '#fbb6ce'),     # Dark bg, light pink
            ('RR', 'rr', '/min', '#2d3748', '#c6f6d5'),      # Dark bg, light green
            ('EtCO2', 'etco2', 'mmHg', '#2d3748', '#fed7d7')  # Dark bg, light red
        ]
        
        # Create grid container
        grid_container = tk.Frame(vital_frame, bg='#1a252f')
        grid_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)
        
        # Store vital cards for dynamic resizing
        self.vital_cards = []
        
        for i, (name, key, unit, bg_color, text_color) in enumerate(params):
            row = i // 4
            col = i % 4
            
            # Modern card-style frame with subtle border
            card = tk.Frame(grid_container, bg=bg_color, relief='solid', borderwidth=1)
            card.grid(row=row, column=col, padx=2, pady=2, sticky='nsew', ipadx=10, ipady=8)
            
            # Parameter name - larger, uppercase for better readability
            name_label = tk.Label(card, text=name.upper(), font=('Helvetica', 10, 'bold'), 
                                bg=bg_color, fg='#a0aec0')
            name_label.pack(anchor='w')
            
            # Value - dynamically sized, prominent
            value_label = tk.Label(card, text="--", font=('Helvetica', 24, 'bold'), 
                                 bg=bg_color, fg=text_color)
            value_label.pack(anchor='w', expand=True, fill='both')
            setattr(self, f'{key}_value', value_label)
            
            # Unit - readable size, subtle
            unit_label = tk.Label(card, text=unit, font=('Helvetica', 9), 
                                bg=bg_color, fg='#718096')
            unit_label.pack(anchor='w')
            
            # Store card info for dynamic sizing
            self.vital_cards.append({
                'card': card,
                'value_label': value_label,
                'unit_label': unit_label,
                'key': key,
                'bg_color': bg_color,
                'text_color': text_color
            })
        
        # Configure responsive grid
        for i in range(4):
            grid_container.grid_columnconfigure(i, weight=1, minsize=95)
        for i in range(2):
            grid_container.grid_rowconfigure(i, weight=1, minsize=52)
            
        # Store grid container for dynamic sizing
        self.vital_grid_container = grid_container
        
        # Schedule initial font size update
        self.root.after(100, self.update_vital_font_sizes)
    
    def update_vital_font_sizes(self):
        """Dynamically adjust font sizes based on container dimensions."""
        if not hasattr(self, 'vital_cards') or not hasattr(self, 'vital_grid_container'):
            return
            
        try:
            # Get current container dimensions
            self.vital_grid_container.update_idletasks()
            container_width = self.vital_grid_container.winfo_width()
            container_height = self.vital_grid_container.winfo_height()
            
            # Calculate card dimensions (4 columns, 2 rows with padding)
            card_width = (container_width - 40) / 4  # Account for padding and margins
            card_height = (container_height - 20) / 2  # Account for padding and margins
            
            # Calculate optimal font size based on card dimensions
            # Use smaller dimension to ensure text fits in both width and height
            min_dimension = min(card_width, card_height)
            
            # Dynamic font sizing formula - scales with container size
            # Minimum 16pt, maximum 48pt, scales with card size for better readability
            base_font_size = max(16, min(48, int(min_dimension * 0.35)))
            
            # Update each vital sign value label
            for card_info in self.vital_cards:
                value_label = card_info['value_label']
                current_font = value_label.cget('font')
                
                # Create new font with dynamic size
                new_font = ('Helvetica', base_font_size, 'bold')
                value_label.config(font=new_font)
                
        except Exception as e:
            # Fallback to default size if sizing fails
            pass
            
        # Schedule next update for smooth resizing
        self.root.after(200, self.update_vital_font_sizes)
    
    def on_window_resize(self, event):
        """Handle window resize events to trigger font size updates."""
        # Only trigger on main window resize, not child widgets
        if event.widget == self.root:
            # Debounce resize events - only update after resize settles
            if hasattr(self, '_resize_after_id'):
                self.root.after_cancel(self._resize_after_id)
            self._resize_after_id = self.root.after(100, self.update_vital_font_sizes)
    
    def create_scrollable_control_panel(self, parent):
        """Create a modern scrollable control panel with improved visuals."""
        # Modern title header
        title_frame = tk.Frame(parent, bg='#1a252f', height=30)
        title_frame.pack(fill=tk.X, padx=0, pady=0)
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="● CONTROLS", 
                font=('Helvetica', 11, 'bold'), bg='#1a252f', fg='#00ff88').pack(anchor='w', padx=5)
        
        # Create modern canvas with improved styling
        canvas = tk.Canvas(parent, bg='#1a252f', highlightthickness=0, borderwidth=0)
        
        # Modern scrollbar with better styling
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview,
                               bg='#2d3748', troughcolor='#1a252f', 
                               activebackground='#4a5568', width=12)
        
        scrollable_frame = tk.Frame(canvas, bg='#1a252f')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Add all control sections to scrollable frame
        self.create_control_panel_content(scrollable_frame)
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def create_control_panel_content(self, parent):
        """Create modern control panel content with improved visual design."""
        # Patient selection with modern styling
        patient_section = tk.Frame(parent, bg='#1a252f')
        patient_section.pack(fill=tk.X, padx=5, pady=3)

        # Section header
        header = tk.Frame(patient_section, bg='#2d3748', height=25)
        header.pack(fill=tk.X, pady=(0, 2))
        header.pack_propagate(False)

        tk.Label(
            header,
            text="PATIENT SELECTION",
            font=('Helvetica', 10, 'bold'),
            bg='#2d3748', fg='#a0aec0'
        ).pack(anchor='w', padx=8, pady=4)

        # Controls container
        controls_container = tk.Frame(patient_section, bg='#2d3748')
        controls_container.pack(fill=tk.X, pady=2)

        # Get available patients
        patients = self.get_available_patients()
        self.patient_var = tk.StringVar(value=self.current_patient)

        # Modern dropdown styling
        patient_dropdown = ttk.Combobox(
            controls_container,
            textvariable=self.patient_var,
            values=patients,
            state='readonly',
            width=18,
            font=('Helvetica', 10)
        )
        patient_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 4), pady=6)
        patient_dropdown.bind('<<ComboboxSelected>>', self.on_patient_change)

        # Modern button styling
        load_btn = tk.Button(
            controls_container,
            text="LOAD",
            command=self.load_patient,
            bg='#00ff88', fg='#1a252f',
            font=('Helvetica', 10, 'bold'),
            activebackground='#00e574', activeforeground='#1a252f',
            relief='flat', borderwidth=0, width=8
        )
        load_btn.pack(side=tk.RIGHT, padx=(4, 8), pady=6)

        # Parameter controls with modern design
        param_section = tk.Frame(parent, bg='#1a252f')
        param_section.pack(fill=tk.X, padx=5, pady=5)

        # Create modern parameter controls
        self.create_ultra_compact_parameter_sliders(param_section)

        # Reflex controls with modern styling
        self.create_ultra_compact_reflex_controls(parent)

        # Emergency controls with improved design
        emergency_section = tk.Frame(parent, bg='#1a252f')
        emergency_section.pack(fill=tk.X, padx=5, pady=3)

        # Section header
        emerg_header = tk.Frame(emergency_section, bg='#2d3748', height=25)
        emerg_header.pack(fill=tk.X, pady=(0, 2))
        emerg_header.pack_propagate(False)

        tk.Label(
            emerg_header,
            text="EMERGENCY PROTOCOLS",
            font=('Helvetica', 10, 'bold'),
            bg='#2d3748', fg='#a0aec0'
        ).pack(anchor='w', padx=8, pady=4)

        # Emergency button container
        emerg_container = tk.Frame(emergency_section, bg='#2d3748')
        emerg_container.pack(fill=tk.X, pady=2)

        # Modern emergency buttons with better colors
        arrest_btn = tk.Button(
            emerg_container,
            text="CARDIAC ARREST",
            command=self.cardiac_arrest,
            bg='#e53e3e', fg='#1a252f',
            font=('Helvetica', 10, 'bold'),
            activebackground='#c53030', activeforeground='#1a252f',
            relief='flat', borderwidth=0
        )
        arrest_btn.grid(row=0, column=0, padx=4, pady=4, sticky='ew')

        hemor_btn = tk.Button(
            emerg_container,
            text="BLOOD SAMPLING",
            command=self.blood_sampling_toggle,
            bg='#dd6b20', fg='#1a252f',
            font=('Helvetica', 10, 'bold'),
            activebackground='#c05621', activeforeground='#1a252f',
            relief='flat', borderwidth=0
        )
        hemor_btn.grid(row=0, column=1, padx=4, pady=4, sticky='ew')

        ecg_leadoff_btn = tk.Button(
            emerg_container,
            text="ECG LEAD OFF",
            command=self.toggle_ecg_leadoff,
            bg='#ffa500', fg='#1a252f',
            font=('Helvetica', 10, 'bold'),
            activebackground='#ff8c00', activeforeground='#1a252f',
            relief='flat', borderwidth=0
        )
        ecg_leadoff_btn.grid(row=1, column=0, padx=4, pady=4, sticky='ew')
        # Store references for toggle styling
        self.blood_sampling_button = hemor_btn
        self.ecg_leadoff_button = ecg_leadoff_btn
        # Emergency status banner
        self.emerg_status_var = tk.StringVar(value="No active emergency modes")
        status_banner = tk.Label(emergency_section, textvariable=self.emerg_status_var,
                                 font=('Helvetica', 9, 'bold'), anchor='w', padx=8,
                                 bg='#24313d', fg='#718096')
        status_banner.pack(fill=tk.X, padx=2, pady=(2,4))

        # SDC Consumer Control Section
        self.create_sdc_consumer_controls(parent)

        # Active alarm status overview - ultra compact
        self.create_alarm_status_overview(parent)

        # Alarm configuration - ultra compact
        self.create_ultra_compact_alarm_controls(parent)
    
    def create_ultra_compact_parameter_sliders(self, parent):
        """Create modern, space-efficient parameter controls."""
        # Section header
        header = tk.Frame(parent, bg='#2d3748', height=25)
        header.pack(fill=tk.X, pady=(0, 3))
        header.pack_propagate(False)
        
        tk.Label(header, text="PHYSIOLOGICAL PARAMETERS", 
                font=('Helvetica', 8, 'bold'), bg='#2d3748', fg='#a0aec0').pack(anchor='w', padx=8, pady=4)
        
        # Parameters container
        params_container = tk.Frame(parent, bg='#2d3748')
        params_container.pack(fill=tk.X, pady=2)
        
        params = [
            ("FiO2", "fio2", 0, 100, 21, "%", "#4fd1c7"),
            ("Blood Vol", "blood_volume", 3000, 6000, 5000, "mL", "#63b3ed"),
            ("HR Set", "hr_setpoint", 40, 150, 70, "bpm", "#00ff88"),
            ("MAP Set", "map_setpoint", 50, 130, 90, "mmHg", "#f687b3"),
            ("RR Set", "rr_setpoint", 8, 40, 15, "bpm", "#ff9500"),
            ("Temp", "temperature", 35.0, 42.0, 37.0, "°C", "#fbb6ce")
        ]
        
        for i, (name, key, min_val, max_val, default, unit, accent_color) in enumerate(params):
            # Modern parameter row
            param_row = tk.Frame(params_container, bg='#1a252f', relief='solid', borderwidth=1)
            param_row.pack(fill=tk.X, padx=4, pady=2)
            
            # Left side: name and value
            left_frame = tk.Frame(param_row, bg='#1a252f')
            left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=4)
            
            tk.Label(left_frame, text=name.upper(), font=('Helvetica', 9, 'bold'), 
                    bg='#1a252f', fg=accent_color).pack(anchor='w')
            
            # Variable for parameter value
            var = tk.DoubleVar(value=default)
            setattr(self, f'{key}_var', var)
            
            # Value display
            value_label = tk.Label(left_frame, text=f"{default} {unit}", font=('Helvetica', 11, 'bold'), 
                                 bg='#1a252f', fg='#e2e8f0')
            value_label.pack(anchor='w')
            setattr(self, f'{key}_label', value_label)
            
            # Right side: slider and apply button
            right_frame = tk.Frame(param_row, bg='#1a252f')
            right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=6, pady=4)
            
            # Modern slider
            resolution = 0.1 if key == "temperature" else 1.0
            scale = tk.Scale(right_frame, from_=min_val, to=max_val, orient=tk.HORIZONTAL,
                           variable=var, resolution=resolution, 
                           command=lambda v, k=key: self.on_parameter_display_change(k, v),
                           length=120, font=('Helvetica', 6), showvalue=False, width=10,
                           bg='#1a252f', fg=accent_color, troughcolor='#2d3748',
                           highlightthickness=0, borderwidth=0)
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
            
            # Modern apply button
            apply_btn = tk.Button(right_frame, text="SET", command=lambda k=key: self.apply_parameter(k),
                                bg=accent_color, fg='#1a252f', font=('Helvetica', 7, 'bold'),
                                activebackground='#a0aec0', activeforeground='#1a252f',
                                relief='flat', borderwidth=0, width=4)
            apply_btn.pack(side=tk.RIGHT)

            # Applied label (live value reflecting model state)
            applied = tk.Label(right_frame, text="--", font=('Helvetica', 7),
                               bg='#1a252f', fg='#a0aec0', width=6, anchor='e')
            applied.pack(side=tk.RIGHT, padx=(0,4))
            setattr(self, f"{key}_applied_label", applied)
    
    def create_ultra_compact_reflex_controls(self, parent):
        """Create modern reflex control interface."""
        reflex_section = tk.Frame(parent, bg='#1a252f')
        reflex_section.pack(fill=tk.X, padx=5, pady=3)
        
        # Section header
        header = tk.Frame(reflex_section, bg='#2d3748', height=25)
        header.pack(fill=tk.X, pady=(0, 2))
        header.pack_propagate(False)
        
        tk.Label(header, text="PHYSIOLOGICAL REFLEXES", 
                font=('Helvetica', 8, 'bold'), bg='#2d3748', fg='#a0aec0').pack(anchor='w', padx=8, pady=4)
        
        # Reflexes container
        reflex_container = tk.Frame(reflex_section, bg='#2d3748')
        reflex_container.pack(fill=tk.X, pady=2)

        # Baroreflex control row
        baro_row = tk.Frame(reflex_container, bg='#1a252f', relief='solid', borderwidth=1)
        baro_row.pack(fill=tk.X, padx=4, pady=2)

        tk.Label(baro_row, text="BAROREFLEX", font=('Helvetica', 7, 'bold'), 
            bg='#1a252f', fg='#63b3ed').pack(side=tk.LEFT, padx=8, pady=4)

        # Baroreflex toggle and status (default OFF)
        self.baroreflex_enabled = tk.BooleanVar(value=False)

        baro_on_btn = tk.Button(baro_row, text="ON", command=lambda: self.toggle_baroreflex(True),
                  bg='#00ff88', fg='#1a252f', font=('Helvetica', 7, 'bold'),
                  activebackground='#00e574', activeforeground='#1a252f',
                  relief='flat', borderwidth=0, width=4)
        baro_on_btn.pack(side=tk.RIGHT, padx=2)

        baro_off_btn = tk.Button(baro_row, text="OFF", command=lambda: self.toggle_baroreflex(False),
                   bg='#e53e3e', fg='#1a252f', font=('Helvetica', 7, 'bold'),
                   activebackground='#c53030', activeforeground='#1a252f',
                   relief='flat', borderwidth=0, width=4)
        baro_off_btn.pack(side=tk.RIGHT, padx=2)

        self.baro_status_label = tk.Label(baro_row, text="OFF", font=('Helvetica', 7, 'bold'), 
             fg='#e53e3e', bg='#1a252f')
        self.baro_status_label.pack(side=tk.RIGHT, padx=(8, 2))
        
        # Chemoreceptor control row
        chemo_row = tk.Frame(reflex_container, bg='#1a252f', relief='solid', borderwidth=1)
        chemo_row.pack(fill=tk.X, padx=4, pady=2)

        tk.Label(chemo_row, text="CHEMORECEPTOR", font=('Helvetica', 7, 'bold'), 
            bg='#1a252f', fg='#63b3ed').pack(side=tk.LEFT, padx=8, pady=4)

        self.chemoreceptor_enabled = tk.BooleanVar(value=False)

        chemo_on_btn = tk.Button(chemo_row, text="ON", command=lambda: self.toggle_chemoreceptor(True),
                   bg='#00ff88', fg='#1a252f', font=('Helvetica', 7, 'bold'),
                   activebackground='#00e574', activeforeground='#1a252f',
                   relief='flat', borderwidth=0, width=4)
        chemo_on_btn.pack(side=tk.RIGHT, padx=2)

        chemo_off_btn = tk.Button(chemo_row, text="OFF", command=lambda: self.toggle_chemoreceptor(False),
                bg='#e53e3e', fg='#1a252f', font=('Helvetica', 7, 'bold'),
                activebackground='#c53030', activeforeground='#1a252f',
                relief='flat', borderwidth=0, width=4)
        chemo_off_btn.pack(side=tk.RIGHT, padx=2)

        self.chemo_status_label = tk.Label(chemo_row, text="OFF", font=('Helvetica', 7, 'bold'), 
             fg='#e53e3e', bg='#1a252f')
        self.chemo_status_label.pack(side=tk.RIGHT, padx=(8, 2))
    
    def create_sdc_consumer_controls(self, parent):
        """Create SDC Consumer start/stop controls."""
        consumer_section = tk.Frame(parent, bg='#1a252f')
        consumer_section.pack(fill=tk.X, padx=5, pady=3)
        
        # Section header
        header = tk.Frame(consumer_section, bg='#2d3748', height=25)
        header.pack(fill=tk.X, pady=(0, 2))
        header.pack_propagate(False)
        
        tk.Label(header, text="SDC CONSUMER CONTROL", 
                font=('Helvetica', 8, 'bold'), bg='#2d3748', fg='#a0aec0').pack(anchor='w', padx=8, pady=4)
        
        # Consumer control container
        consumer_container = tk.Frame(consumer_section, bg='#2d3748')
        consumer_container.pack(fill=tk.X, pady=2)
        
        # Consumer control row
        consumer_row = tk.Frame(consumer_container, bg='#1a252f', relief='solid', borderwidth=1)
        consumer_row.pack(fill=tk.X, padx=4, pady=2)
        
        tk.Label(consumer_row, text="CONSUMER", font=('Helvetica', 7, 'bold'), 
                bg='#1a252f', fg='#63b3ed').pack(side=tk.LEFT, padx=8, pady=4)
        
        # Consumer status and control (default OFF)
        self.consumer_enabled = tk.BooleanVar(value=False)
        
        consumer_start_btn = tk.Button(consumer_row, text="START", command=lambda: self.toggle_consumer(True),
                                      bg='#00ff88', fg='#1a252f', font=('Helvetica', 7, 'bold'),
                                      activebackground='#00e574', activeforeground='#1a252f',
                                      relief='flat', borderwidth=0, width=5)
        consumer_start_btn.pack(side=tk.RIGHT, padx=2)
        
        consumer_stop_btn = tk.Button(consumer_row, text="STOP", command=lambda: self.toggle_consumer(False),
                                     bg='#e53e3e', fg='#1a252f', font=('Helvetica', 7, 'bold'),
                                     activebackground='#c53030', activeforeground='#1a252f',
                                     relief='flat', borderwidth=0, width=5)
        consumer_stop_btn.pack(side=tk.RIGHT, padx=2)
        
        self.consumer_status_label = tk.Label(consumer_row, text="OFF", font=('Helvetica', 7, 'bold'), 
                                             fg='#e53e3e', bg='#1a252f')
        self.consumer_status_label.pack(side=tk.RIGHT, padx=(8, 2))
    
    def create_ultra_compact_alarm_controls(self, parent):
        """Create ultra compact alarm configuration controls."""
        alarm_frame = tk.LabelFrame(
            parent,
            text="Alarms",
            font=('Helvetica', 11, 'bold'),
            bg='#34495e', fg='#1a252f'
        )
        alarm_frame.pack(fill=tk.X, padx=4, pady=4)

        # Patient profile - single line
        profile_line = tk.Frame(alarm_frame, bg='#34495e')
        profile_line.pack(fill=tk.X, padx=4, pady=2)

        tk.Label(
            profile_line, text="Profile:",
            font=('Helvetica', 10, 'bold'), bg='#34495e', fg='#1a252f'
        ).pack(side=tk.LEFT)

        self.patient_profile = tk.StringVar(value="adult")
        profile_combo = ttk.Combobox(
            profile_line, textvariable=self.patient_profile,
            values=["adult", "pediatric", "neonatal"], state="readonly",
            width=12, font=('Helvetica', 10)
        )
        profile_combo.pack(side=tk.LEFT, padx=(6, 0))
        profile_combo.bind('<<ComboboxSelected>>', self.on_patient_profile_change)

        apply_btn = tk.Button(
            profile_line, text="Apply",
            command=self.apply_alarm_settings,
            bg='#3498db', fg='#1a252f', font=('Helvetica', 10, 'bold'),
            activebackground='#2980b9', activeforeground='#1a252f',
            relief='raised', borderwidth=1, width=8
        )
        apply_btn.pack(side=tk.RIGHT)

        # Ultra compact threshold grid
        grid_frame = tk.Frame(alarm_frame, bg='#34495e')
        grid_frame.pack(fill=tk.X, padx=4, pady=2)

        # Headers
        headers = ["Param", "Low", "High", "En"]
        for i, header in enumerate(headers):
            tk.Label(
                grid_frame, text=header,
                font=('Helvetica', 10, 'bold'), bg='#34495e', fg='#1a252f', width=10
            ).grid(row=0, column=i, padx=4, pady=2)

        # HR row
        tk.Label(grid_frame, text="HR", font=('Helvetica', 10, 'bold'), bg='#34495e', fg='#1a252f', width=10).grid(row=1, column=0, padx=4, pady=2)
        self.hr_low_threshold = tk.StringVar(value="60")
        hr_low = tk.Entry(grid_frame, textvariable=self.hr_low_threshold, width=7, font=('Helvetica', 10),
                          bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        hr_low.grid(row=1, column=1, padx=4, pady=2)
        self.hr_high_threshold = tk.StringVar(value="100")
        hr_high = tk.Entry(grid_frame, textvariable=self.hr_high_threshold, width=7, font=('Helvetica', 10),
                           bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        hr_high.grid(row=1, column=2, padx=4, pady=2)
        self.hr_enabled = tk.BooleanVar(value=True)
        hr_check = tk.Checkbutton(grid_frame, variable=self.hr_enabled, font=('Helvetica', 10), bg='#34495e', fg='#1a252f',
                                  selectcolor='#2c3e50', activebackground='#34495e')
        hr_check.grid(row=1, column=3, padx=4, pady=2)

        # MAP row
        tk.Label(grid_frame, text="MAP", font=('Helvetica', 10, 'bold'), bg='#34495e', fg='#1a252f', width=10).grid(row=2, column=0, padx=4, pady=2)
        self.map_low_threshold = tk.StringVar(value="65")
        map_low = tk.Entry(grid_frame, textvariable=self.map_low_threshold, width=7, font=('Helvetica', 10),
                           bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        map_low.grid(row=2, column=1, padx=4, pady=2)
        self.map_high_threshold = tk.StringVar(value="110")
        map_high = tk.Entry(grid_frame, textvariable=self.map_high_threshold, width=7, font=('Helvetica', 10),
                            bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        map_high.grid(row=2, column=2, padx=4, pady=2)
        self.map_enabled = tk.BooleanVar(value=True)
        map_check = tk.Checkbutton(grid_frame, variable=self.map_enabled, font=('Helvetica', 10), bg='#34495e', fg='#1a252f',
                                   selectcolor='#2c3e50', activebackground='#34495e')
        map_check.grid(row=2, column=3, padx=4, pady=2)

        # SpO2 row
        tk.Label(grid_frame, text="SpO2", font=('Helvetica', 10, 'bold'), bg='#34495e', fg='#1a252f', width=10).grid(row=3, column=0, padx=4, pady=2)
        self.spo2_low_threshold = tk.StringVar(value="90")
        spo2_low = tk.Entry(grid_frame, textvariable=self.spo2_low_threshold, width=7, font=('Helvetica', 10),
                            bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        spo2_low.grid(row=3, column=1, padx=4, pady=2)
        self.spo2_high_threshold = tk.StringVar(value="100")
        spo2_high = tk.Entry(grid_frame, textvariable=self.spo2_high_threshold, width=7, font=('Helvetica', 10),
                             bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        spo2_high.grid(row=3, column=2, padx=4, pady=2)
        self.spo2_enabled = tk.BooleanVar(value=True)
        spo2_check = tk.Checkbutton(grid_frame, variable=self.spo2_enabled, font=('Helvetica', 10), bg='#34495e', fg='#1a252f',
                                    selectcolor='#2c3e50', activebackground='#34495e')
        spo2_check.grid(row=3, column=3, padx=4, pady=2)

        # Temperature row
        tk.Label(grid_frame, text="Temp", font=('Helvetica', 10, 'bold'), bg='#34495e', fg='#1a252f', width=10).grid(row=4, column=0, padx=4, pady=2)
        self.temp_low_threshold = tk.StringVar(value="36.0")
        temp_low = tk.Entry(grid_frame, textvariable=self.temp_low_threshold, width=7, font=('Helvetica', 10),
                            bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        temp_low.grid(row=4, column=1, padx=4, pady=2)
        self.temp_high_threshold = tk.StringVar(value="38.5")
        temp_high = tk.Entry(grid_frame, textvariable=self.temp_high_threshold, width=7, font=('Helvetica', 10),
                             bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        temp_high.grid(row=4, column=2, padx=4, pady=2)
        self.temp_enabled = tk.BooleanVar(value=True)
        temp_check = tk.Checkbutton(grid_frame, variable=self.temp_enabled, font=('Helvetica', 10), bg='#34495e', fg='#1a252f',
                                    selectcolor='#2c3e50', activebackground='#34495e')
        temp_check.grid(row=4, column=3, padx=4, pady=2)

        # EtCO2 row
        tk.Label(grid_frame, text="EtCO2", font=('Helvetica', 10, 'bold'), bg='#34495e', fg='#1a252f', width=10).grid(row=5, column=0, padx=4, pady=2)
        self.etco2_low_threshold = tk.StringVar(value="30")
        etco2_low = tk.Entry(grid_frame, textvariable=self.etco2_low_threshold, width=7, font=('Helvetica', 10),
                             bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        etco2_low.grid(row=5, column=1, padx=4, pady=2)
        self.etco2_high_threshold = tk.StringVar(value="50")
        etco2_high = tk.Entry(grid_frame, textvariable=self.etco2_high_threshold, width=7, font=('Helvetica', 10),
                              bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        etco2_high.grid(row=5, column=2, padx=4, pady=2)
        self.etco2_enabled = tk.BooleanVar(value=True)
        etco2_check = tk.Checkbutton(grid_frame, variable=self.etco2_enabled, font=('Helvetica', 10), bg='#34495e', fg='#1a252f',
                                     selectcolor='#2c3e50', activebackground='#34495e')
        etco2_check.grid(row=5, column=3, padx=4, pady=2)

        # Respiratory Rate row
        tk.Label(grid_frame, text="RR", font=('Helvetica', 10, 'bold'), bg='#34495e', fg='#1a252f', width=10).grid(row=6, column=0, padx=4, pady=2)
        self.rr_low_threshold = tk.StringVar(value="12")
        rr_low = tk.Entry(grid_frame, textvariable=self.rr_low_threshold, width=7, font=('Helvetica', 10),
                          bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        rr_low.grid(row=6, column=1, padx=4, pady=2)
        self.rr_high_threshold = tk.StringVar(value="25")
        rr_high = tk.Entry(grid_frame, textvariable=self.rr_high_threshold, width=7, font=('Helvetica', 10),
                           bg='#2c3e50', fg='#e2e8f0', insertbackground='#e2e8f0')
        rr_high.grid(row=6, column=2, padx=4, pady=2)
        self.rr_enabled = tk.BooleanVar(value=True)
        rr_check = tk.Checkbutton(grid_frame, variable=self.rr_enabled, font=('Helvetica', 10), bg='#34495e', fg='#1a252f',
                                  selectcolor='#2c3e50', activebackground='#34495e')
        rr_check.grid(row=6, column=3, padx=4, pady=2)

        # Initialize alarm module if not already done
        if self.alarm_module is None:
            self.alarm_module = AlarmModule(patient_id="default_patient")

    def create_alarm_status_overview(self, parent):
        """Create modern alarm status overview with enhanced visuals."""
        status_section = tk.Frame(parent, bg='#1a252f')
        status_section.pack(fill=tk.X, padx=5, pady=3)

        # Section header
        header = tk.Frame(status_section, bg='#2d3748', height=25)
        header.pack(fill=tk.X, pady=(0, 2))
        header.pack_propagate(False)

        tk.Label(
            header, text="● ALARM STATUS",
            font=('Helvetica', 10, 'bold'), bg='#2d3748', fg='#a0aec0'
        ).pack(anchor='w', padx=8, pady=4)

        # Status container
        status_container = tk.Frame(status_section, bg='#2d3748')
        status_container.pack(fill=tk.X, pady=2)

        # Initialize alarm status labels dictionary
        self.alarm_status_labels = {}

        # Create status indicators for each alarm parameter with color coding
        alarm_params = [
            ("HR", "Heart Rate", "#00ff88"),
            ("MAP", "Blood Pressure", "#4fd1c7"),
            ("SAP", "Systolic BP", "#63b3ed"),
            ("DAP", "Diastolic BP", "#90cdf4"),
            ("Temp", "Temperature", "#f687b3"),
            ("SpO2", "Oxygen Saturation", "#fbb6ce"),
            ("RR", "Respiratory Rate", "#c6f6d5"),
            ("EtCO2", "End-tidal CO2", "#fed7d7")
        ]

        # Create modern grid layout for alarm status
        status_grid = tk.Frame(status_container, bg='#2d3748')
        status_grid.pack(fill=tk.X, padx=4, pady=4)

        for i, (param_short, param_full, accent_color) in enumerate(alarm_params):
            row = i // 4  # 4 parameters per row for compact layout
            col = i % 4

            # Modern alarm status card
            param_card = tk.Frame(status_grid, bg='#1a252f', relief='solid', borderwidth=1)
            param_card.grid(row=row, column=col, padx=2, pady=2, sticky='ew', ipadx=4, ipady=2)

            # Parameter name with accent color
            param_label = tk.Label(
                param_card, text=param_short,
                font=('Helvetica', 10, 'bold'), bg='#1a252f', fg=accent_color
            )
            param_label.pack(anchor='w', padx=4, pady=(2, 0))

            # Status indicator - larger and more prominent
            status_indicator = tk.Label(
                param_card, text="OK",
                font=('Helvetica', 11, 'bold'), bg='#1a252f', fg='#00ff88'
            )
            status_indicator.pack(anchor='w', padx=4, pady=(0, 2))

            # Store reference for updates
            self.alarm_status_labels[param_short] = status_indicator

        # Configure responsive grid
        for col in range(4):
            status_grid.grid_columnconfigure(col, weight=1)

        # Add modern "All Clear" indicator
        self.all_clear_label = tk.Label(
            status_container, text="✓ ALL PARAMETERS NORMAL",
            font=('Helvetica', 10, 'bold'), bg='#2d3748', fg='#00ff88'
        )
        self.all_clear_label.pack(pady=4)

    def update_alarm_status_display(self, alarm_events):
        """Update the alarm status overview display based on current alarms."""
        try:
            if not hasattr(self, 'alarm_status_labels'):
                return
                
            # Map alarm parameter names to display names
            param_mapping = {
                'HeartRate': 'HR',
                'BloodPressureMean': 'MAP',
                # Map systolic/diastolic to MAP indicator in compact view
                'BloodPressureSystolic': 'MAP',
                'BloodPressureDiastolic': 'MAP',
                'SpO2': 'SpO2',
                'SaO2': 'SpO2',  # Alternative mapping
                'Temperature': 'Temp',
                'EtCO2': 'EtCO2',
                'RespiratoryRate': 'RR'
            }
            
            # Reset all indicators to OK
            for param_short, label in self.alarm_status_labels.items():
                label.config(text="OK", fg='#00ff88')
            
            # Track active alarms
            active_alarms = []
            
            # Update indicators based on alarm events
            for alarm_event in alarm_events:
                param_name = alarm_event['parameter']
                display_name = param_mapping.get(param_name, param_name)
                
                if display_name in self.alarm_status_labels:
                    label = self.alarm_status_labels[display_name]
                    
                    if alarm_event['active']:
                        # Determine alarm type and color
                        alarm_type = alarm_event.get('alarm_type', '').upper()
                        value = alarm_event.get('value', 0)
                        
                        if 'HIGH' in alarm_type or 'UPPER' in alarm_type:
                            label.config(text="HIGH", fg='#e53e3e')
                        elif 'LOW' in alarm_type or 'LOWER' in alarm_type:
                            label.config(text="LOW", fg='#ff9500')
                        else:
                            label.config(text="ALARM", fg='#e53e3e')
                        
                        active_alarms.append(display_name)
            
            # Update "All Clear" indicator
            if active_alarms:
                self.all_clear_label.config(text=f"⚠ {len(active_alarms)} Active Alarm(s)", fg='#e53e3e')
            else:
                self.all_clear_label.config(text="✓ All Parameters Normal", fg='#00ff88')
                
        except Exception as e:
            print(f"Error updating alarm status display: {e}")

    def update_alarm_status_from_status(self, status_dict):
        """Update the alarm status overview display from persistent status dict."""
        try:
            if not hasattr(self, 'alarm_status_labels'):
                return

            # Map config parameters to compact display labels
            param_mapping = {
                'HeartRate': 'HR',
                'BloodPressureMean': 'MAP',
                'BloodPressureSystolic': 'MAP',
                'BloodPressureDiastolic': 'MAP',
                'SpO2': 'SpO2',
                'Temperature': 'Temp',
                'EtCO2': 'EtCO2',
                'RespiratoryRate': 'RR'
            }

            # Default everything to OK first
            for param_short, label in self.alarm_status_labels.items():
                label.config(text="OK", fg='#00ff88')

            active_alarms = []
            for param_name, state in status_dict.items():
                display_name = param_mapping.get(param_name)
                if not display_name or display_name not in self.alarm_status_labels:
                    continue
                label = self.alarm_status_labels[display_name]
                if state.get('active'):
                    alarm_type = str(state.get('alarm_type', '')).upper()
                    if 'CRITICAL' in alarm_type:
                        label.config(text="CRIT", fg='#ff0000')
                    elif 'HIGH' in alarm_type or 'UPPER' in alarm_type:
                        label.config(text="HIGH", fg='#e53e3e')
                    elif 'LOW' in alarm_type or 'LOWER' in alarm_type:
                        label.config(text="LOW", fg='#ff9500')
                    else:
                        label.config(text="ALARM", fg='#e53e3e')
                    active_alarms.append(display_name)

            # Update All Clear indicator
            if active_alarms:
                self.all_clear_label.config(text=f"⚠ {len(active_alarms)} Active Alarm(s)", fg='#e53e3e')
            else:
                self.all_clear_label.config(text="✓ All Parameters Normal", fg='#00ff88')
        except Exception as e:
            print(f"Error updating alarm status from status: {e}")

    def apply_alarm_settings(self):
        """Apply alarm threshold settings."""
        if not self.alarm_module:
            self.log_event_safe("Alarm module not initialized")
            return
        try:
            # Update thresholds using the correct parameter names
            self.alarm_module.update_alarm_threshold("HeartRate", "lower_limit", float(self.hr_low_threshold.get()))
            self.alarm_module.update_alarm_threshold("HeartRate", "upper_limit", float(self.hr_high_threshold.get()))
            self.alarm_module.update_alarm_threshold("BloodPressureMean", "lower_limit", float(self.map_low_threshold.get()))
            self.alarm_module.update_alarm_threshold("BloodPressureMean", "upper_limit", float(self.map_high_threshold.get()))
            self.alarm_module.update_alarm_threshold("SpO2", "lower_limit", float(self.spo2_low_threshold.get()))
            self.alarm_module.update_alarm_threshold("SpO2", "upper_limit", float(self.spo2_high_threshold.get()))
            self.alarm_module.update_alarm_threshold("Temperature", "lower_limit", float(self.temp_low_threshold.get()))
            self.alarm_module.update_alarm_threshold("Temperature", "upper_limit", float(self.temp_high_threshold.get()))
            self.alarm_module.update_alarm_threshold("EtCO2", "lower_limit", float(self.etco2_low_threshold.get()))
            self.alarm_module.update_alarm_threshold("EtCO2", "upper_limit", float(self.etco2_high_threshold.get()))
            self.alarm_module.update_alarm_threshold("RespiratoryRate", "lower_limit", float(self.rr_low_threshold.get()))
            self.alarm_module.update_alarm_threshold("RespiratoryRate", "upper_limit", float(self.rr_high_threshold.get()))
            # enabled flags
            config = self.alarm_module.get_alarm_config()
            config["alarm_parameters"]["HeartRate"]["enabled"] = self.hr_enabled.get()
            config["alarm_parameters"]["BloodPressureMean"]["enabled"] = self.map_enabled.get()
            config["alarm_parameters"]["SpO2"]["enabled"] = self.spo2_enabled.get()
            config["alarm_parameters"]["Temperature"]["enabled"] = self.temp_enabled.get()
            config["alarm_parameters"]["EtCO2"]["enabled"] = self.etco2_enabled.get()
            config["alarm_parameters"]["RespiratoryRate"]["enabled"] = self.rr_enabled.get()
            self.alarm_module.save_alarm_config()
            # NEW: write IPC file for provider (alarm updates)
            try:
                import json, os
                base_path = os.getcwd()
                ipc_path = os.path.join(base_path, "alarm_updates.tmp")
                payload = {p: {k: v for k, v in param_cfg.items() if k in ("lower_limit","upper_limit")}
                           for p, param_cfg in config["alarm_parameters"].items()}
                with open(ipc_path, 'w') as f:
                    json.dump(payload, f)
                self.log_event_safe("Alarm settings applied + IPC written for provider")
            except Exception as e_ipc:
                self.log_event_safe(f"Alarm settings applied but IPC write failed: {e_ipc}")
        except ValueError as e:
            self.log_event_safe(f"Invalid threshold value: {e}")
        except Exception as e:
            self.log_event_safe(f"Error applying alarm settings: {e}")
            
    def on_patient_profile_change(self, event=None):
        """Handle patient profile change."""
        profile = self.patient_profile.get()
        if self.alarm_module:
            self.alarm_module.set_patient_profile(profile)
            # Update GUI thresholds based on profile
            self.update_threshold_gui_from_profile(profile)
            
    def update_threshold_gui_from_profile(self, profile):
        """Update GUI threshold values based on patient profile."""
        if not self.alarm_module:
            return
            
        # Set patient profile in alarm module
        self.alarm_module.set_patient_profile(profile)
        
        # Get updated configuration
        config = self.alarm_module.get_alarm_config()
        
        try:
            # Update GUI with current configuration values
            hr_config = config["alarm_parameters"]["HeartRate"]
            self.hr_low_threshold.set(str(int(hr_config["lower_limit"])))
            self.hr_high_threshold.set(str(int(hr_config["upper_limit"])))
            
            map_config = config["alarm_parameters"]["BloodPressureMean"]
            self.map_low_threshold.set(str(int(map_config["lower_limit"])))
            self.map_high_threshold.set(str(int(map_config["upper_limit"])))
            
            spo2_config = config["alarm_parameters"]["SpO2"]
            self.spo2_low_threshold.set(str(int(spo2_config["lower_limit"])))
            self.spo2_high_threshold.set(str(int(spo2_config["upper_limit"])))
            
            # Load new alarm parameters if they exist
            if "Temperature" in config["alarm_parameters"]:
                temp_config = config["alarm_parameters"]["Temperature"]
                self.temp_low_threshold.set(str(float(temp_config["lower_limit"])))
                self.temp_high_threshold.set(str(float(temp_config["upper_limit"])))
            
            if "EtCO2" in config["alarm_parameters"]:
                etco2_config = config["alarm_parameters"]["EtCO2"]
                self.etco2_low_threshold.set(str(int(etco2_config["lower_limit"])))
                self.etco2_high_threshold.set(str(int(etco2_config["upper_limit"])))
            
            if "RespiratoryRate" in config["alarm_parameters"]:
                rr_config = config["alarm_parameters"]["RespiratoryRate"]
                self.rr_low_threshold.set(str(int(rr_config["lower_limit"])))
                self.rr_high_threshold.set(str(int(rr_config["upper_limit"])))
            
        except (KeyError, ValueError) as e:
            self.log_event_safe(f"Error updating GUI from profile: {e}")
            # Fallback to default values if config is incomplete
            if profile == "neonatal":
                self.hr_low_threshold.set("100")
                self.hr_high_threshold.set("180")
                self.map_low_threshold.set("35")
                self.map_high_threshold.set("60")
                self.spo2_low_threshold.set("85")
                self.spo2_high_threshold.set("100")
                # Neonatal-specific ranges
                self.temp_low_threshold.set("36.5")
                self.temp_high_threshold.set("37.5")
                self.etco2_low_threshold.set("30")
                self.etco2_high_threshold.set("45")
                self.rr_low_threshold.set("25")
                self.rr_high_threshold.set("60")
            elif profile == "pediatric":
                self.hr_low_threshold.set("80")
                self.hr_high_threshold.set("140")
                self.map_low_threshold.set("50")
                self.map_high_threshold.set("90")
                self.spo2_low_threshold.set("90")
                self.spo2_high_threshold.set("100")
                # Pediatric-specific ranges
                self.temp_low_threshold.set("36.0")
                self.temp_high_threshold.set("38.0")
                self.etco2_low_threshold.set("30")
                self.etco2_high_threshold.set("45")
                self.rr_low_threshold.set("20")
                self.rr_high_threshold.set("40")
            else:  # adult
                self.hr_low_threshold.set("60")
                self.hr_high_threshold.set("100")
                self.map_low_threshold.set("65")
                self.map_high_threshold.set("110")
                self.spo2_low_threshold.set("90")
                self.spo2_high_threshold.set("100")
                # Adult ranges
                self.temp_low_threshold.set("36.0")
                self.temp_high_threshold.set("38.5")
                self.etco2_low_threshold.set("30")
                self.etco2_high_threshold.set("50")
                self.rr_low_threshold.set("12")
                self.rr_high_threshold.set("25")
            
    def create_log_area(self, parent):
        """Create log display area."""
        log_frame = tk.LabelFrame(parent, text="System Log", 
                                  font=('Arial', 10, 'bold'), bg='#2c3e50', fg='#1a252f')
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # Create text widget with scrollbar
        log_container = tk.Frame(log_frame, bg='#2c3e50')
        log_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = tk.Text(log_container, height=8, font=('Consolas', 9), 
                                 bg='#0b141a', fg='#e2e8f0', state=tk.DISABLED)
        scrollbar = tk.Scrollbar(log_container, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
    def process_queues(self):
        """Process thread-safe queues from main thread."""
        # Process log messages
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_event_safe(message)
        except queue.Empty:
            pass
        
        # Process data updates
        try:
            while True:
                data = self.data_queue.get_nowait()
                self.update_display_safe(data)
        except queue.Empty:
            pass
        
        # Check for connection timeout (no data for 30 seconds)
        import time
        current_time = time.time()
        if self.connected and self.last_data_time > 0 and (current_time - self.last_data_time) > 30:
            self.connected = False
            self.log_queue.put("⚠ SDC connection timeout - no data received for 30 seconds")
        
        # Update connection status with modern colors
        if self.connected:
            self.status_label.config(text="CONNECTED", fg="#00ff88", font=('Helvetica', 8, 'bold'))
        else:
            self.status_label.config(text="DISCONNECTED", fg="#e53e3e", font=('Helvetica', 8, 'bold'))
        
        # Schedule next queue processing
        self.root.after(100, self.process_queues)
        
    def log_event_safe(self, message):
        """Thread-safe logging."""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f"[{timestamp}] {message}"
            
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, log_message + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
            
            # Keep only last 100 lines
            lines = self.log_text.get("1.0", tk.END).split("\n")
            if len(lines) > 100:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.delete("1.0", f"{len(lines)-100}.0")
                self.log_text.config(state=tk.DISABLED)
        except Exception as e:
                                             print(f"Logging error: {e}")
            
    def update_display_safe(self, data):
        """Thread-safe display update."""
        try:
            if isinstance(data, dict):
                self.current_values.update(data)
            # Update display labels
            for param, value in self.current_values.items():
                if hasattr(self, f'{param}_value'):
                    label = getattr(self, f'{param}_value')
                    if param == 'hr' and getattr(self, 'ecg_lead_off_active', False):
                        label.config(text='NOT\nMEAS', fg='#ffcc66')
                        # Dim unit label
                        for card_info in getattr(self, 'vital_cards', []):
                            if card_info.get('key') == 'hr':
                                try:
                                    card_info['unit_label'].config(fg='#444c56')
                                except Exception:
                                    pass
                                break
                        continue
                    if param in ['hr', 'map', 'sap', 'dap', 'sao2', 'rr']:
                        label.config(text=f"{value:.0f}")
                    elif param == 'temperature':
                        label.config(text=f"{value:.1f}")
                    elif param == 'etco2':
                        label.config(text=f"{value:.0f}")
            # If ECG lead off just cleared, restore HR label color & unit
            if not getattr(self, 'ecg_lead_off_active', False):
                try:
                    for card_info in getattr(self, 'vital_cards', []):
                        if card_info.get('key') == 'hr':
                            card_info['value_label'].config(fg=card_info['text_color'])
                            card_info['unit_label'].config(fg='#718096')
                            break
                except Exception:
                    pass
            if self.alarm_module:
                self.evaluate_current_alarms()
        except Exception as e:
            print(f"Display update error: {e}")
    
    def evaluate_current_alarms(self):
        """Evaluate alarms based on current vital signs."""
        try:
            # Check if alarm module is available
            if not self.alarm_module:
                return
                
            # Prepare vital signs for alarm evaluation (using correct parameter mapping)
            vital_signs = {
                'HR': self.current_values.get('hr', 0),
                'MAP': self.current_values.get('map', 0),
                'SaO2': self.current_values.get('sao2', 0),  # Note: using sao2 as SaO2
                'TEMP': self.current_values.get('temperature', 37.0),
                'RR': self.current_values.get('rr', 15),
                'EtCO2': self.current_values.get('etco2', 40)  # Added EtCO2
            }
            
            # Evaluate alarms (produces events only on transitions)
            alarm_events = self.alarm_module.evaluate_alarms(vital_signs)

            # Update persistent alarm status in GUI
            status = self.alarm_module.get_current_alarm_status()
            self.update_alarm_status_from_status(status)
            
            # Process alarm events
            for alarm_event in alarm_events:
                if alarm_event['active']:
                    self.log_event_safe(f"ALARM: {alarm_event['parameter']} {alarm_event['alarm_type']} - Value: {alarm_event['value']:.1f} - {alarm_event['message']}")
                    
                    # Send alarm to SDC if manager is available
                    if self.sdc_alarm_manager:
                        self.sdc_alarm_manager.trigger_alarm(
                            alarm_event['parameter'],
                            alarm_event['alarm_type'],
                            alarm_event['priority'],
                            alarm_event['message']
                        )
                else:
                    self.log_event_safe(f"Alarm cleared: {alarm_event['parameter']} {alarm_event['alarm_type']}")
                    
                    # Clear alarm in SDC if manager is available
                    if self.sdc_alarm_manager:
                        self.sdc_alarm_manager.clear_alarm(
                            alarm_event['parameter'],
                            alarm_event['alarm_type']
                        )
                        
        except Exception as e:
            print(f"Alarm evaluation error: {e}")
            
    # Old SDC consumer methods removed - now using consumer.py subprocess
            
    def start_data_collection(self):
        """Start collecting data from SDC consumer."""
        def collect_loop():
            while self.connected and self.consumer:
                try:
                    # If provider is running, data will come from parse_provider_vitals()
                    # so we just wait - no demo data generation
                    if self.provider_process and self.provider_process.poll() is None:
                        # Provider is running, data comes from provider output parsing
                        time.sleep(1)  # Just wait, data comes from provider output
                        continue
                        
                    # Try to get real SDC data from provider (when not using subprocess)
                    data = self.collect_sdc_data()
                    if data:
                        self.data_queue.put(data)
                        self.log_queue.put(f"Received SDC data: HR={data.get('hr', '?')}, MAP={data.get('map', '?')}")
                    # NO DEMO DATA - only display real provider data
                    time.sleep(1)  # Update every second
                except Exception as e:
                    self.log_queue.put(f"Data collection error: {e}")
                    break
        
        # Start collection in background thread
        collection_thread = threading.Thread(target=collect_loop, daemon=True)
        collection_thread.start()
        
    def start_digital_twin_mode(self):
        """Start digital twin mode - now only displays provider data."""
        self.log_queue.put("Digital twin display mode - waiting for provider data...")
        self.connected = True
        
        # In this mode, we only display data coming from the provider
        # Data will come through parse_provider_vitals() when provider is running
        # No local data generation
        
    def get_digital_twin_data(self):
        """Get real data from the digital twin model."""
        try:
            if not self.dt_model:
                return None
                
            # Step the digital twin forward in time
            # Use the current time step from the model
            current_time = self.dt_model.t
            next_time = current_time + 1.0  # 1 second step
            
            # Run the simulation step
            from scipy.integrate import solve_ivp
            sol = solve_ivp(
                fun=self.dt_model.extended_state_space_equations,
                t_span=[current_time, next_time],
                y0=self.dt_model.current_state,
                dense_output=True,
                rtol=1e-6,
                atol=1e-9
            )
            
            # Update the model state
            self.dt_model.current_state = sol.y[:, -1]
            self.dt_model.t = next_time
            
            # Get the vital signs from the model
            P, F, HR, Sa_O2, RR = self.dt_model.compute_variables(next_time, self.dt_model.current_state)
            
            # Calculate additional parameters
            MAP = np.mean(P[0])  # Mean arterial pressure from left ventricle
            systolic = np.max(P[0]) if hasattr(P[0], '__iter__') else P[0]
            diastolic = np.min(P[0]) if hasattr(P[0], '__iter__') else P[0] * 0.7
            
            # Get temperature (assume normal body temperature with small variation)
            temperature = 37.0 + (self.dt_model.current_state[17] * 0.01 if len(self.dt_model.current_state) > 17 else 0)
            
            # Get etCO2 from the model state
            etco2 = self.dt_model.current_state[17] if len(self.dt_model.current_state) > 17 else 40
            
            return {
                'hr': max(30, min(200, float(HR))),  # Clamp to realistic ranges
                'map': max(40, min(150, float(MAP))),
                'sap': max(60, min(220, float(systolic))),
                'dap': max(30, min(120, float(diastolic))),
                'temperature': max(35.0, min(42.0, float(temperature))),
                'sao2': max(70, min(100, int(Sa_O2))),
                'rr': max(8, min(40, int(RR))),
                'etco2': max(20, min(60, float(etco2)))
            }
            
        except Exception as e:
            self.log_queue.put(f"Digital twin data error: {e}")
            return None
        
    def initialize_display(self):
        """Initialize display to show waiting for provider data."""
        # Set all values to show waiting state
        waiting_data = {
            'hr': '--',
            'map': '--', 
            'sap': '--',
            'dap': '--',
            'temperature': '--',
            'sao2': '--',
            'rr': '--',
            'etco2': '--'
        }
        
        # Update display labels to show waiting state
        for param, value in waiting_data.items():
            if hasattr(self, f'{param}_value'):
                label = getattr(self, f'{param}_value')
                label.config(text=str(value))
        
    def collect_sdc_data(self):
        """Collect data from SDC consumer."""
        try:
            if not self.consumer:
                self.sdc_messages_queue.put("SDC Data: No consumer available")
                return None
                
            # Get medical device data from SDC provider
            mdib = self.consumer.mdib
            if not mdib:
                self.sdc_messages_queue.put("SDC Data: No MDIB available")
                return None
                
            data = {}
            
            # Try to get data from the SDC provider's MDIB
            try:
                self.sdc_messages_queue.put("SDC Data: Querying MDIB for metric states...")
                
                # Get heart rate
                hr_state = mdib.states.descriptor_handle.get("hr")
                if hr_state and len(hr_state) > 0 and hr_state[0].MetricValue:
                    data['hr'] = float(hr_state[0].MetricValue.Value)
                    self.sdc_messages_queue.put(f"SDC Data: HR = {data['hr']}")
                
                # Get blood pressures  
                map_state = mdib.states.descriptor_handle.get("map")
                if map_state and len(map_state) > 0 and map_state[0].MetricValue:
                    data['map'] = float(map_state[0].MetricValue.Value)
                    self.sdc_messages_queue.put(f"SDC Data: MAP = {data['map']}")
                    
                sap_state = mdib.states.descriptor_handle.get("sap")
                if sap_state and len(sap_state) > 0 and sap_state[0].MetricValue:
                    data['sap'] = float(sap_state[0].MetricValue.Value)
                    self.sdc_messages_queue.put(f"SDC Data: SAP = {data['sap']}")
                    
                dap_state = mdib.states.descriptor_handle.get("dap")
                if dap_state and len(dap_state) > 0 and dap_state[0].MetricValue:
                    data['dap'] = float(dap_state[0].MetricValue.Value)
                    self.sdc_messages_queue.put(f"SDC Data: DAP = {data['dap']}")
                
                # Get temperature
                temp_state = mdib.states.descriptor_handle.get("temperature")
                if temp_state and len(temp_state) > 0 and temp_state[0].MetricValue:
                    data['temperature'] = float(temp_state[0].MetricValue.Value)
                    self.sdc_messages_queue.put(f"SDC Data: TEMP = {data['temperature']}")
                
                # Get oxygen saturation
                sao2_state = mdib.states.descriptor_handle.get("sao2")
                if sao2_state and len(sao2_state) > 0 and sao2_state[0].MetricValue:
                    data['sao2'] = float(sao2_state[0].MetricValue.Value)
                    self.sdc_messages_queue.put(f"SDC Data: SaO2 = {data['sao2']}")
                
                # Get respiratory rate
                rr_state = mdib.states.descriptor_handle.get("rr")
                if rr_state and len(rr_state) > 0 and rr_state[0].MetricValue:
                    data['rr'] = float(rr_state[0].MetricValue.Value)
                    self.sdc_messages_queue.put(f"SDC Data: RR = {data['rr']}")
                
                # Get end-tidal CO2
                etco2_state = mdib.states.descriptor_handle.get("etco2")
                if etco2_state and len(etco2_state) > 0 and etco2_state[0].MetricValue:
                    data['etco2'] = float(etco2_state[0].MetricValue.Value)
                    self.sdc_messages_queue.put(f"SDC Data: etCO2 = {data['etco2']}")
                    
            except Exception as e:
                self.log_queue.put(f"Error extracting SDC data: {e}")
                self.sdc_messages_queue.put(f"SDC Data: Error extracting data - {e}")
                return None
                
            # Return data if we got anything, otherwise None
            if data:
                self.sdc_messages_queue.put(f"SDC Data: Successfully collected {len(data)} metrics")
            else:
                self.sdc_messages_queue.put("SDC Data: No metric data available")
            return data if data else None
            
        except Exception as e:
            self.log_queue.put(f"SDC data collection error: {e}")
            self.sdc_messages_queue.put(f"SDC Data: Collection error - {e}")
            return None
        
    def start_provider(self):
        """Start the SDC provider process."""
        try:
            if self.provider_process and self.provider_process.poll() is None:
                self.log_queue.put("⚠ Provider already running")
                return
                
            self.log_queue.put("🚀 Starting SDC provider...")
            
            # Check if provider file exists
            if not os.path.exists("provider_MDT.py"):
                self.log_queue.put("✗ provider_MDT.py not found!")
                return
            
            # Get the selected patient file path
            patient_file = self.current_patient
            if patient_file and not os.path.isabs(patient_file):
                # Convert relative path to absolute path
                if patient_file.startswith("MDTparameters/"):
                    patient_file = os.path.join(os.getcwd(), patient_file)
                else:
                    patient_file = os.path.join(os.getcwd(), patient_file)
            
            # Start provider with selected patient file (use venv python if available)
            python_cmd = self._resolve_python_interpreter()
            cmd = [python_cmd, "-u", "provider_MDT.py", "--adapter", self.network_adapter]
            if patient_file and os.path.exists(patient_file):
                cmd.extend(["--patient-file", patient_file])
                self.log_queue.put(f"Using patient file: {patient_file}")
            else:
                self.log_queue.put("No patient file selected - using default")
            
            self.log_queue.put(f"Command: {' '.join(cmd)}")
            
            self.provider_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,  # Line buffering
                cwd=os.getcwd()
            )
            
            self.provider_status.config(text="Running", foreground="green")
            self.log_queue.put(f"✓ Provider started on adapter {self.network_adapter}")
            self.log_queue.put(f"Provider PID: {self.provider_process.pid}")
            
            # Add test SDC messages when provider starts
            self.sdc_messages_queue.put("SDC Consumer: Provider detected, attempting connection...")
            self.sdc_messages_queue.put("SDC Consumer: Provider UUID: 72313cab-7352-51c9-8373-8b4031a66ec7")
            self.sdc_messages_queue.put("SDC Consumer: Initiating discovery protocol...")
            
            # Start monitoring provider output immediately to capture early failures
            self.monitor_provider_output()

            # Check if process started successfully
            time.sleep(0.5)
            if self.provider_process.poll() is not None:
                self.log_queue.put(f"✗ Provider process exited with code: {self.provider_process.returncode}")
                self.provider_status.config(text="Failed", foreground="red")
                # Try to drain any remaining output to show the error cause
                try:
                    if self.provider_process and self.provider_process.stdout:
                        remaining = self.provider_process.stdout.read()
                        if remaining:
                            for line in remaining.splitlines():
                                self.log_queue.put(f"Provider: {line}")
                except Exception:
                    pass
                try:
                    messagebox.showerror("Provider failed", "Provider process exited immediately. Check the System Log for errors.\nTip: ensure you're using the project virtual environment.")
                except Exception:
                    pass
                return
            
            # Auto-reconnect consumer after a delay
            self.root.after(5000, self.reconnect_sdc)
            
        except Exception as e:
            self.log_queue.put(f"✗ Failed to start provider: {e}")
            self.provider_status.config(text="Error", foreground="red")
            try:
                messagebox.showerror("Failed to start provider", str(e))
            except Exception:
                pass
            
    def monitor_provider_output(self):
        """Monitor provider output in background thread."""
        def read_provider_output():
            try:
                while self.provider_process and self.provider_process.poll() is None:
                    if self.provider_process.stdout:
                        line = self.provider_process.stdout.readline()
                        if line:
                            # Put provider output into log queue to display in GUI
                            self.log_queue.put(f"Provider: {line.strip()}")
                            # Also print to console for debugging with immediate flush
                            print(f"Provider: {line.strip()}", flush=True)
                            
                            # Parse vital signs from provider output and update display
                            self.parse_provider_vitals(line.strip())
                        else:
                            time.sleep(0.1)
                    else:
                        time.sleep(0.5)
                        
                # Process has ended
                if self.provider_process:
                    self.log_queue.put(f"Provider process ended with code: {self.provider_process.returncode}")
                    self.provider_status.config(text="Stopped", foreground="red")
                    
            except Exception as e:
                self.log_queue.put(f"Error reading provider output: {e}")
                print(f"Error reading provider output: {e}", flush=True)
        
        # Start output monitoring in background thread
        output_thread = threading.Thread(target=read_provider_output, daemon=True)
        output_thread.start()
        
    def parse_provider_vitals(self, line):
        """Parse vital signs from provider debug output and update display."""
        try:
            # Parse alarm events first
            self.parse_alarm_events(line)
            
            # Look for lines like: [2025-09-08 16:06:13] HR: 70.0, MAP (avg): 91.9, SYS: 124.7, DIA: 68.6, TEMP: 37.0°C, SaO2: 98.0, RR: 12.0, etCO2: 40.0
            if "] HR:" in line and "MAP (avg):" in line:
                import re
                
                # Extract values using regex
                hr_match = re.search(r'HR: ([\d.]+)', line)
                map_match = re.search(r'MAP \(avg\): ([\d.]+)', line)
                sys_match = re.search(r'SYS: ([\d.]+)', line)
                dia_match = re.search(r'DIA: ([\d.]+)', line)
                temp_match = re.search(r'TEMP: ([\d.]+)', line)
                sao2_match = re.search(r'SaO2: ([\d.]+)', line)
                rr_match = re.search(r'RR: ([\d.]+)', line)
                etco2_match = re.search(r'etCO2: ([\d.]+)', line)
                
                # Create data dictionary with parsed values
                data = {}
                if hr_match: data['hr'] = float(hr_match.group(1))
                if map_match: data['map'] = float(map_match.group(1))
                if sys_match: data['sap'] = float(sys_match.group(1))  # SYS -> sap
                if dia_match: data['dap'] = float(dia_match.group(1))  # DIA -> dap
                if temp_match: data['temperature'] = float(temp_match.group(1))
                if sao2_match: data['sao2'] = float(sao2_match.group(1))
                if rr_match: data['rr'] = float(rr_match.group(1))
                if etco2_match: data['etco2'] = float(etco2_match.group(1))
                
                # Put the real provider data into the data queue
                if data:
                    self.data_queue.put(data)
                    
        except Exception as e:
            print(f"Error parsing provider vitals: {e}", flush=True)

    def parse_alarm_events(self, line):
        """Parse alarm events from provider output and update alarm display."""
        try:
            # Look for alarm trigger messages: "✓ Triggered SDC alarm: HeartRate high - Tachycardia"
            if "✓ Triggered SDC alarm:" in line:
                import re
                # Extract parameter name and alarm type
                match = re.search(r'Triggered SDC alarm: (\w+) (\w+) - (.+)', line)
                if match:
                    param_name = match.group(1)
                    alarm_type = match.group(2)
                    message = match.group(3)
                    
                    # Debug logging
                    self.log_queue.put(f"🚨 PARSING ALARM TRIGGER: {param_name} {alarm_type} - {message}")
                    
                    # Create alarm event
                    alarm_event = {
                        'parameter': param_name,
                        'alarm_type': alarm_type,
                        'active': True,
                        'message': message,
                        'value': 0  # Could be enhanced to parse value
                    }
                    
                    # Update alarm display
                    self.update_alarm_from_event(alarm_event)
                    
            # Look for alarm clear messages: "✓ Cleared SDC alarm: HeartRate high"
            elif "✓ Cleared SDC alarm:" in line:
                import re
                match = re.search(r'Cleared SDC alarm: (\w+) (\w+)', line)
                if match:
                    param_name = match.group(1)
                    alarm_type = match.group(2)
                    
                    # Debug logging  
                    self.log_queue.put(f"✅ PARSING ALARM CLEAR: {param_name} {alarm_type}")
                    
                    # Create alarm clear event
                    alarm_event = {
                        'parameter': param_name,
                        'alarm_type': alarm_type,
                        'active': False,
                        'message': f"Alarm cleared",
                        'value': 0
                    }
                    
                    # Update alarm display
                    self.update_alarm_from_event(alarm_event)
            
            # Look for current status messages: "🟨 CURRENT ALARM STATUS: HeartRate high - Tachycardia"
            elif "🟨 CURRENT ALARM STATUS:" in line:
                import re
                match = re.search(r'CURRENT ALARM STATUS: (\w+) (\w+(?:\s+\w+)*) - (.+)', line)
                if match:
                    param_name = match.group(1)
                    alarm_type = match.group(2).replace(' ', '_')  # Convert back to underscore format
                    message = match.group(3)
                    
                    # Debug logging  
                    self.log_queue.put(f"🔄 PARSING ALARM STATUS: {param_name} {alarm_type} - {message}")
                    
                    # Create alarm status event
                    alarm_event = {
                        'parameter': param_name,
                        'alarm_type': alarm_type,
                        'active': True,
                        'message': message,
                        'value': 0
                    }
                    
                    # Update alarm display (but don't log duplicate messages)
                    self.update_alarm_from_event(alarm_event, is_status_update=True)
                    
        except Exception as e:
            print(f"Error parsing alarm events: {e}", flush=True)
            self.log_queue.put(f"❌ Error parsing alarm events: {e}")

    def update_alarm_from_event(self, alarm_event, is_status_update=False):
        """Update alarm status display from a single alarm event."""
        try:
            # Map alarm parameter names to display names
            param_mapping = {
                'HeartRate': 'HR',
                'BloodPressureMean': 'MAP', 
                'BloodPressureSystolic': 'SAP',
                'BloodPressureDiastolic': 'DAP',
                'SpO2': 'SpO2',
                'Temperature': 'Temp',
                'EtCO2': 'EtCO2',
                'RespiratoryRate': 'RR'
            }
            
            param_name = alarm_event['parameter']
            display_name = param_mapping.get(param_name, param_name)
            
            # Debug logging (only for non-status updates to avoid spam)
            if not is_status_update:
                self.log_queue.put(f"🔄 UPDATING ALARM: {param_name} -> {display_name} (active: {alarm_event['active']})")
            
            if display_name in self.alarm_status_labels:
                label = self.alarm_status_labels[display_name]
                
                if alarm_event['active']:
                    # Alarm triggered
                    alarm_type = alarm_event.get('alarm_type', '').lower()
                    
                    if 'critical' in alarm_type:
                        label.config(text="CRIT", fg='#ff0000')
                        if not is_status_update:
                            self.log_queue.put(f"📊 {display_name} SET TO CRITICAL (BRIGHT RED)")
                    elif 'high' in alarm_type or 'upper' in alarm_type:
                        label.config(text="HIGH", fg='#e53e3e')
                        if not is_status_update:
                            self.log_queue.put(f"📊 {display_name} SET TO HIGH (RED)")
                    elif 'low' in alarm_type or 'lower' in alarm_type:
                        label.config(text="LOW", fg='#ff9500')
                        if not is_status_update:
                            self.log_queue.put(f"📊 {display_name} SET TO LOW (ORANGE)")
                    else:
                        label.config(text="ALARM", fg='#e53e3e')
                        if not is_status_update:
                            self.log_queue.put(f"📊 {display_name} SET TO ALARM (RED)")
                        
                    # Log the alarm for debugging (only for actual events, not status updates)
                    if not is_status_update:
                        self.log_queue.put(f"ALARM: {display_name} {alarm_type.upper()} - {alarm_event['message']}")
                else:
                    # Alarm cleared
                    label.config(text="OK", fg='#00ff88')
                    if not is_status_update:
                        self.log_queue.put(f"📊 {display_name} SET TO OK (GREEN)")
                        self.log_queue.put(f"CLEARED: {display_name} alarm cleared")
                
                # Update all clear indicator
                self.update_all_clear_indicator()
            else:
                if not is_status_update:
                    self.log_queue.put(f"❌ Display name '{display_name}' not found in alarm_status_labels")
                    self.log_queue.put(f"Available labels: {list(self.alarm_status_labels.keys())}")
                    
        except Exception as e:
            print(f"Error updating alarm from event: {e}", flush=True)
            if not is_status_update:
                self.log_queue.put(f"❌ Error updating alarm from event: {e}")

    def update_all_clear_indicator(self):
        """Update the 'All Clear' indicator based on current alarm status."""
        try:
            if not hasattr(self, 'alarm_status_labels') or not hasattr(self, 'all_clear_label'):
                return
                
            # Count active alarms
            active_alarms = []
            for param_short, label in self.alarm_status_labels.items():
                if label.cget('text') != 'OK':
                    active_alarms.append(param_short)
            
            # Update "All Clear" indicator
            if active_alarms:
                self.all_clear_label.config(
                    text=f"⚠ {len(active_alarms)} Active Alarm(s)", 
                    fg='#e53e3e'
                )
            else:
                self.all_clear_label.config(
                    text="✓ All Parameters Normal", 
                    fg='#00ff88'
                )
                
        except Exception as e:
            print(f"Error updating all clear indicator: {e}", flush=True)
            
    def stop_provider(self):
        """Stop the SDC provider process."""
        if self.provider_process:
            try:
                self.provider_process.terminate()
                self.provider_process.wait(timeout=5)
                self.provider_status.config(text="Stopped", foreground="red")
                self.log_queue.put("✓ Provider stopped")
            except subprocess.TimeoutExpired:
                self.provider_process.kill()
                self.log_queue.put("✓ Provider force-killed")
            except Exception as e:
                self.log_queue.put(f"Error stopping provider: {e}")
                
    def stop_consumer(self):
        """Stop the SDC consumer process."""
        if self.consumer_process:
            try:
                self.consumer_process.terminate()
                self.consumer_process.wait(timeout=5)
                self.log_queue.put("✓ Consumer stopped")
                self.sdc_messages_queue.put("SDC Consumer: Stopped")
            except subprocess.TimeoutExpired:
                self.consumer_process.kill()
                self.log_queue.put("✓ Consumer force-killed")
            except Exception as e:
                self.log_queue.put(f"Error stopping consumer: {e}")
        
        # Update consumer state
        self.consumer_running = False
        self.consumer_process = None
        if hasattr(self, 'consumer_status_label'):
            self.consumer_status_label.config(text="OFF", fg="#e53e3e")
        if hasattr(self, 'consumer_enabled'):
            self.consumer_enabled.set(False)
                
    def reconnect_sdc(self):
        """Reconnect to SDC provider."""
        self.connected = False
        if self.consumer_process:
            try:
                self.consumer_process.terminate()
                self.consumer_process.wait(timeout=5)
            except:
                pass
        # Restart consumer process
        self.start_consumer_process()
        
    def get_available_patients(self):
        """Get list of available patient files."""
        patients = []
        
        # Check main directory for *Flat*.json files
        for file in glob.glob("*Flat*.json"):
            patients.append(file)
            
        # Check MDTparameters directory
        if os.path.exists("MDTparameters"):
            for file in glob.glob("MDTparameters/*.json"):
                patients.append(file)
                
        return patients if patients else ["healthyFlat.json"]
        
    def on_patient_change(self, event):
        """Handle patient selection change."""
        self.current_patient = self.patient_var.get()
        self.log_queue.put(f"Selected patient: {self.current_patient}")
        
    def load_patient(self):
        """Load the selected patient."""
        self.log_queue.put(f"Loading patient: {self.current_patient}")
        # TODO: Implement patient loading logic
        
    def on_parameter_display_change(self, param, value):
        """Handle parameter slider display changes (doesn't apply yet)."""
        value = float(value)
        
        # Update label display only
        if hasattr(self, f'{param}_label'):
            label = getattr(self, f'{param}_label')
            unit = {"fio2": "%", "blood_volume": "mL", "hr_setpoint": "bpm", "map_setpoint": "mmHg", "rr_setpoint": "bpm", "temperature": "°C"}[param]
            if param == "blood_volume":
                label.config(text=f"{value:.0f} {unit}")
            else:
                label.config(text=f"{value:.1f} {unit}")
                
    def apply_parameter(self, param):
        """Apply the parameter change to the digital twin model."""
        if not hasattr(self, f'{param}_var'):
            return
            
        var = getattr(self, f'{param}_var')
        value = var.get()
        
        # Log the parameter application
        unit = {"fio2": "%", "blood_volume": "mL", "hr_setpoint": "bpm", "map_setpoint": "mmHg", "rr_setpoint": "bpm", "temperature": "°C"}[param]
        self.log_queue.put(f"✓ Applied {param}: {value:.1f} {unit}")
        
        # Write parameter update to file for provider to read
        param_update_file = os.path.join(os.getcwd(), "param_updates.tmp")
        try:
            with open(param_update_file, 'a') as f:
                f.write(f"{param}={value}\n")
            self.log_queue.put(f"Parameter update sent to provider: {param} = {value}")
        except Exception as e:
            self.log_queue.put(f"⚠ Error sending parameter update: {e}")

        # Direct model application if model instance is present
        if hasattr(self, 'dt_model') and self.dt_model is not None:
            try:
                if param == 'fio2':
                    applied = self.dt_model.set_fio2(value)
                    if applied:
                        self.log_queue.put(f"Model FiO2 updated to {value:.1f}%")
                elif param == 'blood_volume':
                    applied = self.dt_model.set_total_blood_volume(value)
                    if applied:
                        self.log_queue.put(f"Model blood volume updated to {value:.0f} mL")
            except Exception as e:
                self.log_queue.put(f"⚠ Error applying to model: {e}")

    def start_live_param_monitoring(self):
        """Periodically refresh displayed applied FiO2 / TBV from model."""
        if not hasattr(self, 'dt_model') or self.dt_model is None:
            return
        try:
            # Update applied labels if present
            if self.fio2_applied_label is not None:
                try:
                    current_f = getattr(self.dt_model, '_ode_FI_O2', None)
                    if current_f is not None:
                        self.fio2_applied_label.config(text=f"{current_f*100:.0f}%")
                except Exception:
                    pass
            if self.blood_volume_applied_label is not None:
                try:
                    tbv = self.dt_model.master_parameters['misc_constants.TBV']['value']
                    self.blood_volume_applied_label.config(text=f"{tbv:.0f} mL")
                except Exception:
                    pass
        finally:
            # Schedule next update
            if hasattr(self, 'root'):
                self.root.after(1000, self.start_live_param_monitoring)
            
    def toggle_baroreflex(self, enabled):
        """Toggle baroreflex on/off."""
        self.baroreflex_enabled.set(enabled)
        status = "ON" if enabled else "OFF"
        color = "green" if enabled else "red"
        
        self.baro_status_label.config(text=status, fg=color)
        self.log_queue.put(f"✓ Baroreflex {status}")
        
        # Send command to provider to toggle baroreflex
        param_update_file = os.path.join(os.getcwd(), "param_updates.tmp")
        try:
            with open(param_update_file, 'a') as f:
                f.write(f"baroreflex={1 if enabled else 0}\n")
            self.log_queue.put(f"Baroreflex command sent to provider: {enabled}")
        except Exception as e:
            self.log_queue.put(f"⚠ Error sending baroreflex command: {e}")
            
    def toggle_chemoreceptor(self, enabled):
        """Toggle chemoreceptor on/off."""
        self.chemoreceptor_enabled.set(enabled)
        status = "ON" if enabled else "OFF"
        color = "green" if enabled else "red"
        
        self.chemo_status_label.config(text=status, fg=color)
        self.log_queue.put(f"✓ Chemoreceptor {status}")
        
        # Send command to provider to toggle chemoreceptor
        param_update_file = os.path.join(os.getcwd(), "param_updates.tmp")
        try:
            with open(param_update_file, 'a') as f:
                f.write(f"chemoreceptor={1 if enabled else 0}\n")
            self.log_queue.put(f"Chemoreceptor command sent to provider: {enabled}")
        except Exception as e:
            self.log_queue.put(f"⚠ Error sending chemoreceptor command: {e}")
    
    def toggle_consumer(self, start):
        """Toggle SDC consumer on/off."""
        if start and not self.consumer_running:
            # Start the consumer
            self.start_consumer_process()
            self.consumer_enabled.set(True)
            self.consumer_status_label.config(text="STARTING...", fg="#ffa500")
            self.log_queue.put("📡 Starting SDC Consumer...")
        elif not start and self.consumer_running:
            # Stop the consumer
            self.stop_consumer()
            self.consumer_enabled.set(False)
            self.consumer_status_label.config(text="OFF", fg="#e53e3e")
            self.log_queue.put("📡 Stopping SDC Consumer...")
        
    def cardiac_arrest(self):
        """Simulate cardiac arrest scenario."""
        self.log_queue.put("🚨 Emergency: Cardiac Arrest")
        # TODO: Implement cardiac arrest scenario
        
    def hemorrhage(self):
        """Deprecated: replaced by blood sampling."""
        self.log_queue.put("⚠ Hemorrhage button deprecated; use blood sampling.")

    def blood_sampling_toggle(self):
        """Toggle blood sampling scenario (forces MAP/SAP/DAP to 300 while active)."""
        try:
            self.blood_sampling_active = not getattr(self, 'blood_sampling_active', False)
            with open('param_updates.tmp', 'a') as f:
                f.write(f"blood_sampling={1 if self.blood_sampling_active else 0}\n")
            if self.blood_sampling_active:
                self.log_queue.put("🩸 Blood sampling STARTED (forcing arterial pressures to 300)")
                if hasattr(self, 'blood_sampling_button'):
                    self.blood_sampling_button.config(bg='#ffb347', fg='#1a252f')
            else:
                self.log_queue.put("🩸 Blood sampling ENDED (restoring normal pressures)")
                if hasattr(self, 'blood_sampling_button'):
                    self.blood_sampling_button.config(bg='#dd6b20', fg='#1a252f')
            self._update_emergency_status_banner()
        except Exception as e:
            self.log_queue.put(f"❌ Error toggling blood sampling: {e}")

    def toggle_ecg_leadoff(self):
        """Toggle ECG lead off alarm (idempotent toggle)."""
        try:
            self.ecg_lead_off_active = not getattr(self, 'ecg_lead_off_active', False)
            with open('param_updates.tmp', 'a') as f:
                f.write(f"ecg_lead_off={1 if self.ecg_lead_off_active else 0}\n")
            if self.ecg_lead_off_active:
                self.log_queue.put("🔌 ECG Lead Off alarm triggered - HR not measurable")
                if hasattr(self, 'ecg_leadoff_button'):
                    self.ecg_leadoff_button.config(bg='#ffcc66', fg='#1a252f')
            else:
                self.log_queue.put("🔌 ECG Lead Off cleared")
                if hasattr(self, 'ecg_leadoff_button'):
                    self.ecg_leadoff_button.config(bg='#ffa500', fg='#1a252f')
            self._update_emergency_status_banner()
        except Exception as e:
            self.log_queue.put(f"❌ Error toggling ECG lead off: {e}")
    
    def open_sdc_messages_window(self):
        """Open a window to display SDC messages."""
        # Check if window already exists
        if hasattr(self, 'sdc_window') and self.sdc_window.winfo_exists():
            self.sdc_window.lift()  # Bring to front
            return
            
        # Create new window
        self.sdc_window = tk.Toplevel(self.root)
        self.sdc_window.title("SDC Messages Monitor")
        self.sdc_window.geometry("800x600")
        self.sdc_window.configure(bg='#2c3e50')
        
        # Header
        header_frame = tk.Frame(self.sdc_window, bg='#34495e', height=50)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="SDC Protocol Messages", 
                 font=('Arial', 16, 'bold'), fg='#1a252f', bg='#34495e').pack(pady=10)
        
        # Stats frame
        stats_frame = tk.Frame(self.sdc_window, bg='#2c3e50')
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.sdc_msg_count_label = tk.Label(stats_frame, text="Messages: 0", 
                                             font=('Arial', 10), fg='#ecf0f1', bg='#2c3e50')
        self.sdc_msg_count_label.pack(side=tk.LEFT)
        
        self.sdc_connection_status = tk.Label(stats_frame, text="Status: Disconnected", 
                                               font=('Arial', 10), fg='#e74c3c', bg='#2c3e50')
        self.sdc_connection_status.pack(side=tk.RIGHT)
        
        # Messages display
        msg_frame = tk.Frame(self.sdc_window, bg='#2c3e50')
        msg_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        
        # Text widget with scrollbar
        self.sdc_text = tk.Text(msg_frame, font=('Courier', 9), bg='#1a252f', fg='#e2e8f0',
                                insertbackground='#e2e8f0', selectbackground='#3498db',
                                wrap=tk.WORD, state=tk.DISABLED)
        
        sdc_scrollbar = tk.Scrollbar(msg_frame, orient=tk.VERTICAL, command=self.sdc_text.yview)
        self.sdc_text.config(yscrollcommand=sdc_scrollbar.set)
        
        self.sdc_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sdc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Control buttons
        button_frame = tk.Frame(self.sdc_window, bg='#2c3e50')
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Button(button_frame, text="Clear Messages", command=self.clear_sdc_messages,
                  bg='#e67e22', fg='#1a252f', font=('Arial', 10, 'bold'),
                  activebackground='#d35400', activeforeground='#1a252f').pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Save Messages", command=self.save_sdc_messages,
                  bg='#27ae60', fg='#1a252f', font=('Arial', 10, 'bold'),
                  activebackground='#229954', activeforeground='#1a252f').pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Close", command=self.sdc_window.destroy,
                  bg='#95a5a6', fg='#1a252f', font=('Arial', 10, 'bold'),
                  activebackground='#7f8c8d', activeforeground='#1a252f').pack(side=tk.RIGHT, padx=5)
        
        # Initialize message counter
        self.sdc_message_count = 0
        
        # Add initial test message
        self.sdc_messages_queue.put("SDC Messages Window: Initialized and ready")
        
        # Start processing SDC messages
        self.process_sdc_messages()
        
    def process_sdc_messages(self):
        """Process and display SDC messages."""
        if hasattr(self, 'sdc_window') and self.sdc_window.winfo_exists():
            try:
                # Process all queued SDC messages
                while not self.sdc_messages_queue.empty():
                    message = self.sdc_messages_queue.get_nowait()
                    self.sdc_message_count += 1
                    
                    # Update message display
                    self.sdc_text.config(state=tk.NORMAL)
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    self.sdc_text.insert(tk.END, f"[{timestamp}] {message}\n")
                    self.sdc_text.see(tk.END)  # Auto-scroll to bottom
                    self.sdc_text.config(state=tk.DISABLED)
                    
                    # Update message counter
                    self.sdc_msg_count_label.config(text=f"Messages: {self.sdc_message_count}")
                    
                # Update connection status
                if self.connected and self.consumer:
                    self.sdc_connection_status.config(text="Status: Connected", fg='#27ae60')
                else:
                    self.sdc_connection_status.config(text="Status: Disconnected", fg='#e74c3c')
                    
            except queue.Empty:
                pass
            except Exception as e:
                print(f"SDC message processing error: {e}")
                
            # Schedule next update
            self.sdc_window.after(100, self.process_sdc_messages)
    
    def clear_sdc_messages(self):
        """Clear all SDC messages."""
        if hasattr(self, 'sdc_text'):
            self.sdc_text.config(state=tk.NORMAL)
            self.sdc_text.delete(1.0, tk.END)
            self.sdc_text.config(state=tk.DISABLED)
            self.sdc_message_count = 0
            self.sdc_msg_count_label.config(text="Messages: 0")
    
    def save_sdc_messages(self):
        """Save SDC messages to file."""
        try:
            from tkinter import filedialog
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                title="Save SDC Messages"
            )
            if filename:
                content = self.sdc_text.get(1.0, tk.END)
                with open(filename, 'w') as f:
                    f.write(content)
                self.log_queue.put(f"SDC messages saved to {filename}")
        except Exception as e:
            self.log_queue.put(f"Failed to save SDC messages: {e}")

    def get_available_adapters(self):
        """Get list of available network adapters."""
        try:
            # Run ifconfig and parse the output to get adapter names
            result = subprocess.run(['ifconfig'], capture_output=True, text=True)
            adapters = []
            
            for line in result.stdout.split('\n'):
                if line and not line.startswith('\t') and not line.startswith(' '):
                    # Extract adapter name (everything before the colon)
                    adapter_name = line.split(':')[0]
                    if adapter_name and not adapter_name.startswith('lo'):  # Skip loopback
                        adapters.append(adapter_name)
            
            # Common adapters to prioritize
            common_adapters = ['en0', 'en1', 'eth0', 'eth1', 'wlan0', 'wifi0']
            
            # Sort adapters with common ones first
            sorted_adapters = []
            for common in common_adapters:
                if common in adapters:
                    sorted_adapters.append(common)
                    adapters.remove(common)
            
            # Add remaining adapters
            sorted_adapters.extend(sorted(adapters))
            
            # Always include en0 as fallback if not found
            if 'en0' not in sorted_adapters:
                sorted_adapters.insert(0, 'en0')

            # Explicitly include Windows/Hyper-V friendly name if desired by user
            # This helps when running on environments where provider/consumer expect this label
            friendly_name = 'vEthernet (Ethernet0)'
            if friendly_name not in sorted_adapters:
                sorted_adapters.append(friendly_name)
                
            return sorted_adapters if sorted_adapters else ['en0']
            
        except Exception as e:
            self.log_queue.put(f"Failed to get network adapters: {e}")
            # Fallback list including the requested friendly name
            return ['en0', 'en1', 'eth0', 'wlan0', 'vEthernet (Ethernet0)']

    def on_adapter_change(self, event=None):
        """Handle network adapter selection change."""
        try:
            new_adapter = self.selected_adapter.get()
            if new_adapter and new_adapter != self.network_adapter:
                self.network_adapter = new_adapter
                self.adapter_status.config(text=f"Current: {self.network_adapter}")
                self.log_queue.put(f"📡 Network adapter changed to: {self.network_adapter}")
                
                # If provider is running, warn user about restart requirement
                if self.provider_process and self.provider_process.poll() is None:
                    self.log_queue.put("⚠ Provider restart required for adapter change to take effect")
                    
        except Exception as e:
            self.log_queue.put(f"Failed to change adapter: {e}")

def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="SDC Digital Twin Monitor & Control")
    parser.add_argument('--adapter', default='en0', help="Network adapter to use (default: en0)")
    args = parser.parse_args()
    
    root = tk.Tk()
    app = SDCDigitalTwinMonitor(root, args.adapter)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nShutting down...")
        
if __name__ == "__main__":
    main()
