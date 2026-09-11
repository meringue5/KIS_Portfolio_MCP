from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from kis_portfolio.adapters.auth.app import create_app as create_auth_app
from kis_portfolio.adapters.auth.config import AuthServiceSettings, DEFAULT_ALLOWED_SCOPES
from kis_portfolio.adapters.auth.provider import KisOAuthProvider
from kis_portfolio.adapters.mcp import server as v1_adapter
from kis_portfolio.adapters.mcp.v2 import (
    COMMAND_TOOL_CONTRACTS,
    TOOL_CONTRACTS,
    create_v2_full_stateless_transport,
)
from kis_portfolio.adapters.outbound.memory_commands import (
    InMemoryJournalRevisionCommands,
    InMemoryManagedPipelineCommands,
)
from kis_portfolio.adapters.outbound.memory_state import InMemoryStateStore
from kis_portfolio.db import close_connection
from kis_portfolio.services.remote_commands import CommandActor, RemoteCommandApplication
from kis_portfolio.services.remote_migration import load_remote_migration_manifest
from kis_portfolio.services.remote_read_surface import (
    V2_READ_TOOL_NAMES,
    MappingReadQueryPort,
    ReadActor,
    RemoteReadApplication,
)


RESOURCE = "https://resource.example.com/mcp"
FIXTURE_PATH = Path(__file__).with_name("fixtures") / "remote_v2" / "client_profiles.json"
GUIDE_PATH = Path("docs/remote-mcp-v2-migration.md")
V2_TOOL_NAMES = tuple(item.name for item in TOOL_CONTRACTS + COMMAND_TOOL_CONTRACTS)


def _read_application(request_id: str) -> RemoteReadApplication:
    def handler(request, _actor):
        return {
            "schema_version": "1.0.0",
            "as_of": datetime(2026, 9, 11, 1, tzinfo=UTC),
            "source": {"kind": "compatibility_fixture", "available": True},
            "freshness": {"status": "not_assessed", "reason_code": "fixture_only"},
            "quality": {"status": "not_assessed", "reason_code": "fixture_only"},
            "missing_coverage": [{"gap_code": "not_live_client_evidence", "gap_count": 1}],
            "lineage_ref": "fixture:remote-v2-client-profile",
            "request_id": request_id,
            "data": {"request_type": type(request).__name__},
        }

    return RemoteReadApplication(
        MappingReadQueryPort({name: handler for name in V2_READ_TOOL_NAMES}),
        expected_resource=RESOURCE,
    )


def _transport(profile_id: str):
    state = InMemoryStateStore()
    command_application = RemoteCommandApplication(
        state=state,
        managed_pipeline=InMemoryManagedPipelineCommands(),
        revisions=InMemoryJournalRevisionCommands(),
        expected_resource=RESOURCE,
    )
    read_actor = ReadActor(
        "owner-subject",
        profile_id,
        frozenset({"mcp:read"}),
        RESOURCE,
        f"{profile_id}-read-request",
    )
    command_actor = CommandActor(
        "owner-subject",
        profile_id,
        frozenset({"mcp:collect", "mcp:journal.write"}),
        RESOURCE,
        f"{profile_id}-command-request",
    )
    return create_v2_full_stateless_transport(
        _read_application(read_actor.request_id),
        command_application,
        resource_server_url=RESOURCE,
        read_actor_provider=lambda: read_actor,
        command_actor_provider=lambda: command_actor,
    )


def _handshake(profile: dict[str, object], request_id: str) -> dict[str, object]:
    if profile["handshake"] == "server/discover":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "server/discover",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": profile["protocol_version"],
                    "io.modelcontextprotocol/clientInfo": {
                        "name": profile["client_name"],
                        "version": "recorded-fixture",
                    },
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": profile["protocol_version"],
            "capabilities": {},
            "clientInfo": {"name": profile["client_name"], "version": "recorded-fixture"},
        },
    }


