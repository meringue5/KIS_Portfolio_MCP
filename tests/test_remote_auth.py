import importlib

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient


def test_remote_app_requires_auth_token(monkeypatch):
    monkeypatch.delenv("KIS_REMOTE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("KIS_REMOTE_AUTH_DISABLED", raising=False)

    remote = importlib.import_module("kis_mcp_server.remote")

    with pytest.raises(RuntimeError, match="KIS_REMOTE_AUTH_TOKEN"):
        remote.create_app()


def test_remote_healthcheck_does_not_require_auth(monkeypatch):
    monkeypatch.setenv("KIS_REMOTE_AUTH_TOKEN", "secret")

    remote = importlib.import_module("kis_mcp_server.remote")

    with TestClient(remote.create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_remote_mcp_requires_bearer_token(monkeypatch):
    remote = importlib.import_module("kis_mcp_server.remote")
    wrapped = remote.SharedBearerAuthMiddleware(dummy_mcp_app, token="secret")

    client = TestClient(wrapped)

    assert client.get("/mcp").status_code == 401
    assert client.get("/mcp", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/mcp", headers={"Authorization": "Bearer secret"}).status_code == 200


async def dummy_mcp_app(scope, receive, send):
    response = JSONResponse({"ok": True})
    await response(scope, receive, send)
