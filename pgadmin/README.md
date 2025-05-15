# pgAdmin Configuration

This pgAdmin instance provides a web-based administration interface for managing PostgreSQL databases in the monitoring platform.

## Overview

The container is configured to provide easy access to the PostgreSQL databases used by:
- Grafana configuration storage
- Citrix metrics configuration data
- Platform settings

## Configuration

The container is configured through environment variables in docker-compose.yml:

```yaml
environment:
  - PGADMIN_DEFAULT_EMAIL=admin@admin.com
  - PGADMIN_DEFAULT_PASSWORD=admin
  - PGADMIN_CONFIG_SERVER_MODE=False
  - PGADMIN_CONFIG_MASTER_PASSWORD_REQUIRED=False
  - PGADMIN_LISTEN_PORT=5433
```

## Server Configuration

Pre-configured server connections are provided through `docker_pgadmin_servers.json`. The PostgreSQL password is set through the `POSTGRES_PASSWORD` environment variable in the `.env` file:

```json
{
    "Servers": {
        "1": {
            "Name": "Monitoring Platform DB",
            "Group": "Servers",
            "Host": "postgresql",
            "Port": 5432,
            "MaintenanceDB": "postgres",
            "Username": "postgres",
            "SSLMode": "prefer"
        }
    }
}
```

**Database Credentials**:
- Username: postgres
- Password: Value of `POSTGRES_PASSWORD` from `.env`
- Host: postgresql
- Port: 5432
```

## Access

- URL: `http://<your-server>:5433`
- Default credentials:
  - Email: admin@admin.com
  - Password: admin

## Volume Mounts

```yaml
volumes:
  - ${ROOT_PATH}/pgadmin/backup:/backup     # For database backups
  - ./pgadmin/docker_pgadmin_servers.json:/pgadmin4/servers.json
  - /etc/localtime:/etc/localtime:ro
```

## Features

1. **Database Management**
   - Create/modify database objects
   - Execute SQL queries
   - View table data
   - Monitor database performance

2. **Backup & Restore**
   - Create database backups
   - Restore from backup files
   - Export query results

3. **Monitoring**
   - Server status
   - Connection activity
   - Database size analytics
   - Query performance

## Usage Examples

### Database Backup
```sql
-- Through pgAdmin interface:
1. Right-click on database
2. Select "Backup..."
3. Choose format (Custom, tar, plain)
4. Save to /backup directory
```

## Security Considerations

1. **Access Control**
   - Change default credentials in production
   - Use strong passwords
   - Restrict network access to pgAdmin port

2. **SSL/TLS**
   - Configure SSL for database connections
   - Use secure connection strings
   - Verify SSL certificates

3. **Backup Security**
   - Encrypt sensitive backups
   - Regular backup rotation
   - Secure backup storage

