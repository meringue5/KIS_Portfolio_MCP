"""OAuth authorization server for KIS remote MCP."""

from __future__ import annotations

import base64
import hashlib
from json import JSONDecodeError
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from authlib.integrations.starlette_client import OAuth
from mcp.server.auth.provider import (
    AuthorizeError,
    OAuthClientInformationFull,
    OAuthToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientMetadata
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

from kis_portfolio.adapters.auth.config import AuthServiceSettings
from kis_portfolio.adapters.auth.provider import KisOAuthProvider
from kis_portfolio.platform.state_runtime import get_auth_repository

auth_repository = get_auth_repository()


PENDING_AUTH_SESSION_KEY = "kis.oauth.pending"
USER_SESSION_KEY = "kis.oauth.user_id"
PROVIDER_SESSION_KEY = "kis.oauth.provider"


def _hash_pkce_verifier(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _verify_pkce(verifier: str, challenge: str) -> bool:
    try:
        return _hash_pkce_verifier(verifier) == challenge
    except UnicodeEncodeError:
        return False


def _parse_requested_scope(
    scope_text: str | None,
    allowed_scopes: tuple[str, ...],
) -> str:
    normalized = auth_repository.normalize_scope(scope_text or allowed_scopes)
    requested = set(auth_repository.split_scope(normalized))
    if not requested:
        raise AuthorizeError(
            error="invalid_scope",
            error_description="At least one scope is required.",
        )
    if not requested.issubset(set(allowed_scopes)):
        raise AuthorizeError(
            error="invalid_scope",
            error_description="Requested scope is not supported.",
        )
    return normalized


def _is_allowed_email(settings: AuthServiceSettings, email: str) -> bool:
    return email.strip().lower() in settings.owner_emails


def _extract_google_identity(claims: dict[str, Any]) -> tuple[str, str, str | None, dict[str, Any]]:
    subject = str(claims.get("sub", "")).strip()
    email = str(claims.get("email", "")).strip().lower()
    email_verified = bool(claims.get("email_verified"))
    if not subject or not email or not email_verified:
        raise PermissionError("Google account does not have a verified email.")
    display_name = claims.get("name")
    profile = {
        "sub": subject,
        "email": email,
        "name": display_name,
        "picture": claims.get("picture"),
    }
    return subject, email, display_name, profile


def _extract_github_identity(
    profile: dict[str, Any],
    emails: list[dict[str, Any]],
) -> tuple[str, str, str | None, dict[str, Any]]:
    subject = str(profile.get("id", "")).strip()
    if not subject:
        raise PermissionError("GitHub profile is missing an id.")

    verified_primary = next(
        (
            item for item in emails
            if item.get("primary") and item.get("verified") and item.get("email")
        ),
        None,
    )
    if verified_primary is None:
        raise PermissionError("GitHub account does not have a primary verified email.")

    email = str(verified_primary["email"]).strip().lower()
    display_name = profile.get("name") or profile.get("login")
    snapshot = {
        "id": subject,
        "login": profile.get("login"),
        "name": display_name,
        "avatar_url": profile.get("avatar_url"),
        "html_url": profile.get("html_url"),
        "email": email,
    }
    return subject, email, display_name, snapshot


def _upsert_logged_in_identity(
    *,
    settings: AuthServiceSettings,
    provider: str,
    provider_subject: str,
    email: str,
    display_name: str | None,
    profile_data: dict[str, Any],
) -> dict[str, Any]:
    if not _is_allowed_email(settings, email):
        raise PermissionError("This account is not allowlisted for KIS remote access.")
    identity = auth_repository.upsert_auth_identity(
        provider=provider,
        provider_subject=provider_subject,
        email=email,
        email_verified=True,
        display_name=display_name,
        profile_data=profile_data,
    )
    user = auth_repository.get_auth_user_by_id(identity["user_id"])
    if user is None or not user.get("is_active", True):
        raise PermissionError("This account is not active.")
    return user


def _build_discovery_document(settings: AuthServiceSettings) -> dict[str, Any]:
    return {
        "issuer": settings.base_url,
        "authorization_endpoint": f"{settings.base_url}/authorize",
        "token_endpoint": f"{settings.base_url}/token",
        "registration_endpoint": f"{settings.base_url}/register",
        "revocation_endpoint": f"{settings.base_url}/revoke",
        "scopes_supported": list(settings.allowed_scopes),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "revocation_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
    }


def _provider_callback_url(settings: AuthServiceSettings, provider: str) -> str:
    return f"{settings.base_url}/auth/{provider}/callback"


def _normalize_resource(resource: str | None) -> str | None:
    if not resource:
        return None
    return resource.rstrip("/")


def _validate_client_scope(client_record: dict[str, Any], requested_scope: str) -> None:
    registered_scopes = set(auth_repository.split_scope(client_record.get("scope")))
    if not registered_scopes:
        return
    if not set(auth_repository.split_scope(requested_scope)).issubset(registered_scopes):
        raise AuthorizeError(
            error="invalid_scope",
            error_description="Requested scope is not registered for this client.",
        )


def _validate_dynamic_client_metadata(
    settings: AuthServiceSettings,
    metadata: OAuthClientMetadata,
) -> None:
    for redirect_uri in metadata.redirect_uris:
        redirect_text = str(redirect_uri)
        if not any(
            redirect_text == prefix or redirect_text.startswith(prefix)
            for prefix in settings.dynamic_client_redirect_prefixes
        ):
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description="Dynamic clients may only register ChatGPT callback URLs.",
            )

    if metadata.scope:
        requested = set(auth_repository.split_scope(auth_repository.normalize_scope(metadata.scope)))
        allowed = set(settings.allowed_scopes)
        if not requested or not requested.issubset(allowed):
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Client scope must be a subset of supported scopes.",
            )


