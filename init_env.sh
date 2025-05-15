#!/bin/bash

ENV_FILE=".env"

declare -A questions=(
  [GF_SECURITY_ADMIN_USER]="Grafana admin username"
  [GF_SECURITY_ADMIN_PASSWORD]="Grafana admin password"
  [GF_SERVER_DOMAIN]="Grafana server domain"
  [POSTGRES_PASSWORD]="Postgres password"
  [CTX_CLIENT_ID]="Citrix Client ID"
  [CTX_CLIENT_SECRET]="Citrix Client Secret"
)

generate_password() {
  # 20 chars, strong
  tr -dc 'A-Za-z0-9!@#$%^&*()-_' < /dev/urandom | head -c 20
}

prompt_value() {
  local key="$1"
  local prompt="$2"
  local is_password="$3"
  local value
  if [[ "$is_password" == "1" ]]; then
    read -p "$prompt (leave blank to generate randomly): " value
    if [[ -z "$value" ]]; then
      value=$(generate_password)
      echo "Generated: $value"
    fi
  else
    read -p "$prompt: " value
  fi
  echo "$value"
}

# Backup existing .env
if [[ -f "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)"
fi

declare -A new_values
for key in "${!questions[@]}"; do
  prompt="${questions[$key]}"
  is_password=0
  if [[ "$key" == *PASSWORD* || "$key" == *SECRET* ]]; then
    is_password=1
  fi
  new_values[$key]="$(prompt_value "$key" "$prompt" "$is_password")"
  # Remove any existing line for this key
  sed -i "/^$key=/d" "$ENV_FILE" 2>/dev/null
  echo "$key='${new_values[$key]}'" >> "$ENV_FILE"
done

echo ".env updated with: ${!new_values[@]}"
