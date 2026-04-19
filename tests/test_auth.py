from datetime import datetime, timedelta

import pytest

from kis_mcp_server import auth


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_get_token_file_uses_account_specific_name(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_TOKEN_DIR", str(tmp_path))

    assert auth.get_token_file("12345678") == tmp_path / "token_12345678.json"


def test_save_and_load_valid_token(tmp_path):
    token_file = tmp_path / "token.json"
    expires_at = datetime.now() + timedelta(hours=1)

    auth.save_token("abc", expires_at, token_file)

    token, loaded_expires_at = auth.load_token(token_file)
    assert token == "abc"
    assert loaded_expires_at == expires_at


def test_load_token_ignores_expired_token(tmp_path):
    token_file = tmp_path / "token.json"
    auth.save_token("expired", datetime.now() - timedelta(seconds=1), token_file)

    assert auth.load_token(token_file) == (None, None)


def test_load_token_ignores_token_near_expiry(tmp_path):
    token_file = tmp_path / "token.json"
    auth.save_token("near-expiry", datetime.now() + timedelta(minutes=5), token_file)

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


def test_get_token_status_hides_token_value(tmp_path):
    token_file = tmp_path / "token.json"
    auth.save_token(
        "secret-token",
        datetime.now() + timedelta(hours=1),
        token_file,
        response_data={"token_type": "Bearer", "expires_in": 3600},
    )

    status = auth.get_token_status(token_file)

    assert status["exists"] is True
    assert status["status"] == "valid"
    assert status["has_token"] is True
    assert status["token_type"] == "Bearer"
    assert "token" not in status


@pytest.mark.anyio
async def test_get_access_token_reuses_cached_token(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    auth.save_token("cached-token", datetime.now() + timedelta(hours=1), token_file)

    class Client:
        async def post(self, *args, **kwargs):
            raise AssertionError("cached token should avoid network call")

    assert await auth.get_access_token(Client(), "https://example.com", token_file) == "cached-token"


@pytest.mark.anyio
async def test_get_access_token_requests_and_saves_new_token(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    monkeypatch.setenv("KIS_APP_KEY", "app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "app-secret")

    class Response:
        status_code = 200

        def json(self):
            return {
                "access_token": "new-token",
                "token_type": "Bearer",
                "expires_in": 86400,
                "access_token_token_expired": "2026-04-20 12:00:00",
            }

    class Client:
        def __init__(self):
            self.calls = []

        async def post(self, url, headers, json):
            self.calls.append((url, headers, json))
            return Response()

    client = Client()
    token = await auth.get_access_token(client, "https://example.com", token_file)

    assert token == "new-token"
    assert client.calls[0][0] == "https://example.com/oauth2/tokenP"
    saved = auth.load_token(token_file)
    assert saved[0] == "new-token"
    token_data = __import__("json").loads(token_file.read_text())
    assert token_data["token_type"] == "Bearer"
    assert token_data["access_token_token_expired"] == "2026-04-20 12:00:00"
    assert "issued_at" in token_data


@pytest.mark.anyio
async def test_get_hashkey_posts_to_hashkey_endpoint(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "app-secret")

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
