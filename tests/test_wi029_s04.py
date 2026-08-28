from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from kis_portfolio.adapters.outbound.alert_warehouse import AlertWarehouseRepository
from kis_portfolio.modules.monitoring import (
    AlertCandidate,
    AlertEvaluation,
    AlertRuleVersion,
    CalibrationResult,
    ThresholdProfile,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.services import wi029_s04
from kis_portfolio.services.shadow_alerts import RULE_ID, RULE_VERSION


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, payload, *, dataset_id, partition, media_type):
        digest = hashlib.sha256(payload).hexdigest()
        uri = f"gs://private/{dataset_id}/{partition}/{digest}"
        self.objects.setdefault(uri, payload)
        return StoredObject(uri, digest, len(payload), media_type, True)

    def put_file(self, path, *, dataset_id, partition, media_type):
        return self.put_bytes(
            Path(path).read_bytes(), dataset_id=dataset_id,
            partition=partition, media_type=media_type,
        )

    def download(self, uri, destination, *, expected_sha256=None):
        payload = self.objects[uri]
        assert expected_sha256 in {None, hashlib.sha256(payload).hexdigest()}
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination


def test_wi029_s04_verifies_zero_external_path_and_private_round_trip(monkeypatch) -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    store = MemoryStore()
    monkeypatch.setattr(wi029_s04, "GCSObjectStore", lambda *_args, **_kwargs: store)
    monkeypatch.setattr(
        wi029_s04,
        "persist_wi029_s04_evidence",
        lambda _connection: {"shadow_window_status": "collecting"},
    )
    result = wi029_s04.verify_wi029_s04(
        connection, project="fixture-project", bucket="private-bucket"
    )
    assert result["status"] == "verified"
    assert result["migration"] == "0013"
    assert result["uploaded_object_count"] == result["backup_table_count"] + 1
    assert result["downloaded_object_count"] == result["uploaded_object_count"]
    assert result["restored_table_count"] == result["backup_table_count"]
    assert result["external_rule_count"] == 0
    assert result["telegram_claim_count"] == 0
    assert result["evidence"]["shadow_window_status"] == "collecting"
    connection.close()


def test_wi029_s04_persists_immutable_calibration_and_starts_shadow(monkeypatch) -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    report = {
        "replay_start": wi029_s04.REPLAY_START.isoformat(),
        "replay_end": wi029_s04.REPLAY_END.isoformat(),
        "source_mode": "retrospective_reconstructed",
        "observation_count": 7576,
        "eligible_count": 7576,
        "alert_count": 1364,
    }
    calibration = CalibrationResult(
        rule_set_id=RULE_ID,
        rule_set_version=RULE_VERSION,
        selected_profiles={"stock": ThresholdProfile("stock")},
        report=report,
        report_hash=wi029_s04.CALIBRATION_REPORT_HASH,
    )
    monkeypatch.setattr(wi029_s04, "calibrate_price_history", lambda *_args, **_kwargs: calibration)
    rule = AlertRuleVersion.from_document({
        "id": RULE_ID,
        "version": RULE_VERSION,
        "status": "approved",
        "minimum_delivery_severity": "watch",
        "delivery_mode": "shadow",
        "valid_from": datetime(2023, 1, 1, tzinfo=UTC),
        "valid_to": None,
        "metric_refs": ["price-shock"],
        "thresholds": {"profile": "fixture"},
        "limitations": ["shadow only"],
    })
    alerts = AlertWarehouseRepository(connection)
    alerts.register_rule(rule)
    candidate = AlertCandidate.build(rule, AlertEvaluation(
        subject_type="instrument",
        subject_id="opaque-instrument",
        evaluation_date=wi029_s04.SHADOW_START,
        evaluation_slot="kr-1000",
        session_key=f"krx:{wi029_s04.SHADOW_START.isoformat()}",
        evaluation_at=datetime(2026, 8, 28, 1, tzinfo=UTC),
        signal_state="normal",
        severity="normal",
        state_key="normal",
        quality_status="missing_current_price",
        input_lineage_hash="a" * 64,
        public_context={"summary": "fixture"},
        evaluation_run_id="fixture-run",
    ))
    alerts.apply_candidate(candidate)

    first = wi029_s04.persist_wi029_s04_evidence(
        connection, recorded_at=datetime(2026, 8, 28, 14, tzinfo=UTC)
    )
    second = wi029_s04.persist_wi029_s04_evidence(
        connection, recorded_at=datetime(2026, 8, 28, 15, tzinfo=UTC)
    )

    assert first["calibration_inserted"] is True
    assert second["calibration_inserted"] is False
    assert first["calibration_report_hash"] == wi029_s04.CALIBRATION_REPORT_HASH
    assert first["shadow_window_status"] == "collecting"
    assert first["initial_observed_session_count"] == 1
    assert first["initial_quality_suppressed_count"] == 1
    assert first["initial_external_send_count"] == 0
    assert connection.execute("SELECT count(*) FROM control.alert_calibration_runs").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM control.alert_shadow_windows").fetchone()[0] == 1
    connection.close()
