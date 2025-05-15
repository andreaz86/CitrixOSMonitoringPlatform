# Citrix Monitoring Platform

A comprehensive Docker-based monitoring and configuration management system for Citrix environments, providing metrics collection, data storage, and visualization capabilities.

## Table of Contents
- [Project Goals](#project-goals)
- [Component Documentation](#component-documentation)
- [Disclaimer](#disclaimer)
- [System Requirements](#system-requirements)
  - [Host Machine Requirements](#host-machine-requirements)
  - [Software Prerequisites](#software-prerequisites)
  - [Client Components Requirements](#client-components-requirements)
- [System Architecture](#system-architecture)
- [Core Components](#core-components)
  - [Citrix Metrics Collector](#citrix-metrics-collector)
  - [Sidecar](#sidecar)
  - [Telegraf Builder](#telegraf-builder)
  - [Observability Stack](#observability-stack)
  - [Monitoring & Alerting](#monitoring--alerting)
- [Data Flows](#data-flows)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
  - [Main Environment Variables](#main-environment-variables)
  - [Port Configuration](#port-configuration)
  - [Template Directories](#template-directories)
  - [Key Environment Variables](#key-environment-variables)
- [Data Ingestion Paths](#data-ingestion-paths)
  - [Data Ingestion Architecture](#data-ingestion-architecture)
  - [Telegraf Installation on Windows](#telegraf-installation-on-windows)
  - [Distributed Tracing with Jaeger](#distributed-tracing-with-jaeger)
- [Component Roles](#component-roles)
  - [NGINX](#nginx)
  - [Fluent Bit](#fluent-bit)
- [Installation and Startup](#installation-and-startup)
- [System Monitoring](#system-monitoring)
  - [Grafana](#grafana)
  - [Jaeger UI](#jaeger-ui)
- [Data Structure](#data-structure)
  - [VictoriaMetrics](#victoriametrics)
  - [VictoriaLogs](#victorialogs)
  - [PostgreSQL](#postgresql)
- [Development and Maintenance](#development-and-maintenance)
  - [Adding New Metrics](#adding-new-metrics)
  - [Customizing Templates](#customizing-templates)
  - [Adding New Dashboards](#adding-new-dashboards)
- [Troubleshooting](#troubleshooting)
  - [Component Health Check](#component-health-check)
  - [Common Issues](#common-issues)
  - [Log Analysis](#log-analysis)
  - [System Recovery](#system-recovery)

## Project Goals

The main objectives of this project are:

1. **Standalone uberAgent Deployment**
   - Enable uberAgent usage without requiring Splunk infrastructure
   - Reduce total cost of ownership by eliminating Splunk licensing costs
   - Minimize computational resources by using efficient time-series databases
   - Provide a lightweight yet powerful monitoring solution

2. **Resource Optimization**
   - Single VM deployment for the entire monitoring stack
   - Efficient data processing through containerized microservices
   - Optimized storage usage with VictoriaMetrics and VictoriaLogs
   - Minimal memory footprint through careful container configuration

## Component Documentation

Each container in the platform has its own detailed documentation in its respective directory:

- [NGINX Configuration](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/nginx/README.md) - Ingress point for uberAgent metrics
- [Fluent Bit Metrics](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/fluentbit_metrics/README.md) - Metrics processing and transformation
- [Fluent Bit Logs](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/fluentbit_logs/README.md) - Log processing and forwarding
- [Traefik](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/traefik/README.md) - Reverse proxy and SSL termination
- [Telegraf](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/telegraf/README.md) - System and container monitoring
- [Citrix Metrics](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/citrix_metrics/README.md) - Citrix Cloud API integration
- [ProxyTrace](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/proxytrace/README.md) - Session tracing and Jaeger integration
- [Sidecar](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/sidecar/README.md) - Configuration and certificate management
- [Infinity Proxy](https://github.com/andreaz86/CitrixOSMonitoringPlatform/tree/main/infinity_proxy/README.md) - Citrix API proxy for Grafana

Each component's documentation includes:
- Detailed configuration guide
- Environment variables explanation

## Disclaimer

This project is not officially supported by Citrix Systems, Inc. It is a community-driven monitoring solution that integrates with Citrix products. While we strive to maintain compatibility with Citrix services, this is not an official Citrix product, and Citrix does not provide support for this solution.

Pull requests and contributions are welcome and will be handled on a best-effort basis by the community maintainers. While we appreciate community involvement, response times and implementation timelines cannot be guaranteed.

## System Requirements

### Host Machine Requirements
- Operating System: Debian Linux (tested on Debian 12)
- CPU: Minimum 4 cores
- RAM: Minimum 8GB (16GB recommended)
- Storage: it depends by VDA numbers and retention

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

- **Citrix Metrics Collector**: Collects metrics and configuration data from Citrix Cloud API (Catalogs, DeliveryGroups, Machines, SessionFailures)
- **Sidecar**: Manages configuration templates for uberAgent and Telegraf
- **Telegraf Builder**: Builds a custom Windows version of Telegraf based on the configurations templates
- **VictoriaMetrics/VictoriaLogs**: Databases for storing metrics and logs
- **PostgreSQL**: Database for storing configuration data for grafana and Citrix Metric Collector
- **Grafana**: Visualization of metrics and dashboards
- **Fluent Bit**: Processing and forwarding logs and metrics
- **Traefik**: Reverse proxy for accessing grafana and repo
- **NGINX**: Serves configuration files and acts as reverse proxy
- **ProxyTrace**: Proxy for processing trace data from logon metrics
- **Jaeger**: Distributed tracing system for monitoring and troubleshooting
- **VmAgent**: Agent for collecting Prometheus metrics from internal components
- **VmAlert**: Alerting system integrated with VictoriaMetrics
- **Alertmanager**: Handles alerts from VmAlert
- **InfinityProxy**: act as middleware to use infinity datasource in grafana and manipulate auth header required to query Citrix API

## Core Components

### Citrix Metrics Collector

Containerized Python application that collects metrics and configuration data from the Citrix Cloud API.

#### Features
- Collects metrics from Citrix Cloud API and stores them in VictoriaMetrics
- Collects configuration data and stores it in PostgreSQL
- Collect ConfigLogs and store to Victorialogs
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
- Retrieval of Citrix Site ID (used by Infinity Plugin)

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

1. **uberAgent Data Flow**:
   - uberAgent on VDAs collects application metrics and user session data
   - Data is sent to Nginx that cut /uberagent/ from the FluentBit using an Elasticsearch-compatible format
   - FluentBit transforms logs into metrics and forwards them to UberAgent VictoriaMetrics instance
   - Session logon/logoff metrics are also sent to ProxyTrace
   - ProxyTrace transforms these events into trace data for Jaeger
   - Grafana visualizes metrics from VictoriaMetrics
   - Jaeger provides visualization of session traces

2. **Internal Monitoring Flow**:
   - Telegraf collects host and container metrics via Docker API
   - Metrics are stored in the Internal Monitoring VictoriaMetrics instance
   - VmAgent collects additional Prometheus metrics
   - Grafana dashboards display system health and performance

2. **Log Processing**:
   - telegraf collect Windows EventLog and fordward to Fluent Bit Log instance
   - Fluent Bit collects and processes logs
   - Logs are stored in VictoriaLogs
   - Grafana visualizes logs through dashboards


## Prerequisites

- Docker and Docker Compose
- Citrix Cloud API credentials:
  - **Client ID & Secret**: Generated from [Citrix Cloud Portal](https://developer-docs.citrix.com/en-us/citrix-cloud/citrix-cloud-api-overview/get-started-with-citrix-cloud-apis.html)
  - **Customer ID**: Found in [Citrix Cloud Settings](https://support.citrix.com/s/article/CTX586350-how-to-identify-your-citrix-cloud-id?language=en_US)
  - Tested and verified with Citrix Cloud DaaS (formerly Virtual Apps and Desktops Service)
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

2. **`TELEGRAF_PORT`** (Default: 5170)
   - Controls the port for Telegraf event log ingestion
   - Used by Fluent Bit Logs to receive Windows Event Logs
   - Must be configured in:
     - `.env` file

To modify these ports:

1. Update `.env` file:
```ini
UA_INGRESSPORT=8088    # Custom port for uberAgent
TELEGRAF_PORT=5170     # Custom port for Telegraf
```

2. Update client configurations:
   - Modify uberAgent output settings
   - Update Telegraf output configuration
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
uberAgent sends metrics to NGINX using the Elasticsearch Bulk API format:
- **Initial Ingestion**
  - Endpoint: `https://your-domain.com/uberagent/_bulk`
  - Port: Configurable via `UA_INGRESSPORT` (default: 8088)
  - Format: Elasticsearch Bulk API compatible JSON

- **NGINX Processing**
  - Strip /uberagent
  - Forwards to Fluent Bit Metrics (Fluent Bit can't create a custom endpoint)

- **Fluent Bit Metrics Processing**
  - Receives data on port 8088
  - Processes data using Lua transformation scripts
  - Routes specific events to different outputs:
    1. All metrics → VictoriaMetrics
    2. Logon/Logoff events → ProxyTrace (Jaeger)


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

#### 3. Telegraf Installation on Windows

Telegraf can be installed on Windows machines to collect Windows Event Logs and forward them to the monitoring platform:

1. **Download Telegraf Configuration**
   - Access the telegraf configuration at `https://<your-server>/repo/telegraf/telegraf.zip`
   - These configurations are automatically generated by the Sidecar service

2. **Install Telegraf as a Windows Service**
   ```powershell
   # Create installation directory
   New-Item -ItemType Directory -Path "C:\Program Files\Telegraf" -Force

   # Download Telegraf binary from repo
   Invoke-WebRequest -Uri "https://<your-server>/repo/telegraf/telegraf.exe" -OutFile "C:\Program Files\Telegraf\telegraf.exe"
   # Download and extract Telegraf package
   Invoke-WebRequest -Uri "https://<your-server>/repo/telegraf/telegraf.zip" -OutFile "C:\telegraf.zip"
   Expand-Archive -Path "C:\telegraf.zip" -DestinationPath "C:\Program Files\Telegraf" -Force
   Remove-Item -Path "C:\telegraf.zip" -Force
   
   # Create directory for additional configurations
   New-Item -ItemType Directory -Path "C:\Program Files\Telegraf\logs" -Force
   
   # Install as a Windows service
   & 'C:\Program Files\Telegraf\telegraf.exe' --service install --config "C:\Program Files\Telegraf\telegraf.conf" --config-directory "C:\Program Files\Telegraf\telegraf.d"
   
   # Start the service
   Start-Service telegraf
   ```

3. **Verify Installation**
   - Check service status:
     ```powershell
     Get-Service telegraf
     ```
   - View Telegraf logs:
     ```powershell
     Get-Content "C:\Program Files\Telegraf\logs\telegraf.log" -Tail 20
     ```
   - Verify data is being sent to the monitoring platform by checking VictoriaLogs 
     through Grafana's "Windows Event Logs" dashboard

4. **Uninstall Service (if needed)**
   ```powershell
   # Stop service
   Stop-Service telegraf
   
   # Remove service
   & 'C:\Program Files\Telegraf\telegraf.exe' --service uninstall
   
   # Optionally remove installation directory
   Remove-Item -Path "C:\Program Files\Telegraf" -Recurse -Force
   ```

The telegraf.conf file contains all necessary connection information including:
- Connection endpoint (using the SERVERNAMEORIP variable from .env)
- Authentication details
- Event log sources configuration
- Data retention settings

All these settings are automatically configured by the Sidecar service, which generates customized configurations for each environment.

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

1. Clone the repository:
```bash
git clone https://github.com/andreaz86/CitrixOSMonitoringPlatform.git
cd CitrixOSMonitoringPlatform
```

2. Run the initialization script:
```bash
chmod +x init_env.sh
./init_env.sh
```

The `init_env.sh` script is an interactive setup tool that:

a. Guides you through setting up essential environment variables:
  - **Citrix Cloud Credentials**:
    - `CTX_CLIENT_ID`: Your Citrix Cloud API client ID
    - `CTX_CLIENT_SECRET`: Your Citrix Cloud API client secret
    - `CTX_CUSTOMER_ID`: Your Citrix Cloud customer ID

  - **Grafana Configuration**:
    - `GF_SECURITY_ADMIN_USER`: Admin username for Grafana interface
    - `GF_SECURITY_ADMIN_PASSWORD`: Admin password for Grafana login
    - `GF_SERVER_DOMAIN`: Domain name for Grafana (e.g., grafana.example.com)
    - `GF_DATABASE_PASSWORD`: Internal database password for Grafana (can be auto-generated)

  - **System Configuration**:
    - `SERVERNAMEORIP`: Server hostname or IP (used for uberAgent and Telegraf configs)
    - `POSTGRES_PASSWORD`: PostgreSQL admin password (used for pgAdmin access)
    - `DB_SVCCITRIX_PWD`: Service account password for Citrix metrics database

For passwords, the script offers to generate secure random values automatically or lets you input custom values.

c. Additional Setup Tasks:
  - Generates initial SSL certificates if not present
  - Creates `.env` file from template if not exists
  - Validates environment variables

3. Start the services:
```bash
sudo docker compose up -d
```

Note: the Root Path will be created if not exists

## System Monitoring

### Grafana

Access Grafana to view dashboards and metrics:
- URL: `https://<GF_SERVER_DOMAIN>`
- Default credentials: configured in `.env`


### Jaeger UI

Access the Jaeger UI to analyze distributed traces:
- URL: `http://<your-server>:16686`


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
     docker logs nginx 
     
     ```
   
   - **Telegraf**
     ```bash
     # Check Fluent Bit input
     docker logs fluentbit_logs | grep "input"
     
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
docker compose logs -f

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
   docker compose down
   
   # Clean volumes (if needed)
   docker compose down -v
   
   # Rebuild and restart
   docker compose up -d
   ```

3. **Restore Data**
   ```bash
   # Restore PostgreSQL
   cat backup.sql | docker exec -i postgresql psql -U svc_citrix_metrics citrix_metrics
   ```

