"""KIS OAuth token and hashkey helpers."""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .config import get_token_dir


CONTENT_TYPE = "application/json"
AUTH_TYPE = "Bearer"
TOKEN_PATH = "/oauth2/tokenP"
HASHKEY_PATH = "/uapi/hashkey"
TOKEN_REFRESH_SAFETY = timedelta(minutes=10)
DEFAULT_TOKEN_LIFETIME = timedelta(hours=23, minutes=50)


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


def get_token_status(token_file: Path | None = None) -> dict[str, Any]:
    """Return token cache metadata without exposing the token value."""
    path = token_file or get_token_file()
    if not path.exists():
        return {
            "exists": False,
            "status": "missing",
        }

    try:
        token_data = json.loads(path.read_text())
        expires_at = datetime.fromisoformat(token_data["expires_at"])
    except Exception as e:
        return {
            "exists": True,
            "status": "unreadable",
            "error": str(e),
        }

    now = datetime.now()
    if is_token_valid(expires_at, now):
        status = "valid"
    elif now < expires_at:
        status = "near_expiry"
    else:
        status = "expired"

    result = {
        "exists": True,
        "status": status,
        "has_token": bool(token_data.get("token")),
        "issued_at": token_data.get("issued_at"),
        "expires_at": expires_at.isoformat(),
        "minutes_until_expiry": round((expires_at - now).total_seconds() / 60, 1),
    }
    for key in ("token_type", "expires_in", "access_token_token_expired"):
        if key in token_data:
            result[key] = token_data[key]
    return result


def is_token_valid(expires_at: datetime, now: datetime | None = None) -> bool:
    """Return whether a token is safely reusable."""
    now = now or datetime.now()
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
    issued_at = issued_at or datetime.now()
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


@contextmanager
def token_file_lock(token_file: Path):
    """Serialize token refreshes across MCP processes for the same account."""
    lock_path = token_file.with_suffix(token_file.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


async def get_access_token(
    client: httpx.AsyncClient,
    domain: str,
    token_file: Path | None = None,
) -> str:
    """
    Get access token with file-based caching.

    Returns cached token if valid, otherwise requests a new token from KIS.
    """
    path = token_file or get_token_file()
    token, expires_at = load_token(path)
    if token and expires_at:
        return token

    with token_file_lock(path):
        token, expires_at = load_token(path)
        if token and expires_at:
            return token

        token_response = await client.post(
            f"{domain}{TOKEN_PATH}",
            headers={"content-type": CONTENT_TYPE},
            json={
                "grant_type": "client_credentials",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
            },
        )

        if token_response.status_code != 200:
            raise Exception(f"Failed to get token: {token_response.text}")

        issued_at = datetime.now()
        token_data = token_response.json()
        token = token_data["access_token"]
        expires_at = parse_kis_expiry(token_data, issued_at)
        save_token(token, expires_at, path, issued_at=issued_at, response_data=token_data)

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
