# ProxyTrace

ProxyTrace is a high-performance trace data proxy service designed to collect, transform, and forward tracing data from uberAgent to OpenTelemetry-compatible backends. It processes both logon and logoff events, converting them into standardized spans for distributed tracing.

## Features

- **TCP Socket Server**: Receives trace data over TCP socket connections
- **Batch Processing**: Efficiently processes spans in configurable batches
- **OTLP Export**: Exports spans to OpenTelemetry collector endpoints
- **Circuit Breaking**: Built-in circuit breaker to prevent cascading failures
- **InfluxDB Integration**: Maps session GUIDs to trace IDs in InfluxDB for correlation
- **Prometheus Metrics**: Exposes operational metrics for monitoring
- **Configurable Workers**: Multi-threaded design for high throughput

## Configuration

The application can be configured using environment variables:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `LISTEN_HOST` | 0.0.0.0 | Host address to listen on |
| `LISTEN_PORT` | 5000 | Port to listen on for incoming TCP connections |
| `METRICS_PORT` | 8000 | Port for Prometheus metrics endpoint |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | http://jaeger:4318/v1/traces | OpenTelemetry exporter endpoint |
| `WORKER_COUNT` | 8 | Number of worker threads for processing |
| `BATCH_SIZE` | 200 | Maximum number of spans in a batch |
| `BATCH_TIMEOUT` | 0.2 | Maximum time (seconds) to wait before sending a batch |
| `QUEUE_MAXSIZE` | 10000 | Maximum size of internal queues |
| `DEBUG_MODE` | false | Enable verbose logging |
| `INFLUX_URL` | http://victoriametrics:8428 | InfluxDB URL |
| `INFLUX_TOKEN` | | InfluxDB authentication token |
| `INFLUX_ORG` | | InfluxDB organization |
| `INFLUX_BUCKET` | traces | InfluxDB bucket for storing trace mappings |

## Metrics

The application exposes the following Prometheus metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `records_received_total` | Counter | Total number of records received |
| `records_parsed_total` | Counter | Total number of records parsed into spans |
| `batches_sent_total` | Counter | Total number of batches successfully sent |
| `export_failures_total` | Counter | Total number of batch export failures |
| `span_queue_size` | Gauge | Current size of the span queue |
| `batch_latency_seconds` | Summary | Time spent sending batch |

## Architecture

```
┌────────────┐    ┌──────────┐    ┌───────────────┐    ┌──────────────┐
│ TCP Client │───▶│ Receiver │───▶│ Worker Threads │───▶│ Batch Export │───▶ OTLP Endpoint
└────────────┘    └──────────┘    └───────────────┘    └──────────────┘
                                                             │
                                                             ▼
                                                      ┌────────────────┐
                                                      │ InfluxDB       │
                                                      │ (Trace Maps)   │
                                                      └────────────────┘
```

## Deployment

The application is designed to be run in a Docker container. A sample Dockerfile is provided:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY app.py .

RUN pip install --no-cache-dir orjson requests tenacity pybreaker prometheus-client influxdb-client

EXPOSE 5000

CMD ["python", "app.py"]
```

### Docker Compose Example

```yaml
version: '3'
services:
  proxytrace:
    build: ./proxytrace
    ports:
      - "5000:5000"
      - "8000:8000"
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318/v1/traces
      - WORKER_COUNT=8
      - BATCH_SIZE=200
      - DEBUG_MODE=false
      - INFLUX_URL=http://victoriametrics:8428
      - INFLUX_BUCKET=traces
    restart: unless-stopped
```

## Development

### Requirements

- Python 3.11+
- orjson
- requests
- tenacity
- pybreaker
- prometheus-client
- influxdb-client

### Running Locally

```bash
python app.py
```

## Span Transformation

The application transforms incoming uberAgent records into OpenTelemetry spans:

1. Session GUIDs are converted to trace IDs (prefixed with `1` for logon events, `2` for logoff events)
2. Process IDs are used as span IDs
3. Parent process IDs become parent span IDs
4. Process metrics are mapped to span attributes
5. Timing information is preserved and converted to nanosecond precision

## License

[Add license information here]