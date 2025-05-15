# Citrix Metrics Collector

The Citrix Metrics Collector is a sophisticated Python-based service designed to collect, process, and store metrics and configuration data from the Citrix Cloud API. It provides a robust and configurable solution for monitoring Citrix environments.

## Features

- **Dynamic API Integration**
  - Configurable API endpoints and parameters
  - Support for both OData and REST APIs
  - Automatic pagination handling
  - Flexible data mapping

- **Multi-Database Support**
  - VictoriaMetrics for time-series metrics
  - PostgreSQL for configuration data
  - VictoriaLogs for log data

- **Advanced Configuration System**
  - YAML-based configuration files
  - Dynamic field type inference
  - Configurable polling intervals
  - Flexible data mapping

- **Monitoring & Observability**
  - Prometheus metrics export
  - Health check endpoint
  - Detailed logging
  - Performance metrics

## Configuration Files

The service uses two main configuration files:

### api_config.yaml

The `api_config.yaml` file defines the detailed configuration for each Citrix API endpoint. The complete structure is as follows:

```yaml
endpoint_name:                    # Endpoint name (e.g., load_indexes, machines, etc.)
  endpoint: "/api/path"          # API endpoint path
  type: "rest|odata"            # API type: rest for REST API, odata for OData API
  polling_interval: 60          # Polling interval in seconds
  timestamp_field: "DateField"  # Field to use as data timestamp
  filter_field: "DateField"    # Field used for time filtering
  time_window: 5              # Time window in seconds for filtering (optional)
  days_to_search: 1          # Days to keep for logs (only for type: "log")
  select:                   # List of fields to retrieve from the API
    - "Field1"
    - "Field2"
  expand:                  # Nested relationships to expand
    RelatedEntity:        # Name of the entity to expand
      - "RelatedField1"
      - "RelatedField2"
    SubEntity:           # Multiple levels of expansion are possible
      NestedField:
        - "SubField1"
  multi_value_fields:    # Fields that can contain arrays of values
    - "ArrayField1"
```

Supported API types:
- `rest`: For standard Citrix Cloud REST APIs
- `odata`: For Citrix Monitor OData APIs
- `log`: For APIs that return log data

### queries_config.yaml

The `queries_config.yaml` file defines how to process and store the data. The complete structure is as follows:

```yaml
# Common fields for all entities
common_fields:
  Id: "VARCHAR(255)"      # SQL type for Id field
  Name: "VARCHAR(255)"    # SQL type for Name field
  collected_at: "TIMESTAMP"

# Rules for automatic field type inference
field_type_defaults:
  prefixes:              # Types based on field name prefix
    is_: "BOOLEAN"      # Fields starting with "is_" are boolean
    has_: "BOOLEAN"     # Fields starting with "has_" are boolean
    count_: "INTEGER"   # Fields starting with "count_" are integer
  suffixes:            # Types based on field name suffix
    _id: "VARCHAR(255)"
    _count: "INTEGER"
    _date: "TIMESTAMP"
    _time: "TIMESTAMP"
    _type: "INTEGER"
    _state: "INTEGER"
    _status: "INTEGER"
  default: "VARCHAR(255)"  # Default type if no other rules match

# VictoriaMetrics metrics configuration
metrics:
  - api_name: "endpoint_name"         # Endpoint name from api_config.yaml
    measurement_name: "metric_name"   # Metric name in VictoriaMetrics
    tag_mappings:                    # Tag mappings
      tag_name: ["Field", "SubField"] # Support for nested fields
    field_mappings:                  # Metric field mappings
      metric_field: "APIField"      # Metric field : API field
    timestamp_field: "DateField"   # Field to use as timestamp

# PostgreSQL configuration data configuration
config:
  - api_name: "endpoint_name"       # Endpoint name from api_config.yaml
    api_name_override: "other_name" # Optional endpoint name override
    field_types:                   # Explicit field type definitions
      Field1: "VARCHAR(255)"      # SQL type for Field1
      Field2: "INTEGER"          # SQL type for Field2
      BooleanField: "BOOLEAN"   # SQL type for BooleanField
```

