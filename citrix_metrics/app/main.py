import time
import schedule
import threading
from datetime import datetime, timedelta
import signal
import sys
import http.server
import socketserver
import json
import os
import yaml
from prometheus_client import start_http_server, generate_latest, CONTENT_TYPE_LATEST

from utils import config
from api.citrix_client import citrix_client
from database.influx_client import victoria_metrics_manager
from database.postgres_client import postgres_manager
from database.victorialogs_client import victoria_logs_manager
from database.victorialogs_client import victoria_logs_manager
from utils.prometheus_metrics import (
    initialize_metrics, METRICS_COLLECTION_DURATION, METRICS_COLLECTION_ERRORS,
    API_REQUESTS, API_LATENCY, APP_INFO
)

# Global variable to track application health
app_health = {
    "status": "starting",
    "last_metrics_run": None,
    "last_config_run": None,
    "errors": []
}

# Flag per indicare se le metriche Prometheus sono abilitate
ENABLE_PROMETHEUS_METRICS = os.environ.get('ENABLE_PROMETHEUS_METRICS', 'true').lower() == 'true'

# This function has been moved to utils/config.py
# We're keeping this reference for backward compatibility, but it now just forwards to the centralized function
def load_api_config():
    """
    Carica le configurazioni delle API dal file di configurazione.
    Questa funzione ora utilizza l'implementazione centralizzata in utils.config.
    
    Returns:
        dict: Configurazione delle API
    """
    return config.load_api_config()

def load_queries_config():
    """
    Carica le configurazioni delle query da eseguire dal file di configurazione.
    Utilizes the centralized and cached implementation in config.py.
    
    Returns:
        dict: Configurazione delle query o None se il file non è trovato o c'è un errore
    """
    # Use centralized function with caching to avoid loading the file multiple times
    return config.load_queries_config()

