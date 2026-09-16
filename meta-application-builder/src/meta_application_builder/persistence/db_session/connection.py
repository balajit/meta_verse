from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from meta_application_builder.foundation.security_context.identity import (
    IdentityContextManager,
    UnauthenticatedContextError,
)

logger = logging.getLogger("meta_application_builder.persistence.connection")


class DatabaseError(Exception):
    """Base exception for persistence layer operations."""
    pass


class DatabaseSessionError(DatabaseError):
    """Raised when database session creation or transaction initialization fails."""
    pass


class MultiTenantDatabaseManager:
    """
    Manages AsyncPG connection pools with strict session-level RLS variable isolation
    and reset guarantees to prevent cross-tenant connection pool pollution.
    """

    def __init__(self, database_url: str, echo: bool = False, pool_size: int = 20, max_overflow: int = 10) -> None:
        logger.info(
            "Initializing MultiTenantDatabaseManager with pool_size=%d, max_overflow=%d",
            pool_size,
            max_overflow,
        )
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def tenant_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Provides an AsyncSession scoped to the active tenant retrieved from IdentityContextManager.
        Executes SET LOCAL app.current_tenant = '<tenant_id>' within the transaction block and ensures
        all tenant-owned tables (build_jobs, audit_events, idempotency_keys, lineage_closure, sagas)
        are properly isolated under composite foreign keys and strict RLS enforcement.
        """
        try:
            tenant_id = IdentityContextManager.get_current_tenant_id()
        except UnauthenticatedContextError as e:
            logger.error("Attempted to open tenant database session without active security context: %s", str(e))
            raise DatabaseSessionError("Unauthenticated database access attempt.") from e

        logger.debug("Opening tenant-scoped database session for tenant_id='%s'", tenant_id)

        async with self._session_factory() as session:
            try:
                async with session.begin():
                    # Enforce transaction-scoped SET LOCAL app.current_tenant = :tenant_id
                    await session.execute(
                        text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
                        {"tenant_id": tenant_id},
                    )
                    # Also set app.tenant_id for compatibility with existing variable hooks
                    await session.execute(
                        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                        {"tenant_id": tenant_id},
                    )
                    logger.debug("Successfully configured session RLS parameters app.current_tenant and app.tenant_id to '%s'", tenant_id)
                    yield session
            except Exception as exc:
                logger.warning(
                    "Error encountered during tenant session execution; rolling back transaction. Tenant: %s. Error: %s",
                    tenant_id,
                    str(exc),
                )
                await session.rollback()
                raise
            finally:
                # Edge Case Mitigation: Reset RLS context state before returning connection to pool
                try:
                    await session.execute(text("SELECT set_config('app.current_tenant', '', false)"))
                    await session.execute(text("SELECT set_config('app.tenant_id', '', false)"))
                    logger.debug("Successfully cleared tenant session RLS context states.")
                except Exception as reset_exc:
                    logger.warning("Failed to clear session RLS context state: %s", str(reset_exc))

    async def close(self) -> None:
        """Gracefully closes engine pool connection."""
        logger.info("Closing database engine pool")
        await self._engine.dispose()