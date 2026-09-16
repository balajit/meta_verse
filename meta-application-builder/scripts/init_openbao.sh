#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="meta-builder-openbao"
BAO_CMD="docker exec -e BAO_ADDR=http://127.0.0.1:8200 -e BAO_TOKEN=root ${CONTAINER_NAME} bao"

usage() {
    echo "Usage: $0 <env> [secrets-file-path]"
    echo "Examples:"
    echo "  $0 dev                   # Defaults to secrets.dev -> meta-builder/dev/app"
    echo "  $0 prod /secure/prod.env # Custom path -> meta-builder/prod/app"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

ENV=$(echo "$1" | tr '[:upper:]' '[:lower:]')
SECRETS_FILE="${2:-secrets.${ENV}}"
SECRET_PATH="meta-builder/${ENV}/app"

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

echo "Loading secrets from '$SECRETS_FILE' into OpenBao path '$SECRET_PATH'..."

KV_ARGS=()
while IFS= read -r line || [ -n "$line" ]; do
    line=$(echo "$line" | xargs)
    [[ -z "$line" || "$line" =~ ^# ]] && continue

    if [[ "$line" == *"="* ]]; then
        key="${line%%=*}"
        value="${line#*=}"
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
        KV_ARGS+=("${key}=${value}")
    fi
done < "$SECRETS_FILE"

if [ ${#KV_ARGS[@]} -gt 0 ]; then
    ${BAO_CMD} kv put "$SECRET_PATH" "${KV_ARGS[@]}"
    echo "Successfully loaded ${#KV_ARGS[@]} secrets into '$SECRET_PATH'."
else
    echo "Warning: No valid key-value pairs found in '$SECRETS_FILE'."
fi

# Create environment-scoped Transit Key
TRANSIT_KEY="meta-builder-key-${ENV}"
if ! ${BAO_CMD} read "transit/keys/${TRANSIT_KEY}" > /dev/null 2>&1; then
    echo "Generating transit key '${TRANSIT_KEY}'..."
    ${BAO_CMD} write -f "transit/keys/${TRANSIT_KEY}"
fi

# Apply environment-isolated read policy
POLICY_NAME="meta-builder-app-${ENV}"
echo "Applying scoped policy '${POLICY_NAME}'..."
${BAO_CMD} policy write "$POLICY_NAME" - <<EOF
path "meta-builder/data/${ENV}/*" {
  capabilities = ["read"]
}
path "meta-builder/metadata/${ENV}/*" {
  capabilities = ["list", "read"]
}
path "transit/encrypt/${TRANSIT_KEY}" {
  capabilities = ["update"]
}
path "transit/decrypt/${TRANSIT_KEY}" {
  capabilities = ["update"]
}
EOF

echo "OpenBao environment '${ENV}' initialized successfully."