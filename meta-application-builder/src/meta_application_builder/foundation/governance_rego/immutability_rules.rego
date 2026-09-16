package foundation.governance.immutability

import future.keywords.in

default allow_mutation = false

# Allow delta update if field is OVERRIDABLE or EXTENDABLE
allow_mutation {
    input.existing_tier == "OVERRIDABLE"
}

allow_mutation {
    input.existing_tier == "EXTENDABLE"
    input.operation_type in ["ADD_FIELD", "APPEND_ARRAY"]
}

# Block all mutations on FINAL tier
violation {
    input.existing_tier == "FINAL"
    input.mutation_attempted == true
}