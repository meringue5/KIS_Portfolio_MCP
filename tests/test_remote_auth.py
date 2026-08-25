import importlib
import asyncio
from contextlib import asynccontextmanager

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from kis_portfolio.db import auth_repository, close_connection
from kis_portfolio.adapters.auth.config import StaticOAuthClientConfig
from kis_portfolio.adapters.auth.provider import KisOAuthProvider


def test_remote_app_requires_auth_token(monkeypatch):
    monkeypatch.delenv("KIS_REMOTE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("KIS_REMOTE_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("KIS_REMOTE_AUTH_MODE", "bearer")

    remote = importlib.reload(importlib.import_module("kis_portfolio.remote"))

    with pytest.raises(RuntimeError, match="KIS_REMOTE_AUTH_TOKEN"):
        remote.create_app()


def test_remote_healthcheck_does_not_require_auth(monkeypatch):
    monkeypatch.setenv("KIS_REMOTE_AUTH_TOKEN", "secret")
    monkeypatch.setenv("KIS_REMOTE_AUTH_MODE", "bearer")

    remote = importlib.reload(importlib.import_module("kis_portfolio.remote"))

    with TestClient(remote.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_remote_bearer_mode_accepts_exact_mcp_path_without_redirect(monkeypatch):
    monkeypatch.setenv("KIS_REMOTE_AUTH_TOKEN", "secret")
    monkeypatch.setenv("KIS_REMOTE_AUTH_MODE", "bearer")

    remote = importlib.reload(importlib.import_module("kis_portfolio.remote"))
    monkeypatch.setattr(remote, "build_mcp_server", _dummy_remote_server)

    with TestClient(remote.create_app()) as client:
        response = client.get("/mcp", follow_redirects=False)

    assert response.status_code == 401
    assert "location" not in response.headers


def test_remote_mcp_requires_bearer_token(monkeypatch):
    remote = importlib.import_module("kis_portfolio.remote")
    wrapped = remote.SharedBearerAuthMiddleware(dummy_mcp_app, token="secret")

    client = TestClient(wrapped)

    assert client.get("/mcp").status_code == 401
    assert client.get("/mcp", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/mcp", headers={"Authorization": "Bearer secret"}).status_code == 200


async def dummy_mcp_app(scope, receive, send):
    response = JSONResponse({"ok": True})
    await response(scope, receive, send)


@pytest.fixture(autouse=True)
def local_db(monkeypatch, tmp_path):
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))
    yield
    close_connection()


def _oauth_provider() -> KisOAuthProvider:
    return KisOAuthProvider(
        token_pepper="pepper",
        resource_server_url="https://resource.example.com/mcp",
        static_client=StaticOAuthClientConfig(
            client_id="claude-client",
            client_secret="claude-secret",
            client_name="Claude",
            redirect_uris=("https://claude.ai/api/mcp/auth_callback",),
            scope="mcp:read",
        ),
    )


def _dummy_remote_server():
    class DummySessionManager:
        async def handle_request(self, scope, receive, send):
            response = JSONResponse({"ok": True})
            await response(scope, receive, send)

        @asynccontextmanager
        async def run(self):
            yield

    class DummyServer:
        def __init__(self):
            self._session_manager = DummySessionManager()

        def streamable_http_app(self, **_kwargs):
            return Starlette(routes=[Route("/", lambda request: JSONResponse({"unused": True}))])

        @property
        def session_manager(self):
            return self._session_manager

    return DummyServer()


def test_remote_oauth_mode_enforces_token_and_scope(monkeypatch):
    provider = _oauth_provider()
    user = auth_repository.upsert_auth_user("owner@example.com", "Owner")
    grant = auth_repository.upsert_oauth_grant(user["id"], "claude-client", "mcp:read")
    client = asyncio.run(provider.get_client("claude-client"))
    assert client is not None

    code = asyncio.run(provider.issue_authorization_code(
        user_id=user["id"],
        client_id="claude-client",
        grant_id=grant["id"],
        scope="mcp:read",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        redirect_uri_provided_explicitly=True,
        code_challenge="challenge",
        resource="https://resource.example.com/mcp",
        state=None,
        provider="google",
    ))
    stored_code = asyncio.run(provider.load_authorization_code(client, code))
    token = asyncio.run(provider.exchange_authorization_code(
        client,
        stored_code,
        resource="https://resource.example.com/mcp",
    ))

    other_grant = auth_repository.upsert_oauth_grant(user["id"], "claude-client", "")
    wrong_scope_code = asyncio.run(provider.issue_authorization_code(
        user_id=user["id"],
        client_id="claude-client",
        grant_id=other_grant["id"],
        scope="",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        redirect_uri_provided_explicitly=True,
        code_challenge="challenge",
        resource="https://resource.example.com/mcp",
        state=None,
        provider="google",
    ))
    stored_wrong_scope = asyncio.run(provider.load_authorization_code(client, wrong_scope_code))
    wrong_scope_token = asyncio.run(provider.exchange_authorization_code(
        client,
        stored_wrong_scope,
        resource="https://resource.example.com/mcp",
    ))

    monkeypatch.setenv("KIS_REMOTE_AUTH_MODE", "oauth")
    monkeypatch.setenv("KIS_AUTH_ISSUER_URL", "https://auth.example.com")
    monkeypatch.setenv("KIS_RESOURCE_SERVER_URL", "https://resource.example.com/mcp")
    monkeypatch.setenv("KIS_AUTH_TOKEN_PEPPER", "pepper")
    monkeypatch.setenv("KIS_AUTH_REQUIRED_SCOPES", "mcp:read")

    remote = importlib.reload(importlib.import_module("kis_portfolio.remote"))
    monkeypatch.setattr(remote, "build_mcp_server", _dummy_remote_server)

    with TestClient(remote.create_app()) as client_http:
        assert client_http.get("/health").status_code == 200
        assert client_http.get("/mcp").status_code == 401
        assert client_http.get("/mcp/", follow_redirects=False).status_code == 401
        assert client_http.get(
            "/mcp",
            headers={"Authorization": "Bearer invalid"},
        ).status_code == 401
        assert client_http.get(
            "/mcp",
            headers={"Authorization": f"Bearer {wrong_scope_token.access_token}"},
        ).status_code == 403
        assert client_http.get(
            "/mcp/",
            headers={"Authorization": f"Bearer {wrong_scope_token.access_token}"},
            follow_redirects=False,
        ).status_code == 403
        assert client_http.get(
            "/mcp",
            headers={"Authorization": f"Bearer {token.access_token}"},
        ).status_code == 200
        assert client_http.get(
            "/mcp/",
            headers={"Authorization": f"Bearer {token.access_token}"},
            follow_redirects=False,
        ).status_code == 200


def test_remote_oauth_mode_exposes_discovery_and_authorize_redirect(monkeypatch):
    monkeypatch.setenv("KIS_REMOTE_AUTH_MODE", "oauth")
    monkeypatch.setenv("KIS_AUTH_ISSUER_URL", "https://auth.example.com/")
    monkeypatch.setenv("KIS_RESOURCE_SERVER_URL", "https://resource.example.com/mcp")
    monkeypatch.setenv("KIS_AUTH_TOKEN_PEPPER", "pepper")
    monkeypatch.setenv("KIS_AUTH_REQUIRED_SCOPES", "mcp:read")

    remote = importlib.reload(importlib.import_module("kis_portfolio.remote"))
    monkeypatch.setattr(remote, "build_mcp_server", _dummy_remote_server)

    with TestClient(remote.create_app()) as client_http:
        protected = client_http.get("/.well-known/oauth-protected-resource")
        assert protected.status_code == 200
        assert protected.json() == {
            "resource": "https://resource.example.com/mcp",
            "authorization_servers": ["https://auth.example.com"],
            "scopes_supported": ["mcp:read"],
            "bearer_methods_supported": ["header"],
        }

        path_protected = client_http.get("/.well-known/oauth-protected-resource/mcp")
        assert path_protected.status_code == 200
        assert path_protected.json() == protected.json()

        authorization_server = client_http.get("/.well-known/oauth-authorization-server")
        assert authorization_server.status_code == 200
        metadata = authorization_server.json()
        assert metadata["issuer"] == "https://auth.example.com"
        assert metadata["authorization_endpoint"] == "https://auth.example.com/authorize"
        assert metadata["token_endpoint"] == "https://auth.example.com/token"
        assert metadata["registration_endpoint"] == "https://auth.example.com/register"
        assert metadata["scopes_supported"] == ["mcp:read", "offline_access"]
        assert metadata["token_endpoint_auth_methods_supported"] == [
            "client_secret_basic",
            "client_secret_post",
        ]

        redirect = client_http.get(
            "/authorize?response_type=code&client_id=kis-portfolio-claude&state=abc",
            follow_redirects=False,
        )
        assert redirect.status_code == 302
        assert (
            redirect.headers["location"]
            == "https://auth.example.com/authorize?response_type=code&client_id=kis-portfolio-claude&state=abc"
        )


def test_remote_oauth_mode_challenges_with_resource_metadata(monkeypatch):
    monkeypatch.setenv("KIS_REMOTE_AUTH_MODE", "oauth")
    monkeypatch.setenv("KIS_AUTH_ISSUER_URL", "https://auth.example.com")
    monkeypatch.setenv("KIS_RESOURCE_SERVER_URL", "https://resource.example.com/mcp")
    monkeypatch.setenv("KIS_AUTH_TOKEN_PEPPER", "pepper")
    monkeypatch.setenv("KIS_AUTH_REQUIRED_SCOPES", "mcp:read")

    remote = importlib.reload(importlib.import_module("kis_portfolio.remote"))
    monkeypatch.setattr(remote, "build_mcp_server", _dummy_remote_server)

    with TestClient(remote.create_app()) as client_http:
        response = client_http.get("/mcp")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        'Bearer error="invalid_token", error_description="Authentication required", '
        'resource_metadata="https://resource.example.com/.well-known/oauth-protected-resource/mcp"'
    )


