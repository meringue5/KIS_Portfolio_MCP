from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.alert_warehouse import (
    AlertClaimError,
    AlertWarehouseConflictError,
    AlertWarehouseRepository,
)
from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.modules.monitoring import (
    AlertCandidate,
    AlertContractError,
    AlertEvaluation,
    AlertRuleVersion,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


BASE_TIME = datetime(2026, 8, 28, 1, tzinfo=UTC)


def _rule(*, mode: str = "shadow") -> AlertRuleVersion:
    return AlertRuleVersion.from_document({
        "id": "rule.portfolio-drawdown",
        "version": "1.0.0",
        "status": "approved",
        "minimum_delivery_severity": "warning",
        "delivery_mode": mode,
        "valid_from": BASE_TIME - timedelta(days=1),
        "valid_to": None,
        "metric_refs": ["metric.portfolio-drawdown:1.0.0"],
        "thresholds": {"warning": "bootstrap-pending-wi029"},
    })


def _candidate(
    *,
    slot: str,
    session: str,
    state: str,
    severity: str,
    state_key: str,
    at: datetime,
    quality: str = "pass",
    lineage: str | None = None,
    context: dict[str, object] | None = None,
    rule: AlertRuleVersion | None = None,
) -> AlertCandidate:
    evaluation = AlertEvaluation(
        subject_type="portfolio",
        subject_id="subject_opaque_owner",
        evaluation_date=date(2026, 8, 28),
        evaluation_slot=slot,
        session_key=session,
        evaluation_at=at,
        signal_state=state,
        severity=severity,
        state_key=state_key,
        quality_status=quality,
        input_lineage_hash=lineage or f"lineage-{slot}-{state_key}",
        public_context=context or {
            "subject_label": "내 포트폴리오",
            "summary": "허용된 백분율 기반 상태 요약",
            "reason_codes": [state_key],
            "change_percent": "-3.2",
            "metric_refs": ["metric.portfolio-drawdown:1.0.0"],
            "quality_status": quality,
        },
        evaluation_run_id=f"run-{slot}-{at.hour}",
    )
    return AlertCandidate.build(rule or _rule(), evaluation)


def _repository() -> tuple[duckdb.DuckDBPyConnection, AlertWarehouseRepository]:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    return connection, AlertWarehouseRepository(connection)


def test_slots_and_us_close_have_stable_non_overlapping_identity() -> None:
    us = _candidate(
        slot="us-close", session="us-close:2026-08-27", state="active",
        severity="warning", state_key="price-shock-warning", at=BASE_TIME,
    )
    replay = _candidate(
        slot="us-close", session="us-close:2026-08-27", state="active",
        severity="warning", state_key="price-shock-warning", at=BASE_TIME,
    )
    kr = _candidate(
        slot="kr-1000", session="krx:2026-08-28", state="active",
        severity="warning", state_key="price-shock-warning", at=BASE_TIME + timedelta(minutes=1),
    )
    assert us.candidate_id == replay.candidate_id
    assert us.alert_identity == kr.alert_identity
    assert us.candidate_id != kr.candidate_id
    with pytest.raises(AlertContractError, match="slot"):
        _candidate(
            slot="kr-1100", session="krx:2026-08-28", state="normal",
            severity="normal", state_key="normal", at=BASE_TIME,
        )


def test_state_machine_deduplicates_and_handles_escalation_recovery_reentry() -> None:
    connection, repository = _repository()
    entered = _candidate(
        slot="kr-1000", session="krx:2026-08-28", state="active",
        severity="warning", state_key="drawdown-warning", at=BASE_TIME,
    )
    first = repository.apply_candidate(entered)
    assert first.transition is not None
    assert (first.transition.transition_type, first.transition.episode) == ("entered", 1)
    assert first.transition.delivery_required is True
    assert repository.apply_candidate(entered).transition is None

    same_later = _candidate(
        slot="kr-1430", session="krx:2026-08-28", state="active",
        severity="warning", state_key="drawdown-warning", at=BASE_TIME + timedelta(hours=4),
    )
    assert repository.apply_candidate(same_later).transition is None

    escalated = _candidate(
        slot="kr-1600", session="krx:2026-08-28", state="active",
        severity="critical", state_key="drawdown-critical", at=BASE_TIME + timedelta(hours=6),
    )
    second = repository.apply_candidate(escalated).transition
    assert second is not None
    assert second.transition_type == "escalated"
    assert second.delivery_required is True

    recovered = _candidate(
        slot="kr-1000", session="krx:2026-08-29", state="normal",
        severity="normal", state_key="normal", at=BASE_TIME + timedelta(days=1),
    )
    third = repository.apply_candidate(recovered).transition
    assert third is not None
    assert third.transition_type == "recovered"
    assert third.delivery_required is True
    assert third.delivery_severity == "critical"

    reentered = _candidate(
        slot="kr-1430", session="krx:2026-08-29", state="active",
        severity="warning", state_key="drawdown-warning", at=BASE_TIME + timedelta(days=1, hours=4),
    )
    fourth = repository.apply_candidate(reentered).transition
    assert fourth is not None
    assert (fourth.transition_type, fourth.episode) == ("reentered", 2)
    assert connection.execute("SELECT count(*) FROM control.alert_state_revisions").fetchone()[0] == 4
    # A historical candidate that was originally a no-op remains processed and cannot re-enter later state.
    assert repository.apply_candidate(same_later).transition is None
    assert connection.execute("SELECT count(*) FROM control.alert_state_revisions").fetchone()[0] == 4
    connection.close()


def test_non_pass_quality_and_sensitive_context_fail_closed() -> None:
    connection, repository = _repository()
    entered = _candidate(
        slot="kr-1000", session="krx:2026-08-28", state="active",
        severity="warning", state_key="warning", at=BASE_TIME,
    )
    repository.apply_candidate(entered)
    partial = _candidate(
        slot="kr-1430", session="krx:2026-08-28", state="normal",
        severity="normal", state_key="normal", at=BASE_TIME + timedelta(hours=4), quality="partial",
    )
    assert repository.apply_candidate(partial).transition is None
    current = repository.current_state(entered.alert_identity)
    assert current is not None and current.current_state == "active"
    with pytest.raises(AlertClaimError, match="not eligible"):
        repository.claim_dispatch(
            candidate_id=partial.candidate_id, channel="shadow", destination_ref="dest_shadow_owner",
            claimant_id="worker_fixture", lease_token="private-token", claimed_at=BASE_TIME + timedelta(hours=4),
        )
    with pytest.raises(AlertContractError, match="non-allowlisted"):
        _candidate(
            slot="kr-1600", session="krx:2026-08-28", state="active", severity="warning",
            state_key="warning", at=BASE_TIME + timedelta(hours=6),
            context={"account_number": "12345678"},
        )
    with pytest.raises(AlertContractError, match="sensitive content"):
        _candidate(
            slot="kr-1600", session="krx:2026-08-28", state="active", severity="warning",
            state_key="warning", at=BASE_TIME + timedelta(hours=6),
            context={"summary": "account 12345678"},
        )
    connection.close()


def test_candidate_conflict_and_rule_version_mutation_are_rejected() -> None:
    connection, repository = _repository()
    first = _candidate(
        slot="kr-1000", session="krx:2026-08-28", state="active",
        severity="warning", state_key="warning", at=BASE_TIME, lineage="lineage-a",
    )
    repository.write_candidate(first)
    conflict = _candidate(
        slot="kr-1000", session="krx:2026-08-28", state="active",
        severity="warning", state_key="warning", at=BASE_TIME, lineage="lineage-b",
    )
    with pytest.raises(AlertWarehouseConflictError, match="changed on replay"):
        repository.write_candidate(conflict)
    changed = dict(_rule().document)
    changed["delivery_mode"] = "off"
    with pytest.raises(AlertWarehouseConflictError, match="changed in place"):
        repository.register_rule(AlertRuleVersion.from_document(changed))
    connection.close()


def test_late_historical_candidate_is_recorded_without_rewriting_current_state() -> None:
    connection, repository = _repository()
    current = _candidate(
        slot="kr-1600", session="krx:2026-08-28", state="active",
        severity="warning", state_key="warning", at=BASE_TIME + timedelta(hours=6),
    )
    repository.apply_candidate(current)
    late = _candidate(
        slot="kr-1000", session="krx:2026-08-28", state="normal",
        severity="normal", state_key="normal", at=BASE_TIME,
    )
    assert repository.apply_candidate(late).transition is None
    assert repository.current_state(current.alert_identity).current_state == "active"  # type: ignore[union-attr]
    assert connection.execute(
        "SELECT outcome_type FROM control.alert_candidate_outcomes WHERE candidate_id=?", [late.candidate_id]
    ).fetchone()[0] == "out_of_order"
    connection.close()


def test_dispatch_claim_is_idempotent_retryable_and_unknown_is_terminal() -> None:
    connection, repository = _repository()
    candidate = _candidate(
        slot="kr-1000", session="krx:2026-08-28", state="active",
        severity="warning", state_key="warning", at=BASE_TIME,
    )
    repository.apply_candidate(candidate)
    claim = repository.claim_dispatch(
        candidate_id=candidate.candidate_id, channel="shadow", destination_ref="dest_shadow_owner",
        claimant_id="worker_a", lease_token="lease-a", claimed_at=BASE_TIME,
    )
    assert claim.acquired is True
    duplicate = repository.claim_dispatch(
        candidate_id=candidate.candidate_id, channel="shadow", destination_ref="dest_shadow_owner",
        claimant_id="worker_b", lease_token="lease-b", claimed_at=BASE_TIME + timedelta(seconds=1),
    )
    assert (duplicate.acquired, duplicate.status) == (False, "claimed")
    repository.record_attempt(
        dispatch_id=claim.dispatch_id, lease_token="lease-a", outcome="retryable_failure",
        started_at=BASE_TIME, completed_at=BASE_TIME + timedelta(seconds=1), error_code="TIMEOUT",
    )
    retried = repository.claim_dispatch(
        candidate_id=candidate.candidate_id, channel="shadow", destination_ref="dest_shadow_owner",
        claimant_id="worker_b", lease_token="lease-b", claimed_at=BASE_TIME + timedelta(seconds=2),
    )
    assert retried.acquired is True
    repository.record_attempt(
        dispatch_id=claim.dispatch_id, lease_token="lease-b", outcome="unknown",
        started_at=BASE_TIME + timedelta(seconds=2),
        completed_at=BASE_TIME + timedelta(seconds=3), error_code="POST_SEND_TIMEOUT",
    )
    terminal = repository.claim_dispatch(
        candidate_id=candidate.candidate_id, channel="shadow", destination_ref="dest_shadow_owner",
        claimant_id="worker_c", lease_token="lease-c", claimed_at=BASE_TIME + timedelta(hours=1),
    )
    assert (terminal.acquired, terminal.status, terminal.attempt_count) == (False, "unknown", 2)
    with pytest.raises(AlertClaimError, match="external delivery mode"):
        repository.claim_dispatch(
            candidate_id=candidate.candidate_id, channel="telegram", destination_ref="dest_owner_primary",
            claimant_id="worker_c", lease_token="lease-c", claimed_at=BASE_TIME,
        )
    connection.close()


def test_alert_ledger_is_in_complete_parquet_restore(tmp_path: Path) -> None:
    expected = {
        "gold.alert_candidates", "control.alert_rule_versions", "control.alert_state_revisions",
        "control.alert_candidate_outcomes",
        "control.alert_dispatch_claims", "control.alert_delivery_attempts",
    }
    assert expected <= set(v2_backup_table_names())
    connection = duckdb.connect(str(tmp_path / "source.duckdb"))
    MigrationRunner(connection).apply()
    repository = AlertWarehouseRepository(connection)
    candidate = _candidate(
        slot="kr-1000", session="krx:2026-08-28", state="active",
        severity="warning", state_key="warning", at=BASE_TIME,
    )
    repository.apply_candidate(candidate)
    backup = tmp_path / "backup"
    manifest = export_v2_backup(connection, backup, database="fixture")
    connection.close()
    assert manifest["tables"]["gold.alert_candidates"]["rows"] == 1
    assert manifest["tables"]["control.alert_state_revisions"]["rows"] == 1
    restored = restore_v2_backup(backup, tmp_path / "restored.duckdb")
    assert restored["status"] == "verified"
