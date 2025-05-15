# Sidecar Service

The Sidecar Service is an essential component of the architecture that manages the generation, validation, and distribution of configurations for uberAgent and Telegraf clients. It also handles SSL certificate management and interaction with the Citrix Cloud API.

## Key Features

- **Certificate Management**
  - Automatic self-signed certificate generation
  - Existing certificate validation
  - Automatic certificate renewal

- **Template Processing**
  - uberAgent template processing with environment variable substitution
  - Telegraf template processing with multi-configuration support
  - Generation of distributable configuration packages

- **Citrix Cloud Integration**
  - Automatic Site ID retrieval
  - Authentication token management
  - Proxy support for API calls

- **Advanced Logging**
  - Multi-level logging system
  - Debug mode for troubleshooting
  - Detailed operation logging

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CERT_FQDN` | | FQDN for SSL certificate |
| `VERBOSE` | 0 | Logging verbosity level (0-3) |
| `CTX_CLIENT_ID` | | Citrix Cloud Client ID |
| `CTX_CLIENT_SECRET` | | Citrix Cloud Client Secret |
| `CTX_CUSTOMER_ID` | | Citrix Cloud Customer ID |
| `HTTP_PROXY` | | HTTP proxy URL (optional) |
| `HTTPS_PROXY` | | HTTPS proxy URL (optional) |
| `SERVERNAMEORIP` | | Server name or IP for templates |
| `UA_INGRESSPORT` | | uberAgent ingress port |
| `TELEGRAF_PORT` | | Telegraf port |

### Directory Mapping

The sidecar service maps host directories to specific locations inside the container:

| Host Path | Container Path | Description |
|-----------|---------------|-------------|
| `./certs/` | `/etc/certs` | SSL certificates directory |
| `./templates/` | `/etc/templates` | Base templates directory |
| `./uaConfigs/` | `/etc/uaConfigs` | Configuration output directory |
| `./.env` | `/envs/env.list` | Environment variables file |

#### Template Directory Structure (Host)
```
./templates/
├── uberAgent/
│   ├── VDA/              # Virtual Desktop Agent configs
│   ├── Physical/         # Physical workstation configs
│   └── Servers/         # Server configs
└── telegraf/
    ├── telegraf.conf    # Main Telegraf config
    └── telegraf.d/      # Additional Telegraf configs
```

#### Template Directory Structure (Container)
```
/etc/templates/
├── uberAgent/           # Mounted from ./templates/uberAgent
│   ├── VDA/
│   ├── Physical/
│   └── Servers/
└── telegraf/           # Mounted from ./templates/telegraf
    ├── telegraf.conf
    └── telegraf.d/
```

This mapping ensures that:
- Templates are maintained in the host's `./templates/` directory
- Processed configurations are output to the host's `./uaConfigs/` directory
- SSL certificates are stored in the host's `./certs/` directory
- All paths are consistently referenced in documentation and configuration

## Operation

### Startup Process

1. Verify and create necessary directories
2. Check and manage SSL certificates
3. Process uberAgent templates
4. Process Telegraf templates
5. Retrieve Citrix Site ID
6. Generate configuration packages

### Template Processing

#### uberAgent
- Scan all subdirectories in `/etc/templates/uberAgent`
- Each subdirectory represents a different configuration scenario (e.g., VDA, Physical, Servers)
- Process templates independently for each subdirectory
- Substitute environment variables in all files within each subdirectory
- Create separate `.uAConfig` archives for each configuration type

Example directory structure:
```
/etc/templates/uberAgent/
├── VDA/                    # Virtual Desktop configuration
│   ├── uberAgent.conf
│   └── uberAgent-filter.conf
├── Physical/              # Physical workstation configuration
│   ├── uberAgent.conf
│   └── uberAgent-filter.conf
└── Servers/              # Server configuration
    ├── uberAgent.conf
    └── uberAgent-filter.conf
```

This structure allows:
- Different configurations for different use cases
- Independent template processing for each scenario
- Customized filters and settings per environment type
- Flexible deployment options

#### Telegraf
- Process main `telegraf.conf` file
- Handle `telegraf.d` directory for additional configurations
- Create ZIP archive containing all configurations

## Output

### Output Directory Structure

```
/etc/uaConfigs/
├── uberAgent/
│   └── VDA/
│       └── uberAgent.uAConfig
└── telegraf/
    └── telegraf.zip
```

## Monitoring and Debug

- Detailed logs available with different verbosity levels
- Certificate status verification
- Template processing monitoring
- Citrix API call monitoring

## Security

- Secure SSL certificate management
- Protection of Citrix Cloud credentials
- Secure proxy connection support
- TLS peer certificate validation

## Maintenance

### Routine Checks
- Certificate validity verification
- Updated template checks
- Error log monitoring
- Citrix Cloud connectivity verification

### Troubleshooting

Common issues and solutions:

1. **Invalid Certificates**
   - Check expiration date
   - Verify certificate CN
   - Regenerate if necessary

2. **Template Errors**
   - Check environment variable syntax
   - Verify file permissions
   - Check disk space

3. **Citrix API Issues**
   - Verify credentials
   - Check proxy configuration
   - Verify network connectivity
