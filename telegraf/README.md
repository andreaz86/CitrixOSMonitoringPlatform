# Telegraf Configuration

This Telegraf instance is responsible for internal system monitoring, collecting metrics from the Docker host and containers, and sending them to the internal VictoriaMetrics instance.

## Overview

Telegraf is configured to monitor:
- Docker container metrics
- Host system metrics (CPU, memory, disk, network)
- Docker daemon metrics
- System processes

All collected metrics are sent to the `victoriametrics_internal` instance, which is separate from the main VictoriaMetrics instance used for uberAgent data.

## Docker Integration

### Docker Socket Access

Telegraf needs access to the Docker socket (`/var/run/docker.sock`) to collect container metrics. This is configured in `docker-compose.yaml`:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

### Docker Group Mapping

The init script automatically handles the Docker group mapping to ensure Telegraf has the correct permissions to access the Docker socket. This is done by:

1. Getting the Docker group ID from the host system
2. Setting the Telegraf container's group ID to match the host's Docker group
3. Ensuring proper permissions for the Docker socket access

This mapping is managed through the environment variable `TELEGRAF_DOCKER_GID` in the docker-compose file:

```yaml
user: telegraf:${TELEGRAF_DOCKER_GID}
```

## Host System Monitoring

To monitor the host system, Telegraf mounts several host directories in read-only mode:

```yaml
volumes:
  - /:/hostfs:ro
  - /etc/localtime:/etc/localtime:ro
```

Environment variables are set to tell Telegraf where to find the host system files:

```yaml
environment:
  - HOST_ETC=/hostfs/etc
  - HOST_PROC=/hostfs/proc
  - HOST_SYS=/hostfs/sys
  - HOST_VAR=/hostfs/var
  - HOST_RUN=/hostfs/run
  - HOST_MOUNT_PREFIX=/hostfs
```

## Metrics Collection

### Docker Metrics
- Container CPU usage
- Container memory usage
- Container network I/O
- Container block I/O
- Container status and health checks

### Host System Metrics
- CPU usage and load
- Memory usage and swap
- Disk usage and I/O
- Network interface statistics
- System load average
- Process statistics

## Data Flow

1. Telegraf collects metrics from:
   - Docker daemon via Docker socket
   - Host system via mounted directories
   - Internal processes and services

2. Metrics are processed and aggregated by Telegraf

3. Data is sent to `victoriametrics_internal:8428` for storage

4. Metrics can be visualized in Grafana using the internal monitoring dashboards

## Security Considerations

- The container runs with minimal privileges (non-root)
- Host filesystem is mounted read-only
- No external ports are exposed by default

## Configuration

The main configuration file is located at `telegraf/telegraf.conf`. Key settings include:

- Input plugins for Docker and system metrics
- Output configuration for VictoriaMetrics
- Collection intervals
- Metric filtering and processing

## Troubleshooting

Common issues and solutions:

1. Docker Socket Permission Issues:
   ```bash
   # Check Docker group ID on host
   getent group docker

   # Verify Telegraf process group ID
   docker exec telegraf id
   ```

2. Missing Metrics:
   ```bash
   # Check Telegraf logs
   docker logs telegraf


3. High Resource Usage:
   - Review collection intervals in `telegraf.conf`
   - Check number of monitored containers
   - Verify metric filtering rules
