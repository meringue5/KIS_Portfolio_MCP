from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.governance_read_models import (
    EvidencePolicy,
    GovernanceReadModelService,
    ReadModelRequestError,
)


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 9, 9, 1, 0, tzinfo=UTC)


@pytest.fixture
def connection(tmp_path: Path):
    con = duckdb.connect(str(tmp_path / "read-model.duckdb"))
    MigrationRunner(con).apply()
    yield con
    con.close()


def _policy(*, freshness: timedelta = timedelta(hours=2), complete: bool = True) -> EvidencePolicy:
    return EvidencePolicy(
        pipeline_id="pipeline.fixture",
        pipeline_version="1.0.0",
        required_stages=("collect", "publish"),
        required_rules={"dataset.fixture": ("row-count",)} if complete else {},
        required_watermark_types=("logical_date",) if complete else (),
        freshness=freshness if complete else None,
        dataset_wide_coverage=True,
    )


def _service(connection, *, policy: EvidencePolicy | None = None) -> GovernanceReadModelService:
    return GovernanceReadModelService(
        connection,
        ROOT,
        policies=(policy,) if policy else (),
        now=lambda: NOW,
        request_id=lambda: "request-fixture",
    )


def _insert_run(
    con,
    *,
    run_id: str = "run-1",
    status: str = "succeeded",
    stages: tuple[tuple[str, str], ...] = (("collect", "succeeded"), ("publish", "succeeded")),
    rule_status: str | None = "pass",
    watermark_at: datetime | None = NOW - timedelta(minutes=5),
    error_code: str | None = None,
) -> None:
    partition_key = f"account:secret:{run_id}"
    definition = json.dumps({"stages": [item[0] for item in stages], "source_call_budget": 5})
    con.execute(
        "INSERT OR IGNORE INTO control.pipeline_definitions VALUES (?,?,?,?,?,?)",
        ["pipeline.fixture", "1.0.0", "approved", "definition-hash", definition, NOW],
    )
    con.execute(
        """INSERT INTO control.pipeline_runs(
          run_id,pipeline_id,pipeline_version,logical_date,slot,partition_key,idempotency_key,
          status,source_calls,started_at,finished_at,error_code,error_message
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [run_id, "pipeline.fixture", "1.0.0", date(2026, 9, 9), "10:00", partition_key, f"key-{run_id}",
         status, 2, NOW - timedelta(minutes=10), NOW - timedelta(minutes=5), error_code, "raw secret failure"],
    )
    for index, (stage_name, stage_status) in enumerate(stages):
        con.execute(
            "INSERT INTO control.pipeline_stage_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [run_id, stage_name, index, stage_status, 1, 1, 1, 1, NOW, NOW, '{"account":"secret"}', "raw stage error"],
        )
    if rule_status is not None:
        con.execute(
            "INSERT INTO control.quality_results VALUES (?,?,?,?,?,?,?,?,?)",
            [f"quality-{run_id}", run_id, "dataset.fixture", "row-count", rule_status, "secret", "secret", '{"secret":true}', NOW],
        )
    con.execute(
        "INSERT INTO control.lineage_edges VALUES (?,?,?,?,?,?,?,?)",
        [f"lineage-{run_id}", run_id, "account:secret", "object:secret", "fixture", "1", "evidence-hash", NOW],
    )
    if watermark_at is not None:
        con.execute(
            "INSERT INTO control.watermarks VALUES (?,?,?,?,?,?)",
            ["pipeline.fixture", partition_key, "logical_date", "2026-09-09", run_id, watermark_at],
        )


def test_catalog_is_bounded_filtered_and_sensitivity_safe(connection) -> None:
    service = _service(connection)
    first = service.data_catalog(consumer_scope="mcp-read", kind="source", limit=1)
    assert first["quality"]["status"] == "pass"
    assert first["data"]["next_cursor"]
    item = first["data"]["items"][0]
    forbidden = {"provider", "access_method", "auth_class", "rate_limit_policy", "cost_budget"}
    assert forbidden.isdisjoint(item)

    second = service.data_catalog(
        consumer_scope="mcp-read", kind="source", limit=1, cursor=first["data"]["next_cursor"],
    )
    assert second["data"]["items"][0]["id"] > item["id"]
    proposed = service.data_catalog(consumer_scope="mcp-read", kind="source", item_id="source.time-etf")
    assert proposed["data"]["items"] == []
    restricted = service.data_catalog(
        consumer_scope="mcp-read", kind="source", item_id="source.owner-provided-research-document",
    )["data"]["items"]
    assert set(restricted[0]) == {"kind", "id", "version", "lifecycle", "sensitivity", "details_available"}


def test_catalog_supports_all_six_contract_kinds_and_rejects_tampered_cursor(connection) -> None:
    service = _service(connection)
    for kind in ("source", "dataset", "metric", "pipeline", "macro_series", "object"):
        assert service.data_catalog(consumer_scope="mcp-read", kind=kind, limit=1)["data"]["items"]
    with pytest.raises(ReadModelRequestError, match="invalid_kind"):
        service.data_catalog(consumer_scope="mcp-read", kind="collection")
    cursor = service.data_catalog(consumer_scope="mcp-read", kind="dataset", limit=1)["data"]["next_cursor"]
    raw = bytearray(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    raw[-2] = raw[-2] ^ 1
    tampered = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    with pytest.raises(ReadModelRequestError, match="invalid_cursor"):
        service.data_catalog(consumer_scope="mcp-read", kind="dataset", limit=1, cursor=tampered)


def test_pipeline_projection_hashes_sensitive_refs_and_can_prove_pass(connection) -> None:
    _insert_run(connection)
    result = _service(connection, policy=_policy()).pipeline_run(
        consumer_scope="mcp-read", run_id="run-1", as_of=NOW,
    )
    assert result["quality"]["status"] == "pass"
    item = result["data"]["items"][0]
    assert item["partition_ref"].startswith("partition:v1:")
    assert item["definition_hash"] == "definition-hash"
    assert item["source_call_budget"] == 5
    serialized = json.dumps(result, default=str)
    for raw in ("account:secret", "object:secret", "raw secret failure", "raw stage error"):
        assert raw not in serialized


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"status": "failed", "rule_status": "failed"}, "failed"),
        ({"stages": (("collect", "succeeded"),), "rule_status": "pass"}, "partial"),
        ({"watermark_at": NOW - timedelta(days=2)}, "stale"),
    ],
)
def test_pipeline_status_precedence(connection, kwargs, expected) -> None:
    _insert_run(connection, **kwargs)
    result = _service(connection, policy=_policy()).pipeline_run(
        consumer_scope="mcp-read", run_id="run-1", as_of=NOW,
    )
    assert result["quality"]["status"] == expected


def test_succeeded_run_without_executable_policy_is_not_green(connection) -> None:
    _insert_run(connection)
    result = _service(connection).pipeline_run(consumer_scope="mcp-read", run_id="run-1", as_of=NOW)
    assert result["quality"]["status"] == "not_assessed"


def test_unknown_stage_and_rule_are_redacted_and_prevent_green(connection) -> None:
    _insert_run(connection, stages=(("collect", "succeeded"), ("mystery", "succeeded")))
    result = _service(connection, policy=_policy()).pipeline_run(
        consumer_scope="mcp-read", run_id="run-1", as_of=NOW,
    )
    assert result["quality"]["status"] == "not_assessed"
    assert result["data"]["items"][0]["stages"][1]["stage_name"] == "redacted"

    connection.execute("UPDATE control.quality_results SET rule_id='mystery-rule'")
    quality = _service(connection, policy=_policy()).data_quality(
        consumer_scope="mcp-read", dataset_id="dataset.fixture", run_id="run-1", as_of=NOW,
    )
    assert quality["quality"]["status"] != "pass"
    assert quality["data"]["items"][0]["rule_id"] == "redacted"


def test_incomplete_required_stage_and_unknown_watermark_prevent_green(connection) -> None:
    _insert_run(connection, stages=(("collect", "succeeded"), ("publish", "running")))
    service = _service(connection, policy=_policy())
    result = service.pipeline_run(consumer_scope="mcp-read", run_id="run-1", as_of=NOW)
    assert result["quality"]["status"] == "partial"

    connection.execute("UPDATE control.pipeline_stage_runs SET status='succeeded' WHERE stage_name='publish'")
    connection.execute(
        "INSERT INTO control.watermarks VALUES (?,?,?,?,?,?)",
        ["pipeline.fixture", "account:secret:run-1", "secret-type", "secret-value", "run-1", NOW],
    )
    unknown = service.pipeline_run(consumer_scope="mcp-read", run_id="run-1", as_of=NOW)
    assert unknown["quality"]["status"] == "not_assessed"
    assert unknown["data"]["items"][0]["watermarks"][1]["watermark_type"] == "redacted"


def test_quality_exact_run_can_pass_but_dataset_wide_needs_coverage_policy(connection) -> None:
    _insert_run(connection)
    service = _service(connection, policy=_policy())
    exact = service.data_quality(
        consumer_scope="mcp-read", dataset_id="dataset.fixture", run_id="run-1", as_of=NOW,
    )
    assert exact["quality"]["status"] == "pass"
    dataset_wide = service.data_quality(
        consumer_scope="mcp-read", dataset_id="dataset.fixture", as_of=NOW,
    )
    assert dataset_wide["quality"]["status"] == "not_assessed"


def test_pipeline_list_uses_stable_bounded_cursor(connection) -> None:
    _insert_run(connection, run_id="run-1")
    _insert_run(connection, run_id="run-2")
    service = _service(connection, policy=_policy())
    first = service.pipeline_run(
        consumer_scope="mcp-read", pipeline_id="pipeline.fixture", as_of=NOW, limit=1,
    )
    assert [item["run_id"] for item in first["data"]["items"]] == ["run-1"]
    second = service.pipeline_run(
        consumer_scope="mcp-read", pipeline_id="pipeline.fixture", as_of=NOW, limit=1,
        cursor=first["data"]["next_cursor"],
    )
    assert [item["run_id"] for item in second["data"]["items"]] == ["run-2"]
    assert second["data"]["next_cursor"] is None


def test_query_failure_returns_unavailable_and_inputs_are_strict(connection) -> None:
    service = _service(connection)
    with pytest.raises(ReadModelRequestError, match="forbidden"):
        service.pipeline_run(consumer_scope="other", run_id="run-1")
    with pytest.raises(ReadModelRequestError, match="invalid_query_mode"):
        service.pipeline_run(consumer_scope="mcp-read")
    with pytest.raises(ReadModelRequestError, match="invalid_limit"):
        service.data_catalog(consumer_scope="mcp-read", kind="dataset", limit=51)
    connection.execute("DROP TABLE control.quality_results")
    result = service.data_quality(
        consumer_scope="mcp-read", dataset_id="dataset.fixture", as_of=NOW,
    )
    assert result["quality"]["status"] == "unavailable"
    assert result["data"]["items"] == []
