from __future__ import annotations

import logging
from typing import List, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meta_application_builder.persistence.db_session.connection import DatabaseError
from meta_application_builder.persistence.models.registry import DAGLineageClosureModel

logger = logging.getLogger("meta_application_builder.persistence.closure_manager")


class LineageClosureError(DatabaseError):
    """Raised when DAG transitive closure calculation or persistence fails."""
    pass


class LineageClosureManager:
    """
    Computes and queries transitive closure tables for blueprint dependency graphs.
    Reduces runtime lineage traversal from O(V+E) recursive CTE searches to O(1) indexed SQL selects.
    """

    @classmethod
    async def rebuild_closure_for_node(
        cls,
        session: AsyncSession,
        tenant_id: str,
        node_urn: str,
        direct_dependencies: Set[str],
    ) -> None:
        """
        Calculates and inserts all transitive paths (ancestors -> descendants) for a newly published specification.
        """
        logger.info("Rebuilding DAG closure table entries for tenant_id='%s', node_urn='%s'", tenant_id, node_urn)

        try:
            # Self-node depth 0 entry
            closure_entries = [
                DAGLineageClosureModel(
                    tenant_id=tenant_id,
                    ancestor_urn=node_urn,
                    descendant_urn=node_urn,
                    depth=0,
                )
            ]

            # Direct dependencies (depth 1)
            for dep_urn in direct_dependencies:
                closure_entries.append(
                    DAGLineageClosureModel(
                        tenant_id=tenant_id,
                        ancestor_urn=node_urn,
                        descendant_urn=dep_urn,
                        depth=1,
                    )
                )

                # Fetch inherited ancestors from dependency's precomputed closure table entries
                stmt = select(DAGLineageClosureModel).where(
                    DAGLineageClosureModel.tenant_id == tenant_id,
                    DAGLineageClosureModel.ancestor_urn == dep_urn,
                )
                result = await session.execute(stmt)
                inherited_entries = result.scalars().all()

                for inherited in inherited_entries:
                    if inherited.descendant_urn != dep_urn:
                        closure_entries.append(
                            DAGLineageClosureModel(
                                tenant_id=tenant_id,
                                ancestor_urn=node_urn,
                                descendant_urn=inherited.descendant_urn,
                                depth=inherited.depth + 1,
                            )
                        )

            session.add_all(closure_entries)
            await session.flush()
            logger.info("Successfully populated %d transitive closure paths for URN '%s'", len(closure_entries), node_urn)

        except Exception as exc:
            logger.error("Failed to update DAG transitive closure for URN '%s': %s", node_urn, str(exc))
            raise LineageClosureError(f"Transitive closure calculation failed for {node_urn}") from exc

    @classmethod
    async def get_all_descendants(cls, session: AsyncSession, tenant_id: str, ancestor_urn: str) -> List[str]:
        """
        Executes an O(1) indexed read to retrieve all downstream dependent components.
        """
        stmt = (
            select(DAGLineageClosureModel.descendant_urn)
            .where(
                DAGLineageClosureModel.tenant_id == tenant_id,
                DAGLineageClosureModel.ancestor_urn == ancestor_urn,
                DAGLineageClosureModel.depth > 0,
            )
            .order_by(DAGLineageClosureModel.depth)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())