from datetime import UTC, date, datetime

import duckdb

from kis_portfolio.adapters.outbound.instrument_warehouse import InstrumentWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.overseas_instrument_info import OverseasInstrumentInfo
from kis_portfolio.services.sec_issuer_info import OfficialInstrumentClassification, SecIssuerInfo
from kis_portfolio.services import overseas_classification_sync as service


def test_sync_appends_official_version_and_replay_skips_network(monkeypatch) -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    warehouse = V2WarehouseRepository(connection)
    observed = datetime(2026, 8, 28, 1, tzinfo=UTC)
    source = SourceEnvelope(
        "source.kis-open-api", "unknown-instrument", observed, observed,
        {"fixture": True}, "a" * 64, "pass",
    )
    observation_id = warehouse.record_observation("dataset.instrument-master", source, "fixture")
    unknown = {
        "instrument_id": "v1|NAS|EXAMPLE", "market": "NAS", "symbol": "EXAMPLE",
        "name": "Synthetic", "asset_type": "unknown", "economic_exposure": "unknown",
        "currency": "USD", "valid_from": observed, "knowledge_at": observed,
        "classification_source": "unresolved", "classification_quality": "unknown",
    }
    InstrumentWarehouseRepository(connection).record_version(unknown, observation_id)
    connection.execute(
        """
        INSERT INTO gold.portfolio_daily_state VALUES (
            '2026-08-28','kr-1000','account','v1|NAS|EXAMPLE','position',1,1,1,0,
            NULL,NULL,?,'{}','pass','lineage'
        )
        """,
        [observed],
    )
    calls = {"count": 0}

    async def fake_collect(instruments, *, sec_user_agent):
        calls["count"] += 1
        assert sec_user_agent == "KIS Portfolio mustafa@example.com"
        kis = OverseasInstrumentInfo(
            "NAS", "EXAMPLE", "512", "101210", "Overseas stock", "01", "", "", "0", {},
        )
        sec = SecIssuerInfo(
            "0001234567", "Example Corp", "3674", "Semiconductors", ("EXAMPLE",), {},
        )
        classification = OfficialInstrumentClassification(
            "equity", "sec-cik:0001234567", "kis_product_info+sec_edgar",
            "official_reference", {"sec_sic": "3674"},
        )
        return ((instruments[0], kis, sec, classification),)

    monkeypatch.setattr(service, "_collect", fake_collect)
    first = service.sync_held_overseas_classifications(
        connection,
        logical_date=date(2026, 8, 28),
        source_slot="kr-1000",
        sec_user_agent="KIS Portfolio mustafa@example.com",
    )
    assert first["resolved_count"] == 1
    assert first["source_call_count"] == 3
    assert connection.execute(
        "SELECT asset_type,classification_quality FROM silver.instruments_current"
    ).fetchone() == ("equity", "official_reference")
    assert connection.execute("SELECT count(*) FROM silver.instrument_versions").fetchone()[0] == 2
    assert connection.execute(
        "SELECT count(*) FROM bronze.source_observations WHERE dataset_id='dataset.instrument-master'"
    ).fetchone()[0] == 3

    replay = service.sync_held_overseas_classifications(
        connection,
        logical_date=date(2026, 8, 28),
        source_slot="kr-1000",
        sec_user_agent="",
    )
    assert replay["status"] == "skipped"
    assert calls["count"] == 1
    connection.close()
