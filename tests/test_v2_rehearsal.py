from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from kis_portfolio.adapters.outbound.fixture_source import FixtureSourceAdapter
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import ManagedPipelineRunner
from kis_portfolio.platform.read_models import GovernanceReadModel
from kis_portfolio.platform.rehearsal import build_owned_portfolio_fixture_pipeline


ROOT = Path(__file__).parents[1]


def test_owned_portfolio_fixture_pipeline_end_to_end(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "rehearsal.duckdb"))
    MigrationRunner(con).apply()
    source = FixtureSourceAdapter(ROOT / "tests/fixtures/v2/kis_owned_portfolio.json")
    repository = V2WarehouseRepository(con)
    definition = build_owned_portfolio_fixture_pipeline(source, repository)
    runner = ManagedPipelineRunner(con)
    first = runner.run(definition, logical_date=date(2026, 8, 28), slot="16:00")
    second = runner.run(definition, logical_date=date(2026, 8, 28), slot="16:00")
    assert first.status == "succeeded"
    assert second.run_id == first.run_id and second.reused is True
    assert repository.table_count("bronze.source_observations") == 5
    assert repository.table_count("gold.portfolio_daily_state") == 1
    read_model = GovernanceReadModel(con, ROOT)
    assert read_model.pipeline_status(first.run_id)["succeeded_stage_count"] == 4
    assert read_model.quality(first.run_id)[0]["status"] == "pass"
    assert len(read_model.lineage(first.run_id)) >= 3
    con.close()
