from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import (
    LineageEvidence,
    ManagedPipelineRunner,
    PipelineDefinition,
    PipelineExecutionError,
    PipelineStage,
    QualityEvidence,
    StageResult,
)
from kis_portfolio.platform.read_models import GovernanceReadModel


ROOT = Path(__file__).parents[1]


def test_pipeline_resumes_failed_stage_and_reuses_completed_run(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "pipeline.duckdb"))
    MigrationRunner(con).apply()
    runner = ManagedPipelineRunner(con)
    calls = {"collect": 0, "publish": 0}

    def collect(context):
        calls["collect"] += 1
        return StageResult(
            output_count=2,
            source_calls=1,
            quality=(QualityEvidence("dataset.price-bar-daily", "nonempty", "pass", "2", ">0"),),
        )

    def publish(context):
        calls["publish"] += 1
        if calls["publish"] == 1:
            raise RuntimeError("injected failure")
        return StageResult(
            input_count=2,
            output_count=2,
            lineage=(LineageEvidence("dataset.price-bar-daily", "dataset.portfolio-daily-state", "fixture-publish", "1.0.0"),),
        )

    definition = PipelineDefinition(
        "pipeline.fixture-owned-core-v2", "1.0.0",
        (PipelineStage("collect", collect), PipelineStage("publish", publish)),
        source_call_budget=2,
    )
    with pytest.raises(PipelineExecutionError) as failed:
        runner.run(definition, logical_date=date(2026, 8, 28), slot="16:00")
    run_id = failed.value.run_id
    outcome = runner.run(definition, logical_date=date(2026, 8, 28), slot="16:00")
    assert outcome.run_id == run_id
    assert outcome.status == "succeeded"
    assert calls == {"collect": 1, "publish": 2}
    reused = runner.run(definition, logical_date=date(2026, 8, 28), slot="16:00")
    assert reused.reused is True
    assert calls == {"collect": 1, "publish": 2}

    read_model = GovernanceReadModel(con, ROOT)
    assert read_model.pipeline_status(run_id)["succeeded_stage_count"] == 2
    assert read_model.quality(run_id)[0]["status"] == "pass"
    assert read_model.lineage(run_id)[0]["transform_id"] == "fixture-publish"
    assert any(item["id"] == "source.kis-open-api" for item in read_model.catalog()["sources"])
    con.close()


def test_pipeline_stops_before_exceeding_source_call_budget(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "budget.duckdb"))
    MigrationRunner(con).apply()
    runner = ManagedPipelineRunner(con)
    definition = PipelineDefinition(
        "pipeline.fixture-budget", "1.0.0",
        (PipelineStage("collect", lambda _: StageResult(source_calls=3)),),
        source_call_budget=2,
    )
    with pytest.raises(PipelineExecutionError, match="source call budget exceeded"):
        runner.run(definition, logical_date=date(2026, 8, 28), slot="manual")
    con.close()
