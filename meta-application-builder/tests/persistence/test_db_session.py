import pytest

from meta_application_builder.foundation.security_context.claims import SecurityClaims
from meta_application_builder.foundation.security_context.identity import (
    IdentityContextManager,
    UnauthenticatedContextError,
)
from meta_application_builder.persistence.db_session.connection import (
    DatabaseSessionError,
    MultiTenantDatabaseManager,
)


@pytest.mark.asyncio
async def test_tenant_session_unauthenticated_raises_error():
    # Attempting to initialize tenant session without setting IdentityContextManager
    db_manager = MultiTenantDatabaseManager("postgresql+asyncpg://user:pass@localhost:5432/db")

    with pytest.raises(DatabaseSessionError) as exc_info:
        async with db_manager.tenant_session():
            pass

    assert "Unauthenticated database access attempt" in str(exc_info.value)
    await db_manager.close()