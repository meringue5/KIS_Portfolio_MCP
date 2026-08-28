from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kis_portfolio.adapters.outbound.memory_state import InMemoryStateStore


def test_local_state_expiry_claim_and_fencing() -> None:
    store = InMemoryStateStore()
    now = datetime(2026, 8, 28, tzinfo=UTC)
    store.put("oauth_codes", "one", {"subject": "owner"}, expires_at=now + timedelta(minutes=1))
    assert store.get("oauth_codes", "one", now=now) == {"subject": "owner"}
    assert store.get("oauth_codes", "one", now=now + timedelta(minutes=2)) is None

    first = store.claim("kis-token:ria", "worker-a", timedelta(seconds=30), now=now)
    blocked = store.claim("kis-token:ria", "worker-b", timedelta(seconds=30), now=now)
    assert first.acquired is True
    assert blocked.acquired is False
    assert blocked.owner_id == "worker-a"
    assert store.release("kis-token:ria", "worker-b", first.fencing_token) is False
    assert store.release("kis-token:ria", "worker-a", first.fencing_token) is True
    second = store.claim("kis-token:ria", "worker-b", timedelta(seconds=30), now=now)
    assert second.acquired is True
    assert second.fencing_token > first.fencing_token
