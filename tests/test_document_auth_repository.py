from datetime import datetime, timedelta

from kis_portfolio.adapters.outbound.document_auth_repository import DocumentAuthRepository
from kis_portfolio.adapters.outbound.memory_state import InMemoryStateStore


def test_document_auth_repository_oauth_lifecycle_and_single_use():
    repo = DocumentAuthRepository(InMemoryStateStore())
    user = repo.upsert_auth_user("Owner@Example.com", "Owner")
    assert repo.get_auth_user_by_email("owner@example.com")["id"] == user["id"]

    client = repo.upsert_oauth_client(
        client_id="client-1",
        client_secret_hash="hash-only",
        redirect_uris=["https://example.com/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="offline_access mcp:read",
        client_name="test",
        token_endpoint_auth_method="client_secret_post",
    )
    grant = repo.upsert_oauth_grant(user["id"], client["client_id"], "mcp:read offline_access")
    assert repo.get_oauth_grant(user["id"], client["client_id"], "offline_access mcp:read")["id"] == grant["id"]

    code = repo.insert_authorization_code(
        user_id=user["id"], client_id=client["client_id"], grant_id=grant["id"],
        code_digest="code-digest", scope="mcp:read", redirect_uri="https://example.com/callback",
        redirect_uri_provided_explicitly=True, code_challenge="challenge", resource=None,
        state=None, provider="google", expires_at=datetime.now() + timedelta(minutes=10),
    )
    assert repo.consume_authorization_code(code["id"]) is True
    assert repo.consume_authorization_code(code["id"]) is False

    refresh = repo.insert_oauth_token(
        user_id=user["id"], client_id=client["client_id"], grant_id=grant["id"],
        token_type="refresh_token", token_digest="refresh-digest", scope="mcp:read",
        resource=None, expires_at=datetime.now() + timedelta(days=1),
    )
    assert repo.consume_refresh_token(refresh["id"]) is True
    assert repo.consume_refresh_token(refresh["id"]) is False
    assert repo.get_oauth_token("refresh-digest")["revoked_at"] is not None


def test_document_auth_repository_grant_revocation_updates_digest_lookup():
    repo = DocumentAuthRepository(InMemoryStateStore())
    first = repo.insert_oauth_token(
        user_id="u", client_id="c", grant_id="g", token_type="access_token",
        token_digest="one", scope="mcp:read", resource=None,
        expires_at=datetime.now() + timedelta(hours=1),
    )
    repo.insert_oauth_token(
        user_id="u", client_id="c", grant_id="g", token_type="refresh_token",
        token_digest="two", scope="mcp:read", resource=None,
        expires_at=datetime.now() + timedelta(hours=1), parent_token_id=first["id"],
    )
    repo.revoke_oauth_tokens_for_grant("g")
    assert repo.get_oauth_token("one")["revoked_at"] is not None
    assert repo.get_oauth_token("two")["revoked_at"] is not None


def test_document_auth_repository_import_preserves_ids_and_indexes():
    repo = DocumentAuthRepository(InMemoryStateStore())
    record = {
        "id": "existing-user", "primary_email": "owner@example.com", "display_name": "Owner",
        "is_active": True, "created_at": datetime.now(), "updated_at": datetime.now(),
    }
    repo.import_record("auth_users", record)
    assert repo.get_auth_user_by_id("existing-user") == record
    assert repo.get_auth_user_by_email("OWNER@example.com") == record
