---
description: Validate and repair the generated manifest
agent: manifest-validate
---

Validate:

.manifest-pipeline/06-manifest.json

against:

schemas/manifest.schema.json

Run both Python validators.

Repair only conservative structural/reference problems.

Write:

.manifest-pipeline/06-manifest.json
.manifest-pipeline/07-validation.json

Additional context:

$ARGUMENTS
