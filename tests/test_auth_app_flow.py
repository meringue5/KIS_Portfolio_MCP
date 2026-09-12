from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from kis_portfolio.adapters.auth.app import create_app
from kis_portfolio.adapters.auth.config import AuthServiceSettings, StaticOAuthClientConfig
from kis_portfolio.adapters.auth.provider import KisOAuthProvider
from kis_portfolio.db import auth_repository, close_connection


def _settings(base_url: str = "http://testserver") -> AuthServiceSettings:
    return AuthServiceSettings(
        base_url=base_url,
        owner_emails=("owner@example.com",),
        session_secret="session-secret",
        token_pepper="pepper",
        claude_client_id="claude-client",
        claude_client_secret="claude-secret",
        google_client_id="google-client",
        google_client_secret="google-secret",
        github_client_id="github-client",
        github_client_secret="github-secret",
        secure_cookies=False,
    )


def _provider() -> KisOAuthProvider:
    settings = _settings()
    return KisOAuthProvider(
        token_pepper=settings.token_pepper,
        static_client=StaticOAuthClientConfig(
            client_id=settings.claude_client_id,
            client_secret=settings.claude_client_secret,
            client_name="Claude",
            redirect_uris=("https://claude.ai/api/mcp/auth_callback",),
            scope="mcp:read",
        ),
    )


def test_authorize_resumes_pending_request_after_login(monkeypatch, tmp_path):
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))

    settings = _settings()
    provider = _provider()
    user = auth_repository.upsert_auth_user("owner@example.com", "Owner")
    app = create_app(settings=settings, provider=provider)

    async def force_login(request):
        request.session["kis.oauth.user_id"] = user["id"]
        request.session["kis.oauth.provider"] = "google"
        return PlainTextResponse("ok")

    app.router.routes.append(Route("/_test/login", force_login))

    with TestClient(app) as client:
        initial = client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": "claude-client",
                "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
                "scope": "mcp:read",
                "resource": "https://resource.example.com/mcp",
                "state": "state-1",
                "code_challenge": "challenge-1",
                "code_challenge_method": "S256",
            },
        )
        assert initial.status_code == 200
        assert "Google" in initial.text

        login = client.get("/_test/login")
        assert login.status_code == 200

        consent_redirect = client.get("/authorize", follow_redirects=False)
        assert consent_redirect.status_code == 302
        assert consent_redirect.headers["location"] == "/consent"

        approve = client.post("/consent", data={"decision": "approve"}, follow_redirects=False)
        assert approve.status_code == 302
        redirected = urlparse(approve.headers["location"])
        assert redirected.scheme == "https"
        assert redirected.netloc == "claude.ai"
        query = parse_qs(redirected.query)
        assert query["state"] == ["state-1"]
        assert "code" in query and query["code"][0]

    close_connection()


def test_google_login_uses_configured_https_callback(monkeypatch, tmp_path):
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))

    class CapturingOAuthClient:
        def __init__(self):
            self.redirect_uri = None

        async def authorize_redirect(self, request, redirect_uri):
            self.redirect_uri = redirect_uri
            return PlainTextResponse("ok")

    settings = _settings(base_url="https://auth.example.com")
    provider = _provider()
    app = create_app(settings=settings, provider=provider)
    google = CapturingOAuthClient()
    app.state.oauth.google = google

    with TestClient(app) as client:
        initial = client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": "claude-client",
                "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
                "scope": "mcp:read",
                "state": "state-1",
                "code_challenge": "challenge-1",
                "code_challenge_method": "S256",
            },
        )
        assert initial.status_code == 200

        login = client.get("/login/google")
        assert login.status_code == 200

    assert google.redirect_uri == "https://auth.example.com/auth/google/callback"
    close_connection()


def test_dynamic_client_registration_issues_chatgpt_client(monkeypatch, tmp_path):
    close_connection()


def test_dynamic_client_registration_accepts_exact_claude_callback(monkeypatch, tmp_path):
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))
    app = create_app(settings=_settings(), provider=_provider())

    with TestClient(app) as client:
        response = client.post(
            "/register",
            json={
                "client_name": "Claude",
                "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
                "scope": "mcp:read",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["client_secret"]
    assert payload["redirect_uris"] == ["https://claude.ai/api/mcp/auth_callback"]
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))

    app = create_app(settings=_settings(), provider=_provider())

    with TestClient(app) as client:
        response = client.post(
            "/register",
            json={
                "client_name": "ChatGPT Connector",
                "redirect_uris": ["https://chatgpt.com/connector/oauth/callback-123"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
                "scope": "mcp:read",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["client_id"].startswith("kis-chatgpt-")
    assert payload["client_secret"]
    assert payload["token_endpoint_auth_method"] == "client_secret_post"
    assert payload["client_secret_expires_at"] == 0
    stored = auth_repository.get_oauth_client(payload["client_id"])
    assert stored is not None
    assert stored["client_name"] == "ChatGPT Connector"
    close_connection()


def test_openid_configuration_alias_matches_oauth_discovery(monkeypatch, tmp_path):
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))

    app = create_app(settings=_settings(), provider=_provider())

    with TestClient(app) as client:
        oidc = client.get("/.well-known/openid-configuration")
        oauth = client.get("/.well-known/oauth-authorization-server")

    assert oidc.status_code == 200
    assert oauth.status_code == 200
    assert oidc.json() == oauth.json()
    close_connection()


def test_dynamic_client_registration_rejects_untrusted_redirect_uri(monkeypatch, tmp_path):
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))

    app = create_app(settings=_settings(), provider=_provider())

    with TestClient(app) as client:
        response = client.post(
            "/register",
            json={
                "client_name": "Nope",
                "redirect_uris": ["https://evil.example.com/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"
    close_connection()
