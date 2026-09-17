"""Write-only DatabaseMutator managing state modifications, CAS, and transactions."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from meta_builder_brain.exceptions import IdempotencyConflictError, PersistenceError
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


class DatabaseMutator:
    """Write-only persistence layer handling mutation statements and transactional blocks."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool: asyncpg.Pool = pool

    async def upsert_specification(
        self, record: SpecificationRecord
    ) -> SpecificationRecord:
        """Upserts a specification manifest into the registry."""
        query = """
            INSERT INTO specifications_registry (
                urn, namespace, component_name, version, specification_manifest, checksum_sha256
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            ON CONFLICT (urn) DO UPDATE SET
                namespace = EXCLUDED.namespace,
                component_name = EXCLUDED.component_name,
                version = EXCLUDED.version,
                specification_manifest = EXCLUDED.specification_manifest,
                checksum_sha256 = EXCLUDED.checksum_sha256,
                updated_at = NOW()
            RETURNING created_at, updated_at;
        """
        try:
            manifest_json = json.dumps(record.specification_manifest)
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    record.urn,
                    record.namespace,
                    record.component_name,
                    record.version,
                    manifest_json,
                    record.checksum_sha256,
                )
                return SpecificationRecord(
                    urn=record.urn,
                    namespace=record.namespace,
                    component_name=record.component_name,
                    version=record.version,
                    specification_manifest=record.specification_manifest,
                    checksum_sha256=record.checksum_sha256,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        except Exception as err:
            logger.error("Failed upserting spec URN %s: %s", record.urn, str(err))
            raise PersistenceError(f"Failed writing specification record: {err}") from err

    async def record_build_audit(
        self,
        job_id: UUID,
        tenant_id: str,
        status: BuildJobStatus,
        manifest_urn: str,
        execution_graph: Dict[str, Any],
    ) -> BuildJobAuditRecord:
        """Creates an initial build job audit record."""
        query = """
            INSERT INTO build_job_audit (
                job_id, tenant_id, status, manifest_urn, execution_graph, started_at
            ) VALUES ($1, $2, $3::build_job_status_enum, $4, $5::jsonb, NOW())
            RETURNING started_at, created_at, updated_at;
        """
        try:
            graph_json = json.dumps(execution_graph)
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    job_id,
                    tenant_id,
                    status.value,
                    manifest_urn,
                    graph_json,
                )
                return BuildJobAuditRecord(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    status=status,
                    manifest_urn=manifest_urn,
                    execution_graph=execution_graph,
                    started_at=row["started_at"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        except Exception as err:
            logger.error("Failed recording build job audit for %s: %s", str(job_id), str(err))
            raise PersistenceError(f"Error creating build job audit: {err}") from err

    async def update_build_status(
        self,
        job_id: UUID,
        status: BuildJobStatus,
        error_message: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Updates status and completion state of an active build job."""
        query = """
            UPDATE build_job_audit
            SET status = $1::build_job_status_enum,
                error_message = $2,
                completed_at = $3,
                updated_at = NOW()
            WHERE job_id = $4;
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(query, status.value, error_message, completed_at, job_id)
        except Exception as err:
            logger.error("Failed updating build job status for %s: %s", str(job_id), str(err))
            raise PersistenceError(f"Error updating build job status: {err}") from err

    async def record_job_event(
        self, job_id: UUID, event_type: str, payload: Dict[str, Any]
    ) -> BuildJobEventRecord:
        """Appends a discrete progress or diagnostic event to a build job log."""
        query = """
            INSERT INTO build_job_events (
                event_id, job_id, event_type, payload
            ) VALUES (gen_random_uuid(), $1, $2, $3::jsonb)
            RETURNING event_id, created_at;
        """
        try:
            payload_json = json.dumps(payload)
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, job_id, event_type, payload_json)
                return BuildJobEventRecord(
                    event_id=row["event_id"],
                    job_id=job_id,
                    event_type=event_type,
                    payload=payload,
                    created_at=row["created_at"],
                )
        except Exception as err:
            logger.error("Failed logging job event for job %s: %s", str(job_id), str(err))
            raise PersistenceError(f"Error recording job event: {err}") from err

    async def save_artifact_manifest(
        self,
        artifact_id: UUID,
        job_id: UUID,
        urn: str,
        artifact_type: str,
        location_uri: str,
        checksum_sha256: str,
    ) -> ArtifactManifestRecord:
        """Persists metadata manifest for a generated build artifact."""
        query = """
            INSERT INTO artifact_manifests (
                artifact_id, job_id, urn, artifact_type, location_uri, checksum_sha256
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING created_at;
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    artifact_id,
                    job_id,
                    urn,
                    artifact_type,
                    location_uri,
                    checksum_sha256,
                )
                return ArtifactManifestRecord(
                    artifact_id=artifact_id,
                    job_id=job_id,
                    urn=urn,
                    artifact_type=artifact_type,
                    location_uri=location_uri,
                    checksum_sha256=checksum_sha256,
                    created_at=row["created_at"],
                )
        except Exception as err:
            logger.error("Failed saving artifact manifest %s: %s", str(artifact_id), str(err))
            raise PersistenceError(f"Error persisting artifact manifest: {err}") from err

    async def batch_insert_lineage_closures_and_swap_generation(
        self, generation_id: int, closures: List[LineageClosureRecord]
    ) -> None:
        """Atomically inserts batch closure paths and toggles current active generation ID."""
        deactivate_query = """
            UPDATE dag_lineage_closure
            SET is_active = FALSE
            WHERE is_active = TRUE AND generation_id != $1;
        """
        insert_query = """
            INSERT INTO dag_lineage_closure (
                ancestor_urn, descendant_urn, path_length, generation_id, is_active
            ) VALUES ($1, $2, $3, $4, TRUE)
            ON CONFLICT (ancestor_urn, descendant_urn, generation_id) DO UPDATE SET
                path_length = EXCLUDED.path_length,
                is_active = TRUE;
        """
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(deactivate_query, generation_id)
                    if closures:
                        records = [
                            (
                                c.ancestor_urn,
                                c.descendant_urn,
                                c.path_length,
                                generation_id,
                            )
                            for c in closures
                        ]
                        await conn.executemany(insert_query, records)
            logger.info(
                "Swapped DAG active lineage generation to ID %d with %d closure paths.",
                generation_id,
                len(closures),
            )
        except Exception as err:
            logger.error("Atomic generation swap failed for ID %d: %s", generation_id, str(err))
            raise PersistenceError(f"Error executing lineage generation swap: {err}") from err

    async def create_idempotency_key(
        self, key: str, expires_at: datetime
    ) -> bool:
        """Atomic Compare-And-Set key creation for idempotent execution guard."""
        query = """
            INSERT INTO idempotency_records (
                idempotency_key, status, expires_at
            ) VALUES ($1, 'IN_PROGRESS'::idempotency_status_enum, $2)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING idempotency_key;
        """
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, key, expires_at)
                return row is not None
        except Exception as err:
            logger.error("Failed creating idempotency key %s: %s", key, str(err))
            raise PersistenceError(f"Error acquiring idempotency key: {err}") from err

    async def complete_idempotency_key(
        self, key: str, payload: Dict[str, Any]
    ) -> None:
        """Marks an active idempotency token as completed with its response payload."""
        query = """
            UPDATE idempotency_records
            SET status = 'COMPLETED'::idempotency_status_enum,
                response_payload = $1::jsonb,
                updated_at = NOW()
            WHERE idempotency_key = $2;
        """
        try:
            payload_json = json.dumps(payload)
            async with self._pool.acquire() as conn:
                await conn.execute(query, payload_json, key)
        except Exception as err:
            logger.error("Failed completing idempotency key %s: %s", key, str(err))
            raise PersistenceError(f"Error updating idempotency key: {err}") from err

    async def cleanup_expired_idempotency_keys(self) -> int:
        """Deletes expired idempotency tokens from the database."""
        query = """
            DELETE FROM idempotency_records
            WHERE expires_at < NOW();
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(query)
                count = int(result.split(" ")[1]) if result else 0
                return count
        except Exception as err:
            logger.error("Failed cleaning up expired idempotency keys: %s", str(err))
            raise PersistenceError(f"Error purging expired idempotency keys: {err}") from err