from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.consensus_fixtures import normalize_alpha_fixture
from kis_portfolio.adapters.outbound.consensus_warehouse import (
    ConsensusWarehouseRepository,
    snapshot_from_row,
)
from kis_portfolio.platform.consensus_registry import load_consensus_contract_bundle
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.forward_outlook import (
    PRIVATE_BACKUP_STOP_BYTES,
    SILVER_STOP_ROWS,
    ConsensusCallPlan,
    HeldIssuerCandidate,
    TermsReview,
    calculate_forward_revision,
    provider_rolling_comparison,
    publish_session_watermark,
    record_coverage_quality,
    require_owner_only_consumer,
    require_production_activation,
    require_provider_consensus_origin,
    resolve_held_issuer_allowlist,
    three_year_retention_cutoff,
    validate_call_plan,
    validate_capacity,
    validate_terms_review,
)
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


FIXTURE = Path(__file__).parent / "fixtures/v2/alpha_consensus_synthetic.json"
FETCHED_1 = datetime(2026, 9, 10, 1, tzinfo=UTC)
FETCHED_2 = datetime(2026, 9, 11, 1, tzinfo=UTC)
SESSION = date(2026, 9, 9)


def _document() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def warehouse(tmp_path: Path):
    connection = duckdb.connect(str(tmp_path / "forward.duckdb"))
    MigrationRunner(connection).apply()
    bundle = load_consensus_contract_bundle()
    yield connection, bundle, ConsensusWarehouseRepository(connection)
    connection.close()


def _normalized(bundle, *, fetched_at=FETCHED_1, document=None):
    return normalize_alpha_fixture(
        document or _document(),
        bundle=bundle,
        issuer_id="issuer.fixture.us-01",
        expected_symbol="SYNTH",
        fetched_at=fetched_at,
        us_session_date=SESSION,
        request_id=f"fixture-request-{fetched_at.isoformat()}",
    )


def test_contract_bundle_is_exact_approved_and_inactive() -> None:
    bundle = load_consensus_contract_bundle()
    assert bundle.source["id"] == "source.alpha-vantage-personal"
    assert bundle.collection["id"] == "collection.alpha-vantage-consensus-forward-v1"
    assert bundle.dataset["id"] == "dataset.alpha-vantage-consensus-forward-snapshot"
    assert bundle.pipeline["id"] == "pipeline.alpha-vantage-consensus-forward-v1"
    assert bundle.activation_state == "inactive"
    assert len(bundle.definition_hash) == 64
    with pytest.raises(RuntimeError, match="production gate"):
        require_production_activation(bundle)


def test_held_allowlist_is_exact_and_bounded() -> None:
    eligible = HeldIssuerCandidate(
        "issuer.us-01",
        "instrument.us-01",
        "SYNTH1",
        "NASD",
        "equity",
        "overseas_direct",
        "USD",
        Decimal("1"),
        "pass",
    )
    excluded = replace(eligible, issuer_id="issuer.kr-01", market="KRX", provider_symbol="000001")
    assert resolve_held_issuer_allowlist((excluded, eligible)) == (eligible,)
    with pytest.raises(ValueError, match="duplicate issuer"):
        resolve_held_issuer_allowlist((eligible, replace(eligible, provider_symbol="SYNTH2")))
    with pytest.raises(ValueError, match="passing quality"):
        resolve_held_issuer_allowlist((replace(eligible, quality_status="partial"),))
    too_many = tuple(
        replace(
            eligible,
            issuer_id=f"issuer.us-{index:02d}",
            instrument_id=f"instrument.us-{index:02d}",
            provider_symbol=f"SYNTH{index}",
        )
        for index in range(9)
    )
    with pytest.raises(ValueError, match="eight-call"):
        resolve_held_issuer_allowlist(too_many)


