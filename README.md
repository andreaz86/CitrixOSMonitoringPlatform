# Citrix Monitoring Platform

A comprehensive Docker-based monitoring and configuration management system for Citrix environments, providing metrics collection, data storage, and visualization capabilities.

## Disclaimer

This project is not officially supported by Citrix Systems, Inc. It is a community-driven monitoring solution that integrates with Citrix products. While we strive to maintain compatibility with Citrix services, this is not an official Citrix product, and Citrix does not provide support for this solution.

Pull requests and contributions are welcome and will be handled on a best-effort basis by the community maintainers. While we appreciate community involvement, response times and implementation timelines cannot be guaranteed.

For production environments, always ensure you have proper support agreements in place with Citrix for their official products and services.

## System Requirements

### Host Machine Requirements
- Operating System: Debian Linux (tested on Debian 11/12)
- CPU: Minimum 4 cores
- RAM: Minimum 8GB (16GB recommended)
- Storage: At least 100GB available space (SSD recommended)
- Network: Reliable network connection with access to Citrix Cloud APIs

### Software Prerequisites

1. **Docker Installation**
```bash
# Update package index
sudo apt-get update

# Install prerequisites
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker
```

2. **Proxy Configuration (if required)**
   - Configure Docker proxy settings:
   ```bash
   sudo mkdir -p /etc/systemd/system/docker.service.d
   sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf << EOF
   [Service]
   Environment="HTTP_PROXY=http://proxy.example.com:8080"
   Environment="HTTPS_PROXY=http://proxy.example.com:8080"
   Environment="NO_PROXY=localhost,127.0.0.1"
   EOF
   
   # Reload Docker
   sudo systemctl daemon-reload
   sudo systemctl restart docker
   ```

### Client Components Requirements
- uberAgent version: 7.3.1 (tested and verified)
- Client OS: Windows Server 2016/2019/2022, Windows 10/11

## System Architecture

The system consists of multiple Docker containers working together:

- **Citrix Metrics Collector**: Collects metrics and configuration data from Citrix Cloud API
- **Sidecar**: Manages configuration templates for uberAgent and Telegraf
- **Telegraf Builder**: Builds a custom Windows version of Telegraf based on the configurations
- **VictoriaMetrics/VictoriaLogs**: Databases for storing metrics and logs
- **PostgreSQL**: Database for storing configuration data
- **Grafana**: Visualization of metrics and dashboards
- **Fluent Bit**: Processing and forwarding logs and metrics
- **Traefik**: Reverse proxy and load balancer
- **NGINX**: Serves configuration files and acts as a web server
- **ProxyTrace**: Proxy for processing trace data
- **Jaeger**: Distributed tracing system for monitoring and troubleshooting
- **VmAgent**: Agent for collecting Prometheus metrics
- **VmAlert**: Alerting system integrated with VictoriaMetrics
- **Alertmanager**: Handles alerts from VmAlert

## Core Components

### Citrix Metrics Collector

Containerized Python application that collects metrics and configuration data from the Citrix Cloud API.

#### Features
- Collects metrics from Citrix Cloud API and stores them in VictoriaMetrics
- Collects configuration data and stores it in PostgreSQL
- Implements smart bearer token management with auto-refresh capabilities
- Implements retry mechanism for API failures with exponential backoff
- Supports API pagination to handle large datasets
- Provides health check endpoint to monitor application status

### Sidecar

Service that manages templates and configurations for client components such as uberAgent and Telegraf.

#### Features
- Certificate management (generation, validation)
- uberAgent template processing with environment variable substitution
- Telegraf template processing with environment variable substitution
- Creation of configuration packages for distribution to clients
- Retrieval of Citrix Site ID

### Telegraf Builder

Service that builds a custom version of Telegraf for Windows platforms.

#### Features
- Clones Telegraf source code
- Performs cross-platform compilation for Windows
- Customizes based on configuration templates
- Generates ready-to-deploy executables

### Observability Stack

- **VictoriaMetrics**: Two instances of time-series database for metrics storage:
  - **UberAgent Metrics**: Dedicated instance for storing metrics from uberAgent
  - **Internal Monitoring**: Instance for storing system and container metrics
