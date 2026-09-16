import pytest

from meta_application_builder.persistence.event_chain.crypt_chain import (
    CryptographicChainError,
    EventCryptographicChain,
)
from meta_application_builder.persistence.lineage.closure_manager import (
    LineageClosureManager,
)


def test_out_of_order_sequence_tamper_detection():
    """Validates that sequence gap anomalies trigger immediate CryptographicChainError exceptions."""
    payload = {"step": "COMPILE"}
    hash_1 = EventCryptographicChain.calculate_hash(EventCryptographicChain.GENESIS_HASH, 1, payload)

    # Missing sequence number 2
    events = [
        {"sequence_number": 1, "previous_hash": EventCryptographicChain.GENESIS_HASH, "payload": payload,
         "hash": hash_1},
        {"sequence_number": 3, "previous_hash": hash_1, "payload": payload, "hash": "invalid_hash"},
    ]

    with pytest.raises(CryptographicChainError) as exc_info:
        EventCryptographicChain.verify_chain(events)

    assert "Sequence mismatch at position 1: expected 2, got 3" in str(exc_info.value)


def test_modified_previous_hash_detection():
    """Validates that breaking previous_hash linkages in the cryptographic chain is detected."""
    payload_1 = {"step": "INIT"}
    payload_2 = {"step": "BUILD"}

    hash_1 = EventCryptographicChain.calculate_hash(EventCryptographicChain.GENESIS_HASH, 1, payload_1)
    hash_2 = EventCryptographicChain.calculate_hash(hash_1, 2, payload_2)

    events = [
        {"sequence_number": 1, "previous_hash": EventCryptographicChain.GENESIS_HASH, "payload": payload_1,
         "hash": hash_1},
        {
            "sequence_number": 2,
            "previous_hash": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            # Corrupted previous hash
            "payload": payload_2,
            "hash": hash_2,
        },
    ]

    with pytest.raises(CryptographicChainError) as exc_info:
        EventCryptographicChain.verify_chain(events)

    assert "Chain broken at sequence 2" in str(exc_info.value)