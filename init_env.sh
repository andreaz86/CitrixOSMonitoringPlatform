#!/bin/bash

TEMPLATE_FILE=".env.template"
ENV_FILE=".env"

# Remove existing .env and create new one from template
if [[ -f "$ENV_FILE" ]]; then
    rm "$ENV_FILE"
fi
cp "$TEMPLATE_FILE" "$ENV_FILE"

# Get Docker socket GID
DOCKER_GID=$(stat -c '%g' /run/docker.sock)

# Order of questions is important: Citrix, then Grafana, then others
declare -A questions=(
  [CTX_CLIENT_ID]="Citrix Client ID"
  [CTX_CLIENT_SECRET]="Citrix Client Secret"
  [CTX_CUSTOMER_ID]="Citrix Customer ID"
  [GF_SECURITY_ADMIN_USER]="Grafana admin username"
  [GF_SECURITY_ADMIN_PASSWORD]="Grafana admin password (used to connect to Grafana)"
  [GF_SERVER_DOMAIN]="Grafana server domain (e.g. grafana.example.com for self signed certs generation and fix links in Grafana)"
  [SERVERNAMEORIP]="Server name or IP (can be same as Grafana domain if DNS record exists, used for uberAgent and Telegraf config generation)"
  [GF_DATABASE_PASSWORD]="Grafana database password (used to connect to PostgreSQL, you should not even need to know this password, is internal only)"
  [POSTGRES_PASSWORD]="Postgres password (PostgreSQL database password, good to know to use Pgadmin)"
  [DB_SVCCITRIX_PWD]="Service Citrix database password (used by Citrix_Metrics and Grafana, you should not even need to know this password, is internal only)")

generate_password() {
  # 20 chars, using only alphanumeric and selected special chars that are safe
  tr -dc 'A-Za-z0-9#@-_' < /dev/urandom | head -c 20
}

prompt_value() {
  local key="$1"
  local prompt="$2"
  local is_password="$3"
  local value

  while true; do
    if [[ "$key" == "CTX_CLIENT_SECRET" ]]; then
      # Don't generate random for Citrix Client Secret
      read -s -p "$prompt (cannot be empty): " value
      echo  # add a newline after the password
      if [[ -n "$value" ]]; then
        break
      fi
    elif [[ "$is_password" == "1" ]]; then
      # Ask for random generation for all passwords except CTX_CLIENT_SECRET
      read -p "$prompt (do you want to generate randomly? [y/N]): " generate_random
      if [[ "${generate_random,,}" == "y" ]]; then
        value=$(generate_password)
        break
      else
        read -s -p "$prompt (cannot be empty): " value
        echo  # add a newline after the password
        if [[ -n "$value" ]]; then
          break
        fi
      fi
    else
      read -p "$prompt (cannot be empty): " value
      if [[ -n "$value" ]]; then
        break
      fi
    fi
    echo "This field cannot be empty. Please provide a value."
  done
  echo "$value"
}

# Add Docker GID to env file
sed -i "/^TELEGRAF_DOCKER_GID=/d" "$ENV_FILE" 2>/dev/null
echo "TELEGRAF_DOCKER_GID=$DOCKER_GID" >> "$ENV_FILE"

# Define the order of keys we want to process
ordered_keys=(
  "CTX_CLIENT_ID"
  "CTX_CLIENT_SECRET"
  "CTX_CUSTOMER_ID"
  "GF_SECURITY_ADMIN_USER"
  "GF_SECURITY_ADMIN_PASSWORD"
  "GF_SERVER_DOMAIN"
  "SERVERNAMEORIP"
  "GF_DATABASE_PASSWORD"
  "POSTGRES_PASSWORD"
  "DB_SVCCITRIX_PWD"
)

declare -A new_values
for key in "${ordered_keys[@]}"; do
  prompt="${questions[$key]}"
  is_password=0
  if [[ "$key" == *PASSWORD* || "$key" == *SECRET* || "$key" == "DB_SVCCITRIX_PWD" ]]; then
    is_password=1
  fi
  new_values[$key]="$(prompt_value "$key" "$prompt" "$is_password")"
  # Write the key-value pair to the env file, ensuring single line
  echo "${key}='${new_values[$key]}'" >> "$ENV_FILE"
done

echo -e "\nSummary of changes:"
echo "TELEGRAF_DOCKER_GID: $DOCKER_GID"
for key in "${!questions[@]}"; do
  value="${new_values[$key]}"
  echo "$key: $value"
done