def test_fixture_parser_is_typed_strict_and_discards_provider_messages(warehouse) -> None:
    _, bundle, _ = warehouse
    result = _normalized(bundle)
    assert result.status == "pass"
    assert len(result.rows) == 4
    eps, revenue = result.rows[:2]
    assert eps.metric == "eps"
    assert eps.estimate_average == Decimal("10.00")
    assert eps.revision_down_trailing_7_days is None
    assert revenue.metric == "revenue"
    assert revenue.average_7_days_ago is None
    assert len(eps.source_request_ref) == 64

    message = "synthetic provider free-text that must not escape"
    information = normalize_alpha_fixture(
        {"fixture_only": True, "payload": {"Information": message}},
        bundle=bundle,
        issuer_id="issuer.fixture.us-01",
        expected_symbol="SYNTH",
        fetched_at=FETCHED_1,
        us_session_date=SESSION,
        request_id="information-fixture",
    )
    assert information.status == "partial"
    assert information.missing_reason == "provider_information"
    assert message not in repr(information)

    drifted = _document()
    drifted["payload"]["estimates"][0]["unexpected"] = "not allowlisted"
    with pytest.raises(ValueError, match="18-field allowlist"):
        _normalized(bundle, document=drifted)


def test_repository_is_append_only_and_system_as_of_excludes_future(warehouse) -> None:
    connection, bundle, repository = warehouse
    first = _normalized(bundle).rows[0]
    revised_document = deepcopy(_document())
    revised_document["payload"]["estimates"][0]["eps_estimate_average"] = "10.50"
    revised = _normalized(bundle, fetched_at=FETCHED_2, document=revised_document).rows[0]
    first_id = repository.record_snapshot(first, bundle=bundle, pipeline_run_id="run-1")
    assert repository.record_snapshot(first, bundle=bundle, pipeline_run_id="run-1") == first_id
    revised_id = repository.record_snapshot(revised, bundle=bundle, pipeline_run_id="run-2")
    assert first_id != revised_id
    before = repository.snapshots_as_of(
        cutoff_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        issuer_id=first.issuer_id,
    )
    after = repository.snapshots_as_of(
        cutoff_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
        issuer_id=first.issuer_id,
    )
    assert snapshot_from_row(before[0]).estimate_average == Decimal("10.00")
    assert snapshot_from_row(after[0]).estimate_average == Decimal("10.50")
    assert before[0]["knowledge_mode"] == "forward_collected_system_as_of"
    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info('silver.alpha_vantage_consensus_forward_snapshots')"
        ).fetchall()
    }
    assert not {"raw_payload", "provider_message", "api_key"} & columns
    conflicting = replace(first, us_session_date=date(2026, 9, 8))
    with pytest.raises(ValueError, match="immutable fetched-at key"):
        repository.record_snapshot(conflicting, bundle=bundle)


def test_revision_and_provider_attributes_never_claim_historical_pit(warehouse) -> None:
    _, bundle, _ = warehouse
    first = _normalized(bundle).rows[0]
    revised_document = deepcopy(_document())
    revised_document["payload"]["estimates"][0]["eps_estimate_average"] = "10.50"
    current = _normalized(bundle, fetched_at=FETCHED_2, document=revised_document).rows[0]
    result = calculate_forward_revision(
        current,
        first,
        evaluation_at=datetime(2026, 9, 11, 2, tzinfo=UTC),
    )
    assert result.origin == "provider_consensus"
    assert result.average_delta == Decimal("0.50")
    assert result.average_change_pct == Decimal("5.00")
    rolling = provider_rolling_comparison(current, days=30)
    assert rolling.interpretation == "provider_attribute_not_historical_snapshot"
    assert rolling.delta == Decimal("0.75")
    with pytest.raises(ValueError, match="future fetched-at"):
        calculate_forward_revision(
            current,
            first,
            evaluation_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="scenarios"):
        require_provider_consensus_origin("user_scenario")
    with pytest.raises(ValueError, match="Telegram"):
        require_owner_only_consumer("telegram")
    require_owner_only_consumer("owner-only-analysis")


