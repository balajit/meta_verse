"""Public API boundary for meta_compiler.

Hides internal stage pipelines, context mechanics, and storage details from host applications.
"""

from meta_compiler.config import CompilerSettings
from meta_compiler.core.context import CompilationContext
from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.models import CompiledExecutionGraph
from meta_compiler.engine import MetaCompiler
from meta_compiler.exceptions import MetaCompilerError
from meta_compiler.hooks.base import BaseCompilerHook

__all__ = [
    "MetaCompiler",
    "CompilerSettings",
    "CompilationContext",
    "ActionRegistry",
    "CompiledExecutionGraph",
    "MetaCompilerError",
    "BaseCompilerHook",
]
