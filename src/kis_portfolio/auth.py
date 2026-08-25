"""KIS OAuth token and hashkey helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import get_token_dir
from .db.kis_token_repository import get_kis_api_access_token, upsert_kis_api_access_token
from .observability import current_or_new_operation_id, log_event
from .security.redaction import mask_account_id
from .security.token_encryption import (
    TokenDecryptionError,
    TokenEncryptionConfigError,
    decrypt_token,
    ensure_token_encryption_ready,
    encrypt_token,
)


CONTENT_TYPE = "application/json"
AUTH_TYPE = "Bearer"
TOKEN_PATH = "/oauth2/tokenP"
HASHKEY_PATH = "/uapi/hashkey"
TOKEN_REFRESH_SAFETY = timedelta(minutes=10)
DEFAULT_TOKEN_LIFETIME = timedelta(hours=23, minutes=50)
SEOUL_TZ = ZoneInfo("Asia/Seoul")
KIS_EXPIRED_TOKEN_CODES = frozenset({"EGW00123"})
_TOKEN_REFRESH_LOCKS: dict[str, asyncio.Lock] = {}
_PROCESS_TOKEN_CACHE: dict[str, dict[str, Any]] = {}
logger = logging.getLogger("kis-portfolio-auth")


def _kis_now() -> datetime:
    """Return the current KIS wall-clock time as a DB-compatible timestamp."""
    return datetime.now(SEOUL_TZ).replace(tzinfo=None)


def get_token_file(cano: str | None = None) -> Path:
    token_dir = get_token_dir()
    token_dir.mkdir(parents=True, exist_ok=True)
    return token_dir / f"token_{cano or os.environ.get('KIS_CANO', 'default')}.json"


def load_token(token_file: Path | None = None) -> tuple[str | None, datetime | None]:
    """Load token from file if it exists and is not expired."""
    path = token_file or get_token_file()
    if path.exists():
        try:
            token_data = json.loads(path.read_text())
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if is_token_valid(expires_at):
                return token_data["token"], expires_at
        except Exception as e:
            print(f"Error loading token: {e}", file=sys.stderr)
    return None, None


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for KIS token cache operations.")
    return value


def _get_cache_context() -> dict[str, str]:
    account_type = _require_env("KIS_ACCOUNT_TYPE").upper()
    cano = _require_env("KIS_CANO")
    app_key = _require_env("KIS_APP_KEY")
    app_key_fingerprint = hashlib.sha256(app_key.encode("utf-8")).hexdigest()
    return {
        "account_type": account_type,
        "account_id": cano,
        "masked_cano": mask_account_id(cano),
        "account_label": os.environ.get("KIS_ACCOUNT_LABEL", ""),
        "app_key": app_key,
        "cache_key": hashlib.sha256(f"{account_type}:{cano}:{app_key}".encode("utf-8")).hexdigest(),
        "app_key_fingerprint": app_key_fingerprint,
        "app_key_fingerprint_prefix": app_key_fingerprint[:12],
    }


def _coerce_expires_in(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _refresh_after(expires_at: datetime) -> datetime:
    return expires_at - TOKEN_REFRESH_SAFETY


def _common_log_fields(cache_context: dict[str, str], operation_id: str) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "account_label": cache_context.get("account_label") or None,
        "masked_cano": cache_context["masked_cano"],
        "account_type": cache_context["account_type"],
        "app_key_fingerprint_prefix": cache_context["app_key_fingerprint_prefix"],
    }


def _store_process_memory_token(
    *,
    cache_context: dict[str, str],
    token: str,
    issued_at: datetime,
    expires_at: datetime,
    token_type: str | None,
    expires_in: int | None,
    response_expiry_raw: str | None,
    persisted: bool,
) -> None:
    _PROCESS_TOKEN_CACHE[cache_context["cache_key"]] = {
        "token": token,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "token_type": token_type or AUTH_TYPE,
        "expires_in": expires_in,
        "response_expiry_raw": response_expiry_raw,
        "updated_at": _kis_now(),
        "persisted": persisted,
    }


def _read_valid_token_from_process_memory(cache_context: dict[str, str]) -> tuple[str | None, dict[str, Any] | None]:
    record = _PROCESS_TOKEN_CACHE.get(cache_context["cache_key"])
    if record is None:
        return None, None
    expires_at = record.get("expires_at")
    if not isinstance(expires_at, datetime) or not is_token_valid(expires_at):
        return None, record
    token = record.get("token")
    if not isinstance(token, str) or not token:
        return None, record
    return token, record


def clear_process_token_cache() -> None:
    """Clear process-local KIS token cache; intended for tests and controlled diagnostics."""
    _PROCESS_TOKEN_CACHE.clear()


def _persist_token_record(
    *,
    cache_context: dict[str, str],
    token: str,
    issued_at: datetime,
    expires_at: datetime,
    token_type: str | None,
    expires_in: int | None,
    response_expiry_raw: str | None,
    migrated_from_file: bool,
) -> dict[str, Any]:
    ciphertext = encrypt_token(token)
    return upsert_kis_api_access_token(
        cache_key=cache_context["cache_key"],
        account_id=cache_context["account_id"],
        account_type=cache_context["account_type"],
        app_key_fingerprint=cache_context["app_key_fingerprint"],
        token_ciphertext=ciphertext,
        token_type=token_type or AUTH_TYPE,
        issued_at=issued_at,
        expires_at=expires_at,
        expires_in=expires_in,
        response_expiry_raw=response_expiry_raw,
        migrated_from_file=migrated_from_file,
    )


def _read_db_token_record(cache_context: dict[str, str]) -> dict[str, Any] | None:
    return get_kis_api_access_token(cache_context["cache_key"])


def _read_valid_token_from_db(cache_context: dict[str, str]) -> tuple[str | None, dict[str, Any] | None]:
    record = _read_db_token_record(cache_context)
    if record is None:
        return None, None

    expires_at = record.get("expires_at")
    if not isinstance(expires_at, datetime):
        raise RuntimeError("Cached KIS token row is missing a valid expires_at timestamp.")
    if not is_token_valid(expires_at):
        return None, record

    ciphertext = record.get("token_ciphertext")
    if not isinstance(ciphertext, str) or not ciphertext:
        raise RuntimeError("Cached KIS token row is missing token ciphertext.")
    return decrypt_token(ciphertext), record


def _extract_kis_response_fields(response: httpx.Response) -> dict[str, Any]:
    fields: dict[str, Any] = {"http_status": response.status_code}
    try:
        payload = response.json()
    except Exception:
        return fields
    if isinstance(payload, dict):
        fields["kis_msg_cd"] = payload.get("msg_cd")
        fields["kis_msg1"] = payload.get("msg1")
        fields["rt_cd"] = payload.get("rt_cd")
    return fields


def is_kis_expired_token_response(response: httpx.Response) -> bool:
    """Return whether KIS rejected the supplied access token as expired."""
    try:
        payload = response.json()
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("msg_cd") in KIS_EXPIRED_TOKEN_CODES


async def _request_new_token_with_retry(
    client: httpx.AsyncClient,
    domain: str,
    cache_context: dict[str, str],
    operation_id: str,
) -> httpx.Response:
    for attempt in range(2):
        started = time.perf_counter()
        log_event(
            logger,
            "kis_token_request_start",
            **_common_log_fields(cache_context, operation_id),
            attempt=attempt + 1,
        )
        try:
            response = await client.post(
                f"{domain}{TOKEN_PATH}",
                headers={"content-type": CONTENT_TYPE},
                json={
                    "grant_type": "client_credentials",
                    "appkey": os.environ["KIS_APP_KEY"],
                    "appsecret": os.environ["KIS_APP_SECRET"],
                },
            )
        except httpx.ReadTimeout as exc:
            log_event(
                logger,
                "kis_token_request_failed",
                level=logging.WARNING,
                **_common_log_fields(cache_context, operation_id),
                attempt=attempt + 1,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                error_type=type(exc).__name__,
                retried=False,
            )
            raise
        except httpx.HTTPError as exc:
            log_event(
                logger,
                "kis_token_request_failed",
                level=logging.WARNING,
                **_common_log_fields(cache_context, operation_id),
                attempt=attempt + 1,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                error_type=type(exc).__name__,
                retried=False,
            )
            raise

        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        if response.status_code == 200:
            log_event(
                logger,
                "kis_token_request_success",
                **_common_log_fields(cache_context, operation_id),
                attempt=attempt + 1,
                elapsed_ms=elapsed_ms,
                **_extract_kis_response_fields(response),
            )
            return response

        should_retry = response.status_code == 429 or 500 <= response.status_code < 600
        will_retry = should_retry and attempt == 0
        log_event(
            logger,
            "kis_token_request_failed",
            level=logging.WARNING,
            **_common_log_fields(cache_context, operation_id),
            attempt=attempt + 1,
            elapsed_ms=elapsed_ms,
            retried=will_retry,
            **_extract_kis_response_fields(response),
        )
        if will_retry:
            await asyncio.sleep(1)
            continue

        fields = _extract_kis_response_fields(response)
        raise RuntimeError(
            "Failed to get KIS token: "
            f"http_status={response.status_code} "
            f"msg_cd={fields.get('kis_msg_cd')} "
            f"msg1={fields.get('kis_msg1')}"
        )

    raise RuntimeError("Failed to get KIS token after retry.")


def _migrate_legacy_token_if_available(
    cache_context: dict[str, str],
    token_file: Path | None,
) -> tuple[str | None, datetime | None]:
    path = token_file or get_token_file()
    token, expires_at = load_token(path)
    if not token or not expires_at:
        return None, None

    token_data = json.loads(path.read_text())
    issued_at_raw = token_data.get("issued_at")
    issued_at = datetime.fromisoformat(issued_at_raw) if issued_at_raw else _kis_now()
    _persist_token_record(
        cache_context=cache_context,
        token=token,
        issued_at=issued_at,
        expires_at=expires_at,
        token_type=token_data.get("token_type"),
        expires_in=_coerce_expires_in(token_data.get("expires_in")),
        response_expiry_raw=token_data.get("access_token_token_expired"),
        migrated_from_file=True,
    )
    path.unlink(missing_ok=True)
    return token, expires_at


def get_token_status(token_file: Path | None = None) -> dict[str, Any]:
    """Return token cache metadata without exposing the token value."""
    cache_context: dict[str, str] | None = None
    try:
        cache_context = _get_cache_context()
        record = _read_db_token_record(cache_context)
    except RuntimeError as e:
        return {
            "exists": False,
            "status": "misconfigured",
            "storage": None,
            "updated_at": None,
            "refresh_after": None,
            "needs_refresh": True,
            "error": str(e),
        }
    except Exception as e:
        if cache_context is not None:
            memory_token, memory_record = _read_valid_token_from_process_memory(cache_context)
            if memory_record is not None:
                expires_at = memory_record["expires_at"]
                now = _kis_now()
                return {
                    "exists": bool(memory_token),
                    "status": "valid" if memory_token else "expired",
                    "storage": "process_memory",
                    "persisted": False,
                    "has_token": bool(memory_token),
                    "issued_at": memory_record.get("issued_at").isoformat()
                    if memory_record.get("issued_at")
                    else None,
                    "expires_at": expires_at.isoformat(),
                    "refresh_after": _refresh_after(expires_at).isoformat(),
                    "updated_at": memory_record.get("updated_at").isoformat()
                    if memory_record.get("updated_at")
                    else None,
                    "minutes_until_expiry": round((expires_at - now).total_seconds() / 60, 1),
                    "needs_refresh": not bool(memory_token),
                    "db_status": "unreadable",
                    "db_error": str(e),
                }
        return {
            "exists": True,
            "status": "unreadable",
            "storage": "db",
            "updated_at": None,
            "refresh_after": None,
            "needs_refresh": True,
            "error": str(e),
        }

    memory_token, memory_record = _read_valid_token_from_process_memory(cache_context)
    if memory_token and (
        record is None
        or not isinstance(record.get("expires_at"), datetime)
        or memory_record["expires_at"] > record["expires_at"]
        or not is_token_valid(record["expires_at"])
    ):
        expires_at = memory_record["expires_at"]
        now = _kis_now()
        result = {
            "exists": True,
            "status": "valid",
            "storage": "process_memory",
            "persisted": bool(memory_record.get("persisted")),
            "has_token": True,
            "issued_at": memory_record.get("issued_at").isoformat()
            if memory_record.get("issued_at")
            else None,
            "expires_at": expires_at.isoformat(),
            "refresh_after": _refresh_after(expires_at).isoformat(),
            "updated_at": memory_record.get("updated_at").isoformat()
            if memory_record.get("updated_at")
            else None,
            "minutes_until_expiry": round((expires_at - now).total_seconds() / 60, 1),
            "needs_refresh": False,
        }
        if memory_record.get("token_type"):
            result["token_type"] = memory_record["token_type"]
        if memory_record.get("expires_in") is not None:
            result["expires_in"] = memory_record["expires_in"]
        if memory_record.get("response_expiry_raw"):
            result["access_token_token_expired"] = memory_record["response_expiry_raw"]
        return result

    if record is None:
        path = token_file or get_token_file()
        if not path.exists():
            return {
                "exists": False,
                "status": "missing",
                "storage": "none",
                "updated_at": None,
                "refresh_after": None,
                "needs_refresh": True,
            }
        try:
            token_data = json.loads(path.read_text())
            expires_at = datetime.fromisoformat(token_data["expires_at"])
        except Exception as e:
            return {
                "exists": True,
                "status": "unreadable",
                "storage": "legacy_file",
                "updated_at": None,
                "refresh_after": None,
                "needs_refresh": True,
                "error": str(e),
            }
        now = _kis_now()
        if is_token_valid(expires_at, now):
            status = "valid"
        elif now < expires_at:
            status = "near_expiry"
        else:
            status = "expired"
        result = {
            "exists": True,
            "status": status,
            "storage": "legacy_file",
            "has_token": bool(token_data.get("token")),
            "issued_at": token_data.get("issued_at"),
            "expires_at": expires_at.isoformat(),
            "refresh_after": _refresh_after(expires_at).isoformat(),
            "updated_at": None,
            "minutes_until_expiry": round((expires_at - now).total_seconds() / 60, 1),
            "needs_refresh": status != "valid",
        }
        for key in ("token_type", "expires_in", "access_token_token_expired"):
            if key in token_data:
                result[key] = token_data[key]
        return result

    expires_at = record["expires_at"]
    now = _kis_now()
    if is_token_valid(expires_at, now):
        status = "valid"
    elif now < expires_at:
        status = "near_expiry"
    else:
        status = "expired"

    result = {
        "exists": True,
        "status": status,
        "storage": "db",
        "persisted": True,
        "has_token": bool(record.get("token_ciphertext")),
        "issued_at": record["issued_at"].isoformat() if record.get("issued_at") else None,
        "expires_at": expires_at.isoformat(),
        "refresh_after": _refresh_after(expires_at).isoformat(),
        "updated_at": record["updated_at"].isoformat() if record.get("updated_at") else None,
        "minutes_until_expiry": round((expires_at - now).total_seconds() / 60, 1),
        "needs_refresh": status != "valid",
    }
    if record.get("token_type"):
        result["token_type"] = record["token_type"]
    if record.get("expires_in") is not None:
        result["expires_in"] = record["expires_in"]
    if record.get("response_expiry_raw"):
        result["access_token_token_expired"] = record["response_expiry_raw"]
    if record.get("migrated_from_file"):
        result["migrated_from_file"] = True
    return result


def is_token_valid(expires_at: datetime, now: datetime | None = None) -> bool:
    """Return whether a token is safely reusable."""
    now = now or _kis_now()
    return now < expires_at - TOKEN_REFRESH_SAFETY


def parse_kis_expiry(token_data: dict[str, Any], issued_at: datetime) -> datetime:
    """Parse KIS token expiry from the response, falling back conservatively."""
    raw_expiry = token_data.get("access_token_token_expired")
    if raw_expiry:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(str(raw_expiry), fmt)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(str(raw_expiry))
        except ValueError:
            pass

    expires_in = token_data.get("expires_in")
    if expires_in:
        try:
            return issued_at + timedelta(seconds=int(expires_in))
        except Exception:
            pass

    return issued_at + DEFAULT_TOKEN_LIFETIME


def save_token(
    token: str,
    expires_at: datetime,
    token_file: Path | None = None,
    *,
    issued_at: datetime | None = None,
    response_data: dict[str, Any] | None = None,
) -> None:
    """Save token to file."""
    path = token_file or get_token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    issued_at = issued_at or _kis_now()
    payload = {
        "token": token,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    if response_data:
        if "token_type" in response_data:
            payload["token_type"] = response_data["token_type"]
        if "expires_in" in response_data:
            payload["expires_in"] = response_data["expires_in"]
        if "access_token_token_expired" in response_data:
            payload["access_token_token_expired"] = response_data["access_token_token_expired"]

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.chmod(0o600)
    tmp.replace(path)


def _get_refresh_lock(cache_key: str) -> asyncio.Lock:
    lock = _TOKEN_REFRESH_LOCKS.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _TOKEN_REFRESH_LOCKS[cache_key] = lock
    return lock


async def get_access_token(
    client: httpx.AsyncClient,
    domain: str,
    token_file: Path | None = None,
    *,
    force_refresh: bool = False,
) -> str:
    """Get access token from the encrypted DB cache or request a new one."""
    cache_context = _get_cache_context()
    operation_id = current_or_new_operation_id("auth")
    ensure_token_encryption_ready()
    if not force_refresh:
        try:
            token, record = _read_valid_token_from_db(cache_context)
        except (TokenDecryptionError, TokenEncryptionConfigError):
            raise
        except Exception as exc:
            log_event(
                logger,
                "kis_token_cache_lookup",
                level=logging.WARNING,
                **_common_log_fields(cache_context, operation_id),
                storage="db",
                status="unreadable",
                error_type=type(exc).__name__,
            )
            token, memory_record = _read_valid_token_from_process_memory(cache_context)
            if token:
                log_event(
                    logger,
                    "kis_token_cache_lookup",
                    **_common_log_fields(cache_context, operation_id),
                    storage="process_memory",
                    status="hit",
                    expires_at=memory_record["expires_at"],
                    refresh_after=_refresh_after(memory_record["expires_at"]),
                )
                return token
        else:
            log_event(
                logger,
                "kis_token_cache_lookup",
                **_common_log_fields(cache_context, operation_id),
                storage="db",
                status="hit" if token else "miss",
                expires_at=record.get("expires_at") if record else None,
                refresh_after=_refresh_after(record["expires_at"]) if record else None,
            )
            if token:
                return token

            memory_token, memory_record = _read_valid_token_from_process_memory(cache_context)
            if memory_token:
                log_event(
                    logger,
                    "kis_token_cache_lookup",
                    **_common_log_fields(cache_context, operation_id),
                    storage="process_memory",
                    status="hit",
                    expires_at=memory_record["expires_at"],
                    refresh_after=_refresh_after(memory_record["expires_at"]),
                )
                return memory_token

    async with _get_refresh_lock(cache_context["cache_key"]):
        record = None
        db_lookup_failed = False
        if not force_refresh:
            try:
                token, record = _read_valid_token_from_db(cache_context)
            except (TokenDecryptionError, TokenEncryptionConfigError):
                raise
            except Exception as exc:
                db_lookup_failed = True
                log_event(
                    logger,
                    "kis_token_cache_lookup",
                    level=logging.WARNING,
                    **_common_log_fields(cache_context, operation_id),
                    storage="db",
                    status="unreadable",
                    error_type=type(exc).__name__,
                )
            else:
                if token:
                    log_event(
                        logger,
                        "kis_token_cache_lookup",
                        **_common_log_fields(cache_context, operation_id),
                        storage="db",
                        status="hit_after_lock",
                        expires_at=record.get("expires_at") if record else None,
                        refresh_after=_refresh_after(record["expires_at"]) if record else None,
                    )
                    return token

            memory_token, memory_record = _read_valid_token_from_process_memory(cache_context)
            if memory_token:
                log_event(
                    logger,
                    "kis_token_cache_lookup",
                    **_common_log_fields(cache_context, operation_id),
                    storage="process_memory",
                    status="hit_after_lock",
                    expires_at=memory_record["expires_at"],
                    refresh_after=_refresh_after(memory_record["expires_at"]),
                )
                return memory_token

        if record is None and not db_lookup_failed and not force_refresh:
            token, expires_at = _migrate_legacy_token_if_available(cache_context, token_file)
            if token and expires_at:
                return token

        token_response = await _request_new_token_with_retry(
            client,
            domain,
            cache_context,
            operation_id,
        )

        issued_at = _kis_now()
        token_data = token_response.json()
        token = token_data["access_token"]
        expires_at = parse_kis_expiry(token_data, issued_at)
        token_type = token_data.get("token_type")
        expires_in = _coerce_expires_in(token_data.get("expires_in"))
        response_expiry_raw = token_data.get("access_token_token_expired")
        _store_process_memory_token(
            cache_context=cache_context,
            token=token,
            issued_at=issued_at,
            expires_at=expires_at,
            token_type=token_type,
            expires_in=expires_in,
            response_expiry_raw=response_expiry_raw,
            persisted=False,
        )
        try:
            _persist_token_record(
                cache_context=cache_context,
                token=token,
                issued_at=issued_at,
                expires_at=expires_at,
                token_type=token_type,
                expires_in=expires_in,
                response_expiry_raw=response_expiry_raw,
                migrated_from_file=False,
            )
        except Exception as exc:
            log_event(
                logger,
                "kis_token_db_upsert_failed",
                level=logging.WARNING,
                **_common_log_fields(cache_context, operation_id),
                storage="process_memory",
                persisted=False,
                expires_at=expires_at,
                refresh_after=_refresh_after(expires_at),
                error_type=type(exc).__name__,
            )
            log_event(
                logger,
                "kis_token_refresh_complete",
                **_common_log_fields(cache_context, operation_id),
                storage="process_memory",
                persisted=False,
                expires_at=expires_at,
                refresh_after=_refresh_after(expires_at),
            )
        else:
            _PROCESS_TOKEN_CACHE[cache_context["cache_key"]]["persisted"] = True
            log_event(
                logger,
                "kis_token_db_upsert_success",
                **_common_log_fields(cache_context, operation_id),
                storage="db",
                persisted=True,
                expires_at=expires_at,
                refresh_after=_refresh_after(expires_at),
            )
            log_event(
                logger,
                "kis_token_refresh_complete",
                **_common_log_fields(cache_context, operation_id),
                storage="db",
                persisted=True,
                expires_at=expires_at,
                refresh_after=_refresh_after(expires_at),
            )

    return token


async def get_hashkey(
    client: httpx.AsyncClient,
    domain: str,
    token: str,
    body: dict[str, Any],
) -> str:
    """Get hash key for order request."""
    response = await client.post(
        f"{domain}{HASHKEY_PATH}",
        headers={
            "content-type": CONTENT_TYPE,
            "authorization": f"{AUTH_TYPE} {token}",
            "appkey": os.environ["KIS_APP_KEY"],
            "appsecret": os.environ["KIS_APP_SECRET"],
        },
        json=body,
    )

    if response.status_code != 200:
        raise Exception(f"Failed to get hash key: {response.text}")

    return response.json()["HASH"]
