#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print(
        "ERROR: jsonschema is not installed.\n"
        "Install it with: python -m pip install jsonschema",
        file=sys.stderr,
    )
    sys.exit(2)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"File not found: {path}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        )


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: validate_manifest.py SCHEMA_PATH MANIFEST_PATH",
            file=sys.stderr,
        )
        return 2

    schema_path = Path(sys.argv[1])
    manifest_path = Path(sys.argv[2])

    try:
        schema = load_json(schema_path)
        manifest = load_json(manifest_path)

        validator = jsonschema.Draft202012Validator(schema)

        errors = sorted(
            validator.iter_errors(manifest),
            key=lambda error: list(error.absolute_path),
        )

        if errors:
            print(json.dumps({
                "status": "invalid",
                "error_count": len(errors),
                "errors": [
                    {
                        "path": list(error.absolute_path),
                        "schema_path": list(error.absolute_schema_path),
                        "message": error.message,
                    }
                    for error in errors
                ],
            }, indent=2))
            return 1

        print(json.dumps({
            "status": "valid",
            "schema": str(schema_path),
            "manifest": str(manifest_path),
        }, indent=2))

        return 0

    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "message": str(exc),
        }, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
