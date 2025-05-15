#!/bin/sh
# entrypoint.sh
set -e

# Global variables
CERT_DIR=/etc/certs
UA_TEMPLATE_DIR=/etc/templates/uberAgent
TELEGRAF_TEMPLATE_DIR=/etc/templates/telegraf
CONF_DIR=/etc/uaConfigs
# Set default verbosity level if not defined
: ${VERBOSE:=0}

# Function to handle proxy configuration for curl
setup_proxy_for_curl() {
  # Check for proxy environment variables
  if [ -n "$HTTP_PROXY" ] || [ -n "$HTTPS_PROXY" ] || [ -n "$http_proxy" ] || [ -n "$https_proxy" ]; then
    log 1 "Proxy configuration detected"
    # Build proxy parameters for curl
    CURL_PROXY_OPTS=""
    
    # Check each proxy environment variable
    if [ -n "$HTTP_PROXY" ]; then
      log 2 "Using HTTP_PROXY: $HTTP_PROXY"
      CURL_PROXY_OPTS="$CURL_PROXY_OPTS --proxy $HTTP_PROXY"
    elif [ -n "$http_proxy" ]; then
      log 2 "Using http_proxy: $http_proxy"
      CURL_PROXY_OPTS="$CURL_PROXY_OPTS --proxy $http_proxy"
    fi
    
    if [ -n "$HTTPS_PROXY" ]; then
      log 2 "Using HTTPS_PROXY: $HTTPS_PROXY"
      CURL_PROXY_OPTS="$CURL_PROXY_OPTS --proxy-insecure --proxy $HTTPS_PROXY"
    elif [ -n "$https_proxy" ]; then
      log 2 "Using https_proxy: $https_proxy"
      CURL_PROXY_OPTS="$CURL_PROXY_OPTS --proxy-insecure --proxy $https_proxy"
    fi
    
    if [ -n "$NO_PROXY" ]; then
      log 2 "Using NO_PROXY: $NO_PROXY"
      CURL_PROXY_OPTS="$CURL_PROXY_OPTS --noproxy $NO_PROXY"
    elif [ -n "$no_proxy" ]; then
      log 2 "Using no_proxy: $no_proxy"
      CURL_PROXY_OPTS="$CURL_PROXY_OPTS --noproxy $no_proxy"
    fi
    
    log 2 "Curl proxy options: $CURL_PROXY_OPTS"
  else
    log 2 "No proxy configuration detected"
    CURL_PROXY_OPTS=""
  fi
}

# Function to log messages with verbosity control
log() {
  local level=$1
  local message=$2
  local emoji=$3
  
  if [ "$VERBOSE" -ge "$level" ]; then
    if [ -n "$emoji" ]; then
      echo "$emoji $message"
    else
      echo "$message"
    fi
  fi
}

