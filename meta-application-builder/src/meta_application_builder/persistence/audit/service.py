from __future__ import annotations

from typing import Any, Dict

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from meta_application_builder.persistence.db_session.connection import DatabaseError
from meta_application_builder.persistence.event_chain.crypt_chain import (
    EventCryptographicChain,
)
from meta_application_builder.persistence.models.audit import (
    BuildJobAuditModel,
    BuildJobEventModel,
)

# FIX: Swapped to structlog for observability context binding
logger = structlog.get_logger("meta_application_builder.persistence.audit_service")


class AuditLogConcurrencyError(DatabaseError):
    """Raised when concurrent writers break sequence ordering or conflict on hash generation."""
    pass


class AppendOnlyAuditService:
    """
    Manages thread-safe and race-condition-resistant writes to the tamper-evident audit log.
    Uses pessimistic locking on the job row and cryptographically chains events.
    """

    @classmethod
    async def append_event(
        cls,
        session: AsyncSession,
        tenant_id: str,
        job_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> BuildJobEventModel:
        """
        Appends an event to a build job's audit log while locking the root job row to prevent concurrent race conditions.
        """
        # Bind context to the logger for this specific execution trace
        log = logger.bind(tenant_id=tenant_id, job_id=job_id, event_type=event_type)
        log.debug("Attempting to append audit event")

        # Lock the parent audit row to serialize sequence generation under high concurrency
        stmt = (
            select(BuildJobAuditModel)
            .where(
                BuildJobAuditModel.tenant_id == tenant_id,
                BuildJobAuditModel.job_id == job_id,
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            log.error("Audit log write failed: Build job not found")
            raise DatabaseError(f"Build job {job_id} does not exist.")

        # Fetch the latest event sequence number and previous hash
        latest_event_stmt = (
            select(BuildJobEventModel)
            .where(BuildJobEventModel.job_id == job_id)
            .order_by(BuildJobEventModel.sequence_number.desc())
            .limit(1)
        )
        latest_result = await session.execute(latest_event_stmt)
        latest_event = latest_result.scalar_one_or_none()

        if latest_event:
            next_sequence = latest_event.sequence_number + 1
            previous_hash = latest_event.hash
        else:
            next_sequence = 1
            previous_hash = EventCryptographicChain.GENESIS_HASH

        # Compute next hash in chain
        current_hash = EventCryptographicChain.calculate_hash(
            previous_hash=previous_hash,
            sequence_number=next_sequence,
            payload=payload,
        )

        event_record = BuildJobEventModel(
            job_id=job_id,
            sequence_number=next_sequence,
            event_type=event_type,
            payload=payload,
            previous_hash=previous_hash,
            hash=current_hash,
        )

        try:
            session.add(event_record)
            await session.flush()
            log.info(
                "Successfully appended audit event",
                sequence_number=next_sequence,
                event_hash=current_hash[:8],
            )
            return event_record
        except IntegrityError as exc:
            log.error(
                "Race condition detected on sequence insertion",
                sequence_number=next_sequence,
                error=str(exc),
            )
            raise AuditLogConcurrencyError(
                f"Concurrent append detected on job {job_id} at sequence {next_sequence}."
            ) from exc