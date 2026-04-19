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
            return {"access_token": "new-token"}

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
    assert auth.load_token(token_file)[0] == "new-token"


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
