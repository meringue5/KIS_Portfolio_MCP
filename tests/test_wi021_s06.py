from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.trade_cash_backfill import (
    BackfillAccountScope,
    apply_call_budget,
    plan_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_pipeline import (
    BackfillSourcePage,
    FetchedBackfillPartition,
    build_trade_cash_partition_handler,
)
from kis_portfolio.services.trade_cash_backfill_runtime import execute_trade_cash_backfill
from kis_portfolio.services.wi021_s06 import WI021S06Config, reconcile_wi021_s06
from kis_portfolio.services import wi021_s06


def _config(plan, *, quality=6, lineage=3, watermarks=1):
    return WI021S06Config(
        start_date=plan.source_plan.start_date,
        end_date=plan.source_plan.end_date,
        as_of_date=plan.source_plan.as_of_date,
        expected_plan_hash=plan.source_plan.plan_hash,
        expected_budget_hash=plan.budget_hash,
        project="project",
        bucket="private",
        expected_partitions=len(plan.source_plan.callable_partitions),
        expected_quality_rows=quality,
        expected_lineage_rows=lineage,
        expected_watermark_streams=watermarks,
    )


def test_reconciliation_accepts_complete_empty_page_history(tmp_path: Path) -> None:
    connection = duckdb.connect(str(tmp_path / "reconcile.duckdb"))
    MigrationRunner(connection).apply()
    plan = apply_call_budget(plan_trade_cash_backfill(
        [BackfillAccountScope("ria", "01")],
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 5),
        as_of_date=date(2026, 8, 5), partition_days=2,
    ))

    def fetch(_partition, gate):
        gate.reserve(_partition.key)
        return FetchedBackfillPartition((BackfillSourcePage(
            {"output1": []}, datetime(2026, 8, 28, tzinfo=UTC),
        ),), True)

    execute_trade_cash_backfill(connection, plan, build_trade_cash_partition_handler(connection, fetch))
    result = reconcile_wi021_s06(connection, _config(plan))
    assert result["partition_count"] == 3
    assert result["source_calls"] == 3
    assert result["stage_status_counts"] == {"succeeded": 9}
    assert result["purchase_lots"] == 0
    connection.close()


def test_reconciliation_fails_on_incomplete_partition_set(tmp_path: Path) -> None:
    connection = duckdb.connect(str(tmp_path / "empty.duckdb"))
    MigrationRunner(connection).apply()
    plan = apply_call_budget(plan_trade_cash_backfill(
        [BackfillAccountScope("ria", "01")],
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 1), as_of_date=date(2026, 8, 1),
    ))
    with pytest.raises(RuntimeError, match="partition completion"):
        reconcile_wi021_s06(connection, _config(plan, quality=2, lineage=1))
    connection.close()


class _EvidenceStore:
    def put_bytes(self, payload, *, dataset_id, partition, media_type):
        return SimpleNamespace(uri="gs://private/evidence", content_hash="e" * 64)


