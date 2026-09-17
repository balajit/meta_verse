"""Workflow definition persistence repository.

Handles PostgreSQL database operations and table schemas for compiled workflow manifests.
"""

import logging
import time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from meta_compiler.exceptions import MetaCompilerError

logger = logging.getLogger("meta_compiler.persistence.repository")

metadata = MetaData()
meta_workflow_definitions = Table(
    "meta_workflow_definitions",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True, default=uuid4),
    Column("namespace", String(64), nullable=False, index=True),
    Column("name", String(64), nullable=False, index=True),
    Column("version", String(32), nullable=False),
    Column("description", Text, nullable=True),
    Column("compiled_manifest", JSONB, nullable=False),
    Column("execution_plan", JSONB, nullable=False),
    Column("pinned_dependencies", JSONB, nullable=True),
    Column("version_vector", JSONB, nullable=True),
    Column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    ),
)


class RepositoryError(MetaCompilerError):
    """Raised when database operations fail within the repository layer."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, details=details)


class WorkflowRepository:
    """Repository handling asynchronous persistence for compiled workflow definitions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, payload: dict[str, Any]) -> UUID:
        return await self.persist_workflow_definition(payload)

    async def persist_workflow_definition(self, payload: dict[str, Any]) -> UUID:
        """Stages an insert operation into the `meta_workflow_definitions` table."""
        start_time = time.perf_counter()
        definition_id: UUID = payload["id"]

        logger.info(
            "Staging workflow definition persistence for '%s/%s' (ID: %s)",
            payload["namespace"],
            payload["name"],
            definition_id,
            extra={
                "event": "repository.persist_start",
                "namespace": payload["namespace"],
                "name": payload["name"],
                "definition_id": str(definition_id),
            },
        )

        try:
            stmt = meta_workflow_definitions.insert().values(
                id=definition_id,
                namespace=payload["namespace"],
                name=payload["name"],
                version=payload["version"],
                description=payload.get("description"),
                compiled_manifest=payload["compiled_manifest"],
                execution_plan=payload["execution_plan"],
                pinned_dependencies=payload.get("pinned_dependencies"),
                version_vector=payload.get("version_vector"),
            )
            await self.session.execute(stmt)

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Successfully staged workflow definition insert for ID %s in %.2fms",
                definition_id,
                duration_ms,
                extra={
                    "event": "repository.persist_success",
                    "definition_id": str(definition_id),
                    "duration_ms": duration_ms,
                },
            )
            return definition_id

        except Exception as err:
            logger.error(
                "Database insert failed for definition ID %s: %s",
                definition_id,
                err,
                extra={
                    "event": "repository.persist_failure",
                    "definition_id": str(definition_id),
                    "error": str(err),
                },
            )
            raise RepositoryError(
                message=f"Failed to stage workflow definition in database: {err}",
                details={"definition_id": str(definition_id), "error": str(err)},
            ) from err
