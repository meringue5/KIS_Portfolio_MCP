"""Repository helpers for encrypted KIS API access-token cache rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from kis_portfolio.config import get_state_backend
from kis_portfolio.db.connection import get_connection


SEOUL_TZ = ZoneInfo("Asia/Seoul")


TOKEN_COLUMNS = """
    cache_key,
    account_id,
    account_type,
    app_key_fingerprint,
    token_ciphertext,
    token_type,
    issued_at,
    expires_at,
    expires_in,
    response_expiry_raw,
    migrated_from_file,
    created_at,
    updated_at
"""


def _row_to_dict(cursor, row) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def get_kis_api_access_token(cache_key: str) -> dict[str, Any] | None:
    if get_state_backend() == "firestore":
        from kis_portfolio.platform.state_runtime import get_state_store

        record = get_state_store().get("kis_token_cache", cache_key)
        if record is None:
            return None
        for key in ("issued_at", "expires_at", "created_at", "updated_at"):
            value = record.get(key)
            if isinstance(value, datetime) and value.tzinfo is not None:
                record[key] = value.astimezone(SEOUL_TZ).replace(tzinfo=None)
        return record
    con = get_connection()
    cursor = con.execute(
        f"""
        SELECT {TOKEN_COLUMNS}
        FROM kis_api_access_tokens
        WHERE cache_key=?
        """,
        [cache_key],
    )
    return _row_to_dict(cursor, cursor.fetchone())


def upsert_kis_api_access_token(
    *,
    cache_key: str,
    account_id: str,
    account_type: str,
    app_key_fingerprint: str,
    token_ciphertext: str,
    token_type: str,
    issued_at: datetime,
    expires_at: datetime,
    expires_in: int | None,
    response_expiry_raw: str | None,
    migrated_from_file: bool,
) -> dict[str, Any]:
    if get_state_backend() == "firestore":
        from kis_portfolio.platform.state_runtime import get_state_store

        store = get_state_store()
        existing = store.get("kis_token_cache", cache_key) or {}
        now = datetime.now(SEOUL_TZ).replace(tzinfo=None)
        record = {
            "cache_key": cache_key,
            "account_id": account_id,
            "account_type": account_type,
            "app_key_fingerprint": app_key_fingerprint,
            "token_ciphertext": token_ciphertext,
            "token_type": token_type,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "expires_in": expires_in,
            "response_expiry_raw": response_expiry_raw,
            "migrated_from_file": migrated_from_file,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        expiry_aware = expires_at.replace(tzinfo=SEOUL_TZ).astimezone(UTC)
        store.put("kis_token_cache", cache_key, record, expires_at=expiry_aware)
        return record
    con = get_connection()
    now = datetime.now()
    cursor = con.execute(
        f"""
        INSERT INTO kis_api_access_tokens (
            cache_key,
            account_id,
            account_type,
            app_key_fingerprint,
            token_ciphertext,
            token_type,
            issued_at,
            expires_at,
            expires_in,
            response_expiry_raw,
            migrated_from_file,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (cache_key) DO UPDATE SET
            account_id = excluded.account_id,
            account_type = excluded.account_type,
            app_key_fingerprint = excluded.app_key_fingerprint,
            token_ciphertext = excluded.token_ciphertext,
            token_type = excluded.token_type,
            issued_at = excluded.issued_at,
            expires_at = excluded.expires_at,
            expires_in = excluded.expires_in,
            response_expiry_raw = excluded.response_expiry_raw,
            migrated_from_file = excluded.migrated_from_file,
            updated_at = excluded.updated_at
        RETURNING {TOKEN_COLUMNS}
        """,
        [
            cache_key,
            account_id,
            account_type,
            app_key_fingerprint,
            token_ciphertext,
            token_type,
            issued_at,
            expires_at,
            expires_in,
            response_expiry_raw,
            migrated_from_file,
            now,
        ],
    )
    row = cursor.fetchone()
    assert row is not None
    return _row_to_dict(cursor, row) or {}
