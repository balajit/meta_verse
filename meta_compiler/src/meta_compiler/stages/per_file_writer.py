"""Per-file Python generation mirroring JSON schema hierarchy with imports.

Each ``$ref`` to another file becomes a Python import:
``shopping/types/item.json`` with ``price: {$ref: "../../common/types/amount.json"}``
generates ``shopping/types/item.py`` containing ``from ...common.types.amount import Amount``
and ``class Item`` (title-based, not ``ShoppingTypesItem``).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from datamodel_code_generator import DataModelType, InputFileType, generate


def write_per_file_schemas(
    *,
    raw_schemas: dict[str, dict[str, Any]],
    file_index: dict[str, Path],
    schema_dir: Path | None,
    out_root: Path,
    clear_output: bool = True,
) -> list[Path]:
    """Generate one ``.py`` per JSON schema, mirroring hierarchy with imports."""
    if not raw_schemas:
        return []

    out_root = Path(out_root)
    if clear_output and out_root.exists():
        for p in out_root.rglob("*.py"):
            try:
                p.unlink()
            except Exception:
                pass
    out_root.mkdir(parents=True, exist_ok=True)

    # Determine base
    if schema_dir is not None:
        base = Path(schema_dir).resolve()
    else:
        import os

        try:
            common = os.path.commonpath([str(Path(p).resolve()) for p in file_index.values()])  # type: ignore[arg-type]
            base = Path(common)
            if base.is_file():
                base = base.parent
            if not base.is_dir():
                base = base.parent
        except Exception:
            base = Path.cwd()

    def _rel_for(key: str) -> Path:
        src = file_index.get(key)
        if src is not None:
            try:
                return Path(src).resolve().relative_to(base)
            except Exception:
                pass
        return Path(key.replace(".", "/") + ".json")

    def _collect_transitive(start_key: str, seen: set[str] | None = None) -> set[str]:
        if seen is None:
            seen = set()
        if start_key in seen:
            return seen
        seen.add(start_key)
        schema = raw_schemas.get(start_key)
        if not isinstance(schema, dict):
            return seen
        # Walk to find file $refs
        stack: list[Any] = [schema]
        refs: list[str] = []
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "$ref" in node and isinstance(node["$ref"], str):
                    ref = node["$ref"]
                    file_part = ref.split("#")[0]
                    if file_part and not file_part.startswith("#"):
                        refs.append(file_part)
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(node, list):
                for x in node:
                    if isinstance(x, (dict, list)):
                        stack.append(x)
        for ref_file in refs:
            # Resolve file_part relative to start_key's file directory
            src_path = file_index.get(start_key)
            if src_path is None:
                continue
            try:
                target_path = (Path(src_path).parent / ref_file).resolve()
            except Exception:
                continue
            # Find which action_key corresponds to target_path
            for k, p in file_index.items():
                try:
                    if Path(p).resolve() == target_path:
                        _collect_transitive(k, seen)
                        break
                except Exception:
                    continue
        return seen

    written: list[Path] = []
    for action_key in sorted(raw_schemas.keys()):
        # Build minimal tmp_input containing this file + transitive deps
        transitive = _collect_transitive(action_key)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_input = Path(tmp_dir) / "schemas"
            tmp_input.mkdir(parents=True, exist_ok=True)
            for k in transitive:
                rel = _rel_for(k)
                target = tmp_input / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                data = raw_schemas[k]
                cleaned = _strip_ids_for_per_file(data)
                target.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")

            tmp_out = Path(tmp_dir) / "out"
            tmp_out.mkdir(parents=True, exist_ok=True)
            try:
                generate(
                    tmp_input,
                    input_file_type=InputFileType.JsonSchema,
                    output=tmp_out,
                    output_model_type=DataModelType.PydanticV2BaseModel,
                    use_field_description=True,
                    use_double_quotes=True,
                    use_standard_collections=True,
                    use_union_operator=True,
                    use_annotated=True,
                    field_constraints=True,
                    snake_case_field=True,
                    use_title_as_name=True,
                    reuse_model=True,
                )
            except Exception as e:
                # Fallback to single-file bundled for this key
                import logging

                logging.getLogger(__name__).warning("Per-file dir gen failed for %s: %s", action_key, e)
                # Fallback: generate single file via bundled inlined
                try:
                    from meta_compiler.stages.schema_bundler import SchemaBundler

                    bundler = SchemaBundler(Path(base), dict(file_index), raw_schemas)  # type: ignore[arg-type]
                    bundled = bundler.bundle_for(action_key)
                    import re

                    def _pascal_case(n: str) -> str:
                        return "".join(part.capitalize() for part in re.split(r"[^0-9A-Za-z]+", n) if part)

                    title = bundled.get("title") or raw_schemas[action_key].get("title") or Path(action_key.replace(".", "/")).name
                    class_name = _pascal_case(title)
                    from meta_compiler.stages.model_compiler import generate_model_source_code_from_schema

                    schema_doc = {**bundled, "title": class_name, "type": bundled.get("type", "object")}
                    code = generate_model_source_code_from_schema(schema_doc)
                    rel_py = _rel_for(action_key).with_suffix(".py")
                    target = out_root / rel_py
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(code, encoding="utf-8")
                    written.append(target)
                    continue
                except Exception:
                    continue

            # Copy only the target file for this action_key (plus its deps are already in out)
            # For import-linked, we need all transitive files, but they will be generated
            # when their own action_key iteration runs. So just copy the main file for now
            # and let other iterations populate the rest. To avoid overwriting, copy all
            # files generated in tmp_out for this iteration that correspond to transitive keys
            for p in tmp_out.rglob("*.py"):
                try:
                    rel_out = p.relative_to(tmp_out)
                except Exception:
                    continue
                # Only copy files that correspond to our transitive set or are __init__
                # To keep imports valid, we need all files, but we will generate them
                # in their own iterations anyway. So copy only the main file to avoid
                # duplication, but ensure the main file's imports will resolve.
                # For now copy the main file and any new deps that haven't been written yet.
                dest = out_root / rel_out
                if dest.exists():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
                written.append(dest)

    # Ensure __init__.py
    for dirpath in out_root.rglob("*"):
        if dirpath.is_dir():
            init = dirpath / "__init__.py"
            if not init.exists():
                init.write_text("", encoding="utf-8")
    root_init = out_root / "__init__.py"
    if not root_init.exists():
        root_init.write_text("", encoding="utf-8")

    written = sorted(set(written + list(out_root.rglob("*.py"))))
    return written


def _strip_ids_for_per_file(schema: dict[str, Any]) -> dict[str, Any]:
    import copy

    def strip(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("$id", None)
            node.pop("$schema", None)
            for v in node.values():
                strip(v)
        elif isinstance(node, list):
            for x in node:
                strip(x)

    c = copy.deepcopy(schema)
    strip(c)
    return c