def collect_metrics(api_name=None):
    """
    Colleziona metriche da Citrix Cloud e le memorizza in VictoriaMetrics.
    
    Args:
        api_name: Se specificato, raccoglie solo le metriche per quell'API specifica
    """
    if api_name:
        config.logger.info(f"Starting metrics collection for {api_name}")
    else:
        config.logger.info("Starting metrics collection for all configured APIs")
    
    global app_health
    
    # Track metrics collection duration
    start_time = time.time()
    
    try:
        # Carica la configurazione delle query e delle API
        queries_config = load_queries_config()
        api_configs = load_api_config()
        
        # Se non è stata trovata nessuna configurazione, esci
        if queries_config is None:
            config.logger.error("No queries configuration available, skipping metrics collection")
            return
            
        # Current time as end time
        now = datetime.now().isoformat()
        
        if config.DEBUG:
            config.logger.debug(f"Current run time: {now}")
        
        # Esegui tutte le query metriche configurate o solo quella specificata
        if 'metrics' in queries_config:
            for query_config in queries_config['metrics']:
                current_api_name = query_config['api_name']
                
                # Se è stato specificato un api_name e non corrisponde a quello corrente, salta
                if api_name and current_api_name != api_name:
                    continue
                    
                measurement_name = query_config['measurement_name']
                
                # Ottieni il campo timestamp dalla configurazione API se disponibile
                timestamp_field = None
                if current_api_name in api_configs and 'timestamp_field' in api_configs[current_api_name]:
                    timestamp_field = api_configs[current_api_name]['timestamp_field']
                    if config.DEBUG:
                        config.logger.debug(f"Will use '{timestamp_field}' as timestamp field for {current_api_name}")
                
                config.logger.info(f"Collecting {current_api_name} metrics")
                if config.DEBUG:
                    config.logger.debug(f"Using configuration: {json.dumps(query_config)}")
                    # Check if we're dealing with a log type API
                    if current_api_name in api_configs and api_configs[current_api_name].get('type') == 'log':
                        config.logger.debug(f"API {current_api_name} is of type 'log', will be handled by _handle_log_api")
                
                try:
                    # Esegui la query all'API
                    config.logger.debug(f"Calling query_api for {current_api_name}")
                    response = citrix_client.query_api(current_api_name)
                    
                    if response:
                        # Estrai gli elementi dalla risposta
                        items = []
                        if isinstance(response, dict) and 'value' in response:
                            items = response['value']
                        elif isinstance(response, list):
                            items = response
                        
                        if config.DEBUG:
                            config.logger.debug(f"Received {len(items)} items from {current_api_name} API")
                        
                        for idx, item in enumerate(items):
                            if config.DEBUG and idx < 3:  # Logga solo i primi 3 item come esempi
                                config.logger.debug(f"Sample {current_api_name} item {idx+1}: {json.dumps(item)}")
                            
                            # Estrai i tag in base alla mappatura configurata
                            tags = {}
                            for tag_name, item_key in query_config['tag_mappings'].items():
                                if isinstance(item_key, list):  # Path nidificato
                                    value = item
                                    for key in item_key:
                                        if isinstance(value, dict) and key in value:
                                            value = value[key]
                                        else:
                                            value = None
                                            break
                                    if value is not None:
                                        tags[tag_name] = value
                                elif isinstance(item_key, str) and item_key in item:  # Chiave diretta
                                    tags[tag_name] = item[item_key]
                            
                            # Estrai i campi in base alla mappatura configurata
                            fields = {}
                            for field_name, item_key in query_config['field_mappings'].items():
                                if isinstance(item_key, list):  # Path nidificato
                                    value = item
                                    for key in item_key:
                                        if isinstance(value, dict) and key in value:
                                            value = value[key]
                                        else:
                                            value = None
                                            break
                                    if value is not None:
                                        fields[field_name] = value
                                elif isinstance(item_key, str) and item_key in item:  # Chiave diretta
                                    fields[field_name] = item[item_key]
                            
                            # Ottieni il timestamp se configurato
                            timestamp = None
                            if timestamp_field and timestamp_field in item:
                                timestamp = item[timestamp_field]
                                if config.DEBUG and idx < 3:
                                    config.logger.debug(f"Using timestamp '{timestamp}' from field '{timestamp_field}' for item {idx+1}")
                            
                            # Scrivi su VictoriaMetrics
                            victoria_metrics_manager.write_metrics(measurement_name, tags, fields, timestamp)
                        
                        config.logger.info(f"Stored {len(items)} {current_api_name} metrics points")
                    else:
                        if config.DEBUG:
                            config.logger.debug(f"No {current_api_name} metrics received or empty response")
                
                except Exception as e:
                    error_msg = f"Error during {current_api_name} metrics collection: {str(e)}"
                    config.logger.error(error_msg)
                    
                    if config.DEBUG:
                        import traceback
                        config.logger.debug(f"Detailed error traceback: {traceback.format_exc()}")
                        
                    # Increment error counter
                    if ENABLE_PROMETHEUS_METRICS:
                        METRICS_COLLECTION_ERRORS.labels(type=f'metrics_{current_api_name}').inc()
        
        # Store the current time as the last successful run
        victoria_metrics_manager.store_last_metrics_run(now)
        if config.DEBUG:
            config.logger.debug(f"Updated last metrics run timestamp to {now}")
        
        # Update health status
        app_health["status"] = "healthy"
        app_health["last_metrics_run"] = now
        
    except Exception as e:
        error_msg = f"Error during metrics collection: {str(e)}"
        config.logger.error(error_msg)
        if config.DEBUG:
            import traceback
            config.logger.debug(f"Detailed error traceback: {traceback.format_exc()}")
            
        app_health["errors"].append({
            "time": datetime.now().isoformat(),
            "component": "metrics_collector",
            "message": error_msg
        })
        # Keep only the last 10 errors
        if len(app_health["errors"]) > 10:
            app_health["errors"] = app_health["errors"][-10:]
        
        # Increment error counter
        if ENABLE_PROMETHEUS_METRICS:
            METRICS_COLLECTION_ERRORS.labels(type='metrics').inc()
    
    finally:
        # Record collection duration
        duration = time.time() - start_time
        if ENABLE_PROMETHEUS_METRICS:
            collector_type = f'metrics_{api_name}' if api_name else 'metrics'
            METRICS_COLLECTION_DURATION.labels(type=collector_type).observe(duration)
            
        if config.DEBUG:
            config.logger.debug(f"Metrics collection completed in {duration:.2f} seconds")
    
    config.logger.info("Metrics collection completed")

