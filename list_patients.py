#!/usr/bin/env python3
"""
Test script to show available patient parameter files.

Copyright (c) 2025 Dr. L.M. van Loon. All Rights Reserved.

This software is for academic research and educational purposes only.
Commercial use is strictly prohibited without explicit written permission
from Dr. L.M. van Loon.

For commercial licensing inquiries, contact Dr. L.M. van Loon.
"""

import os
import glob

def list_available_patients():
    """List all available patient parameter files."""
    print("🏥 Available Patient Parameter Files:")
    print("=" * 50)
    
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
        
        patients.append((display_name, filename, "Main folder (contains 'Flat')"))
    
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
            patients.append((display_name, relative_path, "MDTparameters folder (contains 'Flat')"))
    
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
            patients.append((display_name, relative_path, "MDTparameters folder"))
    
    # Display all patients
    for i, (display_name, file_path, location) in enumerate(patients, 1):
        print(f"{i:2d}. {display_name}")
        print(f"    File: {file_path}")
        print(f"    Location: {location}")
        print()
    
    print(f"Total: {len(patients)} patient configurations available")
    print("\n🎯 Focus: All files containing 'Flat' + other JSON files from MDTparameters")
    print("🔍 Pattern: *Flat*.json files are prioritized and given better names!")

if __name__ == "__main__":
    list_available_patients()
