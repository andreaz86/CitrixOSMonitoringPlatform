from prometheus_client import Counter, Histogram, Gauge, Info

# API request metrics
API_REQUESTS = Counter(
    'citrix_api_requests_total',
    'Total number of Citrix API requests',
    ['endpoint', 'method', 'status']
)

API_LATENCY = Histogram(
    'citrix_api_request_duration_seconds',
    'Latency of Citrix API requests in seconds',
    ['endpoint', 'method'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

# Metrics collection metrics
METRICS_COLLECTION_DURATION = Histogram(
    'citrix_metrics_collection_duration_seconds',
    'Duration of metrics collection in seconds',
    ['type']
)

METRICS_COLLECTION_ERRORS = Counter(
    'citrix_metrics_collection_errors_total',
    'Total number of errors during metrics collection',
    ['type']
)

# System metrics
APP_INFO = Info(
    'citrix_metrics_app_info',
    'Application information'
)

def initialize_metrics(version='1.0.0'):
    """Initialize metrics with static values."""
    APP_INFO.info({
        'version': version,
        'name': 'citrix_metrics_exporter'
    })