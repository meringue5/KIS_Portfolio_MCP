"""Runtime wiring for operational state and OAuth repositories."""

from __future__ import annotations

from typing import Any

from kis_portfolio.config import get_firestore_database, get_gcp_project, get_state_backend
from kis_portfolio.ports.state import StateStorePort


_state_store: StateStorePort | None = None
_auth_repository: Any | None = None


def get_state_store() -> StateStorePort:
    global _state_store
    if _state_store is not None:
        return _state_store
    backend = get_state_backend()
    if backend != "firestore":
        raise RuntimeError("StateStorePort is only available when KIS_STATE_BACKEND=firestore")
    project = get_gcp_project()
    if not project:
        raise RuntimeError("KIS_GCP_PROJECT or GOOGLE_CLOUD_PROJECT is required for Firestore")
    from kis_portfolio.adapters.outbound.firestore_state import FirestoreStateStore

    _state_store = FirestoreStateStore(project=project, database=get_firestore_database())
    return _state_store


def get_auth_repository() -> Any:
    """Return a module-compatible OAuth repository for the configured backend."""
    global _auth_repository
    if _auth_repository is not None:
        return _auth_repository
    if get_state_backend() == "firestore":
        from kis_portfolio.adapters.outbound.document_auth_repository import DocumentAuthRepository

        _auth_repository = DocumentAuthRepository(get_state_store())
    elif get_state_backend() == "motherduck":
        from kis_portfolio.db import auth_repository

        _auth_repository = auth_repository
    else:
        raise ValueError("KIS_STATE_BACKEND must be 'motherduck' or 'firestore'")
    return _auth_repository


def configure_state_store_for_tests(store: StateStorePort | None) -> None:
    """Inject a deterministic state store and clear derived repository wiring."""
    global _state_store, _auth_repository
    _state_store = store
    _auth_repository = None


def reset_state_runtime() -> None:
    configure_state_store_for_tests(None)
