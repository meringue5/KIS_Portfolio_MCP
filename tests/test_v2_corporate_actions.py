from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.corporate_action_warehouse import (
    CorporateActionWarehouseRepository,
)
from kis_portfolio.adapters.outbound.kis_corporate_actions import (
    normalize_domestic_face_value,
    normalize_domestic_merger_split,
    normalize_overseas_period_right,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


BASE_TIME = datetime(2026, 8, 28, 1, tzinfo=UTC)
INSTRUMENT = "v1|KRX|005930"


def _observation(
    connection: duckdb.DuckDBPyConnection,
    *,
    source_record_id: str,
    payload: dict,
    fetched_at: datetime,
) -> str:
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository

    return V2WarehouseRepository(connection).record_observation(
        "dataset.corporate-action-event",
        SourceEnvelope(
            "source.kis-open-api",
            source_record_id,
            fetched_at,
            fetched_at,
            payload,
            content_hash,
            payload.get("quality_status", "pass"),
        ),
        "corporate-action-fixture-run",
    )


def _confirmed_split(knowledge_at: datetime = BASE_TIME) -> tuple[str, dict]:
    return normalize_domestic_face_value(
        {
            "sht_cd": "005930",
            "record_date": "20260820",
            "list_dt": "20260827",
            "inter_bf_face_amt": "5000",
            "inter_af_face_amt": "500",
        },
        knowledge_at=knowledge_at,
        source_confirmed=True,
    )


def test_confirmed_split_is_idempotent_and_has_reciprocal_adjustment_lineage() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    repository = CorporateActionWarehouseRepository(con)
    source_record_id, payload = _confirmed_split()
    observation_id = _observation(
        con, source_record_id=source_record_id, payload=payload, fetched_at=BASE_TIME
    )
    action_id, revision_id = repository.record_action(payload, observation_id)
    assert repository.record_action(payload, observation_id) == (action_id, revision_id)

    effects = {item["effect_type"]: item for item in repository.effects_for_revision(revision_id)}
    assert set(effects) == {"price_multiplier", "quantity_multiplier"}
    assert effects["quantity_multiplier"]["factor_numerator"] == Decimal("10")
    assert effects["quantity_multiplier"]["factor_denominator"] == Decimal("1")
    assert effects["price_multiplier"]["factor_numerator"] == Decimal("1")
    assert effects["price_multiplier"]["factor_denominator"] == Decimal("10")
    assert con.execute("SELECT count(*) FROM silver.corporate_actions").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM silver.corporate_action_revisions").fetchone()[0] == 1
    assert con.execute(
        "SELECT revision, action_status FROM silver.corporate_actions_current"
    ).fetchone() == (1, "confirmed")
    readiness = repository.adjustment_readiness_as_of(
        instrument_id=INSTRUMENT,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        knowledge_cutoff_at=BASE_TIME,
    )
    assert readiness["status"] == "pass"
    assert readiness["can_compute_returns"] is True
    con.close()


def test_provisional_split_revision_is_visible_at_its_cutoff_and_confirmation_appends() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    repository = CorporateActionWarehouseRepository(con)
    row = {
        "sht_cd": "005930",
        "record_date": "20260820",
        "list_dt": "20260827",
        "inter_bf_face_amt": "5000",
        "inter_af_face_amt": "500",
    }
    source_record_id, provisional = normalize_domestic_face_value(
        row, knowledge_at=BASE_TIME, source_confirmed=False
    )
    first_observation = _observation(
        con, source_record_id=source_record_id, payload=provisional, fetched_at=BASE_TIME
    )
    action_id, first_revision = repository.record_action(provisional, first_observation)

    confirmed_at = BASE_TIME + timedelta(days=1)
    same_source_record_id, confirmed = normalize_domestic_face_value(
        row, knowledge_at=confirmed_at, source_confirmed=True
    )
    assert same_source_record_id == source_record_id
    second_observation = _observation(
        con, source_record_id=source_record_id, payload=confirmed, fetched_at=confirmed_at
    )
    same_action_id, second_revision = repository.record_action(confirmed, second_observation)
    assert same_action_id == action_id
    assert second_revision != first_revision

    before = repository.adjustment_readiness_as_of(
        instrument_id=INSTRUMENT,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        knowledge_cutoff_at=confirmed_at - timedelta(microseconds=1),
    )
    after = repository.adjustment_readiness_as_of(
        instrument_id=INSTRUMENT,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        knowledge_cutoff_at=confirmed_at,
    )
    assert before["status"] == "blocked" and before["can_compute_returns"] is False
    assert after["status"] == "pass" and after["can_compute_returns"] is True
    assert con.execute(
        "SELECT count(*) FROM silver.corporate_action_revisions WHERE corporate_action_id=?",
        [action_id],
    ).fetchone()[0] == 2

    changed_without_time_advance = confirmed | {"post_action_units": Decimal("20")}
    with pytest.raises(ValueError, match="knowledge_at must advance"):
        repository.record_action(changed_without_time_advance, second_observation)
    con.close()


def test_unverified_kis_ratio_and_merger_terms_fail_closed() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    repository = CorporateActionWarehouseRepository(con)
    overseas_record, overseas = normalize_overseas_period_right(
        {
            "pdno": "AAPL",
            "rght_type_cd": "14",
            "acpl_bass_dt": "20260827",
            "stck_alct_rt": "4",
            "dfnt_yn": "확정",
        },
        knowledge_at=BASE_TIME,
        market="NASDAQ",
    )
    overseas_observation = _observation(
        con, source_record_id=overseas_record, payload=overseas, fetched_at=BASE_TIME
    )
    repository.record_action(overseas, overseas_observation)
    blocked = repository.adjustment_readiness_as_of(
        instrument_id="v1|NASDAQ|AAPL",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        knowledge_cutoff_at=BASE_TIME,
    )
    assert blocked["status"] == "blocked"
    assert blocked["can_compute_returns"] is False

    merger_record, merger = normalize_domestic_merger_split(
        {
            "sht_cd": "005930",
            "record_date": "20260820",
            "list_dt": "20260827",
            "merge_type": "인적분할",
            "merge_rate": "1:0.25",
            "seq": "1",
            "opp_cust_cd": "000001",
        },
        knowledge_at=BASE_TIME,
    )
    assert merger["action_type"] == "spin_off"
    assert merger["terms_status"] == "unknown"
    merger_observation = _observation(
        con, source_record_id=merger_record, payload=merger, fetched_at=BASE_TIME
    )
    repository.record_action(merger, merger_observation)
    assert repository.adjustment_readiness_as_of(
        instrument_id=INSTRUMENT,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        knowledge_cutoff_at=BASE_TIME,
    )["can_compute_returns"] is False
    con.close()


def test_absent_governed_coverage_does_not_claim_no_action() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    readiness = CorporateActionWarehouseRepository(con).adjustment_readiness_as_of(
        instrument_id=INSTRUMENT,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        knowledge_cutoff_at=BASE_TIME,
    )
    assert readiness == {
        "status": "not_assessed",
        "can_compute_returns": False,
        "reason": "no_governed_corporate_action_coverage",
        "action_count": 0,
    }
    con.close()


def test_corporate_action_ledger_survives_complete_backup_restore(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    MigrationRunner(source).apply()
    source_record_id, payload = _confirmed_split()
    observation_id = _observation(
        source, source_record_id=source_record_id, payload=payload, fetched_at=BASE_TIME
    )
    action_id, _ = CorporateActionWarehouseRepository(source).record_action(payload, observation_id)
    backup_dir = tmp_path / "backup"
    manifest = export_v2_backup(source, backup_dir, database="fixture")
    source.close()
    assert manifest["tables"]["silver.corporate_actions"]["rows"] == 1
    assert manifest["tables"]["silver.corporate_action_adjustment_effects"]["rows"] == 2

    target = tmp_path / "restored.duckdb"
    result = restore_v2_backup(backup_dir, target)
    assert result["status"] == "verified"
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute(
        "SELECT corporate_action_id, action_status FROM silver.corporate_actions_current"
    ).fetchone() == (action_id, "confirmed")
    assert restored.execute(
        "SELECT count(*) FROM silver.corporate_action_adjustment_effects"
    ).fetchone()[0] == 2
    restored.close()