- **VictoriaLogs**: High-performance log storage solution
- **Jaeger**: Distributed tracing system for monitoring and troubleshooting
- **Grafana**: Visualization platform for metrics and dashboards

### Monitoring & Alerting

- **VmAgent**: Collects Prometheus metrics from various targets
- **VmAlert**: Evaluates alerting rules and sends alerts to Alertmanager
- **Alertmanager**: Handles alert deduplication, grouping, and routing

## Data Flows

### 1. Citrix Cloud Integration
   - **API Collection**
     - Citrix Metrics Collector queries the Citrix Cloud API
     - Uses OAuth2 authentication with automatic token refresh
     - Implements rate limiting and backoff strategies
   
   - **Data Storage**
     - Time-series metrics → VictoriaMetrics
     - Configuration data → PostgreSQL
     - Logs and events → VictoriaLogs
   
   - **Visualization**
     - Real-time metrics in Grafana dashboards
     - Configuration data in custom views
     - Log analysis through Grafana Explore

### 2. Client Agent Management
   - **Template Processing**
     - Sidecar service monitors for configuration changes
     - Templates processed with environment variable substitution
     - Automatic validation of configuration syntax
   
   - **Distribution**
     - Configurations packaged into deployable archives
     - NGINX serves files via HTTPS with client authentication
     - Automatic version control and rollback capability
   
   - **Data Collection**
     - Telegraf collects system and application metrics
     - uberAgent gathers user session and application data
     - Metrics sent back through secure channels
   
   - **Health Monitoring**
     - Agent connectivity monitoring
     - Configuration version tracking
     - Automatic agent update notifications

3. **uberAgent Data Flow**:
   - uberAgent on VDAs collects application metrics and user session data
   - Data is sent to FluentBit using an Elasticsearch-compatible format
   - FluentBit transforms logs into metrics and forwards them to UberAgent VictoriaMetrics instance
   - Session logon/logoff metrics are also sent to ProxyTrace
   - ProxyTrace transforms these events into trace data for Jaeger
   - Grafana visualizes metrics from VictoriaMetrics
   - Jaeger provides visualization of session traces

4. **Internal Monitoring Flow**:
   - Telegraf collects host and container metrics via Docker API
   - Metrics are stored in the Internal Monitoring VictoriaMetrics instance
   - VmAgent collects additional Prometheus metrics
   - Grafana dashboards display system health and performance

5. **Log Processing**:
   - Fluent Bit collects and processes logs
   - Logs are stored in VictoriaLogs
   - Grafana visualizes logs through dashboards

6. **Tracing**:
   - ProxyTrace collects and transforms tracing data
   - Traces are sent to Jaeger
   - Jaeger provides visualization and analysis of distributed traces

## Flow Diagram

The system architecture follows these primary data paths:

```
+-----------------------------------------------------------------------+
|                              Citrix Cloud                             |
+-----------------------------------------------------------------------+
                                   ▲
                                   │
                                   │
                      [flusso  ?  verso Citrix Cloud]
                                   │
+-----------------------------------------------------------------------+
|                                                                       |
|   +-------------+     +-----------+     +------------------+          |
|   |     VDA     |     |   NGINX   |     |   FluentBit      |          |
|   |             |     |  /bulk    |     |    Metrics       |          |
|   |  uberAgent  |--1->| endpoint  |--1-> |   (→Grafana)     |          |
|   +-------------+     +-----------+     +------------------+          |
|        Telegraf           │   ▲                   │                   |
|           │ (2)           │   │(1)                │(2)                |
|           ▼               │   │                   ▼                   |
|   +---------------+       │   │          +------------------+         |
|   | FluentBit     |       │   └--------->| VictoriaMetrics  |         |
|   |    Logs       |--1------------------>|   uberAgent      |         |
|   +---------------+       │              +------------------+         |
|                           │                      ▲                    |
|                           │                      │(2)                 |
|                           │                   +--------+              |
|                           │                   | vmagent|              |
|                           │            (2)-->+--------+              |
|                           │                                             |
|   +------------+     +----------+     +------------------+   +------+ |
|   |   Traefik  |<--443--| Grafana |<--1-|   VictoriaLogs   |<--| Jaeger| |
|   +------------+     +----------+ 2   +------------------+   +------+ |
|        ▲    │(2) 1  │    │3   6│        │4    ▲                    │ |
|        │    +------+    +------┘        │     │                    │ |
|   Admin│                         4       |     │5                   │ |
|       443                                  |     │                   │ |
|                                               │     v                   │ |
|                                               | +---------+           │ |
|                                               | | Sidecar |           │ |
|                                               | +---------+           │ |
|                                               ▼                       │ |
|                                           +---------+                │ |
|                                           |ProxyTrace| (trace in/out)│ |
|                                           +---------+                │ |
|                                                                       |
+-----------------------------------------------------------------------+
|              Host & Containers Monitoring (MoM) – Telegraf            |
|  +-------------+     +----------------+     +----------------------+  |
|  | Docker API  |<--1-|   Telegraf     |--2->|   Host MountPoint   |  |
|  +-------------+     +----------------+     +----------------------+  |
+-----------------------------------------------------------------------+
```

