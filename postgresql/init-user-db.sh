#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE USER grafana WITH PASSWORD '$GF_DATABASE_PASSWORD';
	GRANT ALL PRIVILEGES ON DATABASE grafana TO grafana;
	GRANT ALL ON SCHEMA public TO grafana;
	\c grafana;
	GRANT ALL ON SCHEMA public TO grafana;
	
	CREATE DATABASE citrix_metrics;
	CREATE USER svc_citrix_metrics WITH PASSWORD '$DB_SVCCITRIX_PWD';
	GRANT ALL PRIVILEGES ON DATABASE citrix_metrics TO svc_citrix_metrics;
	\c citrix_metrics;
	GRANT ALL ON SCHEMA public TO svc_citrix_metrics;
	
	GRANT CONNECT ON DATABASE citrix_metrics TO grafana;
	GRANT USAGE ON SCHEMA public TO grafana;
	GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana;
	ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana;
EOSQL