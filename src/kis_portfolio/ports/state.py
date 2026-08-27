"""Operational state contract for leases and idempotency claims."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ClaimResult:
    acquired: bool
    fencing_token: int
    expires_at: datetime
    owner_id: str


class StateStorePort(Protocol):
    def put(self, namespace: str, key: str, value: dict[str, Any], *, expires_at: datetime | None = None) -> None: ...

    def get(self, namespace: str, key: str, *, now: datetime | None = None) -> dict[str, Any] | None: ...

    def claim(self, resource: str, owner_id: str, ttl: timedelta, *, now: datetime | None = None) -> ClaimResult: ...

    def release(self, resource: str, owner_id: str, fencing_token: int) -> bool: ...