def collect_configurations(api_name=None):
    """
    Colleziona dati di configurazione da Citrix Cloud e li memorizza in PostgreSQL.
    
    Args:
        api_name: Se specificato, raccoglie solo la configurazione per quell'API specifica
    """
    if api_name:
        config.logger.info(f"Starting configuration collection for {api_name}")
    else:
        config.logger.info("Starting configuration collection for all configured APIs")
        
    global app_health
    
    # Track configuration collection duration
    start_time = time.time()
    
    try:
        # Carica la configurazione delle query
        queries_config = load_queries_config()
        
        # Se non è stata trovata nessuna configurazione, esci
        if queries_config is None:
            config.logger.error("No queries configuration available, skipping configuration collection")
            return
        
        now = datetime.now().isoformat()
        if config.DEBUG:
            config.logger.debug(f"Starting configuration collection at {now}")
        
        # Esegui tutte le query di configurazione configurate o solo quella specificata
        if 'config' in queries_config:
            for query_config in queries_config['config']:
                current_api_name = query_config['api_name']
                
                # Se è stato specificato un api_name e non corrisponde a quello corrente, salta
                if api_name and current_api_name != api_name:
                    continue
                
                # Se è specificato un override del nome API, usa quello per la query
                api_query_name = query_config.get('api_name_override', current_api_name)
                entity_type = api_query_name.replace('_config', '')  # Remove _config suffix if present
                
                config.logger.info(f"Collecting {current_api_name} configuration")
                if config.DEBUG:
                    config.logger.debug(f"Using configuration: {json.dumps(query_config)}")
                
                try:
                    # Esegui la query all'API senza passare il site_id
                    response = citrix_client.query_api(api_query_name)
                    
                    if response:
                        if config.DEBUG:
                            config.logger.debug(f"Received {len(response) if isinstance(response, list) else 'object'} from {current_api_name} API")
                        
                        # Store configuration data using the generic store_entity method
                        postgres_manager.store_entity(entity_type, response)
                        config.logger.info(f"Stored {current_api_name} configuration data")
                    else:
                        if config.DEBUG:
                            config.logger.debug(f"No {current_api_name} configuration received or empty response")
                
                except Exception as e:
                    error_msg = f"Error during {current_api_name} configuration collection: {str(e)}"
                    config.logger.error(error_msg)
                    
                    if config.DEBUG:
                        import traceback
                        config.logger.debug(f"Detailed error traceback: {traceback.format_exc()}")
                        
                    # Increment error counter
                    if ENABLE_PROMETHEUS_METRICS:
                        METRICS_COLLECTION_ERRORS.labels(type=f'config_{current_api_name}').inc()
        
        # Update health status
        app_health["status"] = "healthy"
        app_health["last_config_run"] = now
    
    except Exception as e:
        error_msg = f"Error during configuration collection: {str(e)}"
        config.logger.error(error_msg)
        
        if config.DEBUG:
            import traceback
            config.logger.debug(f"Detailed error traceback: {traceback.format_exc()}")
            
        app_health["errors"].append({
            "time": datetime.now().isoformat(),
            "component": "config_collector",
            "message": error_msg
        })
        # Keep only the last 10 errors
        if len(app_health["errors"]) > 10:
            app_health["errors"] = app_health["errors"][-10:]
        
        # Increment error counter
        if ENABLE_PROMETHEUS_METRICS:
            METRICS_COLLECTION_ERRORS.labels(type='config').inc()
    
    finally:
        # Record configuration duration
        duration = time.time() - start_time
        if ENABLE_PROMETHEUS_METRICS:
            collector_type = f'config_{api_name}' if api_name else 'config'
            METRICS_COLLECTION_DURATION.labels(type=collector_type).observe(duration)
            
        if config.DEBUG:
            config.logger.debug(f"Configuration collection completed in {duration:.2f} seconds")
    
    config.logger.info("Configuration collection completed")