1. **VDA Metrics Collection**:
   - uberAgent on VDAs collects metrics (path 1)
   - Data flows to FluentBit Metrics which formats and forwards metrics to VictoriaMetrics uberAgent instance (path 2)
   - uberAgent session logs flow to FluentBit Logs (path 2)
   - FluentBit forwards logs to VictoriaLogs (path 1)

2. **Visualization and Monitoring**:
   - Grafana reads from multiple data sources (paths 1, 2, 3, 4)
   - VictoriaLogs provides log data to Grafana (path 1)
   - VictoriaMetrics uberAgent provides metrics to Grafana (path 2)
   - VictoriaMetrics Internal Monitor provides system metrics to Grafana (path 4)

3. **Trace Processing**:
   - ProxyTrace receives session events from FluentBit (path 1)
   - ProxyTrace formats trace data for Jaeger (path 3)
   - Jaeger stores and visualizes traces (path 5)

4. **Internal Monitoring**:
   - Telegraf collects host and container metrics via Docker API (path 1)
   - VmAgent scrapes prometheus endpoints and sends to VictoriaMetrics Internal Monitor (path 2)
   - System metrics are stored in VictoriaMetrics Internal Monitor (paths 4, 5)

5. **Configuration and API**:
   - NGINX serves configuration files generated by the Sidecar (path 1)
   - Traefik provides external access to the admin UI (path 443)
   - Telegraf captures Docker container metrics through the Docker API

6. **Cloud Integration**:
   - Components connect to Citrix Cloud for metrics collection and API access
   - ProxyTrace sends data to Citrix Cloud for extended analytics

## Prerequisites

- Docker and Docker Compose
- Citrix Cloud API credentials (Client ID, Client Secret, Customer ID)
- (Optional) Proxy configuration if the environment is behind a corporate proxy

## Configuration

### Main Environment Variables

The system uses numerous environment variables for configuration, defined in an `.env` file:

- `CTX_CLIENT_ID`: Client ID for the Citrix Cloud API
- `CTX_CLIENT_SECRET`: Client Secret for the Citrix Cloud API
- `CTX_CUSTOMER_ID`: Customer ID for the Citrix Cloud API
- `POSTGRES_PASSWORD`: Password for the PostgreSQL database
- `GF_SECURITY_ADMIN_USER`: Admin username for Grafana
- `GF_SECURITY_ADMIN_PASSWORD`: Admin password for Grafana
- `GF_SERVER_DOMAIN`: Domain name for the Grafana server
- `HTTP_PROXY`: Proxy configuration (if needed)
- `FLUENTBIT_VERSION`: Version of Fluent Bit to use
- `VICTORIAMETRICS_V`: VictoriaMetrics version
- `VICTORIALOGS_V`: VictoriaLogs version
- `UA_DATARETENTION`: Data retention period for uberAgent metrics
- `IM_DATARETENTION`: Data retention period for internal metrics
- `VL_DATARETENTION`: Data retention period for VictoriaLogs
- `TRAEFIK_VERSION`: Traefik version

### Port Configuration

The system allows customization of data ingestion ports through environment variables:

