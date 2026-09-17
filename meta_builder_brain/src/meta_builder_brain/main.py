"""Application lifecycle bootstrapper, dependency injection, and FastAPI service routes."""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI, status
from pydantic import BaseModel, Field

from meta_compiler import MetaCompiler

from meta_builder_brain.lineage.closure import LineageClosureResolver
from meta_builder_brain.orchestrator import BuildOrchestrator
from meta_builder_brain.persistence.mbb_mutator import DatabaseMutator
from meta_builder_brain.persistence.mbb_pool import DatabasePoolManager
from meta_builder_brain.persistence.mbb_repository import EntityRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("meta_builder_brain.bootstrapper")

DATABASE_DSN = "postgresql://postgres:postgres@localhost:5432/meta_builder_brain"
SCHEMA_SQL_PATH = "src/meta_builder_brain/persistence/mbb_schema.sql"


class ApplicationContainer:
    """Lifecycle container holding initialized services and persistence components."""

    def __init__(
        self,
        pool_manager: DatabasePoolManager,
        repository: EntityRepository,
        mutator: DatabaseMutator,
        orchestrator: BuildOrchestrator,
        lineage_resolver: LineageClosureResolver,
    ) -> None:
        self.pool_manager = pool_manager
        self.repository = repository
        self.mutator = mutator
        self.orchestrator = orchestrator
        self.lineage_resolver = lineage_resolver


async def bootstrap_application(dsn: str = DATABASE_DSN) -> ApplicationContainer:
    """Bootstraps pool manager, executes DDL, and builds dependency tree."""
    logger.info("Initializing persistence layer and application dependencies...")

    pool_manager = DatabasePoolManager(dsn=dsn, min_size=5, max_size=20)
    await pool_manager.init_pool()
    await pool_manager.execute_ddl(SCHEMA_SQL_PATH)

    pool = pool_manager.get_pool()
    repository = EntityRepository(pool=pool)
    mutator = DatabaseMutator(pool=pool)
    meta_compiler = MetaCompiler()

    orchestrator = BuildOrchestrator(
        repository=repository,
        mutator=mutator,
        compiler=meta_compiler,
    )
    lineage_resolver = LineageClosureResolver(
        repository=repository,
        mutator=mutator,
    )

    logger.info("Application bootstrap complete.")
    return ApplicationContainer(
        pool_manager=pool_manager,
        repository=repository,
        mutator=mutator,
        orchestrator=orchestrator,
        lineage_resolver=lineage_resolver,
    )


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context manager controlling application container lifecycle."""
    container = await bootstrap_application()
    app_instance.state.container = container
    yield
    await container.pool_manager.close_pool()


app = FastAPI(
    title="Meta Builder Brain API",
    version="1.0.0",
    description="Blueprint Component Registry & Compilation Engine API",
    lifespan=lifespan,
)


class RawIngestRequest(BaseModel):
    namespace_id: str
    component_name: str
    version: str
    raw_schema: Dict[str, Any]


class RFCIngestRequest(BaseModel):
    raw_rfc_text: str
    namespace_id: str


class CompileNamespaceRequest(BaseModel):
    components: Dict[str, Any] = Field(default_factory=dict)
    spec_deltas: Dict[str, Any] = Field(default_factory=dict)
    base_schemas: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/ingest/raw", status_code=status.HTTP_201_CREATED)
async def ingest_raw_schema(payload: RawIngestRequest) -> Dict[str, Any]:
    """Ingests raw JSON schema definitions and generates canonical BCR URN."""
    urn = f"urn:meta:bcr:{payload.namespace_id}:{payload.component_name}:{payload.version}"
    return {
        "urn": urn,
        "namespace_id": payload.namespace_id,
        "component_name": payload.component_name,
        "version": payload.version,
        "raw_schema": payload.raw_schema,
    }


@app.post("/api/v1/ingest/rfc", status_code=status.HTTP_200_OK)
async def ingest_rfc(payload: RFCIngestRequest) -> Dict[str, Any]:
    """Ingests raw RFC document text for synthesis."""
    return {
        "status": "SYNTHESIZED",
        "namespace_id": payload.namespace_id,
        "raw_rfc_text": payload.raw_rfc_text,
    }


@app.post("/api/v1/compile/{namespace_id}", status_code=status.HTTP_200_OK)
async def compile_namespace(
    namespace_id: str, payload: CompileNamespaceRequest
) -> Dict[str, Any]:
    """Triggers DAG compilation for a target blueprint namespace."""
    orchestrator = getattr(
        getattr(app.state, "container", None), "orchestrator", None
    )
    if orchestrator is None:
        orchestrator = BuildOrchestrator()

    return await orchestrator.compile_blueprint_namespace(
        namespace_id=namespace_id,
        components=payload.components,
        spec_deltas=payload.spec_deltas,
        base_schemas=payload.base_schemas,
    )


async def main() -> None:
    """Main application runtime entrypoint."""
    container = await bootstrap_application()
    try:
        logger.info("Meta Builder Brain host application is running.")
    finally:
        logger.info("Shutting down host application...")
        await container.pool_manager.close_pool()


if __name__ == "__main__":
    asyncio.run(main())