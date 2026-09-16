import argparse
import asyncio
import os
import traceback
from pathlib import Path
import sys
from typing import Optional
import json
import httpx

# Import the four core platform components
from meta_builder_brain import MetaBrainSynthesizer
from meta_compiler import MetaCompiler, CompiledArtifacts
from meta_polymorph import NamespaceResolver, TreeResolver
from meta_polymorph.core.types import ResolutionContext


class ControlPlaneClient:
    """HTTP client for dispatching compiled workflow blueprints to meta_control_plane."""

    def __init__(self, control_plane_url: str = "http://localhost:8000"):
        self.base_url = control_plane_url.rstrip("/")

    async def dispatch_dag(self, dag_manifest_path: Path) -> str:
        """Reads dag_blueprint.json and dispatches it to the control plane runtime API."""
        if not dag_manifest_path.exists():
            raise FileNotFoundError(f"DAG blueprint manifest not found at '{dag_manifest_path}'")

        payload = json.loads(dag_manifest_path.read_text(encoding="utf-8"))

        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.post("/api/v1/workflows/dispatch", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("execution_id") or data.get("run_id") or "dispatched"


class EnvironmentValidator:
    """Pre-flight validation engine for runtime dependencies, workspace access, and network services."""

    @staticmethod
    def normalize_namespace(namespace_input: str) -> str:
        """Normalizes inputs like 'telecom/att' or 'global' into canonical namespace paths."""
        clean_path = namespace_input.strip("/")
        if not clean_path or clean_path == "global":
            return "global"

        parts = clean_path.split("/")
        if parts[0] != "global":
            parts.insert(0, "global")
        return "/".join(parts)

    @classmethod
    def validate(cls, input_path: Path, output_dir: Path, execute_flag: bool, control_plane_url: str):
        errors = []

        # 1. API Credentials Check
        if not os.getenv("OPENAI_API_KEY") and not os.getenv("LLM_API_KEY"):
            errors.append("MISSING_ENV: 'OPENAI_API_KEY' or 'LLM_API_KEY' environment variable must be set.")

        # 2. Input File Verification
        if not input_path.exists():
            errors.append(f"INVALID_INPUT: Specification file '{input_path}' does not exist.")

        # 3. Output Directory Write Access Check
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            test_file = output_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
        except Exception as exc:
            errors.append(f"PERMISSION_ERROR: Cannot write to output directory '{output_dir}': {exc}")

        # 4. Control Plane Health Check (Only performed if --execute flag is active)
        if execute_flag:
            try:
                resp = httpx.get(f"{control_plane_url}/health", timeout=3.0)
                if resp.status_code != 200:
                    errors.append(
                        f"CONTROL_PLANE_UNHEALTHY: Server at {control_plane_url} returned status {resp.status_code}")
            except Exception:
                errors.append(
                    f"CONTROL_PLANE_UNREACHABLE: Failed to connect to meta_control_plane at '{control_plane_url}'. "
                    "Ensure the runtime service is running or remove the '--execute' flag."
                )

        if errors:
            print("\n❌ Pre-Flight Environment Validation Failed:\n", file=sys.stderr)
            for err in errors:
                print(f"  • {err}", file=sys.stderr)
            print("\nUse 'meta-builder --help' for usage details.\n", file=sys.stderr)
            sys.exit(1)


class MetaBuilderOrchestrator:
    """Orchestrates Frontend Synthesis -> Namespace Resolution -> Backend Compilation -> Runtime Execution."""

    def __init__(self, control_plane_url: Optional[str] = None,
                 tree_resolver: Optional[TreeResolver] = None,
                 ):
        self.synthesizer = MetaBrainSynthesizer()
        self.tree_resolver = tree_resolver or TreeResolver()
        self.resolver = NamespaceResolver(tree_resolver=self.tree_resolver)

        self.compiler = MetaCompiler()
        self.control_plane_client = ControlPlaneClient(
            control_plane_url=control_plane_url or "http://localhost:8000"
        )

    async def build(
            self,
            input_spec_path: Path,
            namespace_path: str,
            output_dir: Path,
            submit_to_runtime: bool = False,
    ):
        spec_text = input_spec_path.read_text(encoding="utf-8")
        spec_name = input_spec_path.stem

        # Phase 1: Frontend Synthesis (meta_brain)[cite: 7]
        print(f"🧠 [1/4] Synthesizing raw Meta-IR AST from '{input_spec_path.name}'...")
        raw_ir, generated_types_path = await self.synthesizer.synthesize_spec(
            spec_path=input_spec_path,
            spec_name=spec_name,
            output_dir=output_dir,
        )

        if generated_types_path:
            print(f"  └─ ✅ Generated Pydantic types compiled at: {generated_types_path}")

        # Phase 2: Middle-End Resolution (meta_polymorph)[cite: 7]
        print(f"🔗 [2/4] Resolving types against namespace hierarchy '{namespace_path}'...")

        # Build the context expected by NamespaceResolver
        # Split normalized path (e.g., "global/telecom/att") into domain and custom namespace
        # 1. Parse namespace path into domain and custom namespace
        parts = [p for p in namespace_path.split("/") if p != "global"]
        industry_domain = parts[0] if len(parts) > 0 else "global"
        custom_namespace = parts[1] if len(parts) > 1 else None

        # 2. Build ResolutionContext
        context = ResolutionContext.create(
            tenant_id="default_tenant",
            industry_domain=industry_domain,
            custom_namespace=custom_namespace,
        )

        # 3. Compute topological resolution path
        resolution_path = self.resolver.resolve_candidate_path(context)
        # 2. Attach resolution context directly to raw_ir
        if hasattr(raw_ir, "resolution_path"):
            raw_ir.resolution_path = resolution_path.path
        if hasattr(raw_ir, "effective_tier"):
            raw_ir.effective_tier = resolution_path.effective_tier

        # Phase 3: Backend Compilation (meta_compiler)
        print(f"⚙️ [3/4] Compiling dynamic Pydantic models, DB migrations, & DAG blueprints...")

        artifacts = self.compiler.compile(
            manifest_input= raw_ir,
            custom_types_module=generated_types_path,
        )

        written_files = artifacts.write_to_disk(target_dir=output_dir)

        print(f"✅ Generated {len(written_files)} source artifacts in '{output_dir.resolve()}'")

        # Phase 4: Optional Runtime Execution (meta_control_plane)[cite: 7]
        if submit_to_runtime:
            print(f"🛡️ [4/4] Submitting compiled task graph to meta_control_plane...")
            execution_id = await self.control_plane_client.dispatch_dag(
                dag_manifest_path=output_dir / "dag_blueprint.json"
            )
            print(f"🚀 Execution dispatched successfully. Workflow Run ID: {execution_id}")


def main():
    parser = argparse.ArgumentParser(
        prog="meta-builder",
        description="Unified CLI to synthesize, link, compile, and execute component and flow code[cite: 7].",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  meta-builder -i specs/order.md -n telecom/att
  meta-builder -i specs/order.md -n global -o ./dist
  meta-builder -i specs/order.md -n telecom/att --execute --control-plane-url http://10.0.0.1:8000
""",
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        type=Path,
        help="Path to input RFC or prompt specification file (.md, .txt)[cite: 7]",
    )
    parser.add_argument(
        "-n", "--namespace",
        required=True,
        type=str,
        help="Target namespace hierarchy (e.g. global, telecom/, telecom/att)[cite: 7]",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("./generated_service"),
        help="Directory where compiled code and artifacts will be written (default: ./generated_service)[cite: 7]",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Immediately submit compiled DAG manifest to meta_control_plane for execution[cite: 7]",
    )
    parser.add_argument(
        "--control-plane-url",
        type=str,
        default="http://localhost:8000",
        help="Base URL for the meta_control_plane server (default: http://localhost:8000)",
    )

    args = parser.parse_args()

    # 1. Normalize Namespace Format
    normalized_namespace = EnvironmentValidator.normalize_namespace(args.namespace)

    # 2. Execute Pre-Flight Checks
    EnvironmentValidator.validate(
        input_path=args.input,
        output_dir=args.output,
        execute_flag=args.execute,
        control_plane_url=args.control_plane_url,
    )

    # 3. Instantiate and Execute Pipeline
    orchestrator = MetaBuilderOrchestrator(control_plane_url=args.control_plane_url)

    try:
        asyncio.run(
            orchestrator.build(
                input_spec_path=args.input,
                namespace_path=normalized_namespace,
                output_dir=args.output,
                submit_to_runtime=args.execute,
            )
        )
    except Exception as exc:

        print(f"\n❌ Pipeline Build Error: {exc}", file=sys.stderr)

        print("===== EXCEPTION CAUGHT =====", file=sys.stderr)
        print("TYPE:", type(exc), file=sys.stderr)
        print("REPR:", repr(exc), file=sys.stderr)
        print("CAUSE:", repr(exc.__cause__), file=sys.stderr)
        print("CONTEXT:", repr(exc.__context__), file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("===== END EXCEPTION =====", file=sys.stderr)

        sys.exit(1)


if __name__ == "__main__":
    main()