def _orchestration_fixture(monkeypatch, tmp_path: Path, *, upload_fails: bool = False):
    config = WI021S06Config(
        start_date=date(2023, 8, 28), end_date=date(2026, 8, 28), as_of_date=date(2026, 8, 28),
        expected_plan_hash="plan", expected_budget_hash="budget",
        project="project", bucket="private", expected_partitions=1,
        expected_quality_rows=0, expected_lineage_rows=0, expected_watermark_streams=0,
    )
    plan = SimpleNamespace(
        source_plan=SimpleNamespace(
            plan_hash="plan", callable_partitions=(object(),), known_gaps=(),
        ),
        budget_hash="budget",
    )
    connection = duckdb.connect(str(tmp_path / "live.duckdb"))
    MigrationRunner(connection).apply()
    restored_connection = duckdb.connect(str(tmp_path / "restored-fixture.duckdb"))
    calls = []
    monkeypatch.setenv("KIS_RELEASE_IMAGE_DIGEST", "sha256:" + "a" * 64)
    monkeypatch.setenv("KIS_RELEASE_GIT_SHA", "b" * 40)
    monkeypatch.setattr(wi021_s06, "get_db_mode", lambda: "motherduck")
    monkeypatch.setattr(wi021_s06, "get_motherduck_database", lambda: "kis_portfolio")
    monkeypatch.setattr(wi021_s06, "_plan", lambda _config: (object(), plan))

    def export(_connection, path, *, database):
        calls.append(f"export:{path.name}")
        path.mkdir(parents=True)
        return {"tables": {"control.pipeline_runs": {"rows": 0}}}

    def upload(_store, path):
        calls.append(f"upload:{path.name}")
        if upload_fails:
            raise RuntimeError("fixture upload failure")
        return {
            "index_uri": f"gs://private/{path.name}", "index_sha256": "c" * 64,
            "byte_size": 1, "object_count": 1, "status": "uploaded",
        }

    monkeypatch.setattr(wi021_s06, "export_v2_backup", export)
    monkeypatch.setattr(wi021_s06, "upload_v2_backup", upload)
    monkeypatch.setattr(
        wi021_s06, "download_v2_backup",
        lambda _store, *, index_uri, index_sha256, destination: calls.append(f"download:{destination.name}"),
    )
    monkeypatch.setattr(
        wi021_s06, "restore_v2_backup",
        lambda backup, database: calls.append(f"restore:{Path(database).name}"),
    )

    class Source:
        def __init__(self, _accounts):
            calls.append("source:init")
            self.fetch = object()

    monkeypatch.setattr(wi021_s06, "KisTradeCashBackfillSource", Source)
    monkeypatch.setattr(wi021_s06, "build_trade_cash_partition_handler", lambda *_: object())
    monkeypatch.setattr(
        wi021_s06, "execute_trade_cash_backfill",
        lambda *_: calls.append("source:execute") or SimpleNamespace(
            partition_outcomes=(SimpleNamespace(reused=False),),
        ),
    )
    summary = {"partition_count": 1}
    monkeypatch.setattr(
        wi021_s06, "reconcile_wi021_s06",
        lambda *_: calls.append("reconcile") or summary,
    )
    monkeypatch.setattr(wi021_s06.duckdb, "connect", lambda *args, **kwargs: restored_connection)
    return config, connection, calls


def test_orchestration_verifies_private_pre_recovery_before_source(monkeypatch, tmp_path: Path) -> None:
    config, connection, calls = _orchestration_fixture(monkeypatch, tmp_path)
    result = wi021_s06.run_wi021_s06(
        config, connection_factory=lambda: connection, store_factory=lambda _bucket: _EvidenceStore(),
    )
    assert result["status"] == "succeeded"
    assert calls[0].startswith("export:kis-wi021-s06-") and calls[0].endswith("-pre")
    assert calls[1].startswith("upload:kis-wi021-s06-") and calls[1].endswith("-pre")
    assert calls[2:5] == [
        "download:pre-download", "restore:pre-restore.duckdb", "source:init",
    ]
    assert calls.index("source:execute") > calls.index("restore:pre-restore.duckdb")
    connection.close()


def test_pre_upload_failure_performs_zero_source_calls(monkeypatch, tmp_path: Path) -> None:
    config, connection, calls = _orchestration_fixture(monkeypatch, tmp_path, upload_fails=True)
    with pytest.raises(RuntimeError, match="fixture upload failure"):
        wi021_s06.run_wi021_s06(
            config, connection_factory=lambda: connection, store_factory=lambda _bucket: _EvidenceStore(),
        )
    assert calls[0].startswith("export:kis-wi021-s06-") and calls[0].endswith("-pre")
    assert calls[1].startswith("upload:kis-wi021-s06-") and calls[1].endswith("-pre")
    assert len(calls) == 2
    connection.close()
