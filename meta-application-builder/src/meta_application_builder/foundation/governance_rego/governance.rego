# file name: /meta-application-builder/policies/governance.rego

package governance

import rego.v1

default allow = false

# Allow valid payload specifications with non-empty fields and permitted metadata tiers
allow if {
    is_string(input.model_name)
    input.model_name != ""
    is_array(input.fields)
    count(input.fields) > 0
    not is_forbidden_tier
}

is_forbidden_tier if {
    is_string(input.metadata.tier)
    input.metadata.tier == "forbidden"
}