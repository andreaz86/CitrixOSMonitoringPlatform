"""
Module for sending log data to VictoriaLogs
"""
import requests
import json
from datetime import datetime
from typing import Dict, List, Any

from utils import config

class VictoriaLogsManager:
    """Manager for sending logs to VictoriaLogs"""
    def __init__(self):
        """Initialize the VictoriaLogs manager"""
        # VictoriaLogs endpoint for sending logs
        self.url = config.VICTORIA_LOGS_URL
        if not self.url:
            self.url = "http://localhost:9428/insert/jsonline"
        
        # Ensure URL doesn't already contain query parameters
        if "?" in self.url:
            base_url = self.url.split("?")[0]
            config.logger.info(f"URL contains query parameters, using base URL: {base_url}")
            self.url = base_url
        
        # Default parameters (specified in requirements)
        self.default_params = {
            "_msg_field": "fields.Text", 
            "_time_field": "timestamp",
            "_stream_fields": "tags.log_source,tags.metric_type"
        }
        
        # Log initialization info
        config.logger.debug(f"VictoriaLogs endpoint: {self.url}")
        config.logger.debug(f"Default parameters: {self.default_params}")
        
        config.logger.info(f"VictoriaLogsManager initialized with URL: {self.url}")
    
    def write_logs(self, log_data: List[Dict[str, Any]], log_source: str, metric_type: str):
        """
        Write logs to VictoriaLogs using the jsonline format
        
        Args:
            log_data: List of log entries to send
            log_source: Source of the log (e.g., "citrix_configlog")
            metric_type: Type of metric for tagging
        """
        if not log_data:
            config.logger.debug("No log data to send to VictoriaLogs")
            return
            
        try:
            # Prepara un array di entry JSON da inviare come NDJSON
            formatted_entries = []
            stream_fields = []
            
            for entry in log_data:
                # Get timestamp from FormattedEndTime or current time
                timestamp = entry.get("FormattedEndTime")
                # if timestamp and timestamp.endswith('Z'):
                #     timestamp = timestamp[:-1]  # Remove the 'Z' suffix if present
                
                # Create the log entry structure
                log_entry = {
                    "timestamp": timestamp or datetime.now().isoformat(),
                    "log_source": log_source,
                    "metric_type": metric_type,
                    "User": entry.get("User", ""),
                    "Source": entry.get("Source", ""),
                    "AdminMachineIP": entry.get("AdminMachineIP", ""),
                    "IsSuccessful": str(entry.get("IsSuccessful", "")),
                    "OperationType": entry.get("OperationType", ""),
                    "fields": {
                        # Text is the field to be used as message
                        "Text": entry.get("Text","No message"),
                    }
                }
                
                # Remove None values from tags
                # for tag_key in list(log_entry["tags"].keys()):
                #     if log_entry["tags"][tag_key] is None:
                #         log_entry["tags"][tag_key] = ""
                
                if config.DEBUG and not timestamp:
                    config.logger.debug(f"No FormattedEndTime found in log entry, using current time")
                
                # Add all fields to the log entry fields section
                # for key, value in entry.items():
                #     if value is not None:  # Avoid None values
                #         log_entry["fields"][key] = value
                
                # Convert the entry to JSON and add to our array
                formatted_entries.append(json.dumps(log_entry))
                
                # Add tag fields for stream parameters
                # if not stream_fields and log_entry["tags"]:
                #     stream_fields = list(log_entry["tags"].keys())
            
            # Join all entries with newlines to create NDJSON
            ndjson_payload = "\n".join(formatted_entries)
            
            # Construct the full stream fields parameter
            stream_fields_param = "tags." + ",tags.".join(stream_fields)
            
            # Construct URL parameters
            params = {
                "_msg_field": "fields.Text",
                "_time_field": "timestamp",
                "_stream_fields": "stream"
            }
            
            if config.DEBUG:
                config.logger.debug(f"Using parameters for VictoriaLogs: {params}")
                config.logger.debug(f"NDJSON payload size: {len(ndjson_payload)} bytes, {len(formatted_entries)} entries")
                if formatted_entries:
                    config.logger.debug(f"First entry sample: {formatted_entries[0][:200]}...")
            
            # Send NDJSON payload to VictoriaLogs in a single request
            response = requests.post(
                self.url,
                params=params,
                data=ndjson_payload,
                headers={"Content-Type": "application/stream+json"},
                proxies=None  # Ensure no proxy is used
            )
            
            response.raise_for_status()
            
            if config.DEBUG:
                if hasattr(response, 'status_code'):
                    config.logger.debug(f"VictoriaLogs response status code: {response.status_code}")
                if hasattr(response, 'text') and response.text:
                    config.logger.debug(f"VictoriaLogs response content: {response.text[:500]}")
            
            config.logger.info(f"Successfully sent {len(formatted_entries)} log entries to VictoriaLogs in a single request")
            
        except Exception as e:
            config.logger.error(f"Error sending logs to VictoriaLogs: {str(e)}")
            if config.DEBUG:
                import traceback
                config.logger.debug(f"Error traceback: {traceback.format_exc()}")
                if 'response' in locals() and response:
                    if hasattr(response, 'status_code'):
                        config.logger.debug(f"Response status code: {response.status_code}")
                    if hasattr(response, 'text'):
                        config.logger.debug(f"Response content: {response.text[:500]}")

# Create a singleton instance
victoria_logs_manager = VictoriaLogsManager()