1. **`UA_INGRESSPORT`** (Default: 8088)
   - Controls the port for uberAgent data ingestion
   - Used by NGINX to receive uberAgent metrics and logs
   - Must be configured in:
     - `.env` file
     - NGINX configuration
     - uberAgent output settings

2. **`TELEGRAF_PORT`** (Default: 5170)
   - Controls the port for Telegraf event log ingestion
   - Used by Fluent Bit Logs to receive Windows Event Logs
   - Must be configured in:
     - `.env` file
     - Telegraf output configuration
     - Fluent Bit Logs input settings

To modify these ports:

1. Update `.env` file:
```ini
UA_INGRESSPORT=8088    # Custom port for uberAgent
TELEGRAF_PORT=5170     # Custom port for Telegraf
```

2. Verify NGINX configuration:
```nginx
# in nginx.conf
server {
    listen ${UA_INGRESSPORT} ssl;
    # ...configuration continues...
}
```

3. Update client configurations:
   - Modify uberAgent output settings
   - Update Telegraf HTTP output configuration
   - Restart affected services

Note: After changing ports, ensure:
- Firewall rules are updated
- Load balancers are reconfigured
- Client configurations are updated
- Services are restarted to apply changes

### Template Directories

- `templates/telegraf/`: Configuration templates for Telegraf
  - `telegraf.conf`: Main configuration
  - `telegraf.d/`: Modularized additional configurations
- `templates/uberAgent/`: Configuration templates for uberAgent
  - `VDA/`: Configurations for Virtual Delivery Agent

## Initialization and Setup

### Initial Configuration

1. **Environment Setup**
   ```bash
   # Copy example environment file
   cp env.example .env
   
   # Edit environment variables
   nano .env
   ```

2. **Run Initialization Script**
   ```bash
   # Make script executable
   chmod +x init_env.sh
   
   # Run initialization
   ./init_env.sh
   ```

   The initialization script performs the following tasks:
   - Creates necessary directories
   - Generates SSL certificates
   - Sets up database schemas
   - Configures initial permissions
   - Validates environment variables

### Key Environment Variables

Required environment variables in `.env`:

```ini
# Citrix Cloud Credentials
CTX_CLIENT_ID=your-client-id
CTX_CLIENT_SECRET=your-client-secret
CTX_CUSTOMER_ID=your-customer-id

# System Configuration
DOMAIN_NAME=your-domain.com
ROOT_PATH=/path/to/data
DOCKER_HOSTNAME=hostname

# Database Credentials
DB_SVCCITRIX_PWD=password
POSTGRES_PASSWORD=password

# Grafana Configuration
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=password
GF_SERVER_DOMAIN=grafana.your-domain.com

# Component Versions
FLUENTBIT_VERSION=2.1.8
VICTORIAMETRICS_V=v1.91.3
VICTORIALOGS_V=v0.4.2
TRAEFIK_VERSION=2.10

# Data Retention
UA_DATARETENTION=90d
IM_DATARETENTION=30d
VL_DATARETENTION=30d

# Proxy Configuration (if needed)
HTTP_PROXY=http://proxy.example.com:8080
HTTPS_PROXY=http://proxy.example.com:8080
NO_PROXY=localhost,127.0.0.1
```

## Data Ingestion Paths

### Data Ingestion Architecture

#### 1. uberAgent Data Flow
uberAgent sends metrics and logs to NGINX using the Elasticsearch Bulk API format:
- **Initial Ingestion**
  - Endpoint: `https://your-domain.com/_bulk`
  - Port: Configurable via `UA_INGRESSPORT` (default: 8088)
  - Authentication: Client certificate required
  - Format: Elasticsearch Bulk API compatible JSON

- **NGINX Processing**
  - Receives bulk data on `/_bulk` endpoint
  - Validates client certificates
  - Splits large payloads into manageable chunks
  - Forwards to Fluent Bit Metrics

- **Fluent Bit Metrics Processing**
  - Receives data on port 8088
  - Processes data using Lua transformation scripts
  - Routes specific events to different outputs:
    1. All metrics → VictoriaMetrics
    2. Logon/Logoff events → ProxyTrace (Jaeger)

