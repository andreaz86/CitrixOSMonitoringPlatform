# Fluent Bit Logs Configuration

This Fluent Bit instance is configured to receive and process logs from Telegraf, applying transformations to make them more suitable for visualization in Grafana through VictoriaLogs.

## Architecture

```
Telegraf → Fluent Bit Logs (port 5170) → VictoriaLogs → Grafana
```

## Input Configuration

Fluent Bit receives logs from Telegraf over TCP in JSON format. The listening port is configurable through the `TELEGRAF_PORT` environment variable (default: 5170):

```ini
[INPUT]
    Name        tcp
    Listen      0.0.0.0
    Port        ${TELEGRAF_PORT}
    Format      json
    Threaded    true
```

The port configuration is synchronized between:
- Environment variable in `.env`: `TELEGRAF_PORT=5170`
- Docker Compose port mapping: `ports: - ${TELEGRAF_PORT}:5170`
- Telegraf output configuration: 
```ini
[[outputs.socket_writer]]
    address = "tcp://${SERVERNAMEORIP}:${TELEGRAF_PORT}"
```

Telegraf uses the `socket_writer` output plugin instead of HTTP for optimal performance:
- Lower network and CPU overhead through persistent TCP connections
- Reduced latency compared to HTTP requests
- Better handling of high-volume log streams
- Efficient binary streaming of data
- Improved backpressure handling

## Log Processing Pipeline

### 1. Tag Unnesting
The first filter extracts nested tags for better processing:

```ini
[FILTER]
    Name         nest
    Match        *
    Operation    lift
    Nested_under tags
```

This transforms logs from:
```json
{
    "tags": {
        "eventId": "1234",
        "source": "Application"
    }
}
```
to:
```json
{
    "eventId": "1234",
    "source": "Application"
}
```

### 2. Tag Cleanup
Removes the now-empty tags structure:

```ini
[FILTER]
    Name         modify
    Match        *
    Remove       tags
```

### 3. Log Level Normalization
Renames 'LevelText' to 'level' for better Grafana compatibility:

```ini
[FILTER]
    Name         modify
    Match        *
    Rename       LevelText level
```

This allows Grafana to properly interpret log levels:
- ERROR
- WARNING
- INFO
- DEBUG

## Output Configuration

Logs are forwarded to VictoriaLogs with specific parameters for optimal indexing:

```ini
[Output]
    Name http
    Match *
    host victorialogs
    port 9428
    uri /insert/jsonline?_stream_fields=stream&_msg_field=fields.Message&_time_field=timestamp
    format json_lines
    json_date_format iso8601
```

Key parameters:
- `_stream_fields=stream`: Defines log stream identification
- `_msg_field=fields.Message`: Specifies the main message field
- `_time_field=timestamp`: Sets the timestamp field for chronological ordering

## Storage and Buffering

The service uses persistent storage for reliability:

```ini
[SERVICE]
    storage.path    /var/log/flb-storage/
    storage.sync    normal
    storage.checksum    off
    storage.backlog.mem_limit 5M
```

This ensures:
- No log loss during service restarts
- Buffering during high load
- Memory-efficient operation

## Health Monitoring

Built-in health check endpoint for monitoring:

```ini
[SERVICE]
    HTTP_Server  On
    HTTP_Listen  0.0.0.0
    HTTP_PORT    2020
    Health_Check On 
    HC_Errors_Count 5
    HC_Retry_Failure_Count 5
    HC_Period 5
```

## Log Transformation Examples

### Windows Event Logs
Before:
```json
{
    "tags": {
        "LevelText": "Error",
        "Source": "Application"
    },
    "fields": {
        "Message": "Application error"
    }
}
```

After:
```json
{
    "level": "Error",
    "Source": "Application",
    "fields": {
        "Message": "Application error"
    }
}
```

### System Logs
Before:
```json
{
    "tags": {
        "LevelText": "Warning",
        "EventID": 1234
    },
    "fields": {
        "Message": "Disk space low"
    }
}
```

After:
```json
{
    "level": "Warning",
    "EventID": 1234,
    "fields": {
        "Message": "Disk space low"
    }
}
```

## Troubleshooting

1. **Input Verification**
```bash
# Check logs
docker logs fluentbit-logs
```