# Function to get Citrix Cloud Site ID if not already set
get_citrix_site_id() {
  log 0 "🔍 Checking Citrix Cloud Site ID configuration" 
  
  # Source environment variables from env.list file
  if [ -f "/envs/env.list" ]; then
    log 1 "Loading environment variables from /envs/env.list"
    . /envs/env.list
  fi
  
  # Check if CTX_SITE_ID is already set
  if [ -z "$CTX_SITE_ID" ]; then
    log 0 "⚠️ CTX_SITE_ID not found, will attempt to retrieve it from Citrix Cloud API"
    
    # Verify CLIENT_ID and CLIENT_SECRET are available
    if [ -z "$CTX_CLIENT_ID" ] || [ -z "$CTX_CLIENT_SECRET" ]; then
      log 0 "❌ Error: CTX_CLIENT_ID or CTX_CLIENT_SECRET not set in environment variables"
      return 1
    fi
    
    log 1 "Using Client ID: $CTX_CLIENT_ID"
    log 1 "Generating Citrix Cloud Bearer token"
    
    # Initialize proxy options for curl
    setup_proxy_for_curl
    
    # Generate bearer token - Fix JSON payload formatting
    TOKEN_RESPONSE=$(curl -s -X POST $CURL_PROXY_OPTS \
      "https://trust.citrixworkspacesapi.net/root/tokens/clients" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      -d "{\"ClientId\": \"$CTX_CLIENT_ID\", \"ClientSecret\": \"$CTX_CLIENT_SECRET\"}")
    
    # Print the TOKEN_RESPONSE to the console
    log 0 "Token Response from Citrix Cloud API:"
    echo "$TOKEN_RESPONSE"
    
    # Extract token
    BEARER_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"token":"[^"]*' | sed 's/"token":"//')
    
    if [ -z "$BEARER_TOKEN" ]; then
      log 0 "❌ Error: Failed to obtain bearer token from Citrix Cloud"
      return 1
    fi
    
    log 1 "Successfully obtained bearer token"
    log 2 "Token: $BEARER_TOKEN"
    log 1 "Retrieving Site ID from Citrix Cloud API"
    
    # Get customer ID if not already set
    if [ -z "$CTX_CUSTOMER_ID" ]; then
      log 0 "❌ Error: CTX_CUSTOMER_ID not set in environment variables"
      return 1
    fi
    
    # Make API call to get sites - using the Customer API endpoint
    SITES_RESPONSE=$(curl -s -X GET $CURL_PROXY_OPTS \
      "https://api-eu.cloud.com/cvad/manage/me" \
      -H "Authorization: CwsAuth bearer=$BEARER_TOKEN" \
      -H "Citrix-CustomerId: $CTX_CUSTOMER_ID" \
      -H "Content-Type: application/json")
    
    # Save response for debugging if needed
    echo "$SITES_RESPONSE" > /tmp/citrix_response.json
    log 3 "Response saved to /tmp/citrix_response.json for debugging"

    # Print the JSON response to the console
    log 0 "JSON Response from Citrix Cloud API:"
    echo "$SITES_RESPONSE"
    
    # Extract the site ID using JSON path based on Postman script
    extract_site_id_from_response "$SITES_RESPONSE"
    
    if [ -z "$SITE_ID" ] || [ "$SITE_ID" = "null" ]; then
      log 0 "❌ Error: Failed to retrieve Site ID from Citrix Cloud"
      log 2 "Response may be in a different format than expected"
      return 1
    fi
    
    log 0 "✅ Successfully retrieved Citrix Cloud Site ID: $SITE_ID"
    
    # Export the site ID for use in environment
    export CTX_SITE_ID="$SITE_ID"
    
    # Update the env.list file with the new site ID
    update_env_file_with_site_id "$SITE_ID"
  else
    log 0 "✅ CTX_SITE_ID is already set: $CTX_SITE_ID"
  fi
}

# Helper function to extract site ID from API response
extract_site_id_from_response() {
  local SITES_RESPONSE=$1
  
  # First check if we have jq available, which would be ideal for JSON parsing
  if command -v jq > /dev/null 2>&1; then
    log 2 "Using jq to parse JSON response"
    SITE_ID=$(echo "$SITES_RESPONSE" | jq -r '.Customers[0].Sites[0].Id' 2>/dev/null)
  else
    log 2 "jq not available, using grep/sed to extract Site ID"
    # This is a more basic approach that might break with complex JSON
    SITE_ID=$(echo "$SITES_RESPONSE" | grep -o '"Sites":\[[^]]*\]' | grep -o '"Id":"[^"]*' | head -1 | sed 's/"Id":"//')
  fi
}

# Helper function to update env.list file with site ID
update_env_file_with_site_id() {
  local SITE_ID=$1
  
  if [ -f "/envs/env.list" ]; then
    if grep -q "CTX_SITE_ID=" "/envs/env.list"; then
      # Replace existing entry - use temp file approach to avoid "Device or resource busy" error
      sed "s/CTX_SITE_ID=.*/CTX_SITE_ID='$SITE_ID'/g" "/envs/env.list" > "/envs/env.list.tmp" && \
      cat "/envs/env.list.tmp" > "/envs/env.list" && \
      rm "/envs/env.list.tmp"
    else
      # Add new entry with a new line before it
      echo "" >> "/envs/env.list"
      echo "CTX_SITE_ID='$SITE_ID'" >> "/envs/env.list"
    fi
    log 1 "Updated /envs/env.list with the new Site ID"
  fi
}

# Function to ensure required directories exist
setup_directories() {
  log 1 "Creating necessary directories if they don't exist"
  mkdir -p "$CERT_DIR" "$CONF_DIR"
  log 2 "Created directories: $CERT_DIR and $CONF_DIR"
}

# Function to manage certificates
manage_certificates() {
  if [ ! -f "$CERT_DIR/server.crt" ] || [ ! -f "$CERT_DIR/server.key" ]; then
    generate_certificate
  else
    verify_certificate
  fi
}

