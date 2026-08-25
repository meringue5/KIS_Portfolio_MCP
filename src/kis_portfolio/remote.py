"""Remote Streamable HTTP MCP entrypoint."""

from __future__ import annotations

import hmac
import os
from urllib.parse import urlsplit

import httpx
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from kis_portfolio.adapters.auth.provider import KisOAuthProvider
from kis_portfolio.adapters.mcp import build_mcp_server
from kis_portfolio.config import (
    get_auth_allowed_scopes,
    get_auth_issuer_url,
    get_auth_required_scopes,
    get_auth_token_pepper,
    get_remote_auth_mode,
    get_resource_server_url,
)


class SharedBearerAuthMiddleware:
    """Protect remote MCP routes with a shared bearer token."""

    def __init__(
        self,
        app: ASGIApp,
        token: str,
        protected_prefixes: tuple[str, ...] = ("/mcp",),
        allow_paths: tuple[str, ...] = ("/health", "/healthz"),
    ) -> None:
        self.app = app
        self.token = token
        self.protected_prefixes = protected_prefixes
        self.allow_paths = allow_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.allow_paths or not path.startswith(self.protected_prefixes):
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        expected = f"Bearer {self.token}"
        if not hmac.compare_digest(headers.get("authorization", ""), expected):
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


async def _health(_: object) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _strip_trailing_slash(url: str) -> str:
    return url.rstrip("/")


def _origin_from_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _auth_server_metadata(issuer_url: str, scopes: list[str]) -> dict[str, object]:
    issuer = _strip_trailing_slash(issuer_url)
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
        "revocation_endpoint": f"{issuer}/revoke",
        "scopes_supported": scopes,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "revocation_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
    }


def _protected_resource_metadata(
    *,
    issuer_url: str,
    resource_server_url: str,
    scopes: list[str],
) -> dict[str, object]:
    return {
        "resource": _strip_trailing_slash(resource_server_url),
        "authorization_servers": [_strip_trailing_slash(issuer_url)],
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
    }


def _resource_metadata_url(resource_server_url: str) -> str:
    return f"{_origin_from_url(resource_server_url)}/.well-known/oauth-protected-resource/mcp"


def _oauth_challenge(
    *,
    status_code: int,
    resource_server_url: str,
    scopes: list[str],
) -> str:
    parts = [
        f'resource_metadata="{_resource_metadata_url(resource_server_url)}"',
    ]
    if scopes:
        parts.append(f'scope="{" ".join(scopes)}"')
    if status_code == 403:
        parts.insert(0, 'error="insufficient_scope"')
    return "Bearer " + ", ".join(parts)


class OAuthChallengeMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        resource_server_url: str,
        required_scopes: list[str],
    ) -> None:
        self.app = app
        self.resource_server_url = resource_server_url
        self.required_scopes = required_scopes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await self.app(scope, receive, send)
        except HTTPException as error:
            if error.status_code not in (401, 403):
                raise
            response = JSONResponse(
                {"error": "unauthorized" if error.status_code == 401 else "insufficient_scope"},
                status_code=error.status_code,
                headers={
                    "WWW-Authenticate": _oauth_challenge(
                        status_code=error.status_code,
                        resource_server_url=self.resource_server_url,
                        scopes=self.required_scopes,
                    ),
                },
            )
            await response(scope, receive, send)


class ExactPathMCPApp:
    def __init__(self, app: ASGIApp, mount_path: str = "/mcp") -> None:
        self.app = app
        self.mount_path = mount_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        child_scope = dict(scope)
        root_path = scope.get("root_path", "")
        child_scope["root_path"] = f"{root_path}{self.mount_path}"
        child_scope["path"] = "/"
        child_scope["raw_path"] = b"/"
        await self.app(child_scope, receive, send)


def _transport_security(resource_server_url: str | None) -> TransportSecuritySettings:
    if not resource_server_url:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    parts = urlsplit(resource_server_url)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[parts.netloc],
        allowed_origins=[
            _origin_from_url(resource_server_url),
            "https://claude.ai",
            "https://claude.com",
        ],
    )


