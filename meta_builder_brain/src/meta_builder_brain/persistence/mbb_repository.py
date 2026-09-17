"""Read-only EntityRepository encapsulating all SELECT and CTE query operations."""

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from meta_builder_brain.exceptions import EntityNotFoundError, PersistenceError
from meta_builder_brain.persistence.mbb_models import (
    ArtifactManifestRecord,
    BuildJobAuditRecord,
    BuildJobEventRecord,
    BuildJobStatus,
    IdempotencyRecord,
    IdempotencyStatus,
    LineageClosureRecord,
    SpecificationRecord,
)

logger = logging.getLogger(__name__)


class EntityRepository:
    """Read-only data access repository for hydrating domain entity records."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool: asyncpg.Pool = pool

    def _deserialize_json(self, raw_data: Any) -> Dict[str, Any]:
        """Safely deserializes raw JSON inputs ensuring concrete Dict[str, Any] return typing."""
        if isinstance(raw_data, str):
            parsed: Any = json.loads(raw_data)
            if isinstance(parsed, dict):
                return {str(k): v for k, v in parsed.items()}
            return {}
        elif isinstance(raw_data, dict):
            return {str(k): v for k, v in raw_data.items()}
        return {}

    async def get_specification(self, urn: str) -> Optional[SpecificationRecord]:
        """Fetches a single specification record by canonical URN."""
        query = """
            SELECT urn, namespace, component_name, version, specification_manifest, checksum_sha256, created_at, updated_at
            FROM specifications_registry
            WHERE urn = $1;
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, urn)
                if not row:
                    return None
                return SpecificationRecord(
                    urn=row["urn"],
                    namespace=row["namespace"],
                    component_name=row["component_name"],
                    version=row["version"],
                    specification_manifest=self._deserialize_json(
                        row["specification_manifest"]
                    ),
                    checksum_sha256=row["checksum_sha256"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        except Exception as err:
            logger.error("Failed fetching specification for URN %s: %s", urn, str(err))
            raise PersistenceError(f"Error reading specification URN {urn}: {err}") from err

    async def list_specifications(
        self, namespace: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[SpecificationRecord]:
        """Lists specification records with optional filtering by namespace."""
        query_with_ns = """
            SELECT urn, namespace, component_name, version, specification_manifest, checksum_sha256, created_at, updated_at
            FROM specifications_registry
            WHERE namespace = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3;
        """
        query_all = """
            SELECT urn, namespace, component_name, version, specification_manifest, checksum_sha256, created_at, updated_at
            FROM specifications_registry
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2;
        """
        try:
            async with self._pool.acquire() as conn:
                if namespace:
                    rows = await conn.fetch(query_with_ns, namespace, limit, offset)
                else:
                    rows = await conn.fetch(query_all, limit, offset)

                return [
                    SpecificationRecord(
                        urn=r["urn"],
                        namespace=r["namespace"],
                        component_name=r["component_name"],
                        version=r["version"],
                        specification_manifest=self._deserialize_json(
                            r["specification_manifest"]
                        ),
                        checksum_sha256=r["checksum_sha256"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                    )
                    for r in rows
                ]
        except Exception as err:
            logger.error("Failed listing specifications: %s", str(err))
            raise PersistenceError(f"Error listing specifications: {err}") from err

    async def get_build_job(self, job_id: UUID) -> Optional[BuildJobAuditRecord]:
        """Fetches a build job audit record by UUID."""
        query = """
            SELECT job_id, tenant_id, status, manifest_urn, execution_graph, error_message, started_at, completed_at, created_at, updated_at
            FROM build_job_audit
            WHERE job_id = $1;
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, job_id)
                if not row:
                    return None
                return BuildJobAuditRecord(
                    job_id=row["job_id"],
                    tenant_id=row["tenant_id"],
                    status=BuildJobStatus(row["status"]),
                    manifest_urn=row["manifest_urn"],
                    execution_graph=self._deserialize_json(row["execution_graph"]),
                    error_message=row["error_message"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        except Exception as err:
            logger.error("Failed fetching build job %s: %s", str(job_id), str(err))
            raise PersistenceError(f"Error reading build job {job_id}: {err}") from err

    async def get_build_job_events(self, job_id: UUID) -> List[BuildJobEventRecord]:
        """Fetches all events associated with a build job in chronological order."""
        query = """
            SELECT event_id, job_id, event_type, payload, created_at
            FROM build_job_events
            WHERE job_id = $1
            ORDER BY created_at ASC;
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, job_id)
                return [
                    BuildJobEventRecord(
                        event_id=r["event_id"],
                        job_id=r["job_id"],
                        event_type=r["event_type"],
                        payload=self._deserialize_json(r["payload"]),
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
        except Exception as err:
            logger.error("Failed fetching events for job %s: %s", str(job_id), str(err))
            raise PersistenceError(f"Error fetching job events {job_id}: {err}") from err

    async def get_artifact_manifests(self, job_id: UUID) -> List[ArtifactManifestRecord]:
        """Fetches generated artifact manifests for a given build job."""
        query = """
            SELECT artifact_id, job_id, urn, artifact_type, location_uri, checksum_sha256, created_at
            FROM artifact_manifests
            WHERE job_id = $1;
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, job_id)
                return [
                    ArtifactManifestRecord(
                        artifact_id=r["artifact_id"],
                        job_id=r["job_id"],
                        urn=r["urn"],
                        artifact_type=r["artifact_type"],
                        location_uri=r["location_uri"],
                        checksum_sha256=r["checksum_sha256"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
        except Exception as err:
            logger.error("Failed fetching artifacts for job %s: %s", str(job_id), str(err))
            raise PersistenceError(f"Error reading artifacts for job {job_id}: {err}") from err

    async def get_active_closure_descendants(
        self, ancestor_urn: str, generation_id: Optional[int] = None
    ) -> List[LineageClosureRecord]:
        """Executes closure lookup query for descendant components of a given ancestor URN."""
        query_gen = """
            SELECT ancestor_urn, descendant_urn, path_length, generation_id, is_active, created_at
            FROM dag_lineage_closure
            WHERE ancestor_urn = $1 AND generation_id = $2;
        """
        query_active = """
            SELECT ancestor_urn, descendant_urn, path_length, generation_id, is_active, created_at
            FROM dag_lineage_closure
            WHERE ancestor_urn = $1 AND is_active = TRUE;
        """
        try:
            async with self._pool.acquire() as conn:
                if generation_id is not None:
                    rows = await conn.fetch(query_gen, ancestor_urn, generation_id)
                else:
                    rows = await conn.fetch(query_active, ancestor_urn)

                return [
                    LineageClosureRecord(
                        ancestor_urn=r["ancestor_urn"],
                        descendant_urn=r["descendant_urn"],
                        path_length=r["path_length"],
                        generation_id=r["generation_id"],
                        is_active=r["is_active"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
        except Exception as err:
            logger.error("Failed fetching closure descendants for %s: %s", ancestor_urn, str(err))
            raise PersistenceError(f"Error reading lineage closure: {err}") from err

    async def get_idempotency_record(self, idempotency_key: str) -> Optional[IdempotencyRecord]:
        """Retrieves active idempotency record by key."""
        query = """
            SELECT idempotency_key, status, response_payload, created_at, updated_at, expires_at
            FROM idempotency_records
            WHERE idempotency_key = $1;
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, idempotency_key)
                if not row:
                    return None
                return IdempotencyRecord(
                    idempotency_key=row["idempotency_key"],
                    status=IdempotencyStatus(row["status"]),
                    response_payload=self._deserialize_json(row["response_payload"])
                    if row["response_payload"]
                    else None,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    expires_at=row["expires_at"],
                )
        except Exception as err:
            logger.error("Failed reading idempotency key %s: %s", idempotency_key, str(err))
            raise PersistenceError(f"Error fetching idempotency key: {err}") from err