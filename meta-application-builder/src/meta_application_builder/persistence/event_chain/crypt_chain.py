from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List

from meta_application_builder.persistence.db_session.connection import DatabaseError

logger = logging.getLogger("meta_application_builder.persistence.crypt_chain")


class CryptographicChainError(DatabaseError):
    """Raised when log chain integrity or sequence validation fails."""
    pass


class EventCryptographicChain:
    """
    Computes and verifies SHA-256 cryptographic hashes for append-only audit logs.
    Formula: H_n = SHA256(H_{n-1} || sequence_number || JSON_CANONICAL(payload))
    """

    GENESIS_HASH: str = "0000000000000000000000000000000000000000000000000000000000000000"

    @classmethod
    def serialize_canonical(cls, payload: Dict[str, Any]) -> str:
        """Deterministic UTF-8 JSON serialization with sorted keys."""
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def calculate_hash(cls, previous_hash: str, sequence_number: int, payload: Dict[str, Any]) -> str:
        """Calculates hash H_n for a new event given its predecessor state."""
        canonical_json = cls.serialize_canonical(payload)
        digest_input = f"{previous_hash}:{sequence_number}:{canonical_json}".encode("utf-8")
        computed_hash = hashlib.sha256(digest_input).hexdigest()
        logger.debug(
            "Calculated event hash sequence_number=%d, prev_hash=%s..., hash=%s...",
            sequence_number,
            previous_hash[:8],
            computed_hash[:8],
        )
        return computed_hash

    @classmethod
    def verify_chain(cls, events: List[Dict[str, Any]]) -> bool:
        """
        Validates an entire event sequence for tamper detection.
        Expects dicts containing 'sequence_number', 'previous_hash', 'payload', and 'hash'.
        """
        if not events:
            logger.info("Verification skipped: Empty event list received.")
            return True

        logger.info("Verifying audit event chain integrity across %d events.", len(events))
        expected_prev = cls.GENESIS_HASH

        for idx, event in enumerate(events):
            seq = event.get("sequence_number")
            prev_hash = event.get("previous_hash")
            curr_hash = event.get("hash")
            payload = event.get("payload", {})

            expected_seq = idx + 1
            if seq != expected_seq:
                logger.error(
                    "Event chain integrity failure: Sequence gap at index %d. Expected %d, got %s",
                    idx,
                    expected_seq,
                    seq,
                )
                raise CryptographicChainError(f"Sequence mismatch at position {idx}: expected {expected_seq}, got {seq}")

            if prev_hash != expected_prev:
                logger.error(
                    "Event chain integrity failure at seq %d: previous_hash '%s' != expected '%s'",
                    seq,
                    prev_hash,
                    expected_prev,
                )
                raise CryptographicChainError(
                    f"Chain broken at sequence {seq}: previous_hash '{prev_hash}' does not match expected '{expected_prev}'"
                )

            calculated = cls.calculate_hash(prev_hash, seq, payload)
            if calculated != curr_hash:
                logger.error(
                    "Event chain integrity failure: Tampering detected at sequence %d. Stored hash='%s', calculated='%s'",
                    seq,
                    curr_hash,
                    calculated,
                )
                raise CryptographicChainError(
                    f"Tamper detected at sequence {seq}: stored hash '{curr_hash}' does not match calculated '{calculated}'"
                )

            expected_prev = curr_hash

        logger.info("Audit event chain verification completed successfully.")
        return True