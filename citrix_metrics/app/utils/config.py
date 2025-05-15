import os
from dotenv import load_dotenv
import logging
import yaml

# Load environment variables from .env file if present
load_dotenv()

# Get debug setting from environment
DEBUG = os.environ.get('DEBUG', 'false').lower() in ('true', '1', 't', 'yes')

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('citrix_metrics')

if DEBUG:
    logger.debug("Debug mode is enabled")

# Citrix Cloud API Configuration
CITRIX_CLIENT_ID = os.environ.get('CITRIX_CLIENT_ID')
CITRIX_CLIENT_SECRET = os.environ.get('CITRIX_CLIENT_SECRET')
CITRIX_CUSTOMER_ID = os.environ.get('CITRIX_CUSTOMER_ID')
CITRIX_API_BASE_URL = os.environ.get('CITRIX_API_BASE_URL', 'https://api.cloud.com')
CITRIX_AUTH_URL = os.environ.get('CITRIX_AUTH_URL', 'https://api.cloud.com/cctrustoauth2/root/tokens/clients')
# Citrix Instance ID (site ID) storage
CITRIX_INSTANCE_ID = os.environ.get('CITRIX_INSTANCE_ID')
CITRIX_INSTANCE_ID_FILE = os.environ.get('CITRIX_INSTANCE_ID_FILE', '/app/data/citrix_instance_id.txt')

# Proxy Configuration
HTTP_PROXY = os.environ.get('HTTP_PROXY')
HTTPS_PROXY = os.environ.get('HTTPS_PROXY')
NO_PROXY = os.environ.get('NO_PROXY')
# Lowercase variants
http_proxy = os.environ.get('http_proxy')
https_proxy = os.environ.get('https_proxy')
no_proxy = os.environ.get('no_proxy')

# VictoriaMetrics Configuration for Metrics
METRICS_ENDPOINT = os.environ.get('METRICS_ENDPOINT', 'http://victoriametrics:8428')

# VictoriaLogs Configuration for Logs
# The URL per requirements: http://localhost:9428/insert/jsonline?_msg_field=fields.message&_time_field=timestamp,_stream_fields=tags.log_source,tags.metric_type
# We'll use the base URL here and add the query parameters in the client
VICTORIA_LOGS_URL = os.environ.get('VICTORIA_LOGS_URL', 'http://victorialogs:9428/insert/jsonline')

# PostgreSQL Configuration for Settings/Configurations
POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'postgres')
POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'citrix')
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'postgres')

# Collection Intervals (in seconds)
METRICS_COLLECTION_INTERVAL = int(os.environ.get('METRICS_COLLECTION_INTERVAL', '300'))  # 5 minutes default
CONFIG_COLLECTION_INTERVAL = int(os.environ.get('CONFIG_COLLECTION_INTERVAL', '3600'))   # 1 hour default

# Retry configuration
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '3'))
RETRY_BACKOFF_FACTOR = float(os.environ.get('RETRY_BACKOFF_FACTOR', '0.5'))
RETRY_MAX_WAIT = int(os.environ.get('RETRY_MAX_WAIT', '30'))

# Timestamp storage file for metrics collection
LAST_METRICS_RUN_FILE = os.environ.get('LAST_METRICS_RUN_FILE', '/app/data/last_metrics_run.txt')

# Make sure data directory exists
os.makedirs(os.path.dirname(LAST_METRICS_RUN_FILE), exist_ok=True)

def validate_config():
    """Validate that all required configuration parameters are set."""
    missing_vars = []
    for var_name in ['CITRIX_CLIENT_ID', 'CITRIX_CLIENT_SECRET', 'CITRIX_CUSTOMER_ID']:
        if not globals().get(var_name):
            missing_vars.append(var_name)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    if DEBUG:
        logger.debug("Configuration validation successful")
        logger.debug(f"API Base URL: {CITRIX_API_BASE_URL}")
        logger.debug(f"Auth URL: {CITRIX_AUTH_URL}")
        logger.debug(f"Metrics Endpoint: {METRICS_ENDPOINT}")
        logger.debug(f"Collection Interval: {METRICS_COLLECTION_INTERVAL} seconds")
    
    return True

def load_api_config():
    """
    Loads the API configuration from the specified file.
    If the file is not found, it tries a fallback path.
    If still not found, returns an empty dictionary.
    
    Returns:
        dict: API configuration as a dictionary
    """
    api_config_path = os.environ.get('API_CONFIG_PATH', '/etc/citrix_metrics/api_config.yaml')
    
    # Try primary location
    if not os.path.exists(api_config_path):
        # Try fallback location
        fallback_path = '/data/docker_compose/citrix_metrics/config/api_config.yaml'
        if os.path.exists(fallback_path):
            api_config_path = fallback_path
        else:
            logger.error(f"API configuration file not found: {api_config_path} or {fallback_path}")
            return {}
    
    try:
        with open(api_config_path, 'r') as f:
            api_configs = yaml.safe_load(f)
            logger.info(f"Loaded API configurations from {api_config_path}")
            return api_configs
    except Exception as e:
        logger.error(f"Error loading API configurations: {str(e)}")
        return {}

# Cache for queries configuration
_queries_config_cache = None

def load_queries_config():
    """
    Loads the queries configuration from the specified file.
    Uses caching to avoid reading the file multiple times.
    If the file is not found, it tries a fallback path.
    If still not found, returns None.
    
    Returns:
        dict: Queries configuration as a dictionary or None if not found
    """
    global _queries_config_cache
    
    # Return cached config if already loaded
    if _queries_config_cache is not None:
        return _queries_config_cache
        
    queries_config_path = os.environ.get('QUERIES_CONFIG_PATH', '/etc/citrix_metrics/queries_config.yaml')
    
    # Try primary location
    if not os.path.exists(queries_config_path):
        # Try fallback location
        fallback_path = '/data/docker_compose/citrix_metrics/config/queries_config.yaml'
        if os.path.exists(fallback_path):
            queries_config_path = fallback_path
        else:
            logger.error(f"Queries configuration file not found: {queries_config_path} or {fallback_path}")
            return None
    
    try:
        with open(queries_config_path, 'r') as f:
            queries_config = yaml.safe_load(f)
            logger.info(f"Loaded queries configuration from {queries_config_path}")
            _queries_config_cache = queries_config
            return queries_config
    except Exception as e:
        logger.error(f"Error loading queries configuration: {str(e)}")
        return None