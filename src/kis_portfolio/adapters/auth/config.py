"""Configuration helpers for the OAuth authorization server."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_ALLOWED_SCOPES = ("mcp:read", "offline_access")
DEFAULT_CLAUDE_REDIRECT_URIS = (
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
)
DEFAULT_DYNAMIC_CLIENT_REDIRECT_PREFIXES = (
    "https://chatgpt.com/connector/oauth/",
    "https://chatgpt.com/connector_platform_oauth_redirect",
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for OAuth auth server")
    return value


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_scopes(value: str) -> tuple[str, ...]:
    normalized = value.replace(",", " ")
    return tuple(dict.fromkeys(part.strip() for part in normalized.split() if part.strip()))


@dataclass(frozen=True)
class AuthServiceSettings:
    base_url: str
    owner_emails: tuple[str, ...]
    session_secret: str
    token_pepper: str
    claude_client_id: str
    claude_client_secret: str
    google_client_id: str
    google_client_secret: str
    github_client_id: str
    github_client_secret: str
    allowed_scopes: tuple[str, ...] = DEFAULT_ALLOWED_SCOPES
    dynamic_client_redirect_prefixes: tuple[str, ...] = DEFAULT_DYNAMIC_CLIENT_REDIRECT_PREFIXES
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60
    authorization_code_ttl_seconds: int = 10 * 60
    secure_cookies: bool = True

    @classmethod
    def from_env(cls) -> "AuthServiceSettings":
        base_url = _require_env("KIS_AUTH_BASE_URL").rstrip("/")
        owner_emails = tuple(
            email.lower()
            for email in _parse_csv(_require_env("KIS_AUTH_OWNER_EMAILS"))
        )
        return cls(
            base_url=base_url,
            owner_emails=owner_emails,
            session_secret=_require_env("KIS_AUTH_SESSION_SECRET"),
            token_pepper=_require_env("KIS_AUTH_TOKEN_PEPPER"),
            claude_client_id=_require_env("KIS_AUTH_CLAUDE_CLIENT_ID"),
            claude_client_secret=_require_env("KIS_AUTH_CLAUDE_CLIENT_SECRET"),
            google_client_id=_require_env("KIS_OAUTH_GOOGLE_CLIENT_ID"),
            google_client_secret=_require_env("KIS_OAUTH_GOOGLE_CLIENT_SECRET"),
            github_client_id=_require_env("KIS_OAUTH_GITHUB_CLIENT_ID"),
            github_client_secret=_require_env("KIS_OAUTH_GITHUB_CLIENT_SECRET"),
            allowed_scopes=(
                _parse_scopes(os.environ["KIS_AUTH_ALLOWED_SCOPES"])
                if os.environ.get("KIS_AUTH_ALLOWED_SCOPES", "").strip()
                else DEFAULT_ALLOWED_SCOPES
            ),
            dynamic_client_redirect_prefixes=(
                _parse_csv(os.environ["KIS_AUTH_DYNAMIC_CLIENT_REDIRECT_PREFIXES"])
                if os.environ.get("KIS_AUTH_DYNAMIC_CLIENT_REDIRECT_PREFIXES", "").strip()
                else DEFAULT_DYNAMIC_CLIENT_REDIRECT_PREFIXES
            ),
            secure_cookies=base_url.startswith("https://"),
        )

    @property
    def claude_redirect_uris(self) -> tuple[str, ...]:
        value = os.environ.get("KIS_AUTH_CLAUDE_REDIRECT_URIS", "").strip()
        if not value:
            return DEFAULT_CLAUDE_REDIRECT_URIS
        return _parse_csv(value)

    @property
    def allowed_scope_text(self) -> str:
        return " ".join(self.allowed_scopes)

    @property
    def claude_client(self) -> "StaticOAuthClientConfig":
        return StaticOAuthClientConfig(
            client_id=self.claude_client_id,
            client_secret=self.claude_client_secret,
            client_name="Claude",
            redirect_uris=self.claude_redirect_uris,
            scope=self.allowed_scope_text,
            token_endpoint_auth_method="client_secret_basic",
        )


@dataclass(frozen=True)
class StaticOAuthClientConfig:
    client_id: str
    client_secret: str
    client_name: str
    redirect_uris: tuple[str, ...]
    scope: str
    token_endpoint_auth_method: str = "client_secret_basic"
