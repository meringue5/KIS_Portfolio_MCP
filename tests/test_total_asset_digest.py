from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb
import pytest

from kis_portfolio.adapters.outbound.telegram import TelegramPhotoMessage, TelegramRichMessage, TelegramSendResult
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.telegram_delivery import TelegramDeliveryConfig
from kis_portfolio.services.total_asset_digest import (
    PIPELINE_ID,
    V2_PIPELINE_ID,
    OwnerPortfolioReportConfig,
    TotalAssetDigestConfig,
    run_owner_portfolio_report,
    run_total_asset_digest,
    validate_total_asset_report_modes,
)


class RecordingClient:
    def __init__(self, *, outcome: str = "sent") -> None:
        self.outcome = outcome
        self.messages = []

    def send_rich_message(self, *, bot_token, chat_id, message):
        self.messages.append(message)
        return TelegramSendResult(self.outcome, response_ref="telegram-message:123")


class CrashAfterSendClient(RecordingClient):
    def send_rich_message(self, *, bot_token, chat_id, message):
        self.messages.append(message)
        raise SystemExit("simulated process death after provider request")


class RecordingPhotoClient:
    def __init__(self) -> None:
        self.photos: list[TelegramPhotoMessage] = []
        self.rich: list[TelegramRichMessage] = []

    def send_photo_message(self, *, bot_token, chat_id, message):
        self.photos.append(message)
        return TelegramSendResult("sent", response_ref="telegram-message:456")

    def send_rich_message(self, *, bot_token, chat_id, message):
        self.rich.append(message)
        return TelegramSendResult("sent", response_ref="telegram-message:457")


class CrashAfterPhotoClient(RecordingPhotoClient):
    def send_photo_message(self, *, bot_token, chat_id, message):
        self.photos.append(message)
        raise SystemExit("simulated process death after photo request")


def _telegram_config() -> TelegramDeliveryConfig:
    return TelegramDeliveryConfig(enabled=True, bot_token="test-token", chat_id="test-chat")


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute("CREATE TABLE main.market_calendar(market VARCHAR, trade_date DATE, is_open BOOLEAN, note VARCHAR)")
    connection.executemany(
        "INSERT INTO main.market_calendar VALUES ('KRX', ?, true, '')",
        [[date(2026, 9, 7)], [date(2026, 9, 8)]],
    )
    connection.execute(
        "INSERT INTO silver.accounts VALUES ('acct-1','brokerage','brokerage','KRW',?,NULL,'{}')",
        [datetime(2026, 9, 1, tzinfo=UTC)],
    )
    connection.executemany("""
        INSERT INTO silver.instruments VALUES(?,?,?,?,?,'KRW',NULL,?,NULL,'source','{}')
    """, [
        ["KRX:005930", "KRX", "005930", "삼성전자", "equity", datetime(2026, 9, 1, tzinfo=UTC)],
        ["KRX:000660", "KRX", "000660", "SK하이닉스", "equity", datetime(2026, 9, 1, tzinfo=UTC)],
    ])
    for day, values in (
        (7, (("KRX:005930", "position", 600), ("KRX:000660", "position", 200), ("cash|KRW", "cash", 200))),
        (8, (("KRX:005930", "position", 660), ("KRX:000660", "position", 180), ("cash|KRW", "cash", 210))),
    ):
        for instrument, level, value in values:
            connection.execute("""
                INSERT INTO gold.portfolio_daily_state(
                    evaluation_date,evaluation_slot,account_id,instrument_id,aggregate_level,quantity,
                    value_krw,cost_krw,unrealized_pnl_krw,contribution_pct,allocation_pct,as_of,
                    input_watermarks,quality_status,lineage_hash
                ) VALUES (?, 'kr-1000','acct-1',?,?,NULL,?,NULL,NULL,NULL,NULL,?,'{}','pass',?)
            """, [
                date(2026, 9, day), instrument, level, value,
                datetime(2026, 9, day, 1, tzinfo=UTC), f"lineage-{day}-{instrument}",
            ])
    return connection


