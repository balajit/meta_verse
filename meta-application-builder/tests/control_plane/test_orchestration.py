import pytest
from orchestration.recovery.retry_jitter import RetryJitter
from orchestration.state_engine.dual_lock_fencing import (
    DualLockFencing,
    StaleWorkerError,
    WorkerFenceToken,
)
from orchestration.state_engine.state_machine import (
    BuildState,
    BuildStateMachine,
    InvalidStateTransitionError,
)


def test_dual_lock_fencing_valid():
    current = WorkerFenceToken(worker_id="w-1", lease_generation=2, version_id=5)
    recorded = WorkerFenceToken(worker_id="w-1", lease_generation=2, version_id=4)
    assert DualLockFencing.verify_fence(current, recorded) is True

def test_dual_lock_fencing_stale_fails():
    current = WorkerFenceToken(worker_id="w-1", lease_generation=1, version_id=2)
    recorded = WorkerFenceToken(worker_id="w-2", lease_generation=2, version_id=2)
    with pytest.raises(StaleWorkerError):
        DualLockFencing.verify_fence(current, recorded)

def test_state_machine_valid_transition():
    next_state = BuildStateMachine.transition(BuildState.PENDING, BuildState.QUEUED)
    assert next_state == BuildState.QUEUED

def test_state_machine_invalid_transition():
    with pytest.raises(InvalidStateTransitionError):
        BuildStateMachine.transition(BuildState.PENDING, BuildState.COMPLETED)

def test_retry_jitter_bounds():
    delay = RetryJitter.calculate_backoff(attempt=2, base_delay=1.0, max_delay=10.0)
    assert 0.0 <= delay <= 4.0