@pytest.mark.parametrize(
    "profile",
    json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["profiles"],
    ids=lambda profile: profile["profile_id"],
)
def test_recorded_client_profile_starts_fresh_lists_exact_catalog_and_calls_tools(profile):
    app = _transport(profile["profile_id"])
    headers = {"Accept": "application/json, text/event-stream"}
    if profile["origin"] is not None:
        headers["Origin"] = profile["origin"]
    handshake_headers = dict(headers)
    if profile["handshake"] == "server/discover":
        handshake_headers.update({
            "MCP-Protocol-Version": profile["protocol_version"],
            "MCP-Method": "server/discover",
        })

    with TestClient(app, base_url="https://resource.example.com") as client:
        handshake = client.post(
            "/mcp",
            json=_handshake(profile, f"{profile['profile_id']}-handshake"),
            headers=handshake_headers,
        )
        listing = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "list", "method": "tools/list", "params": {}},
            headers=headers,
        )
        results = [
            client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": f"call-{index}",
                    "method": "tools/call",
                    "params": call,
                },
                headers=headers,
            )
            for index, call in enumerate(profile["calls"])
        ]

    assert handshake.status_code == 200
    assert listing.status_code == 200
    assert tuple(tool["name"] for tool in listing.json()["result"]["tools"]) == V2_TOOL_NAMES
    assert all(response.status_code == 200 for response in results)
    assert all(response.json()["result"]["isError"] is False for response in results)
    assert all("structuredContent" in response.json()["result"] for response in results)
    assert "mcp-session-id" not in handshake.headers
    assert "mcp-session-id" not in listing.headers
    assert app.state.kis_public_activation is False
    assert app.state.kis_client_profile_fixture_only is True


def test_manifest_covers_exact_current_v1_and_exact_inactive_v2_catalog():
    manifest = load_remote_migration_manifest()
    current_v1 = set(v1_adapter.mcp._tool_manager._tools)
    current_v2 = set(V2_TOOL_NAMES)

    assert len(current_v1) == 35
    assert len(current_v2) == 18
    assert set(manifest.by_v1_tool()) == current_v1
    assert set(manifest.v2_tools) == current_v2
    assert all(
        set(entry.v2_tools).issubset(current_v2)
        for entry in manifest.entries
        if entry.disposition != "unsupported"
    )


def test_only_disabled_v1_order_stubs_are_explicitly_unsupported():
    manifest = load_remote_migration_manifest()
    unsupported = {
        entry.v1_tool: entry.unsupported_response()
        for entry in manifest.entries
        if entry.disposition == "unsupported"
    }

    assert set(unsupported) == {"submit-stock-order", "submit-overseas-stock-order"}
    assert all(value["status"] == "unsupported" for value in unsupported.values())
    assert all(value["reason_code"] == "unsupported_order_authority_absent" for value in unsupported.values())
    assert all(value["replacement_tools"] == [] for value in unsupported.values())


def _auth_settings(*, allowed_scopes=DEFAULT_ALLOWED_SCOPES) -> AuthServiceSettings:
    return AuthServiceSettings(
        base_url="https://auth.example.com",
        owner_emails=("owner@example.com",),
        session_secret="session-secret",
        token_pepper="pepper",
        claude_client_id="claude-client",
        claude_client_secret="claude-secret",
        google_client_id="google-client",
        google_client_secret="google-secret",
        github_client_id="github-client",
        github_client_secret="github-secret",
        allowed_scopes=allowed_scopes,
        secure_cookies=False,
    )


def test_command_scopes_require_explicit_auth_configuration_and_client_registration(monkeypatch, tmp_path):
    close_connection()
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path / "var"))

    assert DEFAULT_ALLOWED_SCOPES == ("mcp:read", "offline_access")
    settings = _auth_settings(
        allowed_scopes=("mcp:read", "mcp:collect", "mcp:journal.write", "offline_access")
    )
    provider = KisOAuthProvider(token_pepper=settings.token_pepper)
    app = create_auth_app(settings=settings, provider=provider)

    with TestClient(app) as client:
        discovery = client.get("/.well-known/oauth-authorization-server")
        registration = client.post(
            "/register",
            json={
                "client_name": "ChatGPT Connector",
                "redirect_uris": ["https://chatgpt.com/connector/oauth/callback-fixture"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
                "scope": "mcp:read",
            },
        )

    assert discovery.status_code == 200
    assert discovery.json()["scopes_supported"] == list(settings.allowed_scopes)
    assert registration.status_code == 201
    assert registration.json()["scope"] == "mcp:read"
    close_connection()


def test_migration_guide_is_remote_only_and_marks_live_client_evidence_as_gated():
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    prohibited_product_setup = (
        "uv run kis-portfolio-mcp",
        "uv run python server.py",
        "claude_desktop_config.json",
        '"mcpServers"',
        "http://localhost",
    )

    assert all(value not in guide for value in prohibited_product_setup)
    assert "OAuth Remote MCP only" in guide
    assert "public HTTPS Remote MCP URL including `/mcp`" in guide
    assert "new conversation" in guide
    assert "not proof that a live connector or iPhone UI worked" in guide
    assert "https://developers.openai.com/plugins/build/mcp-server/" in guide
    assert "https://support.claude.com/" in guide
