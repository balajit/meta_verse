#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="meta-builder-openbao"
BAO_CMD="docker exec -e BAO_ADDR=http://127.0.0.1:8200 -e BAO_TOKEN=root ${CONTAINER_NAME} bao"

usage() {
    echo "Usage: $0 <env> [secrets-file-path]"
    echo "Examples:"
    echo "  $0 dev                   # Defaults to secrets.dev"
    echo "  $0 prod config/prod.env  # Custom path"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

ENV=$(echo "$1" | tr '[:upper:]' '[:lower:]')
SECRETS_FILE="${2:-secrets.${ENV}}"

if [ ! -f "$SECRETS_FILE" ]; then
    echo "Error: Secrets file '$SECRETS_FILE' not found."
    exit 1
fi

echo "Checking OpenBao connection..."
if ! ${BAO_CMD} status > /dev/null 2>&1; then
    echo "Error: OpenBao container '${CONTAINER_NAME}' is not reachable."
    exit 1
fi

# Ensure secrets engines exist
if ! ${BAO_CMD} secrets list | grep -q "^meta-builder/"; then
    ${BAO_CMD} secrets enable -path=meta-builder kv-v2
    echo "Enabled KV-v2 secrets engine at 'meta-builder/'."
fi

if ! ${BAO_CMD} secrets list | grep -q "^transit/"; then
    ${BAO_CMD} secrets enable transit
    echo "Enabled Transit encryption engine at 'transit/'."
fi

# Track current module and accumulate arguments per section header
CURRENT_MODULE="app"
declare -A MODULE_KV_MAP

echo "Parsing section headers from '$SECRETS_FILE'..."

while IFS= read -r line || [ -n "$line" ]; do
    trimmed=$(echo "$line" | xargs)
    [[ -z "$trimmed" ]] && continue

    # Detect section header comments matching `# meta_*` or `# meta-*`
    if [[ "$trimmed" =~ ^#[[:space:]]*(meta[-_][a-zA-Z0-9_-]+) ]]; then
        CURRENT_MODULE="${BASH_REMATCH[1]}"
        continue
    elif [[ "$trimmed" =~ ^# ]]; then
        continue
    fi

    if [[ "$trimmed" == *"="* ]]; then
        key="${trimmed%%=*}"
        value="${trimmed#*=}"
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

        MODULE_KV_MAP["$CURRENT_MODULE"]+="${key}=${value} "
    fi
done < "$SECRETS_FILE"

# Seed each detected module section into its own OpenBao path
for mod in "${!MODULE_KV_MAP[@]}"; do
    SECRET_PATH="meta-builder/${ENV}/${mod}"
    kv_string="${MODULE_KV_MAP[$mod]}"

    # Write module secrets to OpenBao KV-v2
    ${BAO_CMD} kv put "$SECRET_PATH" $kv_string > /dev/null
    echo "Loaded secrets into OpenBao path: '$SECRET_PATH'"

    # Apply isolated read policy per module
    POLICY_NAME="policy-${ENV}-${mod}"
    ${BAO_CMD} policy write "$POLICY_NAME" - <<EOF > /dev/null
path "meta-builder/data/${ENV}/${mod}" {
  capabilities = ["read"]
}
path "meta-builder/metadata/${ENV}/${mod}" {
  capabilities = ["list", "read"]
}
EOF
    echo "Applied scoped policy: '${POLICY_NAME}'"
done

# Create environment-scoped Transit Key
TRANSIT_KEY="meta-builder-key-${ENV}"
if ! ${BAO_CMD} read "transit/keys/${TRANSIT_KEY}" > /dev/null 2>&1; then
    echo "Generating transit key '${TRANSIT_KEY}'..."
    ${BAO_CMD} write -f "transit/keys/${TRANSIT_KEY}" > /dev/null
fi

echo "OpenBao environment '${ENV}' initialized across ${#MODULE_KV_MAP[@]} module namespace(s)."