from datetime import datetime
import os
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import json

# Change from absolute import to relative import with parent directory
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import config

class VictoriaMetricsManager:
    def __init__(self):
        """Initialize VictoriaMetrics manager with InfluxDB client."""
        self.url = config.METRICS_ENDPOINT
        self.client = None
        self.write_api = None
        self.dummy_bucket = "dummy_bucket"  # Required by InfluxDB client
        self.dummy_org = "dummy_org"        # Required by InfluxDB client
        
        try:
            self.client = InfluxDBClient(
                url=self.url,
                proxies=None,  # Ensure no proxy is used
                verify_ssl=False  # Disable SSL verification if needed
            )
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            config.logger.info(f"Connected to VictoriaMetrics at {self.url}")
        except Exception as e:
            config.logger.error(f"Failed to connect to VictoriaMetrics: {str(e)}")
            raise

    def write_metrics(self, measurement, tags, fields, timestamp=None):
        """
        Write metrics to VictoriaMetrics using InfluxDB line protocol.
        
        Args:
            measurement: The measurement name
            tags: Dictionary of tags
            fields: Dictionary of fields (metrics values)
            timestamp: Timestamp for the data point (defaults to now)
        """
        try:
            point = Point(measurement)
            
            # Add tags
            for tag_key, tag_value in tags.items():
                if tag_value is not None:
                    point = point.tag(tag_key, str(tag_value))
            
            # Add fields
            for field_key, field_value in fields.items():
                if field_value is not None:
                    # Ensure field value is a number or string
                    if isinstance(field_value, (int, float)):
                        point = point.field(field_key, field_value)
                    else:
                        try:
                            numeric_value = float(field_value)
                            point = point.field(field_key, numeric_value)
                        except (ValueError, TypeError):
                            point = point.field(field_key, str(field_value))
            
            # Add timestamp if provided
            if timestamp:
                point = point.time(timestamp)
            
            # Write using dummy bucket/org required by InfluxDB client
            self.write_api.write(bucket=self.dummy_bucket, record=point, org=self.dummy_org)
            
        except Exception as e:
            config.logger.error(f"Failed to write metrics to VictoriaMetrics: {str(e)}")
            raise
    
    def store_last_metrics_run(self, timestamp_iso):
        """
        Store the timestamp of the last successful metrics collection.
        
        Args:
            timestamp_iso: ISO formatted timestamp string
        """
        try:
            with open(config.LAST_METRICS_RUN_FILE, 'w') as f:
                f.write(timestamp_iso)
            config.logger.debug(f"Stored last metrics run timestamp: {timestamp_iso}")
        except Exception as e:
            config.logger.error(f"Failed to store last metrics run timestamp: {str(e)}")
    
    def get_last_metrics_run(self):
        """
        Get the timestamp of the last successful metrics collection.
        
        Returns:
            ISO formatted timestamp string or None if not available
        """
        try:
            if os.path.exists(config.LAST_METRICS_RUN_FILE):
                with open(config.LAST_METRICS_RUN_FILE, 'r') as f:
                    timestamp = f.read().strip()
                config.logger.debug(f"Retrieved last metrics run timestamp: {timestamp}")
                return timestamp
            return None
        except Exception as e:
            config.logger.error(f"Failed to get last metrics run timestamp: {str(e)}")
            return None

# Create a singleton instance
victoria_metrics_manager = VictoriaMetricsManager()