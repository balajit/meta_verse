"""Namespace-driven JSON Schema bundler (stdlib resolver).

Resolves relative ``$ref`` across ``ucp/schemas`` files and collects
them into a flat ``$defs`` map keyed by pascal-cased namespace
(``shopping.types.buyer`` → ``ShoppingTypesBuyer``).  Pure stdlib:
``pathlib`` + ``json`` — no ``jsonschema`` / ``referencing`` extra.

``reuse_model=True`` in datamodel-code-generator then deduplicates the
single bundled class per namespace.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


def _pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^0-9A-Za-z]+", name) if part)


def _json_pointer(doc: Any, pointer: str) -> Any:
    """Resolve ``/$defs/foo/bar`` pointer (leading slash optional)."""
    if not pointer or pointer == "/":
        return doc
    parts = pointer.lstrip("/").split("/")
    cur = doc
    for raw in parts:
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            raise KeyError(f"pointer {pointer!r} missing segment {key!r}")
    return cur


class SchemaBundler:
    """Bundles a single action schema's external ``$ref`` into ``$defs``."""

    def __init__(
        self,
        schema_dir: Path,
        file_index: dict[str, Path],
        raw_schemas: dict[str, dict],
    ) -> None:
        self.schema_dir = schema_dir.resolve()
        self.file_index = file_index  # action_key -> Path
        # reverse index: resolved Path -> action_key
        self.path_to_key: dict[Path, str] = {p.resolve(): k for k, p in file_index.items()}
        self.raw_schemas = raw_schemas

    def bundle_for(self, action_key: str) -> dict:
        raw = self.raw_schemas.get(action_key)
        if raw is None:
            raise KeyError(f"unknown action_key {action_key!r}")
        base_path = self.file_index.get(action_key)
        if base_path is None:
            # fallback: synthesize path from key
            base_path = self.schema_dir / (action_key.replace(".", "/") + ".json")
        base_path = base_path.resolve()

        bundled_defs: dict[str, Any] = {}
        # memo: (target_path, fragment) -> def_name to reuse
        memo: dict[tuple[Path, str | None], str] = {}
        seen_stack: set[tuple[Path, str | None]] = set()

        # work on deep copy
        root = copy.deepcopy(raw)

        def resolve_target(ref_str: str, cur_base: Path) -> tuple[Path, str | None, Any, str]:
            """Return (target_path, fragment, target_doc, def_name)."""
            if "#" in ref_str:
                file_part, frag = ref_str.split("#", 1)
                fragment: str | None = frag or None
            else:
                file_part, fragment = ref_str, None

            if file_part in ("", "."):
                target_path = cur_base
            elif file_part:
                target_path = (cur_base.parent / file_part).resolve()
            else:
                target_path = cur_base

            # fragment normalization: "/$defs/foo" stays as is for pointer
            # def_name derived from namespace or fragment leaf
            if fragment:
                # prefer fragment leaf as name if it looks like a def identifier
                # e.g. "/$defs/response_cart_schema" -> response_cart_schema
                leaf = fragment.strip("/").split("/")[-1]
                # if leaf is a known def, use it; else use target file namespace + leaf
                if leaf and re.match(r"^[A-Za-z0-9_-]+$", leaf):
                    # try to use leaf pascal-cased, but namespace it if target file differs
                    target_key = self.path_to_key.get(target_path)
                    if target_key:
                        # include namespace prefix to avoid collisions: ShoppingCartResponseCartSchema
                        # but keep leaf for readability
                        base_name = _pascal_case(target_key)
                        def_name = (
                            base_name + _pascal_case(leaf)
                            if fragment.startswith("/$defs")
                            else _pascal_case(leaf)
                        )
                        # If fragment is exactly one def, prefer leaf-driven name with namespace prefix
                        # For simplicity use leaf pascal if unique, else namespaced
                    else:
                        def_name = _pascal_case(leaf)
                else:
                    def_name = _pascal_case(fragment)
            else:
                target_key = self.path_to_key.get(target_path)
                if target_key:
                    def_name = _pascal_case(target_key)
                else:
                    # fallback to stem
                    def_name = _pascal_case(target_path.stem)

            # ensure uniqueness if collision
            orig = def_name
            suffix = 1
            while def_name in bundled_defs and memo.get((target_path, fragment)) != def_name:
                suffix += 1
                def_name = f"{orig}{suffix}"

            # load target doc
            target_key = self.path_to_key.get(target_path)
            if target_key and target_key in self.raw_schemas:
                target_doc = self.raw_schemas[target_key]
            elif target_path.is_file():
                target_doc = json.loads(target_path.read_text(encoding="utf-8"))
            else:
                raise FileNotFoundError(
                    f"cannot resolve $ref {ref_str!r} from {cur_base} -> {target_path}"
                )

            if fragment:
                target_doc = _json_pointer(target_doc, fragment)
                # copy if dict to avoid mutating source
                if isinstance(target_doc, dict):
                    target_doc = copy.deepcopy(target_doc)

            return target_path, fragment, target_doc, def_name

        def deref(node: Any, cur_base: Path) -> Any:
            if isinstance(node, dict):
                if "$ref" in node:
                    ref_str = node["$ref"]
                    # siblings besides $ref (e.g. description) are preserved via allOf merge
                    siblings = {k: v for k, v in node.items() if k != "$ref"}
                    key = None
                    # Try to find target
                    # use memo to reuse def
                    # We need to resolve to get def_name; peek without recursion first
                    target_path: Path | None = None
                    fragment: str | None = None
                    def_name: str | None = None
                    # handle internal "#/$defs/..." that points inside current file's $defs
                    # we still bundle it as top-level $defs for reuse_model
                    try:
                        # quick parse to get memo key
                        if "#" in ref_str:
                            fp, frag = ref_str.split("#", 1)
                            frag = frag or None
                        else:
                            fp, frag = ref_str, None
                        if fp in ("", ".") or not fp:
                            tp = cur_base
                        elif fp:
                            tp = (cur_base.parent / fp).resolve()
                        else:
                            tp = cur_base
                        target_path, fragment = tp, frag
                        # check memo
                        memo_key = (target_path, fragment)
                        if memo_key in memo:
                            def_name = memo[memo_key]
                        else:
                            # resolve target to get def_name
                            _, _, _, dn = resolve_target(ref_str, cur_base)
                            def_name = dn
                            memo[memo_key] = def_name
                    except Exception:
                        # fallback: leave ref as is
                        return node

                    assert def_name is not None and target_path is not None
                    memo_key = (target_path, fragment)
                    if def_name not in bundled_defs:
                        if memo_key in seen_stack:
                            # circular — just return ref, do not expand
                            return {"$ref": f"#/$defs/{def_name}"}
                        seen_stack.add(memo_key)
                        try:
                            _, _, target_doc, _ = resolve_target(ref_str, cur_base)
                            # recursively deref target's own refs
                            dereferenced = deref(
                                copy.deepcopy(target_doc)
                                if isinstance(target_doc, dict)
                                else target_doc,
                                target_path,
                            )
                            bundled_defs[def_name] = dereferenced
                        finally:
                            seen_stack.remove(memo_key)
                    # build ref node, merging siblings via allOf if needed
                    ref_node: dict[str, Any] = {"$ref": f"#/$defs/{def_name}"}
                    if siblings:
                        # preserve siblings (description, etc.) by wrapping
                        return {"allOf": [ref_node, siblings]}
                    return ref_node

                # not a $ref dict — recurse into known container keys
                out: dict[str, Any] = {}
                for k, v in node.items():
                    if k in ("properties", "$defs", "definitions", "patternProperties"):
                        if isinstance(v, dict):
                            out[k] = {pk: deref(pv, cur_base) for pk, pv in v.items()}
                        else:
                            out[k] = deref(v, cur_base)
                    elif k in (
                        "items",
                        "contains",
                        "unevaluatedItems",
                        "unevaluatedProperties",
                        "propertyNames",
                        "additionalProperties",
                        "unevaluatedProperties",
                    ):
                        out[k] = deref(v, cur_base) if isinstance(v, dict) else v
                    elif k in ("allOf", "anyOf", "oneOf", "prefixItems"):
                        if isinstance(v, list):
                            out[k] = [deref(x, cur_base) if isinstance(x, dict) else x for x in v]
                        else:
                            out[k] = deref(v, cur_base)
                    else:
                        if isinstance(v, dict):
                            out[k] = deref(v, cur_base)
                        elif isinstance(v, list):
                            out[k] = [deref(x, cur_base) if isinstance(x, dict) else x for x in v]
                        else:
                            out[k] = v
                return out
            elif isinstance(node, list):
                return [deref(x, cur_base) if isinstance(x, dict) else x for x in node]
            return node

        result = deref(root, base_path)

        # Strip remote identifiers that trigger HTTP fetch in datamodel-code-generator.
        # Keep bundled schema self-contained.
        def _strip_ids(node: Any) -> Any:
            if isinstance(node, dict):
                node.pop("$id", None)
                node.pop("$schema", None)
                for v in node.values():
                    _strip_ids(v)
            elif isinstance(node, list):
                for x in node:
                    _strip_ids(x)
            return node

        _strip_ids(result)
        for def_name, def_schema in bundled_defs.items():
            _strip_ids(def_schema)
            # Force namespace-driven class name: override title so
            # use_title_as_name=True emits ShoppingTypesBuyer not Buyer
            if isinstance(def_schema, dict):
                def_schema["title"] = def_name

        if bundled_defs:
            existing = result.get("$defs", {})
            if not isinstance(existing, dict):
                existing = {}
            merged = {**bundled_defs, **existing}
            result["$defs"] = merged
        # also strip ids from merged defs already done
        result.pop("$id", None)
        result.pop("$schema", None)
        return result
