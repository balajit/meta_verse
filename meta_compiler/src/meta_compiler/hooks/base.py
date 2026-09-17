"""Abstract base class for compiler lifecycle middleware hooks."""

import logging
from abc import ABC

from meta_compiler.core.context import CompilationContext

logger = logging.getLogger("meta_compiler.hooks.base")


class BaseCompilerHook(ABC):
    """Abstract interface for injecting cross-cutting concerns into compilation lifecycles."""

    async def on_pre_compile(self, context: CompilationContext) -> None:
        """Executed prior to running stage pipeline validation."""
        pass

    async def on_post_compile(self, context: CompilationContext) -> None:
        """Executed immediately following successful stage pipeline execution."""
        pass

    async def on_persist(self, context: CompilationContext) -> None:
        """Executed immediately after database persistence succeeds."""
        pass

    async def on_error(self, context: CompilationContext, error: Exception) -> None:
        """Executed when an exception occurs during compilation or persistence."""
        pass