def setup_api_schedulers():
    """
    Configura schedulers separati per ogni API in base ai loro intervalli di polling.
    """
    # Carica le configurazioni delle API
    api_configs = load_api_config()
    queries_config = load_queries_config()
    
    if not api_configs:
        config.logger.warning("No API configurations found. Using default intervals.")
        # Fallback to default global intervals
        setup_default_schedulers()
        return
    
    # Scheduling delle metriche
    if queries_config and 'metrics' in queries_config:
        for query_config in queries_config['metrics']:
            api_name = query_config['api_name']
            
            if api_name in api_configs and 'polling_interval' in api_configs[api_name]:
                interval = api_configs[api_name]['polling_interval']
                config.logger.info(f"Scheduling {api_name} metrics collection every {interval} seconds")
                
                # Schedule specific API collection
                schedule.every(interval).seconds.do(collect_metrics, api_name=api_name)
                
                # Run immediately at startup for this API
                collect_metrics(api_name=api_name)
            else:
                # Use default interval if not specified
                default_interval = config.METRICS_COLLECTION_INTERVAL
                config.logger.info(f"No specific interval for {api_name}, using default: {default_interval} seconds")
                schedule.every(default_interval).seconds.do(collect_metrics, api_name=api_name)
                collect_metrics(api_name=api_name)
    
    # Scheduling delle configurazioni
    if queries_config and 'config' in queries_config:
        for query_config in queries_config['config']:
            api_name = query_config['api_name']
            api_query_name = query_config.get('api_name_override', api_name)
            
            if api_query_name in api_configs and 'polling_interval' in api_configs[api_query_name]:
                interval = api_configs[api_query_name]['polling_interval']
                config.logger.info(f"Scheduling {api_name} configuration collection every {interval} seconds")
                
                # Schedule specific API configuration collection
                schedule.every(interval).seconds.do(collect_configurations, api_name=api_name)
                
                # Run immediately at startup for this API
                collect_configurations(api_name=api_name)
            else:
                # Use default interval if not specified
                default_interval = config.CONFIG_COLLECTION_INTERVAL
                config.logger.info(f"No specific interval for {api_name} configuration, using default: {default_interval} seconds")
                schedule.every(default_interval).seconds.do(collect_configurations, api_name=api_name)
                collect_configurations(api_name=api_name)

def setup_default_schedulers():
    """Configura gli scheduler con intervalli globali predefiniti."""
    config.logger.info(f"Starting metrics scheduler with interval of {config.METRICS_COLLECTION_INTERVAL} seconds")
    schedule.every(config.METRICS_COLLECTION_INTERVAL).seconds.do(collect_metrics)
    
    config.logger.info(f"Starting configuration scheduler with interval of {config.CONFIG_COLLECTION_INTERVAL} seconds")
    schedule.every(config.CONFIG_COLLECTION_INTERVAL).seconds.do(collect_configurations)
    
    if config.DEBUG:
        config.logger.debug(f"Scheduled metrics collection every {config.METRICS_COLLECTION_INTERVAL} seconds")
        config.logger.debug(f"Scheduled configuration collection every {config.CONFIG_COLLECTION_INTERVAL} seconds")
        config.logger.debug("Running first collections immediately")
    
    # Run immediately at startup
    collect_metrics()
    collect_configurations()

def run_schedulers():
    """Esegue tutti gli scheduler configurati."""
    while True:
        schedule.run_pending()
        time.sleep(1)

class HTTPHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler for health checks and metrics endpoint."""
    
    def do_GET(self):
        """Handle GET requests to health and metrics endpoints."""
        if self.path == '/health':
            if config.DEBUG:
                config.logger.debug(f"Health check request from {self.client_address[0]}")
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(app_health).encode())
            
            if config.DEBUG:
                config.logger.debug(f"Health check response: {json.dumps(app_health)}")
                
        elif self.path == '/metrics':
            if not ENABLE_PROMETHEUS_METRICS:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'Prometheus metrics endpoint is disabled')
                return
                
            if config.DEBUG:
                config.logger.debug(f"Metrics request from {self.client_address[0]}")
                
            self.send_response(200)
            self.send_header('Content-type', CONTENT_TYPE_LATEST)
            self.end_headers()
            metrics = generate_latest()
            self.wfile.write(metrics)
            
            if config.DEBUG:
                config.logger.debug(f"Metrics response size: {len(metrics)} bytes")
                
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        """Override to use our logger instead."""
        if self.path != '/health' and self.path != '/metrics':
            config.logger.info(f"{self.address_string()} - {format % args}")

def run_http_server():
    """Run the HTTP server for health checks and metrics."""
    try:
        httpd = socketserver.TCPServer(("", 8000), HTTPHandler)
        config.logger.info("HTTP server started on port 8000 with /health" + (" and /metrics" if ENABLE_PROMETHEUS_METRICS else ""))
        if config.DEBUG:
            config.logger.debug("HTTP server is running in debug mode")
        httpd.serve_forever()
    except Exception as e:
        config.logger.error(f"Failed to start HTTP server: {str(e)}")
        if config.DEBUG:
            import traceback
            config.logger.debug(f"HTTP server error details: {traceback.format_exc()}")

def signal_handler(sig, frame):
    """Handle termination signals gracefully."""
    config.logger.info("Received termination signal, shutting down...")
    if config.DEBUG:
        config.logger.debug(f"Signal received: {sig}")
    # Close database connections
    try:
        postgres_manager.close()
        if config.DEBUG:
            config.logger.debug("PostgreSQL connection closed")
    except Exception as e:
        if config.DEBUG:
            config.logger.debug(f"Error closing PostgreSQL connection: {str(e)}")
    sys.exit(0)

def main():
    """Main entry point for the application."""
    # Validate configuration
    if not config.validate_config():
        config.logger.error("Invalid configuration, exiting")
        sys.exit(1)
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    app_version = os.environ.get('APP_VERSION', '1.0.0')
    config.logger.info(f"Starting Citrix Cloud metrics collector v{app_version}")
    config.logger.info(f"Prometheus metrics endpoint is {'enabled' if ENABLE_PROMETHEUS_METRICS else 'disabled'}")
    
    if config.DEBUG:
        config.logger.debug("Application running in DEBUG mode")
        config.logger.debug(f"Python version: {sys.version}")
        config.logger.debug(f"Process ID: {os.getpid()}")
    
    # Initialize Site ID retrieval for REST API calls
    try:
        # First try to get the site_id from the database
        site_id = postgres_manager.get_site_id()
        
        # If not found in the database, try to get it from the Citrix API
        if not site_id:
            config.logger.info("Site ID not found in database, trying to retrieve from Citrix API")
            site_id = citrix_client.get_site_id()
            
            # If we got a site_id from the API, save it in the database for future use
            if site_id:
                postgres_manager.set_site_id(site_id)
        # If site_id was found in the database, make sure to set it in the citrix_client
        elif site_id:
            citrix_client.site_id = site_id
            
        if site_id:
            config.logger.info(f"Citrix Site ID initialized: {site_id}")
        else:
            config.logger.warning("Could not retrieve Citrix Site ID. Some REST API calls may fail.")
    except Exception as e:
        config.logger.error(f"Error retrieving Citrix Site ID: {str(e)}")
    
    # Initialize Prometheus metrics if enabled
    if ENABLE_PROMETHEUS_METRICS:
        initialize_metrics(version=app_version)
        if config.DEBUG:
            config.logger.debug("Prometheus metrics initialized")
    
    # Start HTTP server for health and metrics endpoints
    http_thread = threading.Thread(target=run_http_server)
    http_thread.daemon = True
    http_thread.start()
    if config.DEBUG:
        config.logger.debug("HTTP server thread started")
    
    # Setup schedulers with endpoint-specific intervals
    scheduler_thread = threading.Thread(target=run_schedulers)
    scheduler_thread.daemon = True
    
    # Configure schedulers based on API configurations
    setup_api_schedulers()
    
    # Start the scheduler thread
    scheduler_thread.start()
    
    if config.DEBUG:
        config.logger.debug("Scheduler thread started")
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        config.logger.info("Application interrupted, shutting down...")
        if config.DEBUG:
            config.logger.debug("KeyboardInterrupt received")

if __name__ == "__main__":
    main()