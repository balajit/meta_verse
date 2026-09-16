import pytest

from meta_application_builder.persistence.event_chain.crypt_chain import (
    CryptographicChainError,
    EventCryptographicChain,
)


def test_chain_hash_generation_and_verification():
    payload_1 = {"action": "JOB_SUBMITTED", "user": "usr_alpha"}
    hash_1 = EventCryptographicChain.calculate_hash(
        EventCryptographicChain.GENESIS_HASH, 1, payload_1
    )

    payload_2 = {"action": "COMPILATION_STARTED", "compiler_version": "2.1.0"}
    hash_2 = EventCryptographicChain.calculate_hash(hash_1, 2, payload_2)

    events = [
        {
            "sequence_number": 1,
            "previous_hash": EventCryptographicChain.GENESIS_HASH,
            "payload": payload_1,
            "hash": hash_1,
        },
        {
            "sequence_number": 2,
            "previous_hash": hash_1,
            "payload": payload_2,
            "hash": hash_2,
        },
    ]

    assert EventCryptographicChain.verify_chain(events) is True


def test_chain_tamper_detection_raises_error():
    payload_1 = {"action": "JOB_SUBMITTED", "user": "usr_alpha"}
    hash_1 = EventCryptographicChain.calculate_hash(
        EventCryptographicChain.GENESIS_HASH, 1, payload_1
    )

    # Tampered payload after hash calculation
    tampered_payload_1 = {"action": "JOB_SUBMITTED", "user": "usr_hacker"}

    events = [
        {
            "sequence_number": 1,
            "previous_hash": EventCryptographicChain.GENESIS_HASH,
            "payload": tampered_payload_1,
            "hash": hash_1,
        }
    ]

    with pytest.raises(CryptographicChainError) as exc_info:
        EventCryptographicChain.verify_chain(events)
    assert "Tamper detected" in str(exc_info.value)


def test_chain_sequence_gap_raises_error():
    payload_1 = {"action": "JOB_SUBMITTED"}
    hash_1 = EventCryptographicChain.calculate_hash(
        EventCryptographicChain.GENESIS_HASH, 1, payload_1
    )

    events = [
        {
            "sequence_number": 2,  # Invalid sequence start
            "previous_hash": EventCryptographicChain.GENESIS_HASH,
            "payload": payload_1,
            "hash": hash_1,
        }
    ]

    with pytest.raises(CryptographicChainError) as exc_info:
        EventCryptographicChain.verify_chain(events)
    assert "Sequence mismatch" in str(exc_info.value)