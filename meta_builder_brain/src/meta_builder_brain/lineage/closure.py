"""LineageClosureResolver for calculating and resolving DAG component closures."""

from typing import Any, List, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession

from meta_builder_brain.persistence.mbb_mutator import DatabaseMutator
from meta_builder_brain.persistence.mbb_repository import EntityRepository


class LineageClosureResolver:
    """Resolves transitive ancestor and descendant relationships within component DAGs."""

    def __init__(
        self,
        repository: Any = None,
        mutator: Optional[DatabaseMutator] = None,
    ) -> None:
        if isinstance(repository, AsyncSession):
            self._session: Optional[AsyncSession] = repository
            self._repository: Optional[EntityRepository] = None
        else:
            self._session = None
            self._repository = repository

        self._mutator: Optional[DatabaseMutator] = mutator
        self._relations: Set[tuple[str, str, int]] = set()

    async def register_relation(
        self, ancestor_id: str, descendant_id: str, depth: int = 1
    ) -> None:
        """Registers a directional lineage relation between an ancestor and descendant."""
        self._relations.add((ancestor_id, descendant_id, depth))

    async def resolve_ancestors(self, descendant_id: str) -> List[str]:
        """Resolves all transitive ancestors for the specified descendant entity."""
        ancestors: Set[str] = set()
        queue = [descendant_id]
        visited = set()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            for anc, desc, _ in self._relations:
                if desc == current:
                    ancestors.add(anc)
                    queue.append(anc)

        if not ancestors and descendant_id:
            ancestors.add(descendant_id)

        return list(ancestors)