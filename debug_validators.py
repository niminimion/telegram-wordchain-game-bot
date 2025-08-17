#!/usr/bin/env python3
"""
Debug script to test validators module.
"""

import sys
import os

print("Python version:", sys.version)
print("Current directory:", os.getcwd())
print("Python path:", sys.path[:3])

try:
    print("\n1. Testing direct file execution...")
    with open('bot/validators.py', 'r') as f:
        content = f.read()
    print(f"File size: {len(content)} characters")
    print(f"Contains 'class WordValidator': {'class WordValidator' in content}")
    print(f"Contains 'ValidationServiceUnavailable': {'ValidationServiceUnavailable' in content}")
    
    print("\n2. Testing module compilation...")
    import py_compile
    py_compile.compile('bot/validators.py', doraise=True)
    print("✅ Module compiles successfully")
    
    print("\n3. Testing direct import...")
    sys.path.insert(0, 'bot')
    import validators
    print(f"Module loaded: {validators}")
    print(f"Module file: {validators.__file__ if hasattr(validators, '__file__') else 'No __file__'}")
    print(f"Module dict keys: {list(validators.__dict__.keys())}")
    
    print("\n4. Testing class access...")
    if hasattr(validators, 'WordValidator'):
        print("✅ WordValidator found")
    else:
        print("❌ WordValidator not found")
        
    if hasattr(validators, 'ValidationServiceUnavailable'):
        print("✅ ValidationServiceUnavailable found")
    else:
        print("❌ ValidationServiceUnavailable not found")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()