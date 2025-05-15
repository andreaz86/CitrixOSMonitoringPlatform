# Fluent Bit Metrics Configuration

This Fluent Bit instance is configured to receive and process metrics from uberAgent through NGINX. It acts as a metrics processor and forwarder, handling the transformation of uberAgent's Elasticsearch-compatible data format into VictoriaMetrics format.

## Architecture

```
uberAgent → NGINX (port 8088) → Fluent Bit Metrics → VictoriaMetrics
```

## Input Configuration

Fluent Bit receives data from NGINX, which acts as a reverse proxy for uberAgent's metrics. The configuration is set up to handle the Elasticsearch Bulk API format:

1. NGINX Configuration (`nginx/nginx.conf`):
```nginx
location /uberagent/_bulk {
  proxy_pass http://fluentbit-metrics:8088/_bulk;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header Host $http_host;
  proxy_pass_request_headers on;
}
```

2. Fluent Bit Input Configuration (`fluent-bit.conf`):
```ini
[INPUT]
    Name              http
    Listen           0.0.0.0
    Port             8088
    Tag              uberagent
    Format           json
```

## Data Processing

### Transformation Pipeline

1. **Input Stage**: Receives JSON data in Elasticsearch Bulk API format
2. **Lua Processing**: Transforms data using custom Lua scripts
3. **Output Stage**: Forwards processed metrics to VictoriaMetrics

### Lua Transformation Script Details

The Lua script (`scripts/transform.lua`) is a critical component that processes incoming data from uberAgent. Here's a detailed breakdown of its functionality:

#### Input Processing
- Receives data in Elasticsearch Bulk API format
- Each record consists of two parts:
  1. Metadata line (index information)
  2. Data line (actual metrics)

#### Data Transformation Types

1. **Regular Metrics Processing**
   - Extracts metric names and values
   - Converts timestamp to Unix format
   - Adds necessary labels and tags
   - Formats data for VictoriaMetrics ingestion
   ```lua
   -- Example transformation
   Input: {"@timestamp": "2023-05-15T10:00:00", "metric": "CPU.Usage", "value": 75}
   Output: ua_cpu_usage{host="server1",process="chrome"} 75 1684145400
   ```

#### Buffer Management
- Uses Fluent Bit's built-in storage for reliability
- Implements backpressure handling
- Retries failed writes to VictoriaMetrics

#### Error Handling
- Records transformation errors in logs
- Maintains error counters for monitoring
- Implements fallback transformations for malformed data

## Configuration Files

- `fluent-bit.conf`: Main configuration file
- `parsers.conf`: Custom parser definitions
- `scripts/transform.lua`: Data transformation logic


## Volume Mounts

```yaml
volumes:
  - ./fluentbit_metrics/fluent-bit.conf:/fluent-bit/etc/fluent-bit.conf:ro
  - ./fluentbit_metrics/parsers.conf:/fluent-bit/etc/parsers.conf:ro
  - ./fluentbit_metrics/scripts/transform.lua:/fluent-bit/etc/transform.lua:ro
  - ${ROOT_PATH}/fluentbit_metrics:/var/log/flb-storage/
```

## Security

- No direct external access (protected behind NGINX)
- Read-only configuration files
- Isolated network access (only to VictoriaMetrics and Jaeger)

## Data Flow Examples

1. **Regular Metrics**
```
uberAgent → NGINX → Fluent Bit → VictoriaMetrics
```

2. **Session Events**
```
uberAgent → NGINX → Fluent Bit → VictoriaMetrics
                         ↓
                      Jaeger
```