Example uberAgent configuration:
```ini
[Output]
Type=HTTP
URL=https://your-domain.com/_bulk
Certificate=C:\Program Files\uberAgent\cert\client.crt
PrivateKey=C:\Program Files\uberAgent\cert\client.key
Format=JSON
Port=${UA_INGRESSPORT}
```

#### 2. Telegraf Windows Event Log Collection
Telegraf specifically handles Windows Event Logs:
- **Collection Configuration**
  - Input: Windows Event Log
  - Port: Configurable via `TELEGRAF_PORT` (default: 5170)
  - Direct connection to Fluent Bit Logs

- **Data Flow**
  - Telegraf → Fluent Bit Logs → VictoriaLogs
  - Format: Windows Event Log entries
  - Transport: HTTP to Fluent Bit Logs

Example Telegraf configuration:
```toml
[[inputs.eventlog]]
  ## Windows event log names to monitor.
  event_log = ["Application", "System", "Security"]

[[outputs.http]]
  url = "http://fluentbit_logs:${TELEGRAF_PORT}"
  data_format = "json"
  [outputs.http.headers]
    Content-Type = "application/json"
```

#### 3. Distributed Tracing with Jaeger
The system automatically generates distributed traces for user sessions:

- **Session Events Tracked**
  - Logon Process Events (`uberAgent:Process:LogonProcesses`)
  - Logoff Process Events (`uberAgent:Process:LogoffProcesses`)
  
- **Trace Generation**
  - ProxyTrace receives session events from Fluent Bit
  - Converts session events into OpenTelemetry traces
  - Creates spans for session lifecycle events
  - Forwards trace data to Jaeger

- **Trace Data Fields**
  - Session GUID as trace ID
  - User information
  - Process details
  - Timing information
  - Session state changes

## Component Roles

### NGINX
- Acts as the primary ingress point for metrics and logs
- Terminates SSL/TLS connections
- Performs client certificate validation
- Load balances incoming requests
- Provides request rate limiting
- Configuration location: `/nginx/nginx.conf`

### Fluent Bit
Three main instances:

1. **Fluent Bit Logs (`fluentbit_logs/`)**
   - Processes application and system logs
   - Transforms log data into structured format
   - Forwards logs to VictoriaLogs
   - Configuration: `fluentbit_logs/fluent-bit.conf`

2. **Fluent Bit Metrics (`fluentbit_metrics/`)**
   - Processes metrics from uberAgent
   - Transforms data into VictoriaMetrics format
   - Handles session tracking and trace generation
   - Configuration: `fluentbit_metrics/fluent-bit.conf`

3. **ProxyTrace Fluent Bit**
   - Processes session events
   - Generates distributed traces
   - Forwards trace data to Jaeger
   - Lua scripts for transformation: `fluentbit_metrics/scripts/`

Key Features:
- Buffer management for reliability
- Data transformation using Lua scripts
- Multiple output support
- Automatic retry mechanisms
- Built-in monitoring

## Installation and Startup

1. Clone the repository
2. Create an `.env` file with the necessary environment variables
3. Start the services with Docker Compose:

```bash
docker-compose up -d
```

## System Monitoring

### Grafana

Access Grafana to view dashboards and metrics:
- URL: `https://<GF_SERVER_DOMAIN>`
- Default credentials: configured in `.env`

### Traefik Dashboard

Access the Traefik dashboard to monitor the reverse proxy:
- URL: `http://<your-server>:8084`

### Jaeger UI

Access the Jaeger UI to analyze distributed traces:
- URL: `http://<your-server>:16686`

### Health Check

The Citrix Metrics Collector provides a health check endpoint:
- URL: `http://localhost:8000/health`
- Response: Application status, last successful metrics run, any errors

## Data Structure

### VictoriaMetrics
- Citrix session metrics
- Citrix machine metrics
- System metrics
- Container metrics
- Internal monitoring metrics

### VictoriaLogs
- Application logs
- Trace logs
- System logs

### PostgreSQL
- Citrix site configuration data
- Delivery group configuration data
- Machine configuration data
- Application configuration data
- Grafana configuration

## Development and Maintenance