Supported data types:
- **Metrics**: Time-series data stored in VictoriaMetrics
- **Configuration**: Structural data stored in PostgreSQL
- **Logs**: Events and logs stored in VictoriaLogs

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CITRIX_CLIENT_ID` | | Citrix Cloud API client ID |
| `CITRIX_CLIENT_SECRET` | | Citrix Cloud API client secret |
| `CITRIX_CUSTOMER_ID` | | Citrix Cloud customer ID |
| `CITRIX_API_BASE_URL` | https://api.cloud.com | Citrix API base URL |
| `METRICS_ENDPOINT` | http://victoriametrics:8428 | VictoriaMetrics endpoint |
| `POSTGRES_HOST` | postgresql | PostgreSQL host |
| `POSTGRES_PORT` | 5432 | PostgreSQL port |
| `POSTGRES_DB` | citrix_metrics | Database name |
| `POSTGRES_USER` | svc_citrix_metrics | Database user |
| `POSTGRES_PASSWORD` | | Database password |
| `METRICS_COLLECTION_INTERVAL` | 300 | Metrics collection interval (seconds) |
| `CONFIG_COLLECTION_INTERVAL` | 3600 | Config collection interval (seconds) |
| `MAX_RETRIES` | 3 | Maximum API retry attempts |
| `RETRY_BACKOFF_FACTOR` | 0.5 | Retry backoff factor |
| `RETRY_MAX_WAIT` | 30 | Maximum retry wait time |
| `DEBUG` | false | Enable debug logging |
| `ENABLE_PROMETHEUS_METRICS` | true | Enable Prometheus metrics |

## Deployment

The service is configured in docker-compose.yaml as follows:

```yaml
citrix_metrics:
  build:
    context: ./citrix_metrics
  image: registry.azcloud.ovh/citrix_metrics:latest
  container_name: citrix-metrics
  restart: unless-stopped
  volumes:
    - ./citrix_metrics/app:/app/app
    - ./citrix_metrics/requirements.txt:/app/requirements.txt
    - ${ROOT_PATH}/citrix_metrics/data:/app/data
    - ./citrix_metrics/config:/etc/citrix_metrics
  environment:
    - CITRIX_CLIENT_ID=${CTX_CLIENT_ID}
    - CITRIX_CLIENT_SECRET=${CTX_CLIENT_SECRET}
    - CITRIX_CUSTOMER_ID=${CTX_CUSTOMER_ID}
    - POSTGRES_PASSWORD=${DB_SVCCITRIX_PWD}
    - DEBUG=true
```

## Data Flow

1. **API Data Collection**
   - Periodic polling of configured Citrix Cloud APIs
   - Data validation and transformation
   - Rate limiting and retry handling

2. **Metrics Processing**
   - Extraction of metric values
   - Tag and field mapping
   - Timestamp processing
   - Storage in VictoriaMetrics

3. **Configuration Processing**
   - Data type inference
   - Schema validation
   - Storage in PostgreSQL

4. **Log Processing**
   - Log event processing
   - Timestamp extraction
   - Storage in VictoriaLogs

## Monitoring

### Prometheus Metrics

Available metrics:
- `citrix_metrics_collection_duration_seconds`: Collection duration
- `citrix_metrics_collection_errors_total`: Collection error count
- `citrix_api_requests_total`: API request count
- `citrix_api_latency_seconds`: API request latency
- `citrix_app_info`: Application information

### Health Check

Endpoint: `http://host:8000/health`
Returns:
- Status: starting/healthy/unhealthy
- Last successful runs
- Error information

## Troubleshooting

### Common Issues

1. **API Connection Issues**
   - Verify Citrix Cloud credentials
   - Check network connectivity
   - Verify proxy configuration

2. **Database Connection Issues**
   - Check database credentials
   - Verify network access
   - Check database logs

3. **Data Collection Issues**
   - Check API configuration
   - Verify field mappings
   - Review error logs

### Logging

Log levels:
- ERROR: Critical errors
- WARNING: Important warnings
- INFO: Operation information
- DEBUG: Detailed debugging info

Enable debug mode by setting `DEBUG=true`