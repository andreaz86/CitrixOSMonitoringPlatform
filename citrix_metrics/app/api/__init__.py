#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API module for Citrix Metrics application.
Handles all interactions with external APIs.
"""

# Import the main API client for easier import by other modules
from api.citrix_client import citrix_client

# Expose utility functions for expanded field handling
try:
    from api.citrix_utils import process_expand_config_for_query, process_expanded_fields_in_response
except ImportError:
    # Handle the case where citrix_utils might not be available yet
    pass