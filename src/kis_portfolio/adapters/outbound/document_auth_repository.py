"""OAuth repository implemented on the small document StateStorePort contract."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from kis_portfolio.ports.state import StateStorePort


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=value.tzinfo or UTC)


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def normalize_scope(scope: str | list[str] | None) -> str:
    if scope is None:
        return ""
    values = scope.split() if isinstance(scope, str) else list(scope)
    return " ".join(sorted(dict.fromkeys(item for item in values if item)))


def split_scope(scope: str | None) -> list[str]:
    return scope.split() if scope else []


class DocumentAuthRepository:
    """Deterministic document model with secondary lookup documents.

    Only password hashes and opaque token digests enter this repository. Raw
    bearer values remain solely in the OAuth provider response path.
    """

    normalize_scope = staticmethod(normalize_scope)
    split_scope = staticmethod(split_scope)

    def __init__(self, store: StateStorePort) -> None:
        self.store = store

    def _put(self, namespace: str, key: str, value: dict[str, Any], expires_at: datetime | None = None) -> None:
        self.store.put(namespace, key, value, expires_at=_aware(expires_at))

    def _get(self, namespace: str, key: str) -> dict[str, Any] | None:
        record = self.store.get(namespace, key)
        if record is None:
            return None
        return {
            field: value.astimezone(UTC).replace(tzinfo=None)
            if isinstance(value, datetime) and value.tzinfo is not None else value
            for field, value in record.items()
        }

    def get_auth_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        return self._get("auth_users", f"id:{user_id}")

    def get_auth_user_by_email(self, email: str) -> dict[str, Any] | None:
        index = self._get("auth_users", f"email:{_hash(email.lower())}")
        return self.get_auth_user_by_id(index["id"]) if index else None

    def upsert_auth_user(self, email: str, display_name: str | None) -> dict[str, Any]:
        normalized = email.lower()
        existing = self.get_auth_user_by_email(normalized)
        now = _utcnow()
        record = existing or {
            "id": str(uuid.uuid4()), "primary_email": normalized, "is_active": True, "created_at": now,
        }
        record = {**record, "display_name": display_name or record.get("display_name"), "updated_at": now}
        self._put("auth_users", f"id:{record['id']}", record)
        self._put("auth_users", f"email:{_hash(normalized)}", {"id": record["id"]})
        return record

    def get_auth_identity(self, provider: str, provider_subject: str) -> dict[str, Any] | None:
        return self._get("auth_identities", f"identity:{_hash(provider, provider_subject)}")

    def upsert_auth_identity(self, *, provider: str, provider_subject: str, email: str,
                             email_verified: bool, display_name: str | None,
                             profile_data: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_auth_identity(provider, provider_subject)
        user = self.get_auth_user_by_id(existing["user_id"]) if existing else self.get_auth_user_by_email(email)
        user = user or self.upsert_auth_user(email, display_name)
        now = _utcnow()
        record = {
            "id": existing["id"] if existing else str(uuid.uuid4()), "user_id": user["id"],
            "provider": provider, "provider_subject": provider_subject, "email": email.lower(),
            "email_verified": email_verified, "profile_data": profile_data,
            "created_at": existing.get("created_at", now) if existing else now, "updated_at": now,
        }
        self._put("auth_identities", f"identity:{_hash(provider, provider_subject)}", record)
        return record

    def upsert_oauth_client(self, *, client_id: str, client_secret_hash: str,
                            redirect_uris: list[str], grant_types: list[str], response_types: list[str],
                            scope: str, client_name: str, token_endpoint_auth_method: str,
                            metadata: dict[str, Any] | None = None,
                            client_id_issued_at: datetime | None = None,
                            client_secret_expires_at: datetime | None = None) -> dict[str, Any]:
        existing = self.get_oauth_client(client_id)
        now = _utcnow()
        record = {
            "client_id": client_id, "client_secret_hash": client_secret_hash,
            "redirect_uris": redirect_uris, "grant_types": grant_types, "response_types": response_types,
            "scope": normalize_scope(scope), "client_name": client_name,
            "token_endpoint_auth_method": token_endpoint_auth_method, "metadata": metadata,
            "client_id_issued_at": client_id_issued_at or now,
            "client_secret_expires_at": client_secret_expires_at,
            "created_at": existing.get("created_at", now) if existing else now, "updated_at": now,
        }
        self._put("oauth_clients", f"client:{client_id}", record)
        return record

    def get_oauth_client(self, client_id: str) -> dict[str, Any] | None:
        return self._get("oauth_clients", f"client:{client_id}")

    @staticmethod
    def _grant_key(user_id: str, client_id: str, scope: str) -> str:
        return f"grant:{_hash(user_id, client_id, normalize_scope(scope))}"

    def get_oauth_grant(self, user_id: str, client_id: str, scope: str) -> dict[str, Any] | None:
        record = self._get("oauth_grants", self._grant_key(user_id, client_id, scope))
        return None if record and record.get("revoked_at") else record

    def upsert_oauth_grant(self, user_id: str, client_id: str, scope: str) -> dict[str, Any]:
        key = self._grant_key(user_id, client_id, scope)
        existing = self._get("oauth_grants", key)
        now = _utcnow()
        record = {
            "id": existing["id"] if existing else str(uuid.uuid4()), "user_id": user_id,
            "client_id": client_id, "scope": normalize_scope(scope), "granted_at": now,
            "revoked_at": None, "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }
        self._put("oauth_grants", key, record)
        return record

    def insert_authorization_code(self, *, user_id: str, client_id: str, grant_id: str | None,
                                  code_digest: str, scope: str, redirect_uri: str,
                                  redirect_uri_provided_explicitly: bool, code_challenge: str,
                                  resource: str | None, state: str | None, provider: str | None,
                                  expires_at: datetime) -> dict[str, Any]:
        now = _utcnow()
        record = {
            "id": str(uuid.uuid4()), "user_id": user_id, "client_id": client_id,
            "grant_id": grant_id, "code_digest": code_digest, "scope": normalize_scope(scope),
            "redirect_uri": redirect_uri, "redirect_uri_provided_explicitly": redirect_uri_provided_explicitly,
            "code_challenge": code_challenge, "resource": resource, "state": state, "provider": provider,
            "created_at": now, "expires_at": expires_at, "consumed_at": None, "revoked_at": None,
        }
        self._put("oauth_codes", f"id:{record['id']}", record, expires_at)
        self._put("oauth_codes", f"digest:{code_digest}", record, expires_at)
        return record

    def get_authorization_code(self, code_digest: str) -> dict[str, Any] | None:
        return self._get("oauth_codes", f"digest:{code_digest}")

    def consume_authorization_code(self, code_id: str) -> bool:
        owner = str(uuid.uuid4())
        claim = self.store.claim(f"oauth-code:{code_id}", owner, timedelta(minutes=15))
        if not claim.acquired:
            return False
        record = self._get("oauth_codes", f"id:{code_id}")
        if not record or record.get("consumed_at") or record.get("revoked_at"):
            return False
        now = _utcnow()
        record = {**record, "consumed_at": now, "revoked_at": now}
        self._put("oauth_codes", f"id:{code_id}", record, record.get("expires_at"))
        self._put("oauth_codes", f"digest:{record['code_digest']}", record, record.get("expires_at"))
        return True

    def insert_oauth_token(self, *, user_id: str, client_id: str, grant_id: str | None,
                           token_type: str, token_digest: str, scope: str, resource: str | None,
                           expires_at: datetime | None, parent_token_id: str | None = None,
                           replaces_token_id: str | None = None) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()), "user_id": user_id, "client_id": client_id,
            "grant_id": grant_id, "token_type": token_type, "token_digest": token_digest,
            "scope": normalize_scope(scope), "resource": resource, "created_at": _utcnow(),
            "expires_at": expires_at, "revoked_at": None, "parent_token_id": parent_token_id,
            "replaces_token_id": replaces_token_id,
        }
        self._put("oauth_tokens", f"id:{record['id']}", record, expires_at)
        self._put("oauth_tokens", f"digest:{token_digest}", record, expires_at)
        if grant_id:
            index_key = f"grant:{grant_id}"
            index = self._get("oauth_tokens", index_key) or {"token_ids": []}
            ids = list(dict.fromkeys([*index["token_ids"], record["id"]]))
            self._put("oauth_tokens", index_key, {"token_ids": ids})
        return record

    def get_oauth_token(self, token_digest: str, token_type: str | None = None) -> dict[str, Any] | None:
        record = self._get("oauth_tokens", f"digest:{token_digest}")
        if record and token_type and record.get("token_type") != token_type:
            return None
        return record

    def revoke_oauth_token(self, token_id: str) -> bool:
        record = self._get("oauth_tokens", f"id:{token_id}")
        if not record:
            return False
        record = {**record, "revoked_at": record.get("revoked_at") or _utcnow()}
        self._put("oauth_tokens", f"id:{token_id}", record, record.get("expires_at"))
        self._put("oauth_tokens", f"digest:{record['token_digest']}", record, record.get("expires_at"))
        return True

    def consume_refresh_token(self, token_id: str) -> bool:
        claim = self.store.claim(f"oauth-refresh:{token_id}", str(uuid.uuid4()), timedelta(days=31))
        return bool(claim.acquired and self.revoke_oauth_token(token_id))

    def revoke_oauth_tokens_for_grant(self, grant_id: str) -> None:
        index = self._get("oauth_tokens", f"grant:{grant_id}") or {"token_ids": []}
        for token_id in index["token_ids"]:
            self.revoke_oauth_token(token_id)

    def revoke_oauth_token_by_digest(self, token_digest: str, client_id: str | None = None) -> dict[str, Any] | None:
        token = self.get_oauth_token(token_digest)
        if token is None or (client_id and token["client_id"] != client_id):
            return None
        self.revoke_oauth_token(token["id"])
        return self.get_oauth_token(token_digest)

    def import_record(self, kind: str, record: dict[str, Any]) -> None:
        """Import an existing hashed/digested record while preserving its IDs."""
        if kind == "auth_users":
            self._put(kind, f"id:{record['id']}", record)
            self._put(kind, f"email:{_hash(record['primary_email'].lower())}", {"id": record["id"]})
        elif kind == "auth_identities":
            self._put(kind, f"identity:{_hash(record['provider'], record['provider_subject'])}", record)
        elif kind == "oauth_clients":
            self._put(kind, f"client:{record['client_id']}", record)
        elif kind == "oauth_grants":
            self._put(kind, self._grant_key(record["user_id"], record["client_id"], record["scope"]), record)
        elif kind == "oauth_codes":
            self._put(kind, f"id:{record['id']}", record, record.get("expires_at"))
            self._put(kind, f"digest:{record['code_digest']}", record, record.get("expires_at"))
        elif kind == "oauth_tokens":
            self._put(kind, f"id:{record['id']}", record, record.get("expires_at"))
            self._put(kind, f"digest:{record['token_digest']}", record, record.get("expires_at"))
            if record.get("grant_id"):
                index_key = f"grant:{record['grant_id']}"
                index = self._get(kind, index_key) or {"token_ids": []}
                self._put(kind, index_key, {
                    "token_ids": list(dict.fromkeys([*index["token_ids"], record["id"]]))
                })
        else:
            raise ValueError(f"Unsupported OAuth state kind: {kind}")
