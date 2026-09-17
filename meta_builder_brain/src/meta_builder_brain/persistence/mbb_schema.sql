-- PostgreSQL DDL for meta_builder_brain persistence engine
BEGIN;

-- Custom ENUM types
CREATE TYPE build_job_status_enum AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'CANCELLED'
);

CREATE TYPE idempotency_status_enum AS ENUM (
    'IN_PROGRESS',
    'COMPLETED',
    'FAILED'
);

-- Schema Timestamp Updater Trigger Function
CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 1. Specifications Registry Table
CREATE TABLE IF NOT EXISTS specifications_registry (
    urn VARCHAR(512) PRIMARY KEY,
    namespace VARCHAR(128) NOT NULL,
    component_name VARCHAR(128) NOT NULL,
    version VARCHAR(64) NOT NULL,
    specification_manifest JSONB NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spec_registry_lookup
    ON specifications_registry (namespace, component_name, version);

CREATE INDEX IF NOT EXISTS idx_spec_registry_manifest_gin
    ON specifications_registry USING GIN (specification_manifest);

CREATE TRIGGER trg_specifications_registry_updated_at
    BEFORE UPDATE ON specifications_registry
    FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- 2. Build Job Audit Table
CREATE TABLE IF NOT EXISTS build_job_audit (
    job_id UUID PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    status build_job_status_enum NOT NULL DEFAULT 'PENDING',
    manifest_urn VARCHAR(512) NOT NULL REFERENCES specifications_registry(urn) ON DELETE CASCADE,
    execution_graph JSONB NOT NULL,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_build_job_tenant_status
    ON build_job_audit (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_build_job_created_at
    ON build_job_audit (created_at DESC);

CREATE TRIGGER trg_build_job_audit_updated_at
    BEFORE UPDATE ON build_job_audit
    FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- 3. Build Job Events Table
CREATE TABLE IF NOT EXISTS build_job_events (
    event_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES build_job_audit(job_id) ON DELETE CASCADE,
    event_type VARCHAR(128) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_build_job_events_job_id
    ON build_job_events (job_id, created_at ASC);

-- 4. Artifact Manifests Table
CREATE TABLE IF NOT EXISTS artifact_manifests (
    artifact_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES build_job_audit(job_id) ON DELETE CASCADE,
    urn VARCHAR(512) NOT NULL,
    artifact_type VARCHAR(128) NOT NULL,
    location_uri TEXT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artifact_manifests_job_id
    ON artifact_manifests (job_id);

CREATE INDEX IF NOT EXISTS idx_artifact_manifests_urn
    ON artifact_manifests (urn);

-- 5. DAG Lineage Closure Table
CREATE TABLE IF NOT EXISTS dag_lineage_closure (
    ancestor_urn VARCHAR(512) NOT NULL,
    descendant_urn VARCHAR(512) NOT NULL,
    path_length INT NOT NULL,
    generation_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ancestor_urn, descendant_urn, generation_id)
);

CREATE INDEX IF NOT EXISTS idx_dag_closure_ancestor_active
    ON dag_lineage_closure (ancestor_urn, is_active)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_dag_closure_descendant_active
    ON dag_lineage_closure (descendant_urn, is_active)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_dag_closure_generation
    ON dag_lineage_closure (generation_id);

-- 6. Idempotency Records Table
CREATE TABLE IF NOT EXISTS idempotency_records (
    idempotency_key VARCHAR(256) PRIMARY KEY,
    status idempotency_status_enum NOT NULL DEFAULT 'IN_PROGRESS',
    response_payload JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires_at
    ON idempotency_records (expires_at);

CREATE TRIGGER trg_idempotency_records_updated_at
    BEFORE UPDATE ON idempotency_records
    FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

COMMIT;