def _registration_error_response(error: RegistrationError) -> JSONResponse:
    return JSONResponse(
        {"error": error.error, "error_description": error.error_description},
        status_code=400,
    )


def _merge_query_params(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value is not None})
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))


def _authorization_error_response(
    error: AuthorizeError,
    *,
    redirect_uri: str | None = None,
    state: str | None = None,
) -> Response:
    if redirect_uri:
        url = _merge_query_params(
            redirect_uri,
            {
                "error": error.error,
                "error_description": error.error_description or "",
                "state": state or "",
            },
        )
        return RedirectResponse(url, status_code=302)

    return JSONResponse(
        {"error": error.error, "error_description": error.error_description},
        status_code=400,
    )


def _token_error_response(error: TokenError) -> JSONResponse:
    status_code = 401 if error.error == "invalid_client" else 400
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    if error.error == "invalid_client":
        headers["WWW-Authenticate"] = 'Basic realm="oauth"'
    return JSONResponse(
        {"error": error.error, "error_description": error.error_description},
        status_code=status_code,
        headers=headers,
    )


def _resolve_redirect_uri(
    client_record: dict[str, Any],
    provided_redirect_uri: str | None,
) -> tuple[str, bool]:
    redirect_uris = [str(item) for item in client_record["redirect_uris"]]
    if provided_redirect_uri:
        if provided_redirect_uri not in redirect_uris:
            raise AuthorizeError(
                error="invalid_request",
                error_description="redirect_uri is not registered for this client.",
            )
        return provided_redirect_uri, True

    if len(redirect_uris) == 1:
        return redirect_uris[0], False

    raise AuthorizeError(
        error="invalid_request",
        error_description="redirect_uri is required for this client.",
    )


