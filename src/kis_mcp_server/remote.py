"""Remote Streamable HTTP MCP entrypoint."""

import hmac
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from kis_mcp_server.app import mcp


class SharedBearerAuthMiddleware:
    """Protect remote MCP routes with a shared bearer token."""

    def __init__(
        self,
        app: ASGIApp,
        token: str,
        protected_prefixes: tuple[str, ...] = ("/mcp",),
        allow_paths: tuple[str, ...] = ("/healthz",),
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


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app() -> Starlette:
    """Create the remote MCP ASGI app.

    Remote deployments require KIS_REMOTE_AUTH_TOKEN by default. Use
    KIS_REMOTE_AUTH_DISABLED=true only for local tunnel experiments.
    """
    auth_disabled = os.environ.get("KIS_REMOTE_AUTH_DISABLED", "").lower() == "true"
    auth_token = os.environ.get("KIS_REMOTE_AUTH_TOKEN", "")
    if not auth_disabled and not auth_token:
        raise RuntimeError("KIS_REMOTE_AUTH_TOKEN is required for remote MCP")

    app = mcp.streamable_http_app()
    app.routes.append(Route("/healthz", healthz, methods=["GET"]))

    if not auth_disabled:
        app.add_middleware(SharedBearerAuthMiddleware, token=auth_token)

    return app


def main() -> None:
    import uvicorn

    host = os.environ.get("KIS_REMOTE_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("KIS_REMOTE_PORT", "8000")))
    uvicorn.run("kis_mcp_server.remote:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
