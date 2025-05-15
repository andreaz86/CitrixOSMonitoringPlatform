# Infinity Proxy

The Infinity Proxy is a specialized proxy service designed to facilitate communication between Grafana's Infinity Datasource and the Citrix Cloud API. It provides seamless request forwarding, header modification, and observability features for monitoring API interactions.

## Features

- **HTTP/2 Support**: Full HTTP/2 protocol support for improved performance
- **Transparent Proxying**: Forwards requests to Citrix Cloud API while maintaining headers and authentication
- **OpenTelemetry Integration**: Built-in distributed tracing support with Jaeger
- **Debug Mode**: Detailed logging for troubleshooting
- **Proxy Support**: Configurable HTTP/HTTPS proxy settings
- **Flexible Request Handling**: Supports all HTTP methods (GET, POST, PUT, DELETE, etc.)
- **Error Handling**: Robust error handling with detailed logging

## Configuration

The service can be configured using environment variables:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `DEFAULT_TARGET_HOST` | https://api.cloud.com | Default target host for requests |
| `TARGET_HOST` | api.cloud.com | Host header value for requests |
| `DEBUG` | false | Enable debug logging |
| `HTTP_PROXY` | | HTTP proxy URL (optional) |
| `HTTPS_PROXY` | | HTTPS proxy URL (optional) |
| `JAEGER_ENABLED` | false | Enable OpenTelemetry tracing |
| `JAEGER_HOST` | jaeger | Jaeger host for tracing |
| `JAEGER_PORT` | 4317 | Jaeger port for tracing |

## Deployment

The service is designed to run in a Docker container. Here's an example configuration from docker-compose.yaml:

```yaml
infinity_proxy:
  build: ./infinity_proxy
  image: registry.azcloud.ovh/infinity_proxy:latest
  container_name: infinity_proxy
  hostname: citrixapi
  environment:
    - DEFAULT_TARGET_HOST=https://api.cloud.com
    - TARGET_HOST=api.cloud.com
    - HTTP_PROXY=${HTTP_PROXY}
    - DEBUG=false
    - JAEGER_ENABLED=true
    - JAEGER_HOST=jaeger
    - JAEGER_PORT=4317
  depends_on:
    - jaeger
  restart: unless-stopped
  networks:
    - ctxmon
```

## Development

### Requirements

The service requires Python 3.9+ and the following dependencies:
```text
fastapi==0.103.1
uvicorn==0.23.2
httpx[http2]==0.24.1
python-dotenv==1.0.0
pydantic==2.3.0
opentelemetry-api==1.21.0
opentelemetry-sdk==1.21.0
opentelemetry-exporter-otlp==1.21.0
opentelemetry-instrumentation-fastapi==0.42b0
opentelemetry-instrumentation-httpx==0.42b0
```

### Running Locally

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the service:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 80
```

## Architecture

The proxy works by:

1. Receiving incoming HTTP requests
2. Modifying request headers and authentication if needed
3. Forwarding requests to the Citrix Cloud API
4. Processing responses and returning them to the client
5. Optionally generating tracing data for observability

### Request Flow

```
┌─────────┐      ┌────────────────┐      ┌──────────────┐
│ Grafana │─────▶│ Infinity Proxy │─────▶│ Citrix Cloud │
└─────────┘      └────────────────┘      └──────────────┘
                         │
                         ▼
                   ┌──────────┐
                   │  Jaeger  │
                   └──────────┘
```

## Error Handling

The proxy implements several error handling mechanisms:

- Circuit breaking for failing endpoints
- Automatic retry with exponential backoff
- Detailed error logging in debug mode
- Error propagation with proper HTTP status codes

## Monitoring

When tracing is enabled, the following metrics are available in Jaeger:
- Request duration
- Response status codes
- Error rates
- Request/response sizes

## Security

The proxy supports:
- TLS/SSL with SNI
- Proxy authentication
- Header sanitization
- Secure error handling that prevents information leakage
