import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from meta_application_builder.persistence.models.base import Base

# Ensure ORM models are registered for Alembic metadata discovery

logger = logging.getLogger("alembic.runtime.environment")
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    logger.info("Executing offline migration against URL: %s", url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        logger.info("Enforcing PostgreSQL Row Level Security (RLS) policies during migration.")
        connection.execute(
            text("""
            ALTER TABLE specifications_registry ENABLE ROW LEVEL SECURITY;
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_policy'
                ) THEN
                    CREATE POLICY tenant_isolation_policy ON specifications_registry
                        USING (tenant_id = current_setting('app.tenant_id', true));
                END IF;
            END $$;
            """)
        )
        context.run_migrations()


async def run_async_migrations() -> None:
    """In-process async engine initialization for migrations."""
    logger.info("Executing async online migration.")
    section_config = config.get_section(config.config_ini_section) or {}
    connectable = async_engine_from_config(
        section_config,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()