def test_remote_oauth_mode_rejects_token_for_other_resource(monkeypatch):
    provider = KisOAuthProvider(token_pepper="pepper")
    user = auth_repository.upsert_auth_user("owner@example.com", "Owner")
    grant = auth_repository.upsert_oauth_grant(user["id"], "claude-client", "mcp:read")
    provider.bootstrap_static_client(
        StaticOAuthClientConfig(
            client_id="claude-client",
            client_secret="claude-secret",
            client_name="Claude",
            redirect_uris=("https://claude.ai/api/mcp/auth_callback",),
            scope="mcp:read",
        )
    )
    client = asyncio.run(provider.get_client("claude-client"))
    assert client is not None

    code = asyncio.run(provider.issue_authorization_code(
        user_id=user["id"],
        client_id="claude-client",
        grant_id=grant["id"],
        scope="mcp:read",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        redirect_uri_provided_explicitly=True,
        code_challenge="challenge",
        resource="https://other.example.com/mcp",
        state=None,
        provider="google",
    ))
    stored_code = asyncio.run(provider.load_authorization_code(client, code))
    token = asyncio.run(provider.exchange_authorization_code(
        client,
        stored_code,
        resource="https://other.example.com/mcp",
    ))

    monkeypatch.setenv("KIS_REMOTE_AUTH_MODE", "oauth")
    monkeypatch.setenv("KIS_AUTH_ISSUER_URL", "https://auth.example.com")
    monkeypatch.setenv("KIS_RESOURCE_SERVER_URL", "https://resource.example.com/mcp")
    monkeypatch.setenv("KIS_AUTH_TOKEN_PEPPER", "pepper")
    monkeypatch.setenv("KIS_AUTH_REQUIRED_SCOPES", "mcp:read")

    remote = importlib.reload(importlib.import_module("kis_portfolio.remote"))
    monkeypatch.setattr(remote, "build_mcp_server", _dummy_remote_server)

    with TestClient(
        remote.create_app(),
        base_url="https://resource.example.com",
    ) as client_http:
        response = client_http.get(
            "/mcp",
            headers={"Authorization": f"Bearer {token.access_token}"},
        )

    assert response.status_code == 401


