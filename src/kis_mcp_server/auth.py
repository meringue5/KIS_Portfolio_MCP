"""KIS OAuth token and hashkey helpers."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .config import get_token_dir


CONTENT_TYPE = "application/json"
AUTH_TYPE = "Bearer"
TOKEN_PATH = "/oauth2/tokenP"
HASHKEY_PATH = "/uapi/hashkey"


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
            if datetime.now() < expires_at:
                return token_data["token"], expires_at
        except Exception as e:
            print(f"Error loading token: {e}", file=sys.stderr)
    return None, None


def save_token(token: str, expires_at: datetime, token_file: Path | None = None) -> None:
    """Save token to file."""
    path = token_file or get_token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "token": token,
                "expires_at": expires_at.isoformat(),
            }
        )
    )


async def get_access_token(
    client: httpx.AsyncClient,
    domain: str,
    token_file: Path | None = None,
) -> str:
    """
    Get access token with file-based caching.

    Returns cached token if valid, otherwise requests a new token from KIS.
    """
    token, expires_at = load_token(token_file)
    if token and expires_at and datetime.now() < expires_at:
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

    token_data = token_response.json()
    token = token_data["access_token"]

    expires_at = datetime.now() + timedelta(hours=23)
    save_token(token, expires_at, token_file)

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
