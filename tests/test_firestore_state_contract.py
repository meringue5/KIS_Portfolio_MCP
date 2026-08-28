from __future__ import annotations

import hashlib

import pytest

from kis_portfolio.adapters.outbound.firestore_state import ALLOWED_COLLECTIONS, FirestoreStateStore


def test_firestore_state_collection_allowlist_and_named_database_defaults() -> None:
    assert "oauth_tokens" in ALLOWED_COLLECTIONS
    assert "leases" in ALLOWED_COLLECTIONS
    assert "run_requests" in ALLOWED_COLLECTIONS
    assert FirestoreStateStore._document_id("safe-key") == "safe-key"
    unsafe = "account/with/slash"
    assert FirestoreStateStore._document_id(unsafe) == hashlib.sha256(unsafe.encode()).hexdigest()
    with pytest.raises(ValueError, match="allowlist"):
        FirestoreStateStore._validate_namespace("arbitrary_collection")
