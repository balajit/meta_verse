---
description: Run the complete staged manifest generation pipeline
agent: manifest-orchestrator
---

Run the complete manifest-generation pipeline.

Arguments supplied by the user:

$ARGUMENTS

The pipeline must execute strictly in this order:

1. manifest-schema
2. manifest-domain
3. manifest-relationships
4. manifest-workflows
5. manifest-policies
6. manifest-assemble
7. manifest-validate
8. manifest-audit

Do not parallelize stages.

Do not skip stages.

Do not generate competing manifests.

Persist every stage artifact under:

.manifest-pipeline/

The final production manifest must be:

.manifest-pipeline/final/manifest.json

Before declaring success, run both Python validators against the final
manifest.
