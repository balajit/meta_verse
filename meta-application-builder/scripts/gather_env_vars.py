import ast
import sys
from pathlib import Path
from typing import Dict, Set

# Fallback for Python versions older than 3.11
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# Resolves meta_v root relative to script execution directory
META_V_ROOT = Path(__file__).resolve().parents[2]


class EnvVisitor(ast.NodeVisitor):

    def __init__(self):
        self.found_vars: Dict[str, str] = {}

    def _is_base_settings(self, node: ast.ClassDef) -> bool:
        """Strictly match classes inheriting directly from BaseSettings."""
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseSettings":
                return True
            if isinstance(base, ast.Attribute) and base.attr == "BaseSettings":
                return True
        return False

    def _extract_env_prefix(self, node: ast.ClassDef) -> str:
        env_prefix = ""
        for item in node.body:
            # Pydantic v1: class Config: env_prefix = "..."
            if isinstance(item, ast.ClassDef) and item.name == "Config":
                for cfg_item in item.body:
                    if isinstance(cfg_item, ast.Assign):
                        for target in cfg_item.targets:
                            if (
                                isinstance(target, ast.Name)
                                and target.id == "env_prefix"
                            ):
                                if isinstance(
                                    cfg_item.value, ast.Constant
                                ) and isinstance(cfg_item.value.value, str):
                                    env_prefix = cfg_item.value.value

            # Pydantic v2: model_config = SettingsConfigDict(env_prefix="...") or {"env_prefix": "..."}
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "model_config"
                    ):
                        val = item.value
                        if isinstance(val, ast.Call):
                            for kw in val.keywords:
                                if kw.arg == "env_prefix" and isinstance(
                                    kw.value, ast.Constant
                                ) and isinstance(kw.value.value, str):
                                    env_prefix = kw.value.value
                        elif isinstance(val, ast.Dict):
                            for k, v in zip(val.keys, val.values):
                                if (
                                    isinstance(k, ast.Constant)
                                    and k.value == "env_prefix"
                                    and isinstance(v, ast.Constant)
                                    and isinstance(v.value, str)
                                ):
                                    env_prefix = v.value
        return env_prefix

    def _clean_default(self, node_val: ast.AST) -> str:
        """Unwrap Field(default=...) and SecretStr(...) default values."""
        if isinstance(node_val, ast.Constant):
            return str(node_val.value) if node_val.value is not None else ""

        if isinstance(node_val, ast.Call):
            func_name = ast.unparse(node_val.func)
            if "Field" in func_name:
                for kw in node_val.keywords:
                    if kw.arg in ("default", "default_factory"):
                        return self._clean_default(kw.value)
            if node_val.args:
                return self._clean_default(node_val.args[0])

        return ast.unparse(node_val)

    def visit_ClassDef(self, node: ast.ClassDef):
        if self._is_base_settings(node):
            prefix = self._extract_env_prefix(node)
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(
                    stmt.target, ast.Name
                ):
                    raw_name = stmt.target.id
                    if raw_name in ("model_config", "Config"):
                        continue

                    var_name = f"{prefix}{raw_name}".upper()
                    default = ""
                    if stmt.value:
                        default = self._clean_default(stmt.value)
                    self.found_vars[var_name] = default
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Strictly match os.getenv(...) or os.environ.get(...) calls only."""
        is_os_getenv = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "getenv"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        )
        is_os_environ_get = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "environ"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "os"
        )

        if is_os_getenv or is_os_environ_get:
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                var_name = node.args[0].value.upper()
                default = ""
                if len(node.args) > 1 and isinstance(
                    node.args[1], ast.Constant
                ):
                    default = str(node.args[1].value)
                self.found_vars[var_name] = default

        self.generic_visit(node)


def uses_pydantic_settings(pyproject_path: Path) -> bool:
    """Parses pyproject.toml to verify if pydantic-settings is configured in dependencies."""
    if not pyproject_path.exists() or tomllib is None:
        return True

    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        deps = str(data.get("project", {}).get("dependencies", []))
        opt_deps = str(data.get("project", {}).get("optional-dependencies", {}))
        tool_poetry = str(
            data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        )

        combined_deps = f"{deps} {opt_deps} {tool_poetry}".lower()
        return "pydantic-settings" in combined_deps or "pydantic_settings" in combined_deps
    except Exception:
        return True


def scan_meta_repositories() -> Dict[str, Dict[str, str]]:
    repo_env_map: Dict[str, Dict[str, str]] = {}

    meta_dirs = [
        d
        for d in META_V_ROOT.iterdir()
        if d.is_dir() and d.name.startswith("meta")
    ]

    for project_dir in meta_dirs:
        pyproject_file = project_dir / "pyproject.toml"

        # Check if project declares pydantic-settings in pyproject.toml
        if pyproject_file.exists() and not uses_pydantic_settings(pyproject_file):
            continue

        repo_vars: Dict[str, str] = {}
        for py_file in project_dir.rglob("*.py"):
            if any(
                p in py_file.parts
                for p in (
                    ".venv",
                    "venv",
                    "site-packages",
                    "build",
                    "dist",
                    "tests",
                )
            ):
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
                visitor = EnvVisitor()
                visitor.visit(tree)
                repo_vars.update(visitor.found_vars)
            except Exception:
                continue

        if repo_vars:
            repo_env_map[project_dir.name] = repo_vars

    return repo_env_map


def generate_env_example():
    repo_env_map = scan_meta_repositories()
    output_file = META_V_ROOT / ".env.example"

    lines = [
        "# Consolidated .env.example",
        f"# Auto-generated across meta repositories in {META_V_ROOT.name}\n",
    ]

    seen_keys: Set[str] = set()

    for repo_name, env_vars in sorted(repo_env_map.items()):
        lines.append("# --------------------------------------------------")
        lines.append(f"# {repo_name}")
        lines.append("# --------------------------------------------------")
        for var_name, default_val in sorted(env_vars.items()):
            if var_name not in seen_keys:
                seen_keys.add(var_name)
                lines.append(f"{var_name}={default_val}")
        lines.append("")

    output_file.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"Consolidated {len(seen_keys)} variable(s) from {len(repo_env_map)} module(s) into {output_file}"
    )


if __name__ == "__main__":
    generate_env_example()