def _render_html(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      body {{
        margin: 0;
        background: #111827;
        color: #f9fafb;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      main {{
        max-width: 560px;
        margin: 48px auto;
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: 28px;
      }}
      p {{
        line-height: 1.6;
      }}
      .actions {{
        display: flex;
        gap: 12px;
        margin-top: 20px;
        flex-wrap: wrap;
      }}
      a, button {{
        display: inline-block;
        background: #2563eb;
        color: #fff;
        border: 0;
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 15px;
        text-decoration: none;
        cursor: pointer;
      }}
      button.secondary {{
        background: #374151;
      }}
    </style>
  </head>
  <body>
    <main>{body}</main>
  </body>
</html>"""
    return HTMLResponse(html)


def _get_pending_request(request: Request) -> dict[str, Any] | None:
    pending = request.session.get(PENDING_AUTH_SESSION_KEY)
    return pending if isinstance(pending, dict) else None


def _clear_pending_request(request: Request) -> None:
    request.session.pop(PENDING_AUTH_SESSION_KEY, None)


def _load_authorize_params(request: Request, raw_params: dict[str, str]) -> dict[str, Any]:
    params = {key: value for key, value in raw_params.items() if value not in ("", None)}
    pending = _get_pending_request(request)
    if params:
        return {
            "client_id": str(params.get("client_id", "")).strip(),
            "redirect_uri": str(params.get("redirect_uri", "")).strip() or None,
            "response_type": str(params.get("response_type", "")).strip(),
            "scope": str(params.get("scope", "")).strip() or None,
            "resource": str(params.get("resource", "")).strip() or None,
            "state": str(params.get("state", "")).strip() or None,
            "code_challenge": str(params.get("code_challenge", "")).strip(),
            "code_challenge_method": str(params.get("code_challenge_method", "")).strip(),
        }
    if pending is None:
        return {}
    return {
        "client_id": str(pending.get("client_id", "")).strip(),
        "redirect_uri": str(pending.get("redirect_uri", "")).strip() or None,
        "response_type": "code",
        "scope": str(pending.get("scope", "")).strip() or None,
        "resource": str(pending.get("resource", "")).strip() or None,
        "state": str(pending.get("state", "")).strip() or None,
        "code_challenge": str(pending.get("code_challenge", "")).strip(),
        "code_challenge_method": "S256",
    }


async def _parse_client_credentials(request: Request) -> tuple[str, str | None]:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            client_id, client_secret = decoded.split(":", 1)
        except Exception as exc:  # pragma: no cover - defensive parsing
            raise TokenError(
                error="invalid_client",
                error_description="Invalid basic client credentials.",
            ) from exc
        return client_id, client_secret

    form = await request.form()
    client_id = str(form.get("client_id", "")).strip()
    client_secret = str(form.get("client_secret", "")).strip()
    if not client_id:
        raise TokenError(
            error="invalid_client",
            error_description="client_id is required.",
        )
    return client_id, client_secret or None


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def discovery(request: Request) -> JSONResponse:
    settings: AuthServiceSettings = request.app.state.settings
    return JSONResponse(_build_discovery_document(settings))


async def register(request: Request) -> JSONResponse:
    settings: AuthServiceSettings = request.app.state.settings
    provider: KisOAuthProvider = request.app.state.provider
    try:
        payload = await request.json()
        metadata = OAuthClientMetadata.model_validate(payload)
        _validate_dynamic_client_metadata(settings, metadata)
        client = await provider.create_dynamic_client(metadata)
    except RegistrationError as error:
        return _registration_error_response(error)
    except (JSONDecodeError, ValidationError):
        return _registration_error_response(
            RegistrationError(
                error="invalid_client_metadata",
                error_description="Client metadata payload is invalid.",
            )
        )

    response_payload = client.model_dump(mode="json", exclude_none=True)
    response_payload["client_secret_expires_at"] = (
        response_payload.get("client_secret_expires_at") or 0
    )
    return JSONResponse(
        response_payload,
        status_code=201,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


async def authorize(request: Request) -> Response:
    settings: AuthServiceSettings = request.app.state.settings
    provider: KisOAuthProvider = request.app.state.provider
    raw_params = dict(request.query_params)
    if request.method == "POST":
        raw_params.update({key: str(value) for key, value in (await request.form()).items()})
    params = _load_authorize_params(request, raw_params)

    client_id = str(params.get("client_id", "")).strip()
    redirect_uri_hint = str(params.get("redirect_uri", "")).strip() or None
    resource = _normalize_resource(str(params.get("resource", "")).strip() or None)
    state = str(params.get("state", "")).strip() or None

    try:
        if str(params.get("response_type", "")).strip() != "code":
            raise AuthorizeError(
                error="unsupported_response_type",
                error_description="Only response_type=code is supported.",
            )

        client_record = auth_repository.get_oauth_client(client_id)
        if client_record is None:
            raise AuthorizeError(
                error="unauthorized_client",
                error_description="Unknown OAuth client.",
            )
        redirect_uri, redirect_uri_provided_explicitly = _resolve_redirect_uri(
            client_record,
            redirect_uri_hint,
        )
        if params.get("code_challenge_method") != "S256":
            raise AuthorizeError(
                error="invalid_request",
                error_description="Only PKCE S256 is supported.",
            )
        code_challenge = str(params.get("code_challenge", "")).strip()
        if not code_challenge:
            raise AuthorizeError(
                error="invalid_request",
                error_description="code_challenge is required.",
            )
        scope = _parse_requested_scope(params.get("scope"), settings.allowed_scopes)
        _validate_client_scope(client_record, scope)
    except AuthorizeError as error:
        return _authorization_error_response(error, redirect_uri=redirect_uri_hint, state=state)

    pending = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "redirect_uri_provided_explicitly": redirect_uri_provided_explicitly,
        "scope": scope,
        "resource": resource,
        "state": state,
        "code_challenge": code_challenge,
    }
    request.session[PENDING_AUTH_SESSION_KEY] = pending

    user_id = request.session.get(USER_SESSION_KEY)
    if not user_id:
        body = """
<h1>로그인이 필요합니다</h1>
<p>KIS Portfolio Remote에 연결하려면 허용된 계정으로 로그인하세요.</p>
<div class="actions">
  <a href="/login/google">Google로 로그인</a>
  <a href="/login/github">GitHub로 로그인</a>
</div>
"""
        return _render_html("KIS OAuth Login", body)

    grant = auth_repository.get_oauth_grant(user_id, client_id, scope)
    if grant is not None:
        code = await provider.issue_authorization_code(
            user_id=user_id,
            client_id=client_id,
            grant_id=grant["id"],
            scope=scope,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            code_challenge=code_challenge,
            resource=resource,
            state=state,
            provider=str(request.session.get(PROVIDER_SESSION_KEY, "")) or None,
        )
        _clear_pending_request(request)
        return RedirectResponse(
            _merge_query_params(
                redirect_uri,
                {"code": code, "state": state or ""},
            ),
            status_code=302,
        )

    return RedirectResponse("/consent", status_code=302)


async def consent(request: Request) -> Response:
    provider: KisOAuthProvider = request.app.state.provider
    pending = _get_pending_request(request)
    if pending is None:
        return PlainTextResponse("No pending authorization request.", status_code=400)

    user_id = request.session.get(USER_SESSION_KEY)
    if not user_id:
        return RedirectResponse("/authorize", status_code=302)

    client_record = auth_repository.get_oauth_client(pending["client_id"])
    if client_record is None:
        _clear_pending_request(request)
        return PlainTextResponse("Unknown OAuth client.", status_code=400)

    if request.method == "GET":
        resource_line = ""
        if pending.get("resource"):
            resource_line = f"<p>대상 리소스: <code>{pending['resource']}</code></p>"
        body = f"""
<h1>연결을 승인할까요?</h1>
<p><strong>{client_record.get("client_name") or pending["client_id"]}</strong> 가 포트폴리오 조회 권한을 요청했습니다.</p>
<p>허용 범위: <code>{pending["scope"]}</code></p>
{resource_line}
<form method="post">
  <div class="actions">
    <button type="submit" name="decision" value="approve">승인</button>
    <button class="secondary" type="submit" name="decision" value="deny">거부</button>
  </div>
</form>
"""
        return _render_html("KIS OAuth Consent", body)

    form = await request.form()
    decision = str(form.get("decision", "")).strip().lower()
    redirect_uri = pending["redirect_uri"]
    state = pending.get("state")
    if decision != "approve":
        _clear_pending_request(request)
        return RedirectResponse(
            _merge_query_params(
                redirect_uri,
                {"error": "access_denied", "state": state or ""},
            ),
            status_code=302,
        )

    grant = auth_repository.upsert_oauth_grant(user_id, pending["client_id"], pending["scope"])
    code = await provider.issue_authorization_code(
        user_id=user_id,
        client_id=pending["client_id"],
        grant_id=grant["id"],
        scope=pending["scope"],
        redirect_uri=redirect_uri,
        redirect_uri_provided_explicitly=bool(pending["redirect_uri_provided_explicitly"]),
        code_challenge=pending["code_challenge"],
        resource=_normalize_resource(pending.get("resource")),
        state=state,
        provider=str(request.session.get(PROVIDER_SESSION_KEY, "")) or None,
    )
    _clear_pending_request(request)
    return RedirectResponse(
        _merge_query_params(redirect_uri, {"code": code, "state": state or ""}),
        status_code=302,
    )


async def token(request: Request) -> JSONResponse:
    provider: KisOAuthProvider = request.app.state.provider
    try:
        client_id, client_secret = await _parse_client_credentials(request)
        client = await provider.authenticate_client(client_id, client_secret)
        if client is None:
            raise TokenError(
                error="invalid_client",
                error_description="Client authentication failed.",
            )

        form = await request.form()
        grant_type = str(form.get("grant_type", "")).strip()
        if grant_type == "authorization_code":
            authorization_code = str(form.get("code", "")).strip()
            redirect_uri = str(form.get("redirect_uri", "")).strip()
            code_verifier = str(form.get("code_verifier", "")).strip()
            resource = _normalize_resource(str(form.get("resource", "")).strip() or None)
            if not authorization_code or not redirect_uri or not code_verifier:
                raise TokenError(
                    error="invalid_request",
                    error_description="code, redirect_uri, and code_verifier are required.",
                )
            stored_code = await provider.load_authorization_code(client, authorization_code)
            if stored_code is None:
                raise TokenError(
                    error="invalid_grant",
                    error_description="Authorization code is invalid or expired.",
                )
            if redirect_uri != str(stored_code.redirect_uri):
                raise TokenError(
                    error="invalid_grant",
                    error_description="redirect_uri does not match the authorization code.",
                )
            if resource and stored_code.resource and resource != stored_code.resource:
                raise TokenError(
                    error="invalid_grant",
                    error_description="resource does not match the authorization code.",
                )
            if not _verify_pkce(code_verifier, stored_code.code_challenge):
                raise TokenError(
                    error="invalid_grant",
                    error_description="PKCE verification failed.",
                )
            oauth_token = await provider.exchange_authorization_code(
                client,
                stored_code,
                resource=resource,
            )
        elif grant_type == "refresh_token":
            refresh_token = str(form.get("refresh_token", "")).strip()
            scope_text = str(form.get("scope", "")).strip()
            resource = _normalize_resource(str(form.get("resource", "")).strip() or None)
            if not refresh_token:
                raise TokenError(
                    error="invalid_request",
                    error_description="refresh_token is required.",
                )
            stored_refresh_token = await provider.load_refresh_token(client, refresh_token)
            if stored_refresh_token is None:
                raise TokenError(
                    error="invalid_grant",
                    error_description="Refresh token is invalid or expired.",
                )
            if resource and stored_refresh_token.resource and resource != stored_refresh_token.resource:
                raise TokenError(
                    error="invalid_grant",
                    error_description="resource does not match the refresh token.",
                )
            requested_scopes = auth_repository.split_scope(
                auth_repository.normalize_scope(scope_text or stored_refresh_token.scopes)
            )
            oauth_token = await provider.exchange_refresh_token(
                client,
                stored_refresh_token,
                requested_scopes,
                resource=resource,
            )
        else:
            raise TokenError(
                error="unsupported_grant_type",
                error_description="Only authorization_code and refresh_token are supported.",
            )
    except TokenError as error:
        return _token_error_response(error)

    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    return JSONResponse(oauth_token.model_dump(exclude_none=True), headers=headers)


async def revoke(request: Request) -> Response:
    provider: KisOAuthProvider = request.app.state.provider
    try:
        client_id, client_secret = await _parse_client_credentials(request)
        client = await provider.authenticate_client(client_id, client_secret)
        if client is None:
            raise TokenError(
                error="invalid_client",
                error_description="Client authentication failed.",
            )
    except TokenError as error:
        return _token_error_response(error)

    form = await request.form()
    token_value = str(form.get("token", "")).strip()
    if token_value:
        await provider.revoke_token_string(token_value, client_id=client_id)
    return Response(status_code=200)


async def login_google(request: Request) -> Response:
    if _get_pending_request(request) is None:
        return PlainTextResponse("No pending authorization request.", status_code=400)
    settings: AuthServiceSettings = request.app.state.settings
    redirect_uri = _provider_callback_url(settings, "google")
    return await request.app.state.oauth.google.authorize_redirect(request, redirect_uri)


async def login_github(request: Request) -> Response:
    if _get_pending_request(request) is None:
        return PlainTextResponse("No pending authorization request.", status_code=400)
    settings: AuthServiceSettings = request.app.state.settings
    redirect_uri = _provider_callback_url(settings, "github")
    return await request.app.state.oauth.github.authorize_redirect(request, redirect_uri)


async def auth_google_callback(request: Request) -> Response:
    settings: AuthServiceSettings = request.app.state.settings
    if request.query_params.get("error"):
        return PlainTextResponse("Google login failed.", status_code=400)

    token_data = await request.app.state.oauth.google.authorize_access_token(request)
    claims = token_data.get("userinfo")
    if claims is None:
        claims = await request.app.state.oauth.google.parse_id_token(request, token_data)

    try:
        subject, email, display_name, profile = _extract_google_identity(dict(claims))
        user = _upsert_logged_in_identity(
            settings=settings,
            provider="google",
            provider_subject=subject,
            email=email,
            display_name=display_name,
            profile_data=profile,
        )
    except PermissionError as error:
        return PlainTextResponse(str(error), status_code=403)

    request.session[USER_SESSION_KEY] = user["id"]
    request.session[PROVIDER_SESSION_KEY] = "google"
    return RedirectResponse("/authorize", status_code=302)


async def auth_github_callback(request: Request) -> Response:
    settings: AuthServiceSettings = request.app.state.settings
    if request.query_params.get("error"):
        return PlainTextResponse("GitHub login failed.", status_code=400)

    token_data = await request.app.state.oauth.github.authorize_access_token(request)
    profile_response = await request.app.state.oauth.github.get("user", token=token_data)
    emails_response = await request.app.state.oauth.github.get("user/emails", token=token_data)

    try:
        subject, email, display_name, profile = _extract_github_identity(
            dict(profile_response.json()),
            list(emails_response.json()),
        )
        user = _upsert_logged_in_identity(
            settings=settings,
            provider="github",
            provider_subject=subject,
            email=email,
            display_name=display_name,
            profile_data=profile,
        )
    except PermissionError as error:
        return PlainTextResponse(str(error), status_code=403)

    request.session[USER_SESSION_KEY] = user["id"]
    request.session[PROVIDER_SESSION_KEY] = "github"
    return RedirectResponse("/authorize", status_code=302)


def create_app(
    settings: AuthServiceSettings | None = None,
    provider: KisOAuthProvider | None = None,
) -> Starlette:
    settings = settings or AuthServiceSettings.from_env()
    provider = provider or KisOAuthProvider(
        token_pepper=settings.token_pepper,
        ttl=None,
        static_client=settings.claude_client,
    )

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    oauth.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )

    app = Starlette(
        debug=False,
        routes=[
            Route("/health", health),
            # Some MCP connector clients probe the OIDC discovery alias before
            # falling back to the OAuth authorization server metadata route.
            Route("/.well-known/openid-configuration", discovery),
            Route("/.well-known/oauth-authorization-server", discovery),
            Route("/register", register, methods=["POST"]),
            Route("/authorize", authorize, methods=["GET", "POST"]),
            Route("/token", token, methods=["POST"]),
            Route("/revoke", revoke, methods=["POST"]),
            Route("/login/google", login_google),
            Route("/login/github", login_github),
            Route("/auth/google/callback", auth_google_callback, name="auth_google_callback"),
            Route("/auth/github/callback", auth_github_callback, name="auth_github_callback"),
            Route("/consent", consent, methods=["GET", "POST"]),
        ],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=settings.secure_cookies,
    )
    app.state.settings = settings
    app.state.provider = provider
    app.state.oauth = oauth
    return app


def main() -> None:
    import os
    import uvicorn

    host = os.environ.get("KIS_AUTH_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("KIS_AUTH_PORT", "8001")))
    uvicorn.run("kis_portfolio.adapters.auth:create_app", host=host, port=port, factory=True)
