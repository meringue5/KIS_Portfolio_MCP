from __future__ import annotations

import asyncio

import pytest
from mcp.shared.auth import OAuthClientMetadata

from kis_portfolio.adapters.auth.app import (
    _extract_github_identity,
    _extract_google_identity,
    _is_allowed_email,
    _verify_pkce,
)
from kis_portfolio.adapters.auth.config import AuthServiceSettings, StaticOAuthClientConfig
from kis_portfolio.adapters.auth.provider import KisOAuthProvider, OAuthTTLConfig
from kis_portfolio.db import auth_repository, close_connection


@pytest.fixture(autouse=True)
def local_db(monkeypatch, tmp_path):
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))
    yield
    close_connection()


def _settings() -> AuthServiceSettings:
    return AuthServiceSettings(
        base_url="http://testserver",
        owner_emails=("owner@example.com",),
        session_secret="session-secret",
        token_pepper="pepper",
        claude_client_id="claude-client",
        claude_client_secret="claude-secret",
        google_client_id="google-client",
        google_client_secret="google-secret",
        github_client_id="github-client",
        github_client_secret="github-secret",
        resource_server_url="https://resource.example.com/mcp",
        secure_cookies=False,
    )


def _provider() -> KisOAuthProvider:
    settings = _settings()
    return KisOAuthProvider(
        token_pepper=settings.token_pepper,
        ttl=OAuthTTLConfig(
            access_token_ttl_seconds=900,
            refresh_token_ttl_seconds=3600,
            authorization_code_ttl_seconds=600,
        ),
        static_client=StaticOAuthClientConfig(
            client_id=settings.claude_client_id,
            client_secret=settings.claude_client_secret,
            client_name="Claude",
            redirect_uris=("https://claude.ai/api/mcp/auth_callback",),
            scope="mcp:read",
        ),
    )


def test_authorization_code_one_time_use():
    provider = _provider()
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
        state="state1",
        provider="google",
    ))

    loaded = asyncio.run(provider.load_authorization_code(client, code))
    assert loaded is not None
    assert loaded.subject == user["id"]

    token = asyncio.run(provider.exchange_authorization_code(client, loaded))
    assert token.refresh_token

    loaded_again = asyncio.run(provider.load_authorization_code(client, code))
    assert loaded_again is None


def test_refresh_token_rotation_revokes_old_refresh_token():
    provider = _provider()
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
        state=None,
        provider="google",
    ))
    loaded = asyncio.run(provider.load_authorization_code(client, code))
    assert loaded is not None
    initial = asyncio.run(provider.exchange_authorization_code(client, loaded))

    refresh = asyncio.run(provider.load_refresh_token(client, initial.refresh_token or ""))
    assert refresh is not None

    rotated = asyncio.run(provider.exchange_refresh_token(client, refresh, ["mcp:read"]))
    assert rotated.refresh_token
    assert rotated.refresh_token != initial.refresh_token

    old_refresh = asyncio.run(provider.load_refresh_token(client, initial.refresh_token or ""))
    new_refresh = asyncio.run(provider.load_refresh_token(client, rotated.refresh_token or ""))
    assert old_refresh is None
    assert new_refresh is not None


def test_revoked_access_token_is_rejected():
    provider = _provider()
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
        state=None,
        provider="google",
    ))
    loaded = asyncio.run(provider.load_authorization_code(client, code))
    assert loaded is not None
    token = asyncio.run(provider.exchange_authorization_code(client, loaded))
    access_value = token.access_token

    access = asyncio.run(provider.load_access_token(access_value))
    assert access is not None
    asyncio.run(provider.revoke_token(access))
    assert asyncio.run(provider.load_access_token(access_value)) is None


def test_allowlist_and_provider_identity_helpers():
    settings = _settings()
    assert _is_allowed_email(settings, "OWNER@example.com")
    assert not _is_allowed_email(settings, "other@example.com")

    subject, email, display_name, profile = _extract_google_identity({
        "sub": "google-sub",
        "email": "owner@example.com",
        "email_verified": True,
        "name": "Owner",
        "picture": "https://example.com/me.png",
    })
    assert subject == "google-sub"
    assert email == "owner@example.com"
    assert display_name == "Owner"
    assert profile["picture"] == "https://example.com/me.png"

    gh_subject, gh_email, gh_name, gh_profile = _extract_github_identity(
        {"id": 123, "login": "owner", "name": "Owner"},
        [
            {"email": "owner@example.com", "verified": True, "primary": True},
            {"email": "secondary@example.com", "verified": True, "primary": False},
        ],
    )
    assert gh_subject == "123"
    assert gh_email == "owner@example.com"
    assert gh_name == "Owner"
    assert gh_profile["login"] == "owner"


def test_pkce_verifier_mismatch_is_detected():
    assert _verify_pkce("verifier-123", "not-the-right-challenge") is False


def test_dynamic_client_resource_binding_is_preserved():
    provider = _provider()
    dynamic_client = asyncio.run(provider.create_dynamic_client(
        OAuthClientMetadata(
            redirect_uris=["https://chatgpt.com/connector/oauth/callback-123"],
            token_endpoint_auth_method="client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope="mcp:read",
            client_name="ChatGPT Connector",
        )
    ))

    user = auth_repository.upsert_auth_user("owner@example.com", "Owner")
    grant = auth_repository.upsert_oauth_grant(user["id"], dynamic_client.client_id, "mcp:read")
    client = asyncio.run(provider.get_client(dynamic_client.client_id))
    assert client is not None

    code = asyncio.run(provider.issue_authorization_code(
        user_id=user["id"],
        client_id=dynamic_client.client_id,
        grant_id=grant["id"],
        scope="mcp:read",
        redirect_uri="https://chatgpt.com/connector/oauth/callback-123",
        redirect_uri_provided_explicitly=True,
        code_challenge="challenge",
        resource="https://resource.example.com/mcp",
        state="state1",
        provider="google",
    ))
    loaded = asyncio.run(provider.load_authorization_code(client, code))
    assert loaded is not None
    assert loaded.resource == "https://resource.example.com/mcp"

    token = asyncio.run(
        provider.exchange_authorization_code(
            client,
            loaded,
            resource="https://resource.example.com/mcp",
        )
    )
    access = asyncio.run(provider.load_access_token(token.access_token))
    refresh = asyncio.run(provider.load_refresh_token(client, token.refresh_token or ""))
    assert access is not None
    assert access.subject == user["id"]
    assert access.resource == "https://resource.example.com/mcp"
    assert refresh is not None
    assert refresh.subject == user["id"]
    assert refresh.resource == "https://resource.example.com/mcp"


def test_resource_bound_provider_rejects_unbound_access_token():
    issuer = _provider()
    user = auth_repository.upsert_auth_user("owner@example.com", "Owner")
    grant = auth_repository.upsert_oauth_grant(user["id"], "claude-client", "mcp:read")
    client = asyncio.run(issuer.get_client("claude-client"))
    assert client is not None
    code = asyncio.run(issuer.issue_authorization_code(
        user_id=user["id"],
        client_id="claude-client",
        grant_id=grant["id"],
        scope="mcp:read",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        redirect_uri_provided_explicitly=True,
        code_challenge="challenge",
        resource=None,
    ))
    stored = asyncio.run(issuer.load_authorization_code(client, code))
    token = asyncio.run(issuer.exchange_authorization_code(client, stored))
    verifier = KisOAuthProvider(
        token_pepper="pepper",
        resource_server_url="https://resource.example.com/mcp",
    )

    assert asyncio.run(verifier.load_access_token(token.access_token)) is None