### Adding New Metrics
1. Update the Citrix API client in `citrix_metrics/app/api/citrix_client.py`
2. Add new collection methods based on the new API endpoints
3. Update database schemas as needed

### Customizing Templates
1. Modify files in `templates/telegraf/` or `templates/uberAgent/`
2. Use environment variables with `${VARIABLE_NAME}` syntax for dynamic values
3. Restart the sidecar service to regenerate the configuration packages

### Adding New Dashboards
1. Create a new dashboard in Grafana
2. Export the dashboard to JSON
3. Add the JSON file to `grafana/provisioning/dashboards/`
4. Update `grafana/provisioning/dashboards/dashboard.yml` if needed

## Troubleshooting

### Component Health Check

1. **Container Status**
   ```bash
   # Check container status
   docker ps -a
   
   # View container logs
   docker logs <container_name>
   
   # Check container resources
   docker stats
   ```

2. **Service Endpoints**
   - Grafana: `https://<GF_SERVER_DOMAIN>`
   - NGINX metrics: `http://localhost/nginx_status`
   - Health API: `http://localhost:8000/health`
   - Traefik Dashboard: `http://localhost:8084`

### Common Issues

1. **Container Startup Problems**
   - Check disk space: `df -h`
   - Verify port availability: `netstat -tulpn`
   - Check Docker logs: `journalctl -u docker`
   - Ensure correct permissions: `ls -l /data/docker_compose`

2. **Data Ingestion Issues**
   - **uberAgent**
     ```bash
     # Check NGINX access logs
     docker logs nginx | grep POST
     
     # Verify SSL certificates
     openssl verify /path/to/client.crt
     ```
   
   - **Telegraf**
     ```bash
     # Check Fluent Bit input
     docker logs fluentbit_logs | grep "input"
     
     # Verify metrics format
     curl -v http://localhost:2020
     ```

3. **Database Issues**
   - **VictoriaMetrics**
     ```bash
     # Check metrics ingestion
     curl -s http://localhost:8428/api/v1/status/tsdb
     
     # Verify data presence
     curl -s 'http://localhost:8428/api/v1/export'
     ```
   
   - **PostgreSQL**
     ```bash
     # Connect to database
     docker exec -it postgresql psql -U svc_citrix_metrics -d citrix_metrics
     
     # Check table sizes
     SELECT pg_size_pretty(pg_database_size('citrix_metrics'));
     ```

4. **Performance Issues**
   - Check system resources:
     ```bash
     top
     iostat
     vmstat
     ```
   - Monitor container metrics in Grafana
   - Review VictoriaMetrics query performance
   - Check Fluent Bit buffer status

5. **Proxy and Network Issues**
   ```bash
   # Test Citrix Cloud connectivity
   curl -v --proxy $HTTP_PROXY https://api.cloud.com
   
   # Check DNS resolution
   nslookup api.cloud.com
   
   # Verify proxy settings
   env | grep -i proxy
   ```

### Log Analysis

Key log locations:
```
/data/docker_compose/
├── fluentbit_logs/logs/
├── fluentbit_metrics/logs/
├── nginx/logs/
└── proxytrace/logs/
```

Common log commands:
```bash
# Tail all container logs
docker-compose logs -f

# Check specific container logs
docker logs -f <container_name>

# Search for errors
docker logs <container_name> 2>&1 | grep -i error

# Get last 100 lines
docker logs --tail 100 <container_name>
```

### System Recovery

1. **Backup Important Data**
   ```bash
   # Backup PostgreSQL
   docker exec postgresql pg_dump -U svc_citrix_metrics citrix_metrics > backup.sql
   
   # Backup configurations
   tar -czf configs_backup.tar.gz templates/
   ```

2. **Reset System**
   ```bash
   # Stop all containers
   docker-compose down
   
   # Clean volumes (if needed)
   docker-compose down -v
   
   # Rebuild and restart
   docker-compose up -d --build
   ```

3. **Restore Data**
   ```bash
   # Restore PostgreSQL
   cat backup.sql | docker exec -i postgresql psql -U svc_citrix_metrics citrix_metrics
   ```

## License

This project is distributed under a proprietary license. All rights reserved.