def _create_mcp_handler(resource_server_url: str | None = None) -> tuple[ASGIApp, object]:
    server = build_mcp_server()
    server.streamable_http_app(
        transport_security=_transport_security(resource_server_url),
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await server.session_manager.handle_request(scope, receive, send)

    return handle_streamable_http, server


def _build_bearer_app(auth_token: str) -> ASGIApp:
    mcp_handler, server = _create_mcp_handler(get_resource_server_url())
    exact_mcp_handler = ExactPathMCPApp(mcp_handler)
    app = Starlette(
        routes=[
            Route("/health", _health),
            Route("/healthz", _health),
            Route("/mcp", endpoint=exact_mcp_handler),
            Mount("/mcp", app=mcp_handler),
        ],
        lifespan=lambda app: server.session_manager.run(),
    )
    return SharedBearerAuthMiddleware(app, token=auth_token)


async def _remote_auth_server_metadata(request: Request) -> JSONResponse:
    return JSONResponse(
        _auth_server_metadata(
            _strip_trailing_slash(request.app.state.auth_issuer_url),
            list(request.app.state.supported_scopes),
        )
    )


async def _remote_protected_resource_metadata(request: Request) -> JSONResponse:
    return JSONResponse(
        _protected_resource_metadata(
            issuer_url=request.app.state.auth_issuer_url,
            resource_server_url=request.app.state.resource_server_url,
            scopes=list(request.app.state.required_scopes),
        )
    )


async def _redirect_to_authorization_server(request: Request) -> RedirectResponse:
    issuer = _strip_trailing_slash(request.app.state.auth_issuer_url)
    query = request.url.query
    target = f"{issuer}/authorize"
    if query:
        target = f"{target}?{query}"
    status_code = 307 if request.method == "POST" else 302
    return RedirectResponse(target, status_code=status_code)


async def _proxy_to_authorization_server(request: Request) -> Response:
    issuer = _strip_trailing_slash(request.app.state.auth_issuer_url)
    target = f"{issuer}{request.url.path}"
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in {"authorization", "content-type", "accept"}
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        upstream = await client.request(
            request.method,
            target,
            content=body,
            headers=headers,
        )

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {
            "cache-control",
            "pragma",
            "www-authenticate",
            "content-type",
        }
    }
    return Response(
        upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


def _build_oauth_app() -> ASGIApp:
    issuer_url = get_auth_issuer_url()
    if not issuer_url:
        raise RuntimeError("KIS_AUTH_ISSUER_URL is required for oauth remote auth mode")
    resource_server_url = get_resource_server_url()
    if not resource_server_url:
        raise RuntimeError("KIS_RESOURCE_SERVER_URL is required for oauth remote auth mode")

    token_pepper = get_auth_token_pepper()
    required_scopes = get_auth_required_scopes()
    supported_scopes = get_auth_allowed_scopes()
    provider = KisOAuthProvider(
        token_pepper=token_pepper,
        resource_server_url=resource_server_url,
    )
    mcp_handler, server = _create_mcp_handler(resource_server_url)
    protected_mcp_handler = OAuthChallengeMiddleware(
        RequireAuthMiddleware(
            mcp_handler,
            required_scopes,
            AnyHttpUrl(_resource_metadata_url(resource_server_url)),
        ),
        resource_server_url=resource_server_url,
        required_scopes=required_scopes,
    )
    exact_mcp_handler = ExactPathMCPApp(protected_mcp_handler)

    app = Starlette(
        routes=[
            Route("/health", _health),
            Route("/healthz", _health),
            Route(
                "/.well-known/oauth-protected-resource",
                _remote_protected_resource_metadata,
            ),
            Route(
                "/.well-known/oauth-protected-resource/mcp",
                _remote_protected_resource_metadata,
            ),
            Route(
                "/.well-known/oauth-authorization-server",
                _remote_auth_server_metadata,
            ),
            Route("/authorize", _redirect_to_authorization_server, methods=["GET", "POST"]),
            Route("/register", _proxy_to_authorization_server, methods=["POST"]),
            Route("/token", _proxy_to_authorization_server, methods=["POST"]),
            Route("/revoke", _proxy_to_authorization_server, methods=["POST"]),
            Route("/mcp", endpoint=exact_mcp_handler),
            Mount(
                "/mcp",
                app=protected_mcp_handler,
            ),
        ],
        middleware=[
            Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(provider)),
            Middleware(AuthContextMiddleware),
        ],
        lifespan=lambda app: server.session_manager.run(),
    )
    app.state.auth_issuer_url = _strip_trailing_slash(issuer_url)
    app.state.resource_server_url = _strip_trailing_slash(resource_server_url)
    app.state.required_scopes = required_scopes
    app.state.supported_scopes = supported_scopes
    return app


def create_app() -> ASGIApp:
    """Create the remote MCP ASGI app.

    Remote deployments require KIS_REMOTE_AUTH_TOKEN by default. Use
    KIS_REMOTE_AUTH_DISABLED=true only for local tunnel experiments.
    """
    if os.environ.get("KIS_REMOTE_AUTH_DISABLED", "").lower() == "true":
        auth_mode = "disabled"
    else:
        auth_mode = get_remote_auth_mode()

    if auth_mode == "disabled":
        mcp_handler, server = _create_mcp_handler()
        exact_mcp_handler = ExactPathMCPApp(mcp_handler)
        return Starlette(
            routes=[
                Route("/health", _health),
                Route("/healthz", _health),
                Route("/mcp", endpoint=exact_mcp_handler),
                Mount("/mcp", app=mcp_handler),
            ],
            lifespan=lambda app: server.session_manager.run(),
        )

    if auth_mode == "oauth":
        return _build_oauth_app()

    auth_token = os.environ.get("KIS_REMOTE_AUTH_TOKEN", "")
    if not auth_token:
        raise RuntimeError("KIS_REMOTE_AUTH_TOKEN is required for bearer remote auth mode")
    return _build_bearer_app(auth_token)


def main() -> None:
    import uvicorn

    host = os.environ.get("KIS_REMOTE_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("KIS_REMOTE_PORT", "8000")))
    uvicorn.run("kis_portfolio.remote:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