def test_terms_call_capacity_coverage_and_watermark_guards(warehouse) -> None:
    connection, _, _ = warehouse
    terms = TermsReview(date(2026, 9, 1), date(2026, 12, 1), "a" * 64)
    assert validate_terms_review(terms, as_of=date(2026, 9, 10)) == terms
    with pytest.raises(ValueError, match="not valid"):
        validate_terms_review(terms, as_of=date(2026, 12, 2))
    with pytest.raises(ValueError, match="quarterly"):
        validate_terms_review(
            TermsReview(date(2026, 1, 1), date(2026, 7, 1), "b" * 64),
            as_of=date(2026, 2, 1),
        )
    assert three_year_retention_cutoff(date(2028, 2, 29)) == date(2025, 2, 28)
    plan = ConsensusCallPlan(
        ("issuer-1", "issuer-2", "issuer-3", "issuer-4", "issuer-5"),
        ("S1", "S2", "S3", "S4", "S5"),
        date(2026, 9, 10),
    )
    assert validate_call_plan(plan, terms_review=terms).scope_status == "expanded_within_hard_max"
    with pytest.raises(ValueError, match="fifteen seconds"):
        validate_call_plan(replace(plan, spacing_seconds=14), terms_review=terms)
    with pytest.raises(ValueError, match="same-run retries"):
        validate_call_plan(replace(plan, retry_count=1), terms_review=terms)
    assert validate_capacity(silver_rows=0, private_backup_bytes=0) == "pass"
    assert validate_capacity(silver_rows=SILVER_STOP_ROWS * 4 // 5, private_backup_bytes=0) == "review"
    with pytest.raises(ValueError, match="512 MiB"):
        validate_capacity(silver_rows=0, private_backup_bytes=PRIVATE_BACKUP_STOP_BYTES + 1)

    partial_id, status = record_coverage_quality(
        connection,
        run_id="coverage-1",
        expected_issuer_refs=("issuer-1", "issuer-2"),
        published_issuer_refs=("issuer-1",),
        evaluated_at=FETCHED_1,
    )
    assert status == "partial"
    assert not publish_session_watermark(
        connection,
        run_id="coverage-1",
        session_key="2026-09-09",
        quality_result_id=partial_id,
        observed_at=FETCHED_1,
    )
    pass_id, status = record_coverage_quality(
        connection,
        run_id="coverage-2",
        expected_issuer_refs=("issuer-1", "issuer-2"),
        published_issuer_refs=("issuer-1", "issuer-2"),
        evaluated_at=FETCHED_2,
    )
    assert status == "pass"
    assert publish_session_watermark(
        connection,
        run_id="coverage-2",
        session_key="2026-09-10",
        quality_result_id=pass_id,
        observed_at=FETCHED_2,
    )
    with pytest.raises(ValueError, match="backwards"):
        publish_session_watermark(
            connection,
            run_id="coverage-2",
            session_key="2026-09-09",
            quality_result_id=pass_id,
            observed_at=FETCHED_2,
        )


def test_private_parquet_backup_restores_forward_rows_and_view(warehouse, tmp_path: Path) -> None:
    connection, bundle, repository = warehouse
    for row in _normalized(bundle).rows:
        repository.record_snapshot(row, bundle=bundle)
    backup = tmp_path / "backup"
    manifest = export_v2_backup(connection, backup, database="alpha-fixture")
    qualified = "silver.alpha_vantage_consensus_forward_snapshots"
    assert manifest["tables"][qualified]["rows"] == 4
    assert repository.retention_candidates(
        fetched_before=datetime(2029, 9, 11, tzinfo=UTC)
    )
    target = tmp_path / "restored.duckdb"
    restore_v2_backup(backup, target)
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0] == 4
    assert restored.execute(
        "SELECT count(*) FROM silver.alpha_vantage_consensus_forward_latest"
    ).fetchone()[0] == 4
    restored.close()
