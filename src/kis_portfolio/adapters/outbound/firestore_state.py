"""Firestore Native implementation of the operational StateStorePort."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from google.cloud import firestore

from kis_portfolio.ports.state import ClaimResult


ALLOWED_COLLECTIONS = frozenset({
    "system_config",
    "auth_users",
    "auth_identities",
    "oauth_clients",
    "oauth_grants",
    "oauth_codes",
    "oauth_tokens",
    "kis_token_cache",
    "leases",
    "run_requests",
})


class FirestoreStateStore:
    def __init__(
        self,
        *,
        project: str,
        database: str = "kis-portfolio-state",
        client: firestore.Client | None = None,
    ) -> None:
        self.project = project
        self.database = database
        self.client = client or firestore.Client(project=project, database=database)

    @staticmethod
    def _validate_namespace(namespace: str) -> None:
        if namespace not in ALLOWED_COLLECTIONS:
            raise ValueError(f"collection is not in the application allowlist: {namespace}")

    @staticmethod
    def _document_id(key: str) -> str:
        if not key or "/" in key or len(key.encode()) > 1_500:
            return hashlib.sha256(key.encode()).hexdigest()
        return key

    def put(self, namespace: str, key: str, value: dict[str, Any], *, expires_at: datetime | None = None) -> None:
        self._validate_namespace(namespace)
        document = {"value": value, "updated_at": datetime.now(UTC)}
        if expires_at is not None:
            document["expires_at"] = expires_at
        self.client.collection(namespace).document(self._document_id(key)).set(document)

    def get(self, namespace: str, key: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        self._validate_namespace(namespace)
        snapshot = self.client.collection(namespace).document(self._document_id(key)).get()
        if not snapshot.exists:
            return None
        document = snapshot.to_dict()
        expires_at = document.get("expires_at")
        current = now or datetime.now(UTC)
        if expires_at is not None and expires_at <= current:
            return None
        return document.get("value")

    def claim(self, resource: str, owner_id: str, ttl: timedelta, *, now: datetime | None = None) -> ClaimResult:
        current = now or datetime.now(UTC)
        reference = self.client.collection("leases").document(self._document_id(resource))

        @firestore.transactional
        def acquire(transaction):
            snapshot = reference.get(transaction=transaction)
            existing = snapshot.to_dict() if snapshot.exists else {}
            expires_at = existing.get("expires_at")
            if expires_at is not None and expires_at > current:
                return ClaimResult(False, int(existing["fencing_token"]), expires_at, existing["owner_id"])
            fencing_token = int(existing.get("fencing_token", 0)) + 1
            new_expiry = current + ttl
            transaction.set(reference, {
                "resource_hash": self._document_id(resource),
                "owner_id": owner_id,
                "fencing_token": fencing_token,
                "expires_at": new_expiry,
                "updated_at": current,
            })
            return ClaimResult(True, fencing_token, new_expiry, owner_id)

        return acquire(self.client.transaction())

    def release(self, resource: str, owner_id: str, fencing_token: int) -> bool:
        reference = self.client.collection("leases").document(self._document_id(resource))

        @firestore.transactional
        def release_claim(transaction):
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                return False
            existing = snapshot.to_dict()
            if existing.get("owner_id") != owner_id or int(existing.get("fencing_token", 0)) != fencing_token:
                return False
            transaction.update(reference, {"expires_at": datetime.now(UTC), "released_at": datetime.now(UTC)})
            return True

        return release_claim(self.client.transaction())
