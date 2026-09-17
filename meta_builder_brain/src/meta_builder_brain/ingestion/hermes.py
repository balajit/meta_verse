"""RFC Synthesis agent for Meta Builder Brain."""

from __future__ import annotations

from typing import Any, Dict

from meta_telemetry.tracing import trace_span
from meta_builder_brain.exceptions import HermesSynthesisError


class HermesSynthesisAgent:
    """Agent for synthesizing canonical JSON schemas from raw RFC text specs."""

    @trace_span(name="hermes.synthesize_rfc_spec")
    async def synthesize_rfc_spec(self, raw_rfc_text: str) -> Dict[str, Any]:
        """Parses RFC text and builds a canonical JSON schema object."""
        if not raw_rfc_text or not raw_rfc_text.strip():
            raise HermesSynthesisError("Raw RFC text payload cannot be empty.")

        try:
            properties: Dict[str, Any] = {}
            schema_title = "Synthesized RFC Schema"

            lines = [line.strip() for line in raw_rfc_text.splitlines() if line.strip()]

            for line in lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()

                    if key.lower() == "title":
                        schema_title = val
                        properties["title"] = {
                            "type": "string",
                            "description": val,
                        }
                    else:
                        properties[key] = {
                            "type": "string",
                            "description": val,
                        }

            if not properties:
                raise HermesSynthesisError(
                    "Failed to extract valid key-value schema definitions from RFC text spec."
                )

            return {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "title": schema_title,
                "properties": properties,
            }
        except HermesSynthesisError:
            raise
        except Exception as exc:
            raise HermesSynthesisError(f"RFC synthesis processing failed: {exc}") from exc