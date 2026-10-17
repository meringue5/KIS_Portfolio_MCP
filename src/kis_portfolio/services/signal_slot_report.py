"""One consolidated held-position signal status per governed monitoring slot."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from kis_portfolio.adapters.outbound.telegram import (
    HeldSignalSlotItem,
    HeldSignalSlotReport,
    TelegramBotClient,
    TelegramSendResult,
    render_held_signal_slot_report,
)
from kis_portfolio.modules.core import new_id
from kis_portfolio.services.telegram_delivery import TelegramDeliveryConfig


PIPELINE_ID = "pipeline.telegram-delivery-v2"
PIPELINE_VERSION = "1.5.0"
ALLOWED_SLOTS = frozenset({"kr-1000", "kr-1430", "kr-1600"})
PARTITION_KEY = "owner-held-signal-status"


@dataclass(frozen=True, slots=True)
class SignalSlotReportConfig:
    enabled: bool = False
    max_items: int = 20

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SignalSlotReportConfig":
        values = os.environ if env is None else env
        raw = values.get("KIS_TELEGRAM_SIGNAL_SLOT_REPORT_ENABLED", "false").strip().lower()
        if raw not in {"true", "false"}:
            raise ValueError("KIS_TELEGRAM_SIGNAL_SLOT_REPORT_ENABLED must be true or false")
        return cls(enabled=raw == "true")

    def validate(self) -> None:
        if self.max_items != 20:
            raise ValueError("signal slot report max_items is fixed at 20")


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("signal change_percent is not numeric") from exc
    return result


def _stage_evidence(connection: Any, run_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT evidence FROM control.pipeline_stage_runs WHERE run_id=? AND stage_name='send-slot-report'",
        [run_id],
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
        "evaluated_count": int(evidence.get("evaluated_count", 0)),
        "changed_count": int(evidence.get("changed_count", 0)),
        "active_count": int(evidence.get("active_count", 0)),
        "quality_suppressed_count": int(evidence.get("quality_suppressed_count", 0)),
    }


def _build_report(
    connection: Any,
    *,
    logical_date: date,
    source_slot: str,
    evaluation: Mapping[str, object],
    max_items: int,
) -> tuple[HeldSignalSlotReport, dict[str, object]]:
    if evaluation.get("status") != "succeeded":
        raise ValueError("signal slot report requires a succeeded evaluation")
    if evaluation.get("logical_date") != logical_date.isoformat() or evaluation.get("source_slot") != source_slot:
        raise ValueError("signal evaluation identity does not match the requested report slot")
    evaluation_run_id = str(evaluation.get("run_id") or "")
    if not evaluation_run_id:
        raise ValueError("signal slot report requires evaluation_run_id")
    expected_count = int(evaluation.get("candidate_count", -1))
    if expected_count < 0:
        raise ValueError("signal slot report requires candidate_count")
    rows = connection.execute(
        """
        SELECT c.signal_state,c.severity,c.quality_status,c.evaluation_at,c.public_context,
               o.outcome_type,s.transition_type,coalesce(s.delivery_required,false)
        FROM gold.alert_candidates c
        LEFT JOIN control.alert_candidate_outcomes o USING(candidate_id)
        LEFT JOIN control.alert_state_revisions s USING(candidate_id)
        WHERE c.evaluation_run_id=?
        ORDER BY CASE c.severity WHEN 'critical' THEN 3 WHEN 'warning' THEN 2
                                      WHEN 'watch' THEN 1 ELSE 0 END DESC,
                 abs(try_cast(json_extract_string(c.public_context,'$.change_percent') AS DOUBLE)) DESC NULLS LAST,
                 c.subject_id
        """,
        [evaluation_run_id],
    ).fetchall()
    if len(rows) != expected_count:
        raise RuntimeError("signal evaluation evidence does not reconcile to stored candidates")
    if not rows:
        source_at = datetime.now(UTC)
    else:
        source_at = max(row[3] for row in rows)
    changed_count = sum(bool(row[7]) for row in rows)
    quality_suppressed_count = sum(str(row[2]) != "pass" for row in rows)
    active_rows = [row for row in rows if str(row[0]) == "active" and str(row[2]) == "pass"]
    items: list[HeldSignalSlotItem] = []
    for row in active_rows[:max_items]:
        context = row[4] if isinstance(row[4], dict) else json.loads(str(row[4]))
        reasons = context.get("reason_codes", [])
        if not isinstance(reasons, list) or not reasons:
            raise ValueError("active signal is missing reason_codes")
        items.append(HeldSignalSlotItem(
            label=str(context.get("subject_label") or ""),
            market_label=str(context.get("market_label") or ""),
            severity=str(row[1]),
            reason_code=str(reasons[0]),
            change_percent=_decimal(context.get("change_percent")),
            transition_type=str(row[6]) if bool(row[7]) and row[6] is not None else None,
        ))
    report = HeldSignalSlotReport(
        slot=source_slot,
        source_at=source_at,
        evaluated_count=len(rows),
        changed_count=changed_count,
        active_count=len(active_rows),
        quality_suppressed_count=quality_suppressed_count,
        active_items=tuple(items),
    )
    evidence = {
        "evaluation_run_id": evaluation_run_id,
        "evaluated_count": len(rows),
        "changed_count": changed_count,
        "active_count": len(active_rows),
        "quality_suppressed_count": quality_suppressed_count,
    }
    return report, evidence


def run_signal_slot_report(
    connection: Any,
    *,
    logical_date: date,
    source_slot: str,
    evaluation: Mapping[str, object],
    config: SignalSlotReportConfig | None = None,
    telegram_config: TelegramDeliveryConfig | None = None,
    client: TelegramBotClient | None = None,
) -> dict[str, object]:
    """Send exactly one consolidated status for a completed date-slot evaluation."""
    config = config or SignalSlotReportConfig.from_env()
    config.validate()
    if not config.enabled:
        return {"status": "disabled", "attempt_count": 0}
    if source_slot not in ALLOWED_SLOTS:
        raise ValueError("signal slot report source_slot is not governed")
    telegram_config = telegram_config or TelegramDeliveryConfig.from_env()
    telegram_config.validate_for_send()
    if not telegram_config.enabled or telegram_config.destination_ref != "dest.owner.primary":
        raise RuntimeError("signal slot report requires the verified owner Telegram destination")

    idempotency_key = hashlib.sha256(
        f"signal-slot-report-v1|{logical_date}|{source_slot}|{PARTITION_KEY}".encode()
    ).hexdigest()
    existing = connection.execute(
        "SELECT run_id,status FROM control.pipeline_runs WHERE idempotency_key=?", [idempotency_key],
    ).fetchone()
    if existing:
        run_id, run_status = str(existing[0]), str(existing[1])
        evidence = _stage_evidence(connection, run_id)
        if run_status != "succeeded":
            evidence = {
                **evidence,
                "outcome": "unknown",
                "error_code": "PREVIOUS_SEND_AMBIGUOUS",
            }
            connection.execute(
                """
                UPDATE control.pipeline_stage_runs
                SET status='succeeded',source_calls=1,finished_at=?,evidence=?,error_message=NULL
                WHERE run_id=? AND stage_name='send-slot-report'
                """,
                [datetime.now(UTC), json.dumps(evidence), run_id],
            )
            connection.execute(
                """
                UPDATE control.pipeline_runs
                SET status='succeeded',source_calls=1,finished_at=?,error_code=NULL,error_message=NULL
                WHERE run_id=?
                """,
                [datetime.now(UTC), run_id],
            )
        return _public_outcome(run_id, evidence, reused=True)

    report, build_evidence = _build_report(
        connection,
        logical_date=logical_date,
        source_slot=source_slot,
        evaluation=evaluation,
        max_items=config.max_items,
    )
    message = render_held_signal_slot_report(report)
    report_hash = hashlib.sha256(message.html.encode()).hexdigest()
    run_id = new_id()
    started_at = datetime.now(UTC)
    connection.execute(
        """
        INSERT INTO control.pipeline_runs(
            run_id,pipeline_id,pipeline_version,logical_date,slot,partition_key,idempotency_key,status,started_at
        ) VALUES (?,?,?,?,?,?,?,'running',?)
        """,
        [run_id, PIPELINE_ID, PIPELINE_VERSION, logical_date, source_slot, PARTITION_KEY,
         idempotency_key, started_at],
    )
    connection.execute(
        """
        INSERT INTO control.pipeline_stage_runs(
            run_id,stage_name,stage_order,status,attempt,input_count,output_count,source_calls,
            started_at,finished_at,evidence
        ) VALUES (?, 'build-slot-report', 0, 'succeeded', 1, ?, 1, 0, ?, ?, ?)
        """,
        [run_id, report.evaluated_count, started_at, started_at,
         json.dumps({**build_evidence, "report_hash": report_hash})],
    )
    connection.execute(
        """
        INSERT INTO control.pipeline_stage_runs(
            run_id,stage_name,stage_order,status,attempt,input_count,output_count,source_calls,started_at
        ) VALUES (?, 'send-slot-report', 1, 'running', 1, 1, 0, 0, ?)
        """,
        [run_id, datetime.now(UTC)],
    )
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
        **build_evidence,
        "outcome": result.outcome,
        "error_code": result.error_code,
        "response_ref_hash": (
            hashlib.sha256(result.response_ref.encode()).hexdigest() if result.response_ref else None
        ),
        "report_hash": report_hash,
    }
    finished_at = datetime.now(UTC)
    connection.execute(
        """
        UPDATE control.pipeline_stage_runs
        SET status='succeeded',output_count=?,source_calls=1,finished_at=?,evidence=?
        WHERE run_id=? AND stage_name='send-slot-report'
        """,
        [1 if result.outcome == "sent" else 0, finished_at, json.dumps(evidence), run_id],
    )
    connection.execute(
        "UPDATE control.pipeline_runs SET status='succeeded',source_calls=1,finished_at=? WHERE run_id=?",
        [finished_at, run_id],
    )
    return _public_outcome(run_id, evidence, reused=False)
