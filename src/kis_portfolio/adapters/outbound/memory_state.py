"""Deterministic local StateStorePort implementation for tests and dry-runs."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any

from kis_portfolio.ports.state import ClaimResult


class InMemoryStateStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._values: dict[tuple[str, str], tuple[dict[str, Any], datetime | None]] = {}
        self._claims: dict[str, ClaimResult] = {}
        self._fencing: dict[str, int] = {}

    def put(self, namespace: str, key: str, value: dict[str, Any], *, expires_at: datetime | None = None) -> None:
        with self._lock:
            self._values[(namespace, key)] = (deepcopy(value), expires_at)

    def get(self, namespace: str, key: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        current = now or datetime.now(UTC)
        with self._lock:
            entry = self._values.get((namespace, key))
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and expires_at <= current:
                del self._values[(namespace, key)]
                return None
            return deepcopy(value)

    def claim(self, resource: str, owner_id: str, ttl: timedelta, *, now: datetime | None = None) -> ClaimResult:
        current = now or datetime.now(UTC)
        with self._lock:
            existing = self._claims.get(resource)
            if existing is not None and existing.expires_at > current:
                return ClaimResult(False, existing.fencing_token, existing.expires_at, existing.owner_id)
            token = self._fencing.get(resource, 0) + 1
            self._fencing[resource] = token
            result = ClaimResult(True, token, current + ttl, owner_id)
            self._claims[resource] = result
            return result

    def release(self, resource: str, owner_id: str, fencing_token: int) -> bool:
        with self._lock:
            existing = self._claims.get(resource)
            if existing is None or existing.owner_id != owner_id or existing.fencing_token != fencing_token:
                return False
            del self._claims[resource]
            return True
