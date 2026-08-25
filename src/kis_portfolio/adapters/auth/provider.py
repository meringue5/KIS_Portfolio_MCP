"""OAuth provider backed by DuckDB/MotherDuck state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    RegistrationError,
    OAuthClientInformationFull,
    OAuthToken,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientMetadata

from kis_portfolio.adapters.auth.config import StaticOAuthClientConfig
from kis_portfolio.db import auth_repository
from kis_portfolio.security.oauth_crypto import (
    digest_token,
    generate_token,
    hash_client_secret,
    verify_client_secret,
)


def _to_timestamp(value: datetime | None) -> int | None:
    if value is None:
        return None
    return int(value.replace(tzinfo=UTC).timestamp())


def _from_timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    return value.replace(tzinfo=UTC).timestamp()


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _normalize_resource(resource: str | None) -> str | None:
    if not resource:
        return None
    return resource.rstrip("/")


@dataclass(frozen=True)
class OAuthTTLConfig:
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60
    authorization_code_ttl_seconds: int = 10 * 60


class StoredAuthorizationCode(AuthorizationCode):
    id: str
    user_id: str
    grant_id: str | None = None
    state: str | None = None
    provider: str | None = None
    resource: str | None = None


class StoredRefreshToken(RefreshToken):
    id: str
    user_id: str
    grant_id: str | None = None
    resource: str | None = None


class StoredAccessToken(AccessToken):
    id: str
    user_id: str
    grant_id: str | None = None
    resource: str | None = None


class KisOAuthProvider:
    """Opaque-token OAuth storage and verifier for KIS remote auth."""

    def __init__(
        self,
        *,
        token_pepper: str,
        resource_server_url: str | None = None,
        ttl: OAuthTTLConfig | None = None,
        static_client: StaticOAuthClientConfig | None = None,
    ) -> None:
        if not token_pepper:
            raise RuntimeError("KIS_AUTH_TOKEN_PEPPER is required for OAuth")

        self.token_pepper = token_pepper
        self.resource_server_url = _normalize_resource(resource_server_url)
        self.ttl = ttl or OAuthTTLConfig()
        self.static_client = static_client
        if static_client is not None:
            self.bootstrap_static_client(static_client)

    def _metadata_from_record(self, record: dict[str, object]) -> dict[str, object]:
        metadata = dict(record.get("metadata") or {})
        for key in (
            "client_uri",
            "logo_uri",
            "contacts",
            "tos_uri",
            "policy_uri",
            "jwks_uri",
            "jwks",
            "software_id",
            "software_version",
        ):
            if key in metadata and metadata[key] is None:
                metadata.pop(key, None)
        return metadata

    def _build_client_info(
        self,
        record: dict[str, object],
        *,
        client_secret: str | None = None,
    ) -> OAuthClientInformationFull:
        auth_method = record.get("token_endpoint_auth_method") or "client_secret_post"
        if auth_method not in {"none", "client_secret_post"}:
            auth_method = "client_secret_post"
        extras = self._metadata_from_record(record)
        secret_expires_at = _to_timestamp(record.get("client_secret_expires_at")) or 0
        return OAuthClientInformationFull(
            client_id=record["client_id"],
            client_secret=client_secret,
            redirect_uris=record["redirect_uris"],
            grant_types=record["grant_types"],
            response_types=record["response_types"],
            scope=record.get("scope"),
            client_name=record.get("client_name"),
            token_endpoint_auth_method=auth_method,
            client_id_issued_at=_to_timestamp(record.get("client_id_issued_at")),
            client_secret_expires_at=secret_expires_at,
            **extras,
        )

    def bootstrap_static_client(self, client: StaticOAuthClientConfig) -> None:
        auth_repository.upsert_oauth_client(
            client_id=client.client_id,
            client_secret_hash=hash_client_secret(client.client_secret),
            redirect_uris=list(client.redirect_uris),
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=client.scope,
            client_name=client.client_name,
            token_endpoint_auth_method=client.token_endpoint_auth_method,
            metadata=None,
            client_id_issued_at=_utcnow(),
            client_secret_expires_at=None,
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        record = auth_repository.get_oauth_client(client_id)
        if record is None:
            return None

        return self._build_client_info(record)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        metadata = client_info.model_dump(exclude_none=True)
        client_secret = metadata.pop("client_secret", None)
        if client_secret is None:
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="client_secret is required for registered clients.",
            )
        auth_repository.upsert_oauth_client(
            client_id=client_info.client_id,
            client_secret_hash=hash_client_secret(client_secret),
            redirect_uris=[str(item) for item in client_info.redirect_uris],
            grant_types=list(client_info.grant_types),
            response_types=list(client_info.response_types),
            scope=client_info.scope or "",
            client_name=client_info.client_name or client_info.client_id,
            token_endpoint_auth_method=client_info.token_endpoint_auth_method,
            metadata={
                key: value
                for key, value in metadata.items()
                if key
                not in {
                    "client_id",
                    "client_secret",
                    "client_id_issued_at",
                    "client_secret_expires_at",
                    "redirect_uris",
                    "grant_types",
                    "response_types",
                    "scope",
                    "client_name",
                    "token_endpoint_auth_method",
                }
            } or None,
            client_id_issued_at=_utcnow(),
            client_secret_expires_at=None,
        )

    async def create_dynamic_client(
        self,
        metadata: OAuthClientMetadata,
    ) -> OAuthClientInformationFull:
        if metadata.token_endpoint_auth_method != "client_secret_post":
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Only client_secret_post is supported for dynamic clients.",
            )

        client_id = f"kis-chatgpt-{generate_token(18)}"
        client_secret = generate_token(32)
        issued_at = _utcnow()
        record = auth_repository.upsert_oauth_client(
            client_id=client_id,
            client_secret_hash=hash_client_secret(client_secret),
            redirect_uris=[str(item) for item in metadata.redirect_uris],
            grant_types=list(metadata.grant_types),
            response_types=list(metadata.response_types),
            scope=metadata.scope or "",
            client_name=metadata.client_name or "ChatGPT",
            token_endpoint_auth_method=metadata.token_endpoint_auth_method,
            metadata={
                key: value
                for key, value in metadata.model_dump(exclude_none=True).items()
                if key
                not in {
                    "redirect_uris",
                    "grant_types",
                    "response_types",
                    "scope",
                    "client_name",
                    "token_endpoint_auth_method",
                }
            } or None,
            client_id_issued_at=issued_at,
            client_secret_expires_at=None,
        )
        return self._build_client_info(record, client_secret=client_secret)

    async def authenticate_client(
        self,
        client_id: str,
        client_secret: str | None,
    ) -> OAuthClientInformationFull | None:
        record = auth_repository.get_oauth_client(client_id)
        if record is None:
            return None

        auth_method = record.get("token_endpoint_auth_method") or "client_secret_post"
        if auth_method == "none":
            return self._build_client_info(record)

        if not client_secret:
            return None
        expires_at = record.get("client_secret_expires_at")
        if expires_at is not None and expires_at <= _utcnow():
            return None

        if not verify_client_secret(client_secret, record["client_secret_hash"]):
            return None

        return self._build_client_info(record)

    async def issue_authorization_code(
        self,
        *,
        user_id: str,
        client_id: str,
        grant_id: str | None,
        scope: str,
        redirect_uri: str,
        redirect_uri_provided_explicitly: bool,
        code_challenge: str,
        resource: str | None = None,
        state: str | None = None,
        provider: str | None = None,
    ) -> str:
        code = generate_token(32)
        expires_at = _utcnow() + timedelta(seconds=self.ttl.authorization_code_ttl_seconds)
        auth_repository.insert_authorization_code(
            user_id=user_id,
            client_id=client_id,
            grant_id=grant_id,
            code_digest=digest_token(code, self.token_pepper),
            scope=scope,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            code_challenge=code_challenge,
            resource=_normalize_resource(resource),
            state=state,
            provider=provider,
            expires_at=expires_at,
        )
        return code

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> StoredAuthorizationCode | None:
        record = auth_repository.get_authorization_code(
            digest_token(authorization_code, self.token_pepper)
        )
        if record is None:
            return None
        if record["client_id"] != client.client_id:
            return None
        if record.get("consumed_at") is not None or record.get("revoked_at") is not None:
            return None
        if record["expires_at"] <= _utcnow():
            return None

        return StoredAuthorizationCode(
            id=record["id"],
            user_id=record["user_id"],
            grant_id=record.get("grant_id"),
            state=record.get("state"),
            provider=record.get("provider"),
            code=authorization_code,
            scopes=auth_repository.split_scope(record["scope"]),
            expires_at=_from_timestamp(record["expires_at"]),
            client_id=record["client_id"],
            code_challenge=record["code_challenge"],
            redirect_uri=record["redirect_uri"],
            redirect_uri_provided_explicitly=record["redirect_uri_provided_explicitly"],
            resource=record.get("resource"),
        )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: StoredAuthorizationCode,
        *,
        resource: str | None = None,
    ) -> OAuthToken:
        auth_repository.consume_authorization_code(authorization_code.id)
        resolved_resource = _normalize_resource(resource) or authorization_code.resource
        return await self._issue_token_pair(
            user_id=authorization_code.user_id,
            client_id=client.client_id,
            grant_id=authorization_code.grant_id,
            scopes=authorization_code.scopes,
            resource=resolved_resource,
        )

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> StoredRefreshToken | None:
        record = auth_repository.get_oauth_token(
            digest_token(refresh_token, self.token_pepper),
            token_type="refresh_token",
        )
        if record is None:
            return None
        if record["client_id"] != client.client_id:
            return None
        if record.get("revoked_at") is not None:
            return None
        expires_at = record.get("expires_at")
        if expires_at is not None and expires_at <= _utcnow():
            return None

        return StoredRefreshToken(
            id=record["id"],
            user_id=record["user_id"],
            grant_id=record.get("grant_id"),
            token=refresh_token,
            client_id=record["client_id"],
            scopes=auth_repository.split_scope(record["scope"]),
            expires_at=_to_timestamp(expires_at),
            resource=record.get("resource"),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: StoredRefreshToken,
        scopes: list[str],
        *,
        resource: str | None = None,
    ) -> OAuthToken:
        requested_scopes = scopes or refresh_token.scopes
        if not set(requested_scopes).issubset(set(refresh_token.scopes)):
            raise TokenError(
                error="invalid_scope",
                error_description="Requested scope exceeds previously granted scope.",
            )

        auth_repository.revoke_oauth_token(refresh_token.id)
        return await self._issue_token_pair(
            user_id=refresh_token.user_id,
            client_id=client.client_id,
            grant_id=refresh_token.grant_id,
            scopes=requested_scopes,
            resource=_normalize_resource(resource) or refresh_token.resource,
            rotated_refresh_token_id=refresh_token.id,
        )

    async def load_access_token(self, token: str) -> StoredAccessToken | None:
        record = auth_repository.get_oauth_token(
            digest_token(token, self.token_pepper),
            token_type="access_token",
        )
        if record is None:
            return None
        if record.get("revoked_at") is not None:
            return None
        expires_at = record.get("expires_at")
        if expires_at is not None and expires_at <= _utcnow():
            return None
        record_resource = _normalize_resource(record.get("resource"))
        if self.resource_server_url and record_resource and record_resource != self.resource_server_url:
            return None

        return StoredAccessToken(
            id=record["id"],
            user_id=record["user_id"],
            grant_id=record.get("grant_id"),
            token=token,
            client_id=record["client_id"],
            scopes=auth_repository.split_scope(record["scope"]),
            expires_at=_to_timestamp(expires_at),
            resource=record.get("resource"),
        )

    async def verify_token(self, token: str) -> StoredAccessToken | None:
        """Verify a bearer token for the MCP 2.x resource-server middleware."""
        return await self.load_access_token(token)

    async def revoke_token(
        self,
        token: StoredAccessToken | StoredRefreshToken,
    ) -> None:
        if token.grant_id:
            auth_repository.revoke_oauth_tokens_for_grant(token.grant_id)
            return
        auth_repository.revoke_oauth_token(token.id)

    async def revoke_token_string(
        self,
        token: str,
        *,
        client_id: str | None = None,
    ) -> bool:
        digest = digest_token(token, self.token_pepper)
        record = auth_repository.get_oauth_token(digest)
        if record is None:
            return False
        if client_id is not None and record["client_id"] != client_id:
            return False
        if record.get("grant_id"):
            auth_repository.revoke_oauth_tokens_for_grant(record["grant_id"])
        else:
            auth_repository.revoke_oauth_token(record["id"])
        return True

    async def _issue_token_pair(
        self,
        *,
        user_id: str,
        client_id: str,
        grant_id: str | None,
        scopes: list[str],
        resource: str | None,
        rotated_refresh_token_id: str | None = None,
    ) -> OAuthToken:
        scope_text = auth_repository.normalize_scope(scopes)
        now = _utcnow()
        access_token = generate_token(32)
        refresh_token = generate_token(32)
        normalized_resource = _normalize_resource(resource)

        refresh_row = auth_repository.insert_oauth_token(
            user_id=user_id,
            client_id=client_id,
            grant_id=grant_id,
            token_type="refresh_token",
            token_digest=digest_token(refresh_token, self.token_pepper),
            scope=scope_text,
            resource=normalized_resource,
            expires_at=now + timedelta(seconds=self.ttl.refresh_token_ttl_seconds),
            parent_token_id=rotated_refresh_token_id,
            replaces_token_id=rotated_refresh_token_id,
        )
        auth_repository.insert_oauth_token(
            user_id=user_id,
            client_id=client_id,
            grant_id=grant_id,
            token_type="access_token",
            token_digest=digest_token(access_token, self.token_pepper),
            scope=scope_text,
            resource=normalized_resource,
            expires_at=now + timedelta(seconds=self.ttl.access_token_ttl_seconds),
            parent_token_id=refresh_row["id"],
            replaces_token_id=None,
        )

        return OAuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=self.ttl.access_token_ttl_seconds,
            scope=scope_text,
            refresh_token=refresh_token,
        )
