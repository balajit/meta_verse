"""Unified Pytest fixtures for meta_builder_brain unit and integration tests."""

from typing import AsyncGenerator, Dict, List
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from meta_builder_brain.config import BrainSettings
from meta_builder_brain.persistence.mbb_mutator import DatabaseMutator
from meta_builder_brain.persistence.mbb_repository import EntityRepository
from meta_builder_brain.persistence.models import Base

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def mock_settings() -> BrainSettings:
    """Provides test application settings instance."""
    return BrainSettings(
        DATABASE_DSN="postgresql://postgres:postgres@localhost:5432/test_meta_builder_brain",
        OPA_SIDECAR_URL="http://localhost:8181/v1/data",
        BCR_URN_PREFIX="urn:meta:bcr:",
        ENVIRONMENT="testing",
        LOG_LEVEL="DEBUG",
    )


@pytest_asyncio.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated, in-memory SQLAlchemy AsyncSession per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def mock_pg_connection() -> AsyncMock:
    """Mocks an individual asyncpg connection object with context managers and query methods."""
    conn = AsyncMock(spec=asyncpg.Connection)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.executemany = AsyncMock(return_value=None)

    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=transaction_mock)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_mock)

    return conn


@pytest.fixture
def mock_pg_pool(mock_pg_connection: AsyncMock) -> AsyncMock:
    """Mocks an asyncpg.Pool handling pool.acquire() context management."""
    pool = AsyncMock(spec=asyncpg.Pool)

    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=mock_pg_connection)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)

    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool


@pytest.fixture
def entity_repository(mock_pg_pool: AsyncMock) -> EntityRepository:
    """Provides an EntityRepository instance backed by the mocked asyncpg connection pool."""
    return EntityRepository(pool=mock_pg_pool)


@pytest.fixture
def database_mutator(mock_pg_pool: AsyncMock) -> DatabaseMutator:
    """Provides a DatabaseMutator instance backed by the mocked asyncpg connection pool."""
    return DatabaseMutator(pool=mock_pg_pool)


@pytest.fixture
def sample_urns() -> Dict[str, str]:
    """Provides standard sample component URN strings for test assertions."""
    return {
        "valid": "urn:meta:bcr:global:user_entity:v1.0",
        "valid_dep": "urn:meta:bcr:global:base_entity:v1.0",
        "invalid": "invalid:urn:format",
    }


@pytest.fixture
def sample_dag_components(sample_urns: Dict[str, str]) -> Dict[str, List[str]]:
    """Provides sample DAG dependency mappings for topology testing."""
    return {
        sample_urns["valid"]: [sample_urns["valid_dep"]],
        sample_urns["valid_dep"]: [],
    }