#!/usr/bin/env python3
"""
Wrapper script to run the Citrix Metrics Collector application
with proper Python import paths.
"""
import os
import sys

# Add the app directory to the Python path
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "app"))
sys.path.append(APP_DIR)

# Now import and run the main module
from main import main

if __name__ == "__main__":
    main()