from __future__ import annotations

import asyncio
from datetime import datetime

from kis_portfolio.services import token_warmup


def apply_account_env(monkeypatch):
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")
    for suffix, cano, prdt in [
        ("RIA", "11111111", "01"),
        ("ISA", "22222222", "01"),
        ("BROKERAGE", "33333333", "01"),
        ("IRP", "44444444", "29"),
        ("PENSION", "55555555", "22"),
    ]:
        monkeypatch.setenv(f"KIS_APP_KEY_{suffix}", f"key-{suffix}")
        monkeypatch.setenv(f"KIS_APP_SECRET_{suffix}", f"secret-{suffix}")
        monkeypatch.setenv(f"KIS_CANO_{suffix}", cano)
        monkeypatch.setenv(f"KIS_ACNT_PRDT_CD_{suffix}", prdt)


def test_valid_through_refresh_decision_uses_refresh_after():
    status = {
        "status": "valid",
        "expires_at": "2026-05-15T16:39:00",
        "refresh_after": "2026-05-15T16:29:00",
    }

    assert token_warmup._needs_refresh_for_valid_through(
        status,
        datetime(2026, 5, 15, 16, 30),
    )


def test_warm_token_cache_dry_run_does_not_request_token(monkeypatch):
    apply_account_env(monkeypatch)

    def fake_status():
        return {
            "exists": True,
            "status": "valid",
            "storage": "db",
            "expires_at": "2026-05-15T16:35:00",
            "refresh_after": "2026-05-15T16:25:00",
            "needs_refresh": False,
        }

    async def fail_get_access_token(*args, **kwargs):
        raise AssertionError("dry-run must not call KIS token endpoint")

    monkeypatch.setattr(token_warmup, "get_token_status", fake_status)
    monkeypatch.setattr(token_warmup, "get_access_token", fail_get_access_token)

    result = asyncio.run(
        token_warmup.warm_token_cache(
            account_label="brokerage",
            valid_through="16:30",
            dry_run=True,
        )
    )

    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert result["count"] == 1
    assert result["needs_refresh_count"] == 1
    assert result["would_refresh_count"] == 1
    assert result["accounts"][0]["refresh_status"] == "would_refresh"


def test_warm_token_cache_refreshes_when_not_dry_run(monkeypatch):
    apply_account_env(monkeypatch)
    statuses = [
        {
            "exists": True,
            "status": "expired",
            "storage": "db",
            "expires_at": "2026-05-15T12:00:00",
            "refresh_after": "2026-05-15T11:50:00",
            "needs_refresh": True,
        },
        {
            "exists": True,
            "status": "valid",
            "storage": "db",
            "expires_at": "2026-05-16T16:30:00",
            "refresh_after": "2026-05-16T16:20:00",
            "needs_refresh": False,
        },
    ]
    calls = []

    def fake_status():
        return statuses.pop(0)

    async def fake_get_access_token(client, domain, *, force_refresh=False):
        calls.append(force_refresh)
        return "token-value"

    monkeypatch.setattr(token_warmup, "get_token_status", fake_status)
    monkeypatch.setattr(token_warmup, "get_access_token", fake_get_access_token)

    result = asyncio.run(
        token_warmup.warm_token_cache(
            account_label="brokerage",
            valid_through="16:30",
            dry_run=False,
        )
    )

    assert calls == [True]
    assert result["refresh_count"] == 1
    assert result["accounts"][0]["refresh_status"] == "refreshed"
    assert "token-value" not in str(result)