# Helper function to generate a new certificate
generate_certificate() {
  log 0 "🔐 Certificates missing: generating self-signed..." 
  openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/server.key" \
    -out    "$CERT_DIR/server.crt" \
    -subj   "/CN=${CERT_FQDN}"
  log 1 "Generated new self-signed certificate with CN=${CERT_FQDN}"
}

# Helper function to verify existing certificate
verify_certificate() {
  log 1 "🔍 Verifying existing certificate..."
  if ! openssl x509 -in "$CERT_DIR/server.crt" -noout >/dev/null 2>&1; then
    log 0 "❌ Invalid certificate detected: regenerating self-signed..."
    generate_certificate
  else
    log 0 "✅ Valid certificate found."
    log 2 "Certificate details:"
    [ "$VERBOSE" -ge 2 ] && openssl x509 -in "$CERT_DIR/server.crt" -noout -text | grep -E 'Subject:|Not Before:|Not After :' | sed 's/^/    /'
  fi
}

# Function to process uberAgent templates
process_uberagent_templates() {
  log 0 "⚙️ Processing uberAgent templates"
  log 1 "Scanning directory: $UA_TEMPLATE_DIR for template configurations"

  for subdir in "$UA_TEMPLATE_DIR"/*; do
    [ -d "$subdir" ] || continue
    name=$(basename "$subdir")
    log 0 "⚙️ Processing folder: $name"
    log 2 "Full path: $subdir"

    process_uberagent_folder "$subdir" "$name"
  done
}

# Helper function to process a single uberAgent folder
process_uberagent_folder() {
  local subdir=$1
  local name=$2

  # setup temp workspace and copy all files (preserves full tree)
  tmp=$(mktemp -d)
  log 2 "Created temporary workspace: $tmp"
  cp -a "$subdir/." "$tmp/"
  log 2 "Copied all files from $subdir to temporary workspace"

  # perform envsubst on every file under tmp
  substitute_env_vars "$tmp"

  # prepare output directory - changing from $CONF_DIR/$name to $CONF_DIR/uberAgent/$name
  outdir="$CONF_DIR/uberAgent/$name"
  mkdir -p "$outdir"
  log 2 "Created output directory: $outdir"

  # create zip preserving the internal folder structure
  zipfile="$outdir/uberAgent.uAConfig"
  log 1 "  - Creating archive $zipfile"
  (cd "$tmp" && zip -r "$zipfile" . >/dev/null)
  log 2 "  - Archive created successfully with $(find "$tmp" -type f | wc -l) files"

  # cleanup
  rm -rf "$tmp"
  log 2 "Cleaned up temporary workspace for $name"
}

# Helper function to substitute env vars in files
substitute_env_vars() {
  local dir=$1
  
  find "$dir" -type f | while IFS= read -r file; do
    log 1 "  - Substituting environment variables in $(basename "$file")"
    log 3 "    Full path: $file"
    envsubst < "$file" > "${file}.new" && mv "${file}.new" "$file"
    log 3 "    Environment variable substitution completed"
  done
}

# Function to process Telegraf templates
process_telegraf_templates() {
  log 0 "⚙️ Processing Telegraf templates"
  log 1 "Scanning directory: $TELEGRAF_TEMPLATE_DIR for telegraf configurations"

  # Setup temp workspace for telegraf
  tmp=$(mktemp -d)
  log 2 "Created temporary workspace for telegraf: $tmp"

  process_telegraf_main_conf "$tmp"
  process_telegraf_conf_d "$tmp"

  # Prepare output directory for telegraf
  telegraf_outdir="$CONF_DIR/telegraf"
  mkdir -p "$telegraf_outdir"
  log 2 "Created output directory for telegraf: $telegraf_outdir"

  # Create zip preserving the internal folder structure for telegraf
  telegraf_zipfile="$telegraf_outdir/telegraf.zip"
  log 1 "  - Creating archive $telegraf_zipfile"
  (cd "$tmp" && zip -r "$telegraf_zipfile" . >/dev/null)
  total_files=$(find "$tmp" -type f | wc -l)
  log 2 "  - Archive created successfully with $total_files files"

  # Cleanup telegraf temp files
  rm -rf "$tmp"
  log 2 "Cleaned up temporary workspace for telegraf"
}

# Helper function to process main telegraf.conf
process_telegraf_main_conf() {
  local tmp=$1
  
  # Check if telegraf.conf exists in TELEGRAF_TEMPLATE_DIR
  if [ -f "$TELEGRAF_TEMPLATE_DIR/telegraf.conf" ]; then
    log 1 "  - Found telegraf.conf"
    # Copy and process the main telegraf.conf file
    cp "$TELEGRAF_TEMPLATE_DIR/telegraf.conf" "$tmp/"
    log 2 "  - Copied main telegraf.conf to temporary workspace"
    log 1 "  - Substituting environment variables in telegraf.conf"
    envsubst < "$tmp/telegraf.conf" > "$tmp/telegraf.conf.new" && mv "$tmp/telegraf.conf.new" "$tmp/telegraf.conf"
    log 3 "  - Environment variable substitution in telegraf.conf completed"
  else
    log 1 "  - Warning: telegraf.conf not found in $TELEGRAF_TEMPLATE_DIR"
  fi
}

# Helper function to process telegraf.d directory
process_telegraf_conf_d() {
  local tmp=$1
  
  # Check if telegraf.d directory exists and process its content
  if [ -d "$TELEGRAF_TEMPLATE_DIR/telegraf.d" ]; then
    log 1 "  - Found telegraf.d directory"
    conf_count=$(find "$TELEGRAF_TEMPLATE_DIR/telegraf.d" -name "*.conf" | wc -l)
    log 2 "  - Found $conf_count configuration files in telegraf.d directory"
    
    mkdir -p "$tmp/telegraf.d"
    log 2 "  - Created telegraf.d directory in temporary workspace"
    
    # Copy all files from telegraf.d and process them
    for conf_file in "$TELEGRAF_TEMPLATE_DIR/telegraf.d"/*.conf; do
      [ -f "$conf_file" ] || continue
      conf_name=$(basename "$conf_file")
      log 1 "  - Processing $conf_name"
      cp "$conf_file" "$tmp/telegraf.d/"
      log 3 "  - Copied $conf_name to temporary workspace"
      log 2 "  - Substituting environment variables in $conf_name"
      envsubst < "$tmp/telegraf.d/$conf_name" > "$tmp/telegraf.d/$conf_name.new" && mv "$tmp/telegraf.d/$conf_name.new" "$tmp/telegraf.d/$conf_name"
      log 3 "  - Environment variable substitution in $conf_name completed"
    done
  else
    log 1 "  - Warning: telegraf.d directory not found in $TELEGRAF_TEMPLATE_DIR"
  fi
}

# Function to display summary of operations
display_summary() {
  log 0 "👍 All tasks completed successfully."
  
  if [ "$VERBOSE" -ge 1 ]; then
    log 0 "📋 Summary of operations:"
    log 0 "  - Directory setup: $CERT_DIR, $CONF_DIR"
    
    # Certificate status
    if [ -f "$CERT_DIR/server.crt" ]; then
      log 0 "  - Certificate: ✅ Valid certificate at $CERT_DIR/server.crt"
    else
      log 0 "  - Certificate: ❌ Missing or invalid"
    fi
    
    # uberAgent templates
    ua_count=$(find "$CONF_DIR/uberAgent" -name "uberAgent.uAConfig" 2>/dev/null | wc -l)
    if [ "$ua_count" -gt 0 ]; then
      log 0 "  - uberAgent: ✅ Processed $ua_count configuration template(s)"
      log 0 "    - Source: $UA_TEMPLATE_DIR"
      log 0 "    - Output: $CONF_DIR/uberAgent"
    else
      log 0 "  - uberAgent: ❌ No configurations processed"
    fi
    
    # Telegraf templates
    if [ -f "$CONF_DIR/telegraf/telegraf.zip" ]; then
      log 0 "  - Telegraf: ✅ Configuration package created"
      log 0 "    - Source: $TELEGRAF_TEMPLATE_DIR"
      log 0 "    - Output: $CONF_DIR/telegraf/telegraf.zip"
    else
      log 0 "  - Telegraf: ❌ No configuration package created"
    fi
    
    # Citrix Site ID
    if [ -n "$CTX_SITE_ID" ]; then
      log 0 "  - Citrix: ✅ Site ID found/retrieved: $CTX_SITE_ID"
    else
      log 0 "  - Citrix: ❓ Site ID not available"
    fi
  fi
}

# Main execution flow
main() {
  # Print startup message
  log 0 "🚀 Starting configuration process"
  
  # Run each task in sequence
  setup_directories
  manage_certificates
  process_uberagent_templates
  process_telegraf_templates
  get_citrix_site_id
  display_summary
}

# Start execution
main