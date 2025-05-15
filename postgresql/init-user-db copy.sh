#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE USER grafana WITH PASSWORD '$GF_DATABASE_PASSWORD';
	GRANT ALL PRIVILEGES ON DATABASE grafana TO grafana;
	GRANT ALL ON SCHEMA public TO grafana;
	\c grafana;
	GRANT ALL ON SCHEMA public TO grafana;
EOSQL