"""Scheduled privacy-safe total-asset Telegram digest."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Mapping

import duckdb

from kis_portfolio.adapters.outbound.telegram import (
    TelegramBotClient,
    TelegramSendResult,
    TotalAssetDigest,
    TotalAssetDigestContributor,
    render_total_asset_digest,
)
from kis_portfolio.application.valuation_change import (
    build_valuation_change_result,
    load_v2_canonical_state,
)
from kis_portfolio.modules.core import new_id
from kis_portfolio.platform.pipeline import ManagedPipelineRunner, PipelineDefinition, PipelineStage, StageResult
from kis_portfolio.services.telegram_delivery import TelegramDeliveryConfig


PIPELINE_ID = "pipeline.telegram-total-asset-digest-v1"
PIPELINE_VERSION = "1.0.0"
ALLOWED_SLOTS = frozenset({"kr-1000", "kr-1600"})
PARTITION_KEY = "owner-consolidated"


@dataclass(frozen=True, slots=True)
class TotalAssetDigestConfig:
    enabled: bool = False
    top_n: int = 3

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "TotalAssetDigestConfig":
        values = os.environ if env is None else env
        raw = values.get("KIS_TELEGRAM_TOTAL_ASSET_REPORT_ENABLED", "false").strip().lower()
        if raw not in {"true", "false"}:
            raise ValueError("KIS_TELEGRAM_TOTAL_ASSET_REPORT_ENABLED must be true or false")
        return cls(enabled=raw == "true")

    def validate(self) -> None:
        if self.top_n != 3:
            raise ValueError("scheduled total-asset digest top_n is fixed at 3")


def _definition() -> PipelineDefinition:
    return PipelineDefinition(
        PIPELINE_ID,
        PIPELINE_VERSION,
        (
            PipelineStage("build-report", lambda _: StageResult()),
            PipelineStage("send-rich-message", lambda _: StageResult()),
        ),
        source_call_budget=1,
    )


def _previous_open_date(connection: Any, logical_date: date) -> date | None:
    try:
        row = connection.execute("""
            SELECT max(trade_date) FROM main.market_calendar
            WHERE lower(market)='krx' AND is_open AND trade_date < ?
        """, [logical_date]).fetchone()
    except duckdb.Error:
        return None
    return row[0] if row and row[0] else None


def _decimal(value: object | None) -> Decimal:
    return Decimal("0") if value is None else Decimal(str(value))


def _contributor_label(item: Mapping[str, object]) -> str:
    name = str(item.get("name") or "").strip()
    symbol = str(item.get("symbol") or "").strip()
    market = str(item.get("market") or "").strip().upper()
    if name and symbol and symbol not in name:
        return f"{name} ({symbol})"
    return name or symbol or market or "종목"


def _build_digest(connection: Any, *, logical_date: date, slot: str, top_n: int) -> tuple[TotalAssetDigest, dict[str, object]]:
    prior_date = _previous_open_date(connection, logical_date)
    fallback_source_at = datetime.now(UTC)
    if prior_date is None:
        digest = TotalAssetDigest(slot, fallback_source_at, "unavailable", unavailable_codes=("missing_market_calendar",))
        return digest, {"quality_status": "unavailable", "blocker_codes": ["missing_market_calendar"]}

    prior = load_v2_canonical_state(connection, evaluation_date=prior_date, evaluation_slot=slot)
    current = load_v2_canonical_state(connection, evaluation_date=logical_date, evaluation_slot=slot)
    blockers: list[str] = []
    if prior is None:
        blockers.append("missing_prior_state")
    if current is None:
        blockers.append("missing_current_state")
    source_at = current.snapshot_at if current is not None else fallback_source_at
    if blockers:
        digest = TotalAssetDigest(slot, source_at, "unavailable", unavailable_codes=tuple(blockers))
        return digest, {
            "quality_status": "unavailable",
            "blocker_codes": blockers,
            "prior_date": prior_date.isoformat(),
        }

    assert prior is not None and current is not None
    result = build_valuation_change_result(prior, current, top_n=top_n, include_account_breakdown=False)
    if result["status"] != "pass":
        public_blockers = ["state_quality_failed"]
        if result["totals"]["reconciliation_status"] != "pass":
            public_blockers.append("reconciliation_failed")
        digest = TotalAssetDigest(slot, current.snapshot_at, "unavailable", unavailable_codes=tuple(public_blockers))
        return digest, {
            "quality_status": "unavailable",
            "blocker_codes": public_blockers,
            "prior_date": prior_date.isoformat(),
        }

    prior_total = _decimal(result["totals"]["previous_total_asset_krw"])
    total_change = _decimal(result["totals"]["total_asset_change_krw"])
    if prior_total == 0:
        digest = TotalAssetDigest(slot, current.snapshot_at, "unavailable", unavailable_codes=("state_quality_failed",))
        return digest, {
            "quality_status": "unavailable",
            "blocker_codes": ["state_quality_failed"],
            "prior_date": prior_date.isoformat(),
        }

    def convert(items: list[dict[str, object]]) -> tuple[TotalAssetDigestContributor, ...]:
        return tuple(
            TotalAssetDigestContributor(
                _contributor_label(item), _decimal(item.get("total_asset_impact_pct")),
            )
            for item in items[:top_n]
        )

    digest = TotalAssetDigest(
        slot=slot,
        source_at=current.snapshot_at,
        quality_status="pass",
        total_change_percent=total_change / prior_total * Decimal("100"),
        positive=convert(result["top_positive_contributors"]),
        negative=convert(result["top_negative_contributors"]),
        cash_impact_percent_points=_decimal(result["cash"]["total_asset_impact_pct"]),
        reconciliation_status="pass",
    )
    return digest, {
        "quality_status": "pass",
        "blocker_codes": [],
        "prior_date": prior_date.isoformat(),
        "positive_count": len(digest.positive),
        "negative_count": len(digest.negative),
        "reconciliation_status": "pass",
    }


def _stage_evidence(connection: Any, run_id: str, stage_name: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT evidence FROM control.pipeline_stage_runs WHERE run_id=? AND stage_name=?", [run_id, stage_name],
    ).fetchone()
    if not row or row[0] in (None, ""):
        return {}
    value = row[0] if isinstance(row[0], dict) else json.loads(str(row[0]))
    return value if isinstance(value, dict) else {}


def _public_outcome(run_id: str, evidence: Mapping[str, object], *, reused: bool) -> dict[str, object]:
    return {
        "status": "completed",
        "run_id": run_id,
        "reused": reused,
        "outcome": str(evidence.get("outcome", "unknown")),
        "error_code": evidence.get("error_code"),
        "quality_status": str(evidence.get("quality_status", "unknown")),
    }


def run_total_asset_digest(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    slot: str,
    config: TotalAssetDigestConfig | None = None,
    telegram_config: TelegramDeliveryConfig | None = None,
    client: TelegramBotClient | None = None,
) -> dict[str, object]:
    """Send one terminal digest per date/slot; ambiguous sends are never replayed."""
    config = config or TotalAssetDigestConfig.from_env()
    config.validate()
    if not config.enabled:
        return {"status": "disabled", "attempt_count": 0}
    if slot not in ALLOWED_SLOTS:
        return {"status": "skipped", "reason": "slot_not_enabled", "attempt_count": 0}

    telegram_config = telegram_config or TelegramDeliveryConfig.from_env()
    telegram_config.validate_for_send()
    if not telegram_config.enabled:
        raise RuntimeError("total-asset digest requires Telegram delivery enablement")

    definition = _definition()
    runner = ManagedPipelineRunner(connection)
    runner.register_definition(definition)
    logical_key = runner.logical_key(definition, logical_date, slot, PARTITION_KEY)
    existing = connection.execute(
        "SELECT run_id,status FROM control.pipeline_runs WHERE idempotency_key=?", [logical_key],
    ).fetchone()
    if existing:
        run_id, run_status = str(existing[0]), str(existing[1])
        send_row = connection.execute(
            "SELECT status FROM control.pipeline_stage_runs WHERE run_id=? AND stage_name='send-rich-message'",
            [run_id],
        ).fetchone()
        if send_row:
            evidence = _stage_evidence(connection, run_id, "send-rich-message")
            if str(send_row[0]) != "succeeded":
                evidence = {
                    "outcome": "unknown",
                    "error_code": "PREVIOUS_SEND_AMBIGUOUS",
                    "quality_status": evidence.get("quality_status", "unknown"),
                }
                connection.execute("""
                    UPDATE control.pipeline_stage_runs SET status='succeeded',source_calls=1,finished_at=?,evidence=?,error_message=NULL
                    WHERE run_id=? AND stage_name='send-rich-message'
                """, [datetime.now(UTC), json.dumps(evidence), run_id])
            if run_status != "succeeded":
                connection.execute("""
                    UPDATE control.pipeline_runs SET status='succeeded',source_calls=1,finished_at=?,error_code=NULL,error_message=NULL
                    WHERE run_id=?
                """, [datetime.now(UTC), run_id])
            return _public_outcome(run_id, evidence, reused=True)
    else:
        run_id = new_id()
        connection.execute("""
            INSERT INTO control.pipeline_runs(
                run_id,pipeline_id,pipeline_version,logical_date,slot,partition_key,idempotency_key,status,started_at
            ) VALUES (?,?,?,?,?,?,?,'running',?)
        """, [run_id, PIPELINE_ID, PIPELINE_VERSION, logical_date, slot, PARTITION_KEY, logical_key, datetime.now(UTC)])

    connection.execute("""
        UPDATE control.pipeline_runs SET status='running',finished_at=NULL,error_code=NULL,error_message=NULL WHERE run_id=?
    """, [run_id])
    try:
        digest, build_evidence = _build_digest(
            connection, logical_date=logical_date, slot=slot, top_n=config.top_n,
        )
        message = render_total_asset_digest(digest)
    except Exception as exc:
        connection.execute("""
            UPDATE control.pipeline_runs SET status='failed',finished_at=?,error_code='build_failed',error_message=?
            WHERE run_id=?
        """, [datetime.now(UTC), type(exc).__name__, run_id])
        raise

    report_hash = hashlib.sha256(message.html.encode()).hexdigest()
    build_evidence = {**build_evidence, "report_hash": report_hash, "top_n": config.top_n}
    connection.execute("""
        INSERT INTO control.pipeline_stage_runs(
            run_id,stage_name,stage_order,status,attempt,input_count,output_count,source_calls,started_at,finished_at,evidence
        ) VALUES (?, 'build-report', 0, 'succeeded', 1, 2, 1, 0, ?, ?, ?)
        ON CONFLICT(run_id,stage_name) DO UPDATE SET
            status='succeeded',attempt=pipeline_stage_runs.attempt+1,input_count=2,output_count=1,
            source_calls=0,started_at=excluded.started_at,finished_at=excluded.finished_at,evidence=excluded.evidence,error_message=NULL
    """, [run_id, datetime.now(UTC), datetime.now(UTC), json.dumps(build_evidence)])
    connection.execute("""
        INSERT INTO control.pipeline_stage_runs(
            run_id,stage_name,stage_order,status,attempt,input_count,output_count,source_calls,started_at
        ) VALUES (?, 'send-rich-message', 1, 'running', 1, 1, 0, 0, ?)
    """, [run_id, datetime.now(UTC)])

    transport = client or TelegramBotClient()
    try:
        result = transport.send_rich_message(
            bot_token=telegram_config.bot_token,
            chat_id=telegram_config.chat_id,
            message=message,
        )
    except Exception:
        result = TelegramSendResult("unknown", error_code="TRANSPORT_EXCEPTION")
    evidence = {
        "outcome": result.outcome,
        "error_code": result.error_code,
        "response_ref_hash": (
            hashlib.sha256(result.response_ref.encode()).hexdigest() if result.response_ref else None
        ),
        "quality_status": build_evidence["quality_status"],
        "report_hash": report_hash,
    }
    connection.execute("""
        UPDATE control.pipeline_stage_runs SET status='succeeded',output_count=?,source_calls=1,finished_at=?,evidence=?
        WHERE run_id=? AND stage_name='send-rich-message'
    """, [1 if result.outcome == "sent" else 0, datetime.now(UTC), json.dumps(evidence), run_id])
    connection.execute("""
        UPDATE control.pipeline_runs SET status='succeeded',source_calls=1,finished_at=? WHERE run_id=?
    """, [datetime.now(UTC), run_id])
    return _public_outcome(run_id, evidence, reused=False)