def test_digest_sends_privacy_safe_top_contributors_once() -> None:
    connection = _connection()
    client = RecordingClient()
    kwargs = {
        "logical_date": date(2026, 9, 8),
        "slot": "kr-1000",
        "config": TotalAssetDigestConfig(enabled=True),
        "telegram_config": _telegram_config(),
        "client": client,
    }

    first = run_total_asset_digest(connection, **kwargs)
    replay = run_total_asset_digest(connection, **kwargs)

    assert first["outcome"] == "sent" and first["reused"] is False
    assert replay["outcome"] == "sent" and replay["reused"] is True
    assert len(client.messages) == 1
    html = client.messages[0].html
    assert "전 거래일 동일 시각 대비 +5.00%" in html
    assert "삼성전자 (005930) +6.00%p" in html
    assert "SK하이닉스 (000660) -2.00%p" in html
    assert "현금 영향" in html and "+1.00%p" in html
    assert "1050" not in html and "1000" not in html
    assert connection.execute(
        "SELECT source_calls FROM control.pipeline_runs WHERE pipeline_id=?", [PIPELINE_ID],
    ).fetchone()[0] == 1


def test_digest_sends_explicit_unavailable_instead_of_fabricated_numbers() -> None:
    connection = _connection()
    connection.execute("DELETE FROM gold.portfolio_daily_state WHERE evaluation_date='2026-09-07'")
    client = RecordingClient()

    result = run_total_asset_digest(
        connection,
        logical_date=date(2026, 9, 8),
        slot="kr-1000",
        config=TotalAssetDigestConfig(enabled=True),
        telegram_config=_telegram_config(),
        client=client,
    )

    assert result["outcome"] == "sent"
    assert result["quality_status"] == "unavailable"
    assert "계산 보류" in client.messages[0].html
    assert "%p" not in client.messages[0].html


def test_digest_skips_1430_without_claim_or_send() -> None:
    connection = _connection()
    client = RecordingClient()

    result = run_total_asset_digest(
        connection,
        logical_date=date(2026, 9, 8),
        slot="kr-1430",
        config=TotalAssetDigestConfig(enabled=True),
        telegram_config=_telegram_config(),
        client=client,
    )

    assert result == {"status": "skipped", "reason": "slot_not_enabled", "attempt_count": 0}
    assert not client.messages
    assert connection.execute(
        "SELECT count(*) FROM control.pipeline_runs WHERE pipeline_id=?", [PIPELINE_ID],
    ).fetchone()[0] == 0


def test_ambiguous_interrupted_send_is_sealed_and_never_replayed() -> None:
    connection = _connection()
    crashed = CrashAfterSendClient()
    kwargs = {
        "logical_date": date(2026, 9, 8),
        "slot": "kr-1000",
        "config": TotalAssetDigestConfig(enabled=True),
        "telegram_config": _telegram_config(),
    }
    with pytest.raises(SystemExit):
        run_total_asset_digest(connection, client=crashed, **kwargs)
    replacement = RecordingClient()

    recovered = run_total_asset_digest(connection, client=replacement, **kwargs)

    assert recovered["outcome"] == "unknown"
    assert recovered["error_code"] == "PREVIOUS_SEND_AMBIGUOUS"
    assert recovered["reused"] is True
    assert len(crashed.messages) == 1 and not replacement.messages


def test_digest_is_disabled_by_default_before_any_ledger_write() -> None:
    connection = _connection()
    result = run_total_asset_digest(
        connection, logical_date=date(2026, 9, 8), slot="kr-1000",
        config=TotalAssetDigestConfig(),
    )
    assert result == {"status": "disabled", "attempt_count": 0}
    assert connection.execute(
        "SELECT count(*) FROM control.pipeline_runs WHERE pipeline_id=?", [PIPELINE_ID],
    ).fetchone()[0] == 0


