from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import duckdb

from kis_portfolio.adapters.outbound.instrument_warehouse import InstrumentWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.shadow_alerts import run_shadow_signal_evaluation


LOGICAL_DATE = date(2026, 8, 28)


def _warehouse(*, include_us: bool = False, unknown: bool = False) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    repository = V2WarehouseRepository(connection)
    fetched = datetime(2026, 8, 28, 7, tzinfo=UTC)
    body = {"fixture": "shadow-alert"}
    observation_id = repository.record_observation(
        "dataset.price-bar-daily",
        SourceEnvelope(
            "source.kis-open-api", "shadow-price", fetched, fetched, body,
            hashlib.sha256(json.dumps(body).encode()).hexdigest(), "pass",
        ),
        "shadow-fixture",
    )
    instruments = [("v1|KRX|FIXTURE", "KRX", "FIXTURE", "unknown" if unknown else "etf")]
    if include_us:
        instruments.append(("v1|NAS|EXAMPLE", "NAS", "EXAMPLE", "equity"))
    for instrument_id, market, symbol, asset_type in instruments:
        InstrumentWarehouseRepository(connection).record_version({
            "instrument_id": instrument_id,
            "market": market,
            "symbol": symbol,
            "name": "Synthetic",
            "asset_type": asset_type,
            "economic_exposure": "unknown",
            "currency": "KRW" if market == "KRX" else "USD",
            "valid_from": datetime(2023, 1, 1, tzinfo=UTC),
            "knowledge_at": fetched,
            "classification_source": "fixture",
            "classification_quality": "unknown" if unknown else "official_reference",
        }, observation_id)
        for index in range(121):
            session = LOGICAL_DATE - timedelta(days=120 - index)
            if market != "KRX":
                session -= timedelta(days=1)
            close = Decimal("90") if index == 120 else Decimal("100")
            repository.upsert_price_bar({
                "instrument_id": instrument_id,
                "session_date": session,
                "price_basis": "adjusted",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 3000 if index == 120 else 1000,
                "effective_at": datetime.combine(session, datetime.min.time(), tzinfo=UTC),
                "knowledge_at": fetched,
                "endpoint": "fixture.history",
                "request_option": "adjusted",
                "volume_basis": "provider-reported",
                "reconstruction_mode": (
                    "operational_strict" if index == 120 else "retrospective_reconstructed"
                ),
                "quality_status": "pass",
            }, observation_id)
        connection.execute(
            """
            INSERT INTO gold.portfolio_daily_state VALUES (
                ?, 'kr-1000', 'account-fixture', ?, 'position', 1, 90, 100, -10,
                NULL, NULL, ?, '{}', 'pass', ?
            )
            """,
            [LOGICAL_DATE, instrument_id, fetched, f"lineage-{instrument_id}"],
        )
        if market == "KRX":
            connection.execute(
                """
                INSERT INTO gold.portfolio_daily_state VALUES (
                    ?, 'kr-1600', 'account-fixture', ?, 'position', 1, 90, 100, -10,
                    NULL, NULL, ?, '{}', 'pass', ?
                )
                """,
                [LOGICAL_DATE, instrument_id, fetched, f"lineage-close-{instrument_id}"],
            )
    return connection


def test_shadow_runtime_is_db_only_and_idempotent() -> None:
    connection = _warehouse()
    first = run_shadow_signal_evaluation(
        connection, logical_date=LOGICAL_DATE, source_slot="kr-1600"
    )
    assert first["candidate_count"] == 1
    assert first["transition_count"] == 1
    assert first["shadow_claim_count"] == 1
    assert first["external_send_count"] == 0
    assert connection.execute(
        "SELECT channel,claim_status FROM control.alert_dispatch_claims"
    ).fetchone() == ("shadow", "completed")
    assert connection.execute("SELECT count(*) FROM control.alert_delivery_attempts").fetchone()[0] == 1

    replay = run_shadow_signal_evaluation(
        connection, logical_date=LOGICAL_DATE, source_slot="kr-1600"
    )
    assert replay["candidate_count"] == 1
    assert replay["transition_count"] == 0
    assert replay["shadow_claim_count"] == 0
    assert connection.execute("SELECT count(*) FROM gold.alert_candidates").fetchone()[0] == 1
    connection.close()


def test_morning_run_adds_us_close_and_unknown_class_fails_closed() -> None:
    connection = _warehouse(include_us=True, unknown=True)
    result = run_shadow_signal_evaluation(
        connection, logical_date=LOGICAL_DATE, source_slot="kr-1000"
    )
    assert result["evaluation_slots"] == ["kr-1000", "us-close"]
    assert result["slot_candidate_counts"] == {"kr-1000": 1, "us-close": 1}
    assert result["quality_suppressed_count"] == 1
    rows = connection.execute(
        "SELECT evaluation_slot,quality_status FROM gold.alert_candidates ORDER BY evaluation_slot"
    ).fetchall()
    assert rows == [("kr-1000", "unknown_asset_class"), ("us-close", "pass")]
    assert connection.execute(
        """
        SELECT count(*) FROM control.alert_dispatch_claims WHERE channel='telegram'
        """
    ).fetchone()[0] == 0
    connection.close()
