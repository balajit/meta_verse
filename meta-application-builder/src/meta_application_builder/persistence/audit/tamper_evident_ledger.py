"""
Cryptographic Tamper-Evident Audit Ledger.
Enforces event_id uniqueness, canonical payload hashing, and SHA-256 hash chaining
across (tenant_id, job_id, event_id, event_type, actor, timestamp, sequence_number, prev_hash, payload_digest).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.getLogger("meta_application_builder.audit.tamper_evident_ledger")

GENESIS_PREV_HASH = "0" * 64


class AuditLedgerError(Exception):
    """Base exception for tamper-evident audit ledger failures."""
    pass


class DuplicateAuditEventError(AuditLedgerError):
    """Raised when an event_id already exists in the audit ledger (idempotency violation)."""
    pass


class HashChainIntegrityError(AuditLedgerError):
    """Raised when the hash chain validation fails due to tampering or sequence mismatch."""
    pass


class AuditEventRecord(BaseModel):
    """Pydantic representation of a tamper-evident audit log record."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(..., description="Tenant namespace identifier")
    job_id: Optional[str] = Field(default=None, description="Associated compilation or build job ID")
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique event ID enforcing idempotency")
    event_type: str = Field(..., min_length=1, max_length=128)
    actor: str = Field(..., description="Principal or service context performing action")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence_number: int = Field(..., ge=1, description="Strictly increasing sequence number per tenant ledger")
    prev_hash: str = Field(..., min_length=64, max_length=64, description="SHA-256 hash of preceding record")
    payload_digest: str = Field(..., min_length=64, max_length=64, description="SHA-256 digest of payload")
    hash: str = Field(..., min_length=64, max_length=64, description="Computed cryptographic hash of this record")
    payload: Dict[str, Any] = Field(default_factory=dict)


class TamperEvidentLedger:
    """Manages append-only, cryptographically verifiable audit records."""

    @staticmethod
    def compute_payload_digest(payload: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 hash of JSON-serialized payload."""
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_event_hash(
        tenant_id: str,
        job_id: Optional[str],
        event_id: uuid.UUID | str,
        event_type: str,
        actor: str,
        timestamp: datetime,
        sequence_number: int,
        prev_hash: str,
        payload_digest: str,
    ) -> str:
        """
        Computes canonical SHA-256 hash over the 9-tuple:
        (tenant_id, job_id, event_id, event_type, actor, timestamp, sequence_number, prev_hash, payload_digest)
        """
        iso_timestamp = timestamp.astimezone(timezone.utc).isoformat()
        canonical_str = (
            f"tenant_id={tenant_id}|"
            f"job_id={job_id or ''}|"
            f"event_id={str(event_id)}|"
            f"event_type={event_type}|"
            f"actor={actor}|"
            f"timestamp={iso_timestamp}|"
            f"sequence_number={sequence_number}|"
            f"prev_hash={prev_hash}|"
            f"payload_digest={payload_digest}"
        )
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    async def append_event(
        self,
        session: AsyncSession,
        tenant_id: str,
        event_type: str,
        actor: str,
        payload: Dict[str, Any],
        job_id: Optional[str] = None,
        event_id: Optional[uuid.UUID] = None,
    ) -> AuditEventRecord:
        """
        Appends a new audit record to the ledger within active RLS-protected database session.
        Enforces idempotency on event_id, calculates canonical payload digest, fetches latest hash,
        and constructs tamper-evident chain link.
        """
        target_event_id = event_id or uuid.uuid4()

        # 1. Idempotency Check
        check_existing_sql = text("""
            SELECT event_id FROM audit_events WHERE tenant_id = :tenant_id AND event_id = :event_id
        """)
        res = await session.execute(check_existing_sql, {"tenant_id": tenant_id, "event_id": target_event_id})
        if res.fetchone() is not None:
            raise DuplicateAuditEventError(
                f"Audit event with ID '{target_event_id}' already exists for tenant '{tenant_id}'."
            )

        # 2. Fetch latest sequence number and hash for tenant (pessimistic lock on tenant chain tail)
        latest_record_sql = text("""
            SELECT sequence_number, hash
            FROM audit_events
            WHERE tenant_id = :tenant_id
            ORDER BY sequence_number DESC
            LIMIT 1
            FOR UPDATE
        """)
        res_latest = await session.execute(latest_record_sql, {"tenant_id": tenant_id})
        last_row = res_latest.fetchone()

        if last_row:
            sequence_number = last_row.sequence_number + 1
            prev_hash = last_row.hash
        else:
            sequence_number = 1
            prev_hash = GENESIS_PREV_HASH

        # 3. Compute digests and block hash
        now = datetime.now(timezone.utc)
        payload_digest = self.compute_payload_digest(payload)
        computed_hash = self.compute_event_hash(
            tenant_id=tenant_id,
            job_id=job_id,
            event_id=target_event_id,
            event_type=event_type,
            actor=actor,
            timestamp=now,
            sequence_number=sequence_number,
            prev_hash=prev_hash,
            payload_digest=payload_digest,
        )

        record = AuditEventRecord(
            tenant_id=tenant_id,
            job_id=job_id,
            event_id=target_event_id,
            event_type=event_type,
            actor=actor,
            timestamp=now,
            sequence_number=sequence_number,
            prev_hash=prev_hash,
            payload_digest=payload_digest,
            hash=computed_hash,
            payload=payload,
        )

        # 4. Insert into PostgreSQL with unique constraint on (tenant_id, event_id)
        insert_sql = text("""
            INSERT INTO audit_events (
                tenant_id, job_id, event_id, event_type, actor, timestamp,
                sequence_number, prev_hash, payload_digest, hash, payload
            ) VALUES (
                :tenant_id, :job_id, :event_id, :event_type, :actor, :timestamp,
                :sequence_number, :prev_hash, :payload_digest, :hash, :payload
            )
        """)
        await session.execute(
            insert_sql,
            {
                "tenant_id": record.tenant_id,
                "job_id": record.job_id,
                "event_id": record.event_id,
                "event_type": record.event_type,
                "actor": record.actor,
                "timestamp": record.timestamp,
                "sequence_number": record.sequence_number,
                "prev_hash": record.prev_hash,
                "payload_digest": record.payload_digest,
                "hash": record.hash,
                "payload": json.dumps(record.payload),
            },
        )

        logger.info(
            "audit_event_appended",
            tenant_id=tenant_id,
            event_id=str(target_event_id),
            sequence_number=sequence_number,
            hash=computed_hash,
        )
        return record