from __future__ import annotations

from enum import Enum

import structlog

logger = structlog.get_logger(__name__)

class BuildState(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    ACQUIRED = "ACQUIRED"
    VALIDATING_SYNTAX = "VALIDATING_SYNTAX"
    VALIDATING_POLICY = "VALIDATING_POLICY"
    COMPILING_IR = "COMPILING_IR"
    SYNTHESIZING_CODE = "SYNTHESIZING_CODE"
    VERIFYING_AST = "VERIFYING_AST"
    PACKAGING = "PACKAGING"
    PERSISTING_CAS = "PERSISTING_CAS"
    PUBLISHING_BCR = "PUBLISHING_BCR"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class InvalidStateTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""
    pass

class BuildStateMachine:
    VALID_TRANSITIONS: dict[BuildState, set[BuildState]] = {
        BuildState.PENDING: {BuildState.QUEUED, BuildState.CANCELLED},
        BuildState.QUEUED: {BuildState.ACQUIRED, BuildState.CANCELLED},
        BuildState.ACQUIRED: {BuildState.VALIDATING_SYNTAX, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.VALIDATING_SYNTAX: {BuildState.VALIDATING_POLICY, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.VALIDATING_POLICY: {BuildState.COMPILING_IR, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.COMPILING_IR: {BuildState.SYNTHESIZING_CODE, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.SYNTHESIZING_CODE: {BuildState.VERIFYING_AST, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.VERIFYING_AST: {BuildState.PACKAGING, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.PACKAGING: {BuildState.PERSISTING_CAS, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.PERSISTING_CAS: {BuildState.PUBLISHING_BCR, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.PUBLISHING_BCR: {BuildState.COMPLETED, BuildState.FAILED, BuildState.CANCELLED},
        BuildState.COMPLETED: set(),
        BuildState.FAILED: {BuildState.PENDING},
        BuildState.CANCELLED: set()
    }

    @classmethod
    def transition(cls, current: BuildState, target: BuildState) -> BuildState:
        allowed = cls.VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            logger.error("invalid_state_transition", current=current, target=target)
            raise InvalidStateTransitionError(f"Cannot transition build lifecycle from {current} to {target}")
        logger.info("state_transition_success", from_state=current, to_state=target)
        return target