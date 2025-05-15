#!/bin/sh
# entrypoint.sh
set -e
#. /envs/env.list

CERT_DIR=/etc/certs
UA_TEMPLATE_DIR=/etc/templates/uberAgent
TELEGRAF_TEMPLATE_DIR=/etc/templates/telegraf
CONF_DIR=/etc/uaConfigs
#VERBOSE=3
# Set default verbosity level if not defined
: ${VERBOSE:=0}

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
    
    # Generate bearer token - Fix JSON payload formatting
    TOKEN_RESPONSE=$(curl -s -X POST \
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
    SITES_RESPONSE=$(curl -s -X GET \
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
    # Format expected: data.Customers[0].Sites[0].Id
    # Using a combination of grep and sed to extract this from the JSON
    
    # First check if we have jq available, which would be ideal for JSON parsing
    if command -v jq > /dev/null 2>&1; then
      log 2 "Using jq to parse JSON response"
      SITE_ID=$(echo "$SITES_RESPONSE" | jq -r '.Customers[0].Sites[0].Id' 2>/dev/null)
    else
      log 2 "jq not available, using grep/sed to extract Site ID"
      # This is a more basic approach that might break with complex JSON
      SITE_ID=$(echo "$SITES_RESPONSE" | grep -o '"Sites":\[[^]]*\]' | grep -o '"Id":"[^"]*' | head -1 | sed 's/"Id":"//')
    fi
    
    if [ -z "$SITE_ID" ] || [ "$SITE_ID" = "null" ]; then
      log 0 "❌ Error: Failed to retrieve Site ID from Citrix Cloud"
      log 2 "Response may be in a different format than expected"
      return 1
    fi
    
    log 0 "✅ Successfully retrieved Citrix Cloud Site ID: $SITE_ID"
    
    # Export the site ID for use in environment
    export CTX_SITE_ID="$SITE_ID"
    
    # Update the env.list file with the new site ID
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
  else
    log 0 "✅ CTX_SITE_ID is already set: $CTX_SITE_ID"
  fi
}

log 0 "🚀 Starting configuration process" 

# Call the function to verify and obtain Citrix Site ID if needed


# 1) ensure directories exist
log 1 "Creating necessary directories if they don't exist"
mkdir -p "$CERT_DIR" "$CONF_DIR"
log 2 "Created directories: $CERT_DIR and $CONF_DIR"

# 2) certificates: if missing or invalid, generate self-signed with CN=${CERT_FQDN}
if [ ! -f "$CERT_DIR/server.crt" ] || [ ! -f "$CERT_DIR/server.key" ]; then
  log 0 "🔐 Certificates missing: generating self-signed..." 
  openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/server.key" \
    -out    "$CERT_DIR/server.crt" \
    -subj   "/CN=${CERT_FQDN}"
  log 1 "Generated new self-signed certificate with CN=${CERT_FQDN}"
else
  log 1 "🔍 Verifying existing certificate..."
  if ! openssl x509 -in "$CERT_DIR/server.crt" -noout >/dev/null 2>&1; then
    log 0 "❌ Invalid certificate detected: regenerating self-signed..."
    openssl req -x509 -nodes -days 3650 \
      -newkey rsa:2048 \
      -keyout "$CERT_DIR/server.key" \
      -out    "$CERT_DIR/server.crt" \
      -subj   "/CN=${CERT_FQDN}"
    log 1 "Regenerated new self-signed certificate with CN=${CERT_FQDN}"
  else
    log 0 "✅ Valid certificate found."
    log 2 "Certificate details:"
    [ "$VERBOSE" -ge 2 ] && openssl x509 -in "$CERT_DIR/server.crt" -noout -text | grep -E 'Subject:|Not Before:|Not After :' | sed 's/^/    /'
  fi
fi

# 3) iterate over each direct subdirectory of UA_TEMPLATE_DIR
log 0 "⚙️ Processing uberAgent templates"
log 1 "Scanning directory: $UA_TEMPLATE_DIR for template configurations"

for subdir in "$UA_TEMPLATE_DIR"/*; do
  [ -d "$subdir" ] || continue
  name=$(basename "$subdir")
  log 0 "⚙️ Processing folder: $name"
  log 2 "Full path: $subdir"

  # setup temp workspace and copy all files (preserves full tree)
  tmp=$(mktemp -d)
  log 2 "Created temporary workspace: $tmp"
  cp -a "$subdir/." "$tmp/"
  log 2 "Copied all files from $subdir to temporary workspace"

  # perform envsubst on every file under tmp
  find "$tmp" -type f | while IFS= read -r file; do
    log 1 "  - Substituting environment variables in $(basename "$file")"
    log 3 "    Full path: $file"
    envsubst < "$file" > "${file}.new" && mv "${file}.new" "$file"
    log 3 "    Environment variable substitution completed"
  done

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
done

# Process the TELEGRAF_TEMPLATE_DIR structure
log 0 "⚙️ Processing Telegraf templates"
log 1 "Scanning directory: $TELEGRAF_TEMPLATE_DIR for telegraf configurations"

# Setup temp workspace for telegraf
tmp=$(mktemp -d)
log 2 "Created temporary workspace for telegraf: $tmp"

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

# 4) done
log 0 "👍 All tasks completed. Exiting."

if [ "$VERBOSE" -ge 1 ]; then
  log 1 "Summary of operations:"
  log 1 "  - Certificate operations completed"
  log 1 "  - Processed uberAgent templates from: $UA_TEMPLATE_DIR"
  log 1 "  - Processed Telegraf templates from: $TELEGRAF_TEMPLATE_DIR"
  log 1 "  - Configuration files available in: $CONF_DIR"
  [ -f "$CERT_DIR/server.crt" ] && log 1 "  - Certificate available at: $CERT_DIR/server.crt"
fi

get_citrix_site_id