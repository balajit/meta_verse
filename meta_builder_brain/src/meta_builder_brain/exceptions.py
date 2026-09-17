"""Centralized exception hierarchy for Meta Builder Brain."""

from typing import Any, Optional


class MetaBuilderBrainError(Exception):
    """Base exception class for all domain-specific errors in Meta Builder Brain."""

    def __init__(self, message: str, payload: Optional[Any] = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload


# --- Configuration & Telemetry ---

class ConfigurationError(MetaBuilderBrainError):
    """Raised when application configuration bootstrapping or OpenBao secret loading fails."""
    pass


class TelemetryInitError(MetaBuilderBrainError):
    """Raised when telemetry or structured logging initialization fails."""
    pass


# --- DAG & Lineage ---

class DAGEngineError(MetaBuilderBrainError):
    """Base exception for Directed Acyclic Graph execution and topology failures."""
    pass


class DAGCycleError(DAGEngineError):
    """Raised when a cyclic dependency is detected within component graph topology."""
    pass


class DAGNodeNotFoundError(DAGEngineError):
    """Raised when a target component or URN node is missing from the DAG."""
    pass


class EmptyDAGError(DAGEngineError):
    """Raised when an operation is executed on a DAG containing no node components."""
    pass


class InvalidURNError(DAGEngineError):
    """Raised when a URN string does not match the expected URN specification format."""
    pass


class LineageResolutionError(MetaBuilderBrainError):
    """Raised when lineage closure or multi-tenant graph lookup fails."""
    pass


# --- Governance & Policy ---

class GovernancePolicyError(MetaBuilderBrainError):
    """Base exception for Open Policy Agent and governance validation failures."""
    pass


class GovernancePolicyViolationError(GovernancePolicyError):
    """Raised when an entity specification or FSM state transition violates policy rules."""
    pass


class OPAPolicyValidationError(GovernancePolicyViolationError):
    """Raised when OPA policy validation checks fail or deny execution."""
    pass


class OPAServiceUnavailableError(GovernancePolicyError):
    """Raised when the OPA sidecar HTTP engine times out, drops connection, or returns 5xx."""
    pass


# --- Persistence & Repository ---

class PersistenceError(MetaBuilderBrainError):
    """Base exception for database access and transaction failures."""
    pass


class DatabaseConnectionError(PersistenceError):
    """Raised when database connectivity drops or connection pooling fails."""
    pass


class EntityNotFoundError(PersistenceError):
    """Raised when a requested entity URN or primary key record does not exist."""
    pass


class DuplicateURNError(PersistenceError):
    """Raised when inserting an entity URN that violates unique primary key constraints."""
    pass


class TransactionRollbackError(PersistenceError):
    """Raised when an active database transaction fails and undergoes rollback."""
    pass


class UnsupportedTypeMappingError(PersistenceError):
    """Raised when an unknown or unsupported field type mapping is encountered during dynamic ORM/schema mapping."""
    pass


class CASLockError(PersistenceError):
    """Raised when optimistic concurrency fence token validation fails."""
    pass


class IdempotencyError(PersistenceError):
    """Raised when duplicate processing is detected on an active key."""
    pass


class IdempotencyConflictError(IdempotencyError):
    """Raised when a concurrent operation or key collision violates idempotency guarantees."""
    pass


class SagaError(PersistenceError):
    """Raised when saga transaction verification fails."""
    pass


class MigrationError(PersistenceError):
    """Raised when database migration execution fails."""
    pass


# --- Ingestion & Orchestration ---

class IngestionError(MetaBuilderBrainError):
    """Base exception for external document parsing and ingestion pipelines."""
    pass


class HermesSynthesisError(IngestionError):
    """Raised when RFC text parsing fails to synthesize valid schema representations."""
    pass


class BuildExecutionError(MetaBuilderBrainError):
    """Raised when build job orchestration or compiler execution encounters an unrecoverable failure."""
    pass