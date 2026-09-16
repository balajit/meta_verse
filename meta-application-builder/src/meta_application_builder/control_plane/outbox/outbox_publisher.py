from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class OutboxPublisherError(Exception):
    """Raised when outbox event dispatch fails against external brokers."""
    pass


class OutboxPublisher:
    def __init__(
        self,
        broker_client: Any,
        batch_size: int = 50,
        worker_id: str | None = None,
        lease_duration_seconds: int = 60,
        max_retries: int = 5,
        base_backoff_seconds: int = 2,
    ) -> None:
        self.broker_client = broker_client
        self.batch_size = batch_size
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.lease_duration_seconds = lease_duration_seconds
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds

    def _calculate_next_attempt(self, attempt_count: int) -> datetime:
        delay_seconds = self.base_backoff_seconds ** max(1, attempt_count)
        return datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

    async def dispatch_pending_events(self, session: AsyncSession) -> int:
        """
        Polls outbox events using non-blocking pessimistic locks (FOR UPDATE SKIP LOCKED),
        claims durable worker leases, dispatches to broker, and atomically updates status with
        exponential backoff scheduling on failure.
        """
        now = datetime.now(timezone.utc)
        logger.info("dispatching_outbox_batch_start", worker_id=self.worker_id, batch_size=self.batch_size)

        try:
            # 1. Non-blocking pessimistic lock fetch (FOR UPDATE SKIP LOCKED)
            query = text("""
                SELECT id, topic, payload, attempt_count
                FROM outbox_events
                WHERE status IN ('PENDING', 'FAILED_RETRY')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
                  AND (leased_until IS NULL OR leased_until <= :now)
                ORDER BY created_at ASC
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            """)

            result = await session.execute(query, {"now": now, "batch_size": self.batch_size})
            events = result.fetchall()

            if not events:
                logger.debug("no_pending_outbox_events", worker_id=self.worker_id)
                return 0

            event_ids = [evt.id for evt in events]
            leased_until = now + timedelta(seconds=self.lease_duration_seconds)

            # 2. Claim durable worker lease
            claim_query = text("""
                UPDATE outbox_events
                SET worker_id = :worker_id,
                    leased_until = :leased_until,
                    status = 'IN_FLIGHT'
                WHERE id = ANY(:event_ids)
            """)
            await session.execute(claim_query, {
                "worker_id": self.worker_id,
                "leased_until": leased_until,
                "event_ids": event_ids,
            })

            dispatched_count = 0

            # 3. Process events and update state atomically per message ACK
            for event in events:
                attempt_count = event.attempt_count + 1
                try:
                    await self.broker_client.publish(
                        topic=event.topic,
                        payload=event.payload
                    )

                    # Mark COMPLETED on broker ACK
                    ack_query = text("""
                        UPDATE outbox_events
                        SET status = 'COMPLETED',
                            processed_at = :now,
                            worker_id = NULL,
                            leased_until = NULL
                        WHERE id = :event_id
                    """)
                    await session.execute(ack_query, {"now": datetime.now(timezone.utc), "event_id": event.id})
                    dispatched_count += 1

                except Exception as pub_err:
                    logger.warning(
                        "outbox_event_publish_failed",
                        event_id=str(event.id),
                        attempt=attempt_count,
                        error=str(pub_err)
                    )
                    next_attempt = self._calculate_next_attempt(attempt_count)
                    new_status = 'DEAD_LETTER' if attempt_count >= self.max_retries else 'FAILED_RETRY'

                    fail_query = text("""
                        UPDATE outbox_events
                        SET status = :status,
                            attempt_count = :attempt_count,
                            next_attempt_at = :next_attempt,
                            last_error = :error_msg,
                            worker_id = NULL,
                            leased_until = NULL
                        WHERE id = :event_id
                    """)
                    await session.execute(fail_query, {
                        "status": new_status,
                        "attempt_count": attempt_count,
                        "next_attempt": next_attempt,
                        "error_msg": str(pub_err),
                        "event_id": event.id,
                    })

            logger.info("dispatching_outbox_batch_success", dispatched_count=dispatched_count)
            return dispatched_count

        except Exception as e:
            logger.error("outbox_dispatch_failed", worker_id=self.worker_id, error=str(e))
            raise OutboxPublisherError(f"Failed to dispatch outbox batch: {e}") from e