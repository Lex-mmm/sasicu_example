#!/usr/bin/env python3
"""
Quick System Check for Digital Twin Monitoring System
Run this script to verify your system is ready!

Copyright (c) 2025 Dr. L.M. van Loon. All Rights Reserved.

This software is for academic research and educational purposes only.
Commercial use is strictly prohibited without explicit written permission
from Dr. L.M. van Loon.

For commercial licensing inquiries, contact Dr. L.M. van Loon.
"""

import sys
import os

def check_python_version():
    """Check if Python version is adequate."""
    print("🐍 Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro} - Good!")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} - Need 3.8+")
        return False

def check_required_modules():
    """Check if required Python modules are available."""
    print("\n📦 Checking required modules...")
    modules = {
        'numpy': 'Numerical computing',
        'scipy': 'Scientific computing', 
        'tkinter': 'GUI framework',
        'matplotlib': 'Plotting library'
    }
    
    all_good = True
    for module, description in modules.items():
        try:
            __import__(module)
            print(f"   ✅ {module} - {description}")
        except ImportError:
            print(f"   ❌ {module} - {description} (MISSING)")
            all_good = False
    
    return all_good

def check_required_files():
    """Check if essential files are present."""
    print("\n📁 Checking required files...")
    required_files = [
        ('launcher.py', 'Main launcher'),
        ('direct_monitor.py', 'Direct monitor'),
        ('digital_twin_model.py', 'Digital twin model'),
        ('healthyFlat.json', 'Healthy patient parameters')
    ]
    
    all_good = True
    for filename, description in required_files:
        if os.path.exists(filename):
            print(f"   ✅ {filename} - {description}")
        else:
            print(f"   ❌ {filename} - {description} (MISSING)")
            all_good = False
    
    return all_good

def check_patient_files():
    """Check available patient parameter files."""
    print("\n👥 Checking patient files...")
    
    # Check main folder
    main_patients = []
    for file in os.listdir('.'):
        if file.endswith('.json') and 'Flat' in file:
            main_patients.append(file)
    
    # Check MDTparameters folder
    mdt_patients = []
    if os.path.exists('MDTparameters'):
        for file in os.listdir('MDTparameters'):
            if file.endswith('.json'):
                mdt_patients.append(f"MDTparameters/{file}")
    
    total_patients = len(main_patients) + len(mdt_patients)
    print(f"   📊 Found {total_patients} patient configuration files:")
    
    for patient in main_patients:
        print(f"      • {patient}")
    for patient in mdt_patients:
        print(f"      • {patient}")
    
    return total_patients > 0

def main():
    """Run all system checks."""
    print("🏥 Digital Twin Monitoring System - System Check")
    print("© 2025 Dr. L.M. van Loon - Academic/Educational Use Only")
    print("=" * 50)
    
    checks = [
        check_python_version(),
        check_required_modules(),
        check_required_files(),
        check_patient_files()
    ]
    
    print("\n" + "=" * 50)
    if all(checks):
        print("🎉 SUCCESS! Your system is ready to go!")
        print("\n🚀 Next steps:")
        print("   1. Run: python3 launcher.py")
        print("   2. Select a patient type")
        print("   3. Click 'Start Monitor'")
        print("   4. Enjoy real-time physiological monitoring!")
    else:
        print("❌ ISSUES FOUND! Please fix the problems above.")
        print("\n🔧 Common solutions:")
        print("   • Install missing modules: pip install numpy scipy matplotlib")
        print("   • Make sure you're in the correct directory")
        print("   • Check that all files were downloaded properly")
    
    print("\n📖 Need help? Check the README.md file!")
    print("\n📄 License: Academic/Educational Use Only")
    print("   Commercial use requires permission from Dr. L.M. van Loon")

if __name__ == "__main__":
    main()
