package foundation.governance.tenant_isolation

import future.keywords.in

default allow = false

# Enforce strict namespace matching against tenant_id and explicit ABAC permission
allow {
    valid_tenant_id
    valid_target_urn
    user_has_required_permission
}

valid_tenant_id {
    input.identity.tenant_id != ""
    # Enforce strict regex matching to reject path traversal attempts like 'tenant_../../admin'
    regex.match("^tenant_[a-z0-9_]{3,32}$", input.identity.tenant_id)
}

valid_target_urn {
    valid_tenant_id
    expected_prefix := concat("", ["urn:meta:bcr:provider:", input.identity.tenant_id, ":"])
    startswith(input.target_urn, expected_prefix)
}

user_has_required_permission {
    input.required_permission in input.identity.permissions
}