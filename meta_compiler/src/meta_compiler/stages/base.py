"""Abstract base stage contract for the MetaCompiler engine pipeline."""

import logging
from abc import ABC, abstractmethod

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext

logger = logging.getLogger("meta_compiler.stages.base")


class BaseCompilerStage(ABC):
    """Abstract Base Class for all isolated compiler stages in the MetaCompiler pipeline."""

    @abstractmethod
    def run(self, context: CompilationContext, registry: ActionRegistry) -> None:
        """Executes stage transformation or validation against the compilation context.

        Args:
            context: Shared compilation context carrying raw input, AST specs, and artifacts.
            registry: Central action registry for input/output schema and action resolution.

        Raises:
            MetaCompilerError: Subclasses raise domain-specific compiler exceptions on failure.
        """
        pass