def test_owner_report_sends_exact_values_alias_composition_and_chart_once() -> None:
    connection = _connection()
    client = RecordingPhotoClient()
    kwargs = {
        "logical_date": date(2026, 9, 8),
        "slot": "kr-1000",
        "config": OwnerPortfolioReportConfig(enabled=True, owner_destination_approved=True),
        "telegram_config": _telegram_config(),
        "client": client,
    }

    first = run_owner_portfolio_report(connection, **kwargs)
    replay = run_owner_portfolio_report(connection, **kwargs)

    assert first["outcome"] == "sent" and first["reused"] is False
    assert replay["outcome"] == "sent" and replay["reused"] is True
    assert len(client.photos) == 1 and not client.rich
    message = client.photos[0]
    assert "₩1,050" in message.caption_html
    assert "+₩50 (+5.00%)" in message.caption_html
    assert "BROKERAGE: ₩1,050 · 100.00%" in message.caption_html
    assert "국내: ₩840 · 80.00%" in message.caption_html
    assert "현금: ₩210 · 20.00%" in message.caption_html
    assert "acct-1" not in message.caption_html
    assert message.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert message.png_bytes[16:24] == (1200).to_bytes(4, "big") + (800).to_bytes(4, "big")

    evidence = connection.execute("""
        SELECT s.evidence FROM control.pipeline_runs r
        JOIN control.pipeline_stage_runs s USING(run_id)
        WHERE r.pipeline_id=? AND s.stage_name='send-owner-report'
    """, [V2_PIPELINE_ID]).fetchone()[0]
    evidence_text = str(evidence)
    assert "report_hash" in evidence_text and "chart_hash" in evidence_text
    assert "₩1,050" not in evidence_text and "BROKERAGE" not in evidence_text


def test_owner_report_suppresses_amounts_and_chart_when_state_is_incomplete() -> None:
    connection = _connection()
    connection.execute("DELETE FROM gold.portfolio_daily_state WHERE evaluation_date='2026-09-07'")
    client = RecordingPhotoClient()

    result = run_owner_portfolio_report(
        connection,
        logical_date=date(2026, 9, 8),
        slot="kr-1000",
        config=OwnerPortfolioReportConfig(enabled=True, owner_destination_approved=True),
        telegram_config=_telegram_config(),
        client=client,
    )

    assert result["quality_status"] == "unavailable"
    assert not client.photos and len(client.rich) == 1
    assert "계산 보류" in client.rich[0].html
    assert "₩" not in client.rich[0].html


def test_owner_report_requires_private_destination_approval_and_exclusive_mode() -> None:
    with pytest.raises(ValueError, match="approved private destination"):
        OwnerPortfolioReportConfig(enabled=True).validate()
    with pytest.raises(ValueError, match="mutually exclusive"):
        validate_total_asset_report_modes(
            TotalAssetDigestConfig(enabled=True),
            OwnerPortfolioReportConfig(enabled=True, owner_destination_approved=True),
        )


def test_owner_report_rejects_non_owner_destination_before_ledger_or_send() -> None:
    connection = _connection()
    client = RecordingPhotoClient()
    with pytest.raises(RuntimeError, match="verified owner destination"):
        run_owner_portfolio_report(
            connection,
            logical_date=date(2026, 9, 8),
            slot="kr-1000",
            config=OwnerPortfolioReportConfig(enabled=True, owner_destination_approved=True),
            telegram_config=TelegramDeliveryConfig(
                enabled=True, bot_token="test-token", chat_id="test-chat", destination_ref="dest.group",
            ),
            client=client,
        )
    assert not client.photos and not client.rich
    assert connection.execute(
        "SELECT count(*) FROM control.pipeline_runs WHERE pipeline_id=?", [V2_PIPELINE_ID],
    ).fetchone()[0] == 0


def test_ambiguous_owner_photo_send_is_sealed_and_never_replayed() -> None:
    connection = _connection()
    crashed = CrashAfterPhotoClient()
    kwargs = {
        "logical_date": date(2026, 9, 8),
        "slot": "kr-1000",
        "config": OwnerPortfolioReportConfig(enabled=True, owner_destination_approved=True),
        "telegram_config": _telegram_config(),
    }
    with pytest.raises(SystemExit):
        run_owner_portfolio_report(connection, client=crashed, **kwargs)
    replacement = RecordingPhotoClient()

    recovered = run_owner_portfolio_report(connection, client=replacement, **kwargs)

    assert recovered["outcome"] == "unknown"
    assert recovered["error_code"] == "PREVIOUS_SEND_AMBIGUOUS"
    assert len(crashed.photos) == 1 and not replacement.photos and not replacement.rich