def test_remote_oauth_mode_supports_2026_discovery(monkeypatch):
    provider = _oauth_provider()
    user = auth_repository.upsert_auth_user("owner@example.com", "Owner")
    grant = auth_repository.upsert_oauth_grant(user["id"], "claude-client", "mcp:read")
    client = asyncio.run(provider.get_client("claude-client"))
    assert client is not None

    code = asyncio.run(provider.issue_authorization_code(
        user_id=user["id"],
        client_id="claude-client",
        grant_id=grant["id"],
        scope="mcp:read",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        redirect_uri_provided_explicitly=True,
        code_challenge="challenge",
        resource="https://resource.example.com/mcp",
        state=None,
        provider="google",
    ))
    stored_code = asyncio.run(provider.load_authorization_code(client, code))
    token = asyncio.run(provider.exchange_authorization_code(
        client,
        stored_code,
        resource="https://resource.example.com/mcp",
    ))

    monkeypatch.setenv("KIS_REMOTE_AUTH_MODE", "oauth")
    monkeypatch.setenv("KIS_AUTH_ISSUER_URL", "https://auth.example.com")
    monkeypatch.setenv("KIS_RESOURCE_SERVER_URL", "https://resource.example.com/mcp")
    monkeypatch.setenv("KIS_AUTH_TOKEN_PEPPER", "pepper")
    monkeypatch.setenv("KIS_AUTH_REQUIRED_SCOPES", "mcp:read")

    remote = importlib.reload(importlib.import_module("kis_portfolio.remote"))

    request = {
        "jsonrpc": "2.0",
        "id": "discover-1",
        "method": "server/discover",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientInfo": {
                    "name": "Claude",
                    "version": "test",
                },
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        },
    }
    headers = {
        "Authorization": f"Bearer {token.access_token}",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "MCP-Method": "server/discover",
        "Origin": "https://claude.ai",
    }

    with TestClient(
        remote.create_app(),
        base_url="https://resource.example.com",
    ) as client_http:
        response = client_http.post("/mcp", json=request, headers=headers)
        follow_up_request = dict(request, id="discover-2")
        follow_up = client_http.post("/mcp", json=follow_up_request, headers=headers)
        health = client_http.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "discover-1"
    assert "2026-07-28" in payload["result"]["supportedVersions"]
    assert follow_up.status_code == 200
    assert follow_up.json()["id"] == "discover-2"
    assert health.status_code == 200
