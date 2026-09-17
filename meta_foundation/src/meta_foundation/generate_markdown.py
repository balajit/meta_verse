import ast
from pathlib import Path

# Directories and pattern names to ignore during file traversal
EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "build",
    "dist",
    "site-packages",
    ".pytest_cache",
    ".mypy_cache",
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".uv",
}


def should_exclude_path(file_path: Path, root_path: Path) -> bool:
    """Check if any parent directory or file in the relative path should be excluded."""
    rel_parts = file_path.relative_to(root_path).parts
    for part in rel_parts:
        # Exclude known environment/cache dirs or any hidden folder starting with '.'
        if part in EXCLUDE_DIR_NAMES or part.startswith(".") or part.endswith(".egg-info"):
            return True
        # Exclude private modules/folders starting with '_' (except __init__.py)
        if part.startswith("_") and part != "__init__.py":
            return True
    return False


def format_arg(arg: ast.arg, default: ast.expr | None = None) -> str:
    arg_str = arg.arg
    if arg.annotation:
        arg_str += f": {ast.unparse(arg.annotation)}"
    if default:
        arg_str += f" = {ast.unparse(default)}"
    return arg_str


def get_func_sig(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    is_async = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    args = []
    defaults_offset = len(node.args.args) - len(node.args.defaults)

    for i, arg in enumerate(node.args.args):
        default = None
        if i >= defaults_offset:
            default = node.args.defaults[i - defaults_offset]
        args.append(format_arg(arg, default))

    if node.args.vararg:
        args.append(f"*{format_arg(node.args.vararg)}")
    if node.args.kwarg:
        args.append(f"**{format_arg(node.args.kwarg)}")

    ret_type = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{is_async}def {node.name}({', '.join(args)}){ret_type}"


def get_module_all(tree: ast.Module) -> set[str] | None:
    """Extract __all__ exported names if defined in the module."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        return {
                            elt.value for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        }
    return None


def parse_python_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=str(file_path))
        except SyntaxError:
            return None

    public_exports = get_module_all(tree)
    classes = []
    functions = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if public_exports is not None and node.name not in public_exports:
                continue
            if public_exports is None and node.name.startswith("_"):
                continue

            doc = ast.get_docstring(node)
            bases = [ast.unparse(b) for b in node.bases]
            fields = []
            methods = []

            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if not item.target.id.startswith("_"):
                        type_str = ast.unparse(item.annotation)
                        default_str = f" = {ast.unparse(item.value)}" if item.value else ""
                        fields.append(f"{item.target.id}: {type_str}{default_str}")
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not item.name.startswith("_") or item.name == "__init__":
                        methods.append((get_func_sig(item), ast.get_docstring(item)))

            classes.append({
                "name": node.name,
                "bases": bases,
                "doc": doc,
                "fields": fields,
                "methods": methods
            })

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if public_exports is not None and node.name not in public_exports:
                continue
            if public_exports is None and node.name.startswith("_"):
                continue

            doc = ast.get_docstring(node)
            functions.append((get_func_sig(node), doc))

    return {"classes": classes, "functions": functions}


def generate_markdown(libraries: list[str], output_file: str = "meta_compiler_public_libraries_spec.md"):
    md = ["# Public Custom Libraries Specification Summary\n"]

    for lib in libraries:
        lib_path = Path(lib)
        if not lib_path.exists():
            print(f"Skipping {lib}: Path not found.")
            continue

        md.append(f"## Library: `{lib_path.name}`\n")

        if lib_path.is_dir():
            all_files = sorted(lib_path.glob("**/*.py"))
            py_files = [f for f in all_files if not should_exclude_path(f, lib_path)]
        else:
            py_files = [lib_path]

        for py_file in py_files:
            parsed = parse_python_file(py_file)
            if not parsed or (not parsed["classes"] and not parsed["functions"]):
                continue

            rel_path = py_file.relative_to(lib_path) if lib_path.is_dir() else py_file.name
            md.append(f"### File: `{rel_path}`\n")

            if parsed["classes"]:
                md.append("#### Classes & Models\n")
                for cls in parsed["classes"]:
                    base_str = f"({', '.join(cls['bases'])})" if cls["bases"] else ""
                    md.append(f"```python\nclass {cls['name']}{base_str}:\n```")
                    if cls["doc"]:
                        md.append(f"> {cls['doc'].strip()}\n")

                    if cls["fields"]:
                        md.append("**Fields / Attributes:**")
                        for field in cls["fields"]:
                            md.append(f"- `{field}`")
                        md.append("")

                    if cls["methods"]:
                        md.append("**Methods:**")
                        for sig, doc in cls["methods"]:
                            md.append(f"```python\n{sig}\n```")
                            if doc:
                                md.append(f"> {doc.strip()}\n")

            if parsed["functions"]:
                md.append("#### Top-Level Functions\n")
                for sig, doc in parsed["functions"]:
                    md.append(f"```python\n{sig}\n```")
                    if doc:
                        md.append(f"> {doc.strip()}\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"Public specification generated successfully: {output_file}")


# TARGET_LIBRARIES = [
# "../meta-telemetry",
# "../meta-config",
# "../meta_compiler",
# "../meta_polymorph",
# "../meta_builder_brain",
# "../blueprint-component-strategy"
if __name__ == "__main__":
    TARGET_LIBRARIES = [
        "../meta_compiler"

    ]
    generate_markdown(TARGET_LIBRARIES)