from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

from kis_portfolio import auth
from kis_portfolio.db.connection import close_connection, get_connection
from kis_portfolio.db.kis_token_repository import get_kis_api_access_token, upsert_kis_api_access_token
from kis_portfolio.kis_token_crypto import (
    TokenDecryptionError,
    TokenEncryptionConfigError,
    encrypt_token,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def local_token_cache_env(tmp_path, monkeypatch):
    close_connection()
    auth.clear_process_token_cache()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")
    monkeypatch.setenv("KIS_CANO", "12345678")
    monkeypatch.setenv("KIS_APP_KEY", "app-key-1")
    monkeypatch.setenv("KIS_APP_SECRET", "app-secret-1")
    monkeypatch.setenv("KIS_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    async def no_rate_limit_wait(*args, **kwargs):
        return 0.0

    monkeypatch.setattr(auth, "wait_for_kis_slot", no_rate_limit_wait)
    yield tmp_path
    auth.clear_process_token_cache()
    close_connection()


def _cache_key(account_type: str, cano: str, app_key: str) -> str:
    return hashlib.sha256(f"{account_type}:{cano}:{app_key}".encode("utf-8")).hexdigest()


def _insert_cached_row(
    *,
    token: str = "cached-token",
    account_type: str = "REAL",
    cano: str = "12345678",
    app_key: str = "app-key-1",
    expires_at: datetime | None = None,
    issued_at: datetime | None = None,
    migrated_from_file: bool = False,
    token_ciphertext: str | None = None,
):
    issued_at = issued_at or auth._kis_now()
    expires_at = expires_at or (issued_at + timedelta(hours=1))
    return upsert_kis_api_access_token(
        cache_key=_cache_key(account_type, cano, app_key),
        account_id=cano,
        account_type=account_type,
        app_key_fingerprint=hashlib.sha256(app_key.encode("utf-8")).hexdigest(),
        token_ciphertext=token_ciphertext or encrypt_token(token),
        token_type="Bearer",
        issued_at=issued_at,
        expires_at=expires_at,
        expires_in=int((expires_at - issued_at).total_seconds()),
        response_expiry_raw=expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        migrated_from_file=migrated_from_file,
    )


def test_get_token_file_uses_account_specific_name(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_TOKEN_DIR", str(tmp_path))

    assert auth.get_token_file("12345678") == tmp_path / "token_12345678.json"


def test_save_and_load_valid_token(tmp_path):
    token_file = tmp_path / "token.json"
    expires_at = auth._kis_now() + timedelta(hours=1)

    auth.save_token("abc", expires_at, token_file)

    token, loaded_expires_at = auth.load_token(token_file)
    assert token == "abc"
    assert loaded_expires_at == expires_at


def test_load_token_ignores_expired_token(tmp_path):
    token_file = tmp_path / "token.json"
    auth.save_token("expired", auth._kis_now() - timedelta(seconds=1), token_file)

    assert auth.load_token(token_file) == (None, None)


def test_load_token_ignores_token_near_expiry(tmp_path):
    token_file = tmp_path / "token.json"
    auth.save_token("near-expiry", auth._kis_now() + timedelta(minutes=5), token_file)

    assert auth.load_token(token_file) == (None, None)


def test_parse_kis_expiry_prefers_response_expiry():
    issued_at = datetime(2026, 4, 19, 10, 0, 0)

    expires_at = auth.parse_kis_expiry(
        {"access_token_token_expired": "2026-04-20 09:59:59", "expires_in": 60},
        issued_at,
    )

    assert expires_at == datetime(2026, 4, 20, 9, 59, 59)


def test_parse_kis_expiry_uses_expires_in():
    issued_at = datetime(2026, 4, 19, 10, 0, 0)

    expires_at = auth.parse_kis_expiry({"expires_in": "3600"}, issued_at)

    assert expires_at == datetime(2026, 4, 19, 11, 0, 0)


@pytest.mark.anyio
async def test_get_token_status_hides_token_value(local_token_cache_env):
    future_expiry = (auth._kis_now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    class Response:
        status_code = 200

        @property
        def text(self):
            return "ok"

        def json(self):
            return {
                "access_token": "new-token",
                "token_type": "Bearer",
                "expires_in": 86400,
                "access_token_token_expired": future_expiry,
            }

    class Client:
        async def post(self, *args, **kwargs):
            return Response()

    await auth.get_access_token(Client(), "https://example.com")
    status = auth.get_token_status()

    assert status["exists"] is True
    assert status["status"] == "valid"
    assert status["storage"] == "db"
    assert status["has_token"] is True
    assert status["token_type"] == "Bearer"
    assert "token" not in status


@pytest.mark.anyio
async def test_get_access_token_reuses_cached_db_token(local_token_cache_env):
    _insert_cached_row()

    class Client:
        async def post(self, *args, **kwargs):
            raise AssertionError("cached token should avoid network call")

    assert await auth.get_access_token(Client(), "https://example.com") == "cached-token"


@pytest.mark.anyio
async def test_get_access_token_refreshes_expired_kis_wall_clock_token(
    local_token_cache_env,
    monkeypatch,
):
    monkeypatch.setattr(auth, "_kis_now", lambda: datetime(2026, 8, 25, 15, 40, 0))
    _insert_cached_row(
        issued_at=datetime(2026, 8, 24, 15, 35, 0),
        expires_at=datetime(2026, 8, 25, 15, 35, 0),
    )

    class Response:
        status_code = 200

        def json(self):
            return {
                "access_token": "refreshed-token",
                "token_type": "Bearer",
                "expires_in": 86400,
                "access_token_token_expired": "2026-08-26 15:40:00",
            }

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            return Response()

    client = Client()

    assert await auth.get_access_token(client, "https://example.com") == "refreshed-token"
    assert client.calls == 1

    status = auth.get_token_status()
    assert status["status"] == "valid"
    assert status["expires_at"] == "2026-08-26T15:40:00"


@pytest.mark.anyio
async def test_get_access_token_requests_and_saves_new_token(local_token_cache_env):
    future_expiry = (auth._kis_now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    class Response:
        status_code = 200

        @property
        def text(self):
            return "ok"

        def json(self):
            return {
                "access_token": "new-token",
                "token_type": "Bearer",
                "expires_in": 86400,
                "access_token_token_expired": future_expiry,
            }

    class Client:
        def __init__(self):
            self.calls = []

        async def post(self, url, headers, json):
            self.calls.append((url, headers, json))
            return Response()

    client = Client()
    token = await auth.get_access_token(client, "https://example.com")

    assert token == "new-token"
    assert client.calls[0][0] == "https://example.com/oauth2/tokenP"
    assert not auth.get_token_file().exists()

    row = get_kis_api_access_token(_cache_key("REAL", "12345678", "app-key-1"))
    assert row is not None
    assert row["token_type"] == "Bearer"
    assert row["response_expiry_raw"] == future_expiry


@pytest.mark.anyio
async def test_get_access_token_logs_refresh_without_secrets(local_token_cache_env, caplog):
    future_expiry = (auth._kis_now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    class Response:
        status_code = 200

        def json(self):
            return {
                "access_token": "very-sensitive-token",
                "token_type": "Bearer",
                "expires_in": 86400,
                "access_token_token_expired": future_expiry,
            }

    class Client:
        async def post(self, *args, **kwargs):
            return Response()

    caplog.set_level(logging.INFO)

    token = await auth.get_access_token(Client(), "https://example.com")

    assert token == "very-sensitive-token"
    assert "kis_token_request_start" in caplog.text
    assert "kis_token_db_upsert_success" in caplog.text
    assert "very-sensitive-token" not in caplog.text
    assert "app-secret-1" not in caplog.text
    assert "12345678" not in caplog.text


@pytest.mark.anyio
async def test_get_access_token_uses_process_memory_when_db_upsert_fails(
    local_token_cache_env,
    monkeypatch,
):
    future_expiry = (auth._kis_now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    class Response:
        status_code = 200

        def json(self):
            return {
                "access_token": "memory-token",
                "token_type": "Bearer",
                "expires_in": 86400,
                "access_token_token_expired": future_expiry,
            }

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            return Response()

    def fail_upsert(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(auth, "upsert_kis_api_access_token", fail_upsert)

    client = Client()
    assert await auth.get_access_token(client, "https://example.com") == "memory-token"
    assert client.calls == 1

    status = auth.get_token_status()
    assert status["storage"] == "process_memory"
    assert status["persisted"] is False
    assert status["needs_refresh"] is False

    class NoNetworkClient:
        async def post(self, *args, **kwargs):
            raise AssertionError("process memory token should avoid a second token request")

    assert await auth.get_access_token(NoNetworkClient(), "https://example.com") == "memory-token"


@pytest.mark.anyio
async def test_get_access_token_retries_429_or_5xx_once(local_token_cache_env, monkeypatch):
    class Response:
        def __init__(self, status_code, token=None):
            self.status_code = status_code
            self.token = token

        def json(self):
            if self.status_code == 200:
                return {"access_token": self.token, "token_type": "Bearer", "expires_in": 86400}
            return {"rt_cd": "1", "msg_cd": "EGW00001", "msg1": "temporary"}

    class Client:
        def __init__(self):
            self.responses = [Response(500), Response(200, "retried-token")]
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            return self.responses.pop(0)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(auth.asyncio, "sleep", fake_sleep)
    client = Client()

    assert await auth.get_access_token(client, "https://example.com") == "retried-token"
    assert client.calls == 2


@pytest.mark.anyio
async def test_get_access_token_does_not_retry_4xx(local_token_cache_env):
    class Response:
        status_code = 400

        def json(self):
            return {"rt_cd": "1", "msg_cd": "BAD", "msg1": "bad request"}

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            return Response()

    client = Client()

    with pytest.raises(RuntimeError):
        await auth.get_access_token(client, "https://example.com")
    assert client.calls == 1


@pytest.mark.anyio
async def test_get_access_token_does_not_retry_read_timeout(local_token_cache_env):
    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            raise httpx.ReadTimeout("timeout")

    client = Client()

    with pytest.raises(httpx.ReadTimeout):
        await auth.get_access_token(client, "https://example.com")
    assert client.calls == 1


@pytest.mark.anyio
async def test_get_access_token_refreshes_near_expiry_db_token(local_token_cache_env):
    _insert_cached_row(expires_at=auth._kis_now() + timedelta(minutes=5))

    class Response:
        status_code = 200

        @property
        def text(self):
            return "ok"

        def json(self):
            return {
                "access_token": "refreshed-token",
                "token_type": "Bearer",
                "expires_in": 86400,
            }

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            return Response()

    client = Client()
    token = await auth.get_access_token(client, "https://example.com")

    assert token == "refreshed-token"
    assert client.calls == 1


@pytest.mark.anyio
async def test_get_access_token_requires_token_encryption_key(local_token_cache_env, monkeypatch):
    monkeypatch.delenv("KIS_TOKEN_ENCRYPTION_KEY", raising=False)

    class Client:
        async def post(self, *args, **kwargs):
            raise AssertionError("network call must not happen without encryption key")

    with pytest.raises(TokenEncryptionConfigError):
        await auth.get_access_token(Client(), "https://example.com")


@pytest.mark.anyio
async def test_get_access_token_fails_closed_on_corrupted_ciphertext(local_token_cache_env):
    _insert_cached_row(token_ciphertext="corrupted")

    class Client:
        async def post(self, *args, **kwargs):
            raise AssertionError("corrupted cache row must not fall back to network")

    with pytest.raises(TokenDecryptionError):
        await auth.get_access_token(Client(), "https://example.com")


@pytest.mark.anyio
async def test_get_access_token_migrates_legacy_file_to_db(local_token_cache_env):
    legacy_file = Path(local_token_cache_env) / "tokens" / "token_12345678.json"
    auth.save_token(
        "legacy-token",
        auth._kis_now() + timedelta(hours=1),
        legacy_file,
        response_data={"token_type": "Bearer", "expires_in": 3600},
    )

    class Client:
        async def post(self, *args, **kwargs):
            raise AssertionError("legacy token migration should avoid network call")

    token = await auth.get_access_token(Client(), "https://example.com", legacy_file)

    assert token == "legacy-token"
    assert not legacy_file.exists()
    row = get_kis_api_access_token(_cache_key("REAL", "12345678", "app-key-1"))
    assert row is not None
    assert row["migrated_from_file"] is True


@pytest.mark.anyio
async def test_get_access_token_ignores_legacy_file_when_db_row_exists(local_token_cache_env):
    _insert_cached_row(token="db-token")
    legacy_file = Path(local_token_cache_env) / "tokens" / "token_12345678.json"
    auth.save_token("legacy-token", auth._kis_now() + timedelta(hours=1), legacy_file)

    class Client:
        async def post(self, *args, **kwargs):
            raise AssertionError("valid db row should avoid network call")

    token = await auth.get_access_token(Client(), "https://example.com", legacy_file)

    assert token == "db-token"
    assert legacy_file.exists()


@pytest.mark.anyio
async def test_get_access_token_serializes_refreshes_per_cache_key(local_token_cache_env):
    class Response:
        status_code = 200

        @property
        def text(self):
            return "ok"

        def json(self):
            return {
                "access_token": "shared-token",
                "token_type": "Bearer",
                "expires_in": 86400,
            }

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            await asyncio.sleep(0.05)
            return Response()

    client = Client()
    tokens = await asyncio.gather(
        auth.get_access_token(client, "https://example.com"),
        auth.get_access_token(client, "https://example.com"),
    )

    assert tokens == ["shared-token", "shared-token"]
    assert client.calls == 1


@pytest.mark.anyio
async def test_get_access_token_does_not_reuse_old_row_after_app_key_change(
    local_token_cache_env,
    monkeypatch,
):
    _insert_cached_row(token="token-for-key-1")

    class Response:
        status_code = 200

        @property
        def text(self):
            return "ok"

        def json(self):
            return {
                "access_token": "token-for-key-2",
                "token_type": "Bearer",
                "expires_in": 86400,
            }

    class Client:
        def __init__(self):
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            return Response()

    monkeypatch.setenv("KIS_APP_KEY", "app-key-2")
    monkeypatch.setenv("KIS_APP_SECRET", "app-secret-2")

    client = Client()
    token = await auth.get_access_token(client, "https://example.com")

    assert token == "token-for-key-2"
    assert client.calls == 1
    row_count = get_connection().execute("SELECT count(*) FROM kis_api_access_tokens").fetchone()[0]
    assert row_count == 2


@pytest.mark.anyio
async def test_cached_token_survives_connection_restart(local_token_cache_env):
    class Response:
        status_code = 200

        @property
        def text(self):
            return "ok"

        def json(self):
            return {
                "access_token": "persisted-token",
                "token_type": "Bearer",
                "expires_in": 86400,
            }

    class WriteClient:
        async def post(self, *args, **kwargs):
            return Response()

    first_token = await auth.get_access_token(WriteClient(), "https://example.com")
    assert first_token == "persisted-token"

    close_connection()

    class ReadClient:
        async def post(self, *args, **kwargs):
            raise AssertionError("reopened DB should still reuse cached token")

    second_token = await auth.get_access_token(ReadClient(), "https://example.com")
    assert second_token == "persisted-token"


@pytest.mark.anyio
async def test_get_hashkey_posts_to_hashkey_endpoint(local_token_cache_env):
    class Response:
        status_code = 200

        def json(self):
            return {"HASH": "hash-value"}

    class Client:
        def __init__(self):
            self.calls = []

        async def post(self, url, headers, json):
            self.calls.append((url, headers, json))
            return Response()

    client = Client()
    result = await auth.get_hashkey(client, "https://example.com", "token", {"a": 1})

    assert result == "hash-value"
    assert client.calls[0][0] == "https://example.com/uapi/hashkey"
    assert client.calls[0][1]["authorization"] == "Bearer token"
