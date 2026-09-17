"""Database connection pool management and schema bootstrapping."""

import asyncio
import logging
from typing import Optional

import aiofiles
import asyncpg  # type: ignore[import-untyped]
from alembic import command
from alembic.config import Config

from meta_builder_brain.exceptions import DatabaseConnectionError, PersistenceError

logger = logging.getLogger(__name__)


class DatabasePoolManager:
    """Manages the asyncpg connection pool lifecycle and schema DDL initialization."""

    def __init__(
        self,
        dsn: str,
        min_size: int = 5,
        max_size: int = 20,
        command_timeout: float = 60.0,
    ) -> None:
        self._dsn: str = dsn
        self._min_size: int = min_size
        self._max_size: int = max_size
        self._command_timeout: float = command_timeout
        self._pool: Optional[asyncpg.Pool] = None

    async def init_pool(self) -> None:
        """Initializes the underlying asyncpg connection pool."""
        if self._pool is not None:
            logger.warning("DatabasePoolManager pool is already initialized.")
            return

        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=self._min_size,
                max_size=self._max_size,
                command_timeout=self._command_timeout,
            )
            logger.info("Successfully initialized asyncpg database connection pool.")
        except Exception as err:
            logger.error("Failed to initialize database connection pool: %s", str(err))
            raise DatabaseConnectionError(
                f"Could not connect to database pool: {err}"
            ) from err

    async def close_pool(self) -> None:
        """Gracefully terminates all active connections in the pool."""
        if self._pool is None:
            logger.warning("DatabasePoolManager pool is not active or already closed.")
            return

        try:
            await self._pool.close()
            self._pool = None
            logger.info("Asyncpg connection pool closed successfully.")
        except Exception as err:
            logger.error("Error closing connection pool: %s", str(err))
            raise DatabaseConnectionError(
                f"Error closing connection pool: {err}"
            ) from err

    def get_pool(self) -> asyncpg.Pool:
        """Retrieves the active asyncpg connection pool instance."""
        if self._pool is None:
            raise DatabaseConnectionError(
                "Database pool has not been initialized. Call init_pool() first."
            )
        return self._pool

    async def execute_ddl(self, schema_file_path: str) -> None:
        """Executes raw DDL statements from an external SQL file to bootstrap schema."""
        pool = self.get_pool()
        try:
            async with aiofiles.open(schema_file_path, mode="r") as sql_file:
                sql_content = await sql_file.read()

            async with pool.acquire() as conn:
                await conn.execute(sql_content)
            logger.info(
                "Schema DDL executed successfully from path: %s", schema_file_path
            )
        except FileNotFoundError as err:
            logger.error("Schema SQL file not found at path: %s", schema_file_path)
            raise PersistenceError(
                f"DDL schema file not found: {schema_file_path}"
            ) from err
        except Exception as err:
            logger.error("Failed executing schema DDL: %s", str(err))
            raise PersistenceError(f"Failed executing schema DDL: {err}") from err

    async def execute_migrations(self, alembic_ini_path: str) -> None:
        """Programmatically runs Alembic database migrations to upgrade head."""

        def _run_alembic_upgrade() -> None:
            alembic_cfg = Config(alembic_ini_path)
            command.upgrade(alembic_cfg, "head")

        try:
            await asyncio.to_thread(_run_alembic_upgrade)
            logger.info(
                "Alembic migrations executed successfully using config: %s",
                alembic_ini_path,
            )
        except Exception as err:
            logger.error("Failed executing Alembic migrations: %s", str(err))
            raise PersistenceError(
                f"Failed executing Alembic migrations: {err}"
            ) from err