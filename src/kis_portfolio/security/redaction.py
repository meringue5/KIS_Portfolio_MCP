"""Redaction helpers for sensitive response and log values."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


DEFAULT_SECRET_KEYS = frozenset({
    "authorization",
    "appsecret",
    "app_secret",
    "client_secret",
    "kis_app_secret",
    "motherduck_token",
    "token",
    "access_token",
    "refresh_token",
})
DEFAULT_ACCOUNT_KEYS = frozenset({"cano", "account_id", "account_no", "account_number", "acnt_no"})


def mask_account_id(account_id: str) -> str:
    """Mask a KIS account id while preserving the existing public shape."""
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return f"{account_id[:2]}{'*' * max(len(account_id) - 4, 0)}{account_id[-2:]}"


def redact_mapping(
    value: Mapping[str, Any],
    *,
    secret_keys: Iterable[str] = DEFAULT_SECRET_KEYS,
    replacement: str = "<redacted>",
) -> dict[str, Any]:
    """Return a shallow copy with known secret-looking keys redacted."""
    normalized_keys = {key.lower() for key in secret_keys}
    return {
        key: replacement if str(key).lower() in normalized_keys else item
        for key, item in value.items()
    }


def redact_nested(value: Any) -> Any:
    """Recursively redact credentials and mask account identifiers before landing."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in DEFAULT_SECRET_KEYS:
                result[key] = "<redacted>"
            elif normalized in DEFAULT_ACCOUNT_KEYS and isinstance(item, str):
                result[key] = mask_account_id(item)
            else:
                result[key] = redact_nested(item)
        return result
    if isinstance(value, list):
        return [redact_nested(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_nested(item) for item in value)
    return value
