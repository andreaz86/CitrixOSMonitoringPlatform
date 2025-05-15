# NGINX Configuration

This NGINX instance serves as the entry point for uberAgent metrics and configuration files distribution. It handles SSL/TLS termination and proxies requests to the appropriate backend services.

## TCP Entry Point Configuration

The main entry point for uberAgent metrics is configured using the `UA_INGRESSPORT` environment variable (default: 8088):

```nginx
server { 
   listen ${UA_INGRESSPORT};
   server_name frontend;
   
   location /uberagent/_bulk {
     proxy_pass http://fluentbit-metrics:8088/_bulk;
     proxy_set_header X-Real-IP $remote_addr;
     proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
     proxy_set_header Host $http_host;
     proxy_pass_request_headers on;
   }
}
```

The port configuration is synchronized across:
- Environment variable in `.env`: `UA_INGRESSPORT=8088`
- Docker Compose port mapping: `ports: - "${UA_INGRESSPORT}:8088"`
- NGINX configuration: `listen ${UA_INGRESSPORT};`
- uberAgent client configuration: `URL=https://your-domain.com:${UA_INGRESSPORT}/`

## Configuration Repository

NGINX also serves as a distribution point for uberAgent and Telegraf configurations (reversed proxied by traefik):

```nginx
server {
    listen       8089;
    server_name  localhost;

    location /repo {
        root   /usr/share/nginx/html;
        index  index.html index.htm;
        autoindex on;  # Enable directory listing
    }
}
```


## Volume Mounts

```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro   # Main configuration
  - ./certs:/etc/nginx/certs                      # SSL/TLS certificates
  - ./uaConfigs:/usr/share/nginx/html/repo:ro     # Configuration repository
```

## Security

- SSL/TLS encryption using certificates from sidecar
- Read-only configuration mounts
- No direct access to backend services
- Proper header forwarding for client identification

## Request Flow

1. **uberAgent Metrics**
   ```
   uberAgent → NGINX:${UA_INGRESSPORT} → Fluent Bit Metrics:8088
   ```

2. **Configuration Downloads**
   ```
   Client → traefik →  NGINX:8089/repo → Static Files
   ```

## Troubleshooting

1. **Proxy Issues**
```bash
# Check logs for proxy errors
docker logs nginx | grep error

