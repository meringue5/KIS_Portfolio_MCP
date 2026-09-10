import asyncio
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from kis_portfolio.adapters.mcp.v2 import (
    MAX_REQUEST_BODY_BYTES,
    TOOL_CONTRACTS,
    build_v2_read_server,
    create_v2_stateless_transport,
)
from kis_portfolio.adapters.mcp import v2 as v2_adapter
from kis_portfolio.services.remote_read_surface import (
    MAX_RESPONSE_BYTES,
    V2_READ_TOOL_NAMES,
    MappingReadQueryPort,
    MarketHistoryRequest,
    ReadActor,
    RemoteReadApplication,
    RemoteReadError,
)


RESOURCE = "https://resource.example.com/mcp"
ACTOR = ReadActor(
    actor_id="owner-subject",
    client_id="claude-client",
    scopes=frozenset({"mcp:read"}),
    resource=RESOURCE,
    request_id="request-42",
)


def _envelope(*, data=None):
    return {
        "schema_version": "1.0.0",
        "as_of": datetime(2026, 9, 11, tzinfo=UTC),
        "source": {"kind": "fixture", "available": True},
        "freshness": {"status": "not_assessed", "reason_code": "fixture"},
        "quality": {"status": "not_assessed", "reason_code": "fixture"},
        "missing_coverage": [{"gap_code": "fixture_only", "gap_count": 1}],
        "lineage_ref": "lineage:v1:fixture",
        "request_id": "port-value-must-be-replaced",
        "data": data or {"items": []},
    }


def _application(handler=None):
    selected = handler or (lambda _request, _actor: _envelope())
    port = MappingReadQueryPort({name: selected for name in V2_READ_TOOL_NAMES})
    return RemoteReadApplication(port, expected_resource=RESOURCE)


def test_v2_catalog_is_exactly_fifteen_read_tools_with_owned_contracts():
    server = build_v2_read_server(_application(), actor_provider=lambda: ACTOR)
    tools = server._tool_manager.list_tools()

    assert tuple(tool.name for tool in tools) == V2_READ_TOOL_NAMES
    assert tuple(contract.name for contract in TOOL_CONTRACTS) == V2_READ_TOOL_NAMES
    assert all(tool.annotations.read_only_hint is True for tool in tools)
    assert all(tool.annotations.destructive_hint is False for tool in tools)
    assert all(tool.meta["kis/scope"] == "mcp:read" for tool in tools)
    assert all(tool.meta["kis/outputSchemaRef"] for tool in tools)
    assert "run-managed-pipeline" not in {tool.name for tool in tools}
    assert "submit-stock-order" not in {tool.name for tool in tools}
    by_name = {tool.name: tool for tool in tools}
    assert by_name["get-market-snapshot"].parameters["properties"]["market"]["enum"] == [
        "KR", "US", "FX",
    ]
    assert by_name["get-position-analysis"].parameters["properties"]["limit"]["maximum"] == 200
    assert by_name["get-portfolio-overview"].output_schema["additionalProperties"] is False
    assert set(by_name["get-portfolio-overview"].output_schema["required"]) == {
        "schema_version", "as_of", "source", "freshness", "quality",
        "missing_coverage", "lineage_ref", "request_id", "data",
    }


def test_tool_handler_delegates_a_typed_request_and_binds_request_id():
    captured = {}

    async def handler(request, actor):
        captured.update(request=request, actor=actor)
        return _envelope(data={"account_alias": request.account_alias})

    server = build_v2_read_server(_application(handler), actor_provider=lambda: ACTOR)
    tool = next(item for item in server._tool_manager.list_tools() if item.name == "get-portfolio-overview")

    result = asyncio.run(tool.fn(account_alias="brokerage", include_holdings=False))

    assert result.request_id == "request-42"
    assert result.data == {"account_alias": "brokerage"}
    assert captured["request"].model_dump()["include_holdings"] is False
    assert captured["actor"] == ACTOR


@pytest.mark.parametrize(
    ("actor", "code"),
    [
        (ReadActor("owner", "client", frozenset(), RESOURCE, "request"), "insufficient_scope"),
        (ReadActor("owner", "client", frozenset({"mcp:read"}), "https://other.example/mcp", "request"), "invalid_resource"),
        (ReadActor("", "client", frozenset({"mcp:read"}), RESOURCE, "request"), "invalid_actor"),
    ],
)
def test_application_authorization_fails_closed(actor, code):
    with pytest.raises(RemoteReadError, match=code):
        asyncio.run(_application().execute("get-portfolio-overview", {}, actor))


def test_query_port_rejects_missing_or_extra_capabilities():
    with pytest.raises(RemoteReadError, match="incomplete_query_port"):
        MappingReadQueryPort({"get-portfolio-overview": lambda _request, _actor: _envelope()})


def test_input_dto_enforces_dates_enums_and_bounds():
    with pytest.raises(ValidationError):
        MarketHistoryRequest(
            instrument_id="AAPL",
            market="EU",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 9, 11),
            limit=1_001,
        )
    with pytest.raises(ValidationError):
        MarketHistoryRequest(
            instrument_id="AAPL",
            market="US",
            start_date=date(2026, 9, 11),
            end_date=date(2026, 1, 1),
        )


def test_actor_projection_drops_raw_bearer_and_normalizes_resource(monkeypatch):
    class Token:
        token = "must-never-leave-auth-context"
        subject = "owner-subject"
        client_id = "claude-client"
        scopes = ["mcp:read"]
        resource = f"{RESOURCE}/"

    monkeypatch.setattr(v2_adapter, "get_access_token", lambda: Token())

    actor = v2_adapter.actor_from_auth_context()

    assert actor.actor_id == "owner-subject"
    assert actor.resource == RESOURCE
    assert not hasattr(actor, "token")


def test_application_enforces_maximum_300_second_deadline():
    with pytest.raises(RemoteReadError, match="invalid_deadline"):
        RemoteReadApplication(
            MappingReadQueryPort({name: lambda _request, _actor: _envelope() for name in V2_READ_TOOL_NAMES}),
            expected_resource=RESOURCE,
            deadline_seconds=301,
        )


def test_application_reports_query_timeout_without_partial_success():
    async def slow(_request, _actor):
        await asyncio.sleep(0.02)
        return _envelope()

    application = RemoteReadApplication(
        MappingReadQueryPort({name: slow for name in V2_READ_TOOL_NAMES}),
        expected_resource=RESOURCE,
        deadline_seconds=0.001,
    )

    with pytest.raises(RemoteReadError, match="query_deadline_exceeded"):
        asyncio.run(application.execute("get-portfolio-overview", {}, ACTOR))


@pytest.mark.parametrize("unsafe_key", ["raw", "access_token", "app_secret", "cano", "account_number"])
def test_response_rejects_raw_secret_and_account_identifier_fields(unsafe_key):
    def handler(_request, _actor):
        return _envelope(data={unsafe_key: "must-not-leak"})

    with pytest.raises(RemoteReadError, match="unsafe_response_field"):
        asyncio.run(_application(handler).execute("get-portfolio-overview", {}, ACTOR))


def test_response_size_is_bounded_to_256_kib():
    def handler(_request, _actor):
        return _envelope(data={"large": "x" * MAX_RESPONSE_BYTES})

    with pytest.raises(RemoteReadError, match="response_too_large"):
        asyncio.run(_application(handler).execute("get-portfolio-overview", {}, ACTOR))


def test_official_transport_is_stateless_json_and_has_no_public_activation():
    app = create_v2_stateless_transport(
        _application(),
        resource_server_url=RESOURCE,
        actor_provider=lambda: ACTOR,
    )
    request = {
        "jsonrpc": "2.0",
        "id": "discover-1",
        "method": "server/discover",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientInfo": {"name": "fixture", "version": "1"},
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "MCP-Method": "server/discover",
        "Origin": "https://claude.ai",
    }

    with TestClient(app, base_url="https://resource.example.com") as client:
        first = client.post("/mcp", json=request, headers=headers)
        request["id"] = "discover-2"
        second = client.post("/mcp", json=request, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == "discover-1"
    assert second.json()["id"] == "discover-2"
    assert "mcp-session-id" not in first.headers
    assert app.state.kis_max_response_bytes == MAX_RESPONSE_BYTES
    assert app.state.kis_public_activation is False


def test_two_independent_transport_instances_do_not_share_session_state():
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Origin": "https://claude.com",
    }
    observed = []

    for _ in range(2):
        app = create_v2_stateless_transport(
            _application(), resource_server_url=RESOURCE, actor_provider=lambda: ACTOR,
        )
        with TestClient(app, base_url="https://resource.example.com") as client:
            response = client.post("/mcp", json=request, headers=headers)
        observed.append(response)

    assert all(response.status_code == 200 for response in observed)
    assert all(len(response.json()["result"]["tools"]) == 15 for response in observed)
    assert all("mcp-session-id" not in response.headers for response in observed)


def test_transport_rejects_unapproved_host_origin_and_oversized_body():
    app = create_v2_stateless_transport(
        _application(), resource_server_url=RESOURCE, actor_provider=lambda: ACTOR,
    )
    payload = b"x" * (MAX_REQUEST_BODY_BYTES + 1)

    with TestClient(app, base_url="https://resource.example.com") as client:
        wrong_origin = client.post(
            "/mcp",
            content=b"{}",
            headers={"content-type": "application/json", "origin": "https://evil.example"},
        )
        oversized = client.post(
            "/mcp",
            content=payload,
            headers={"content-type": "application/json", "origin": "https://claude.com"},
        )
        wrong_host = client.post(
            "/mcp",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "origin": "https://claude.com",
                "host": "evil.example",
            },
        )

    assert wrong_origin.status_code == 403
    assert wrong_host.status_code == 421
    assert oversized.status_code == 413
