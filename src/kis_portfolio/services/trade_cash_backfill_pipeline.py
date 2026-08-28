"""Canonical trade/cash normalization for bounded backfill source pages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

import duckdb

from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.modules.exposure import canonical_instrument_id
from kis_portfolio.platform.pipeline import (
    LineageEvidence,
    QualityEvidence,
    StageContext,
    StageResult,
)
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.trade_cash_backfill import (
    DOMESTIC_ORDER_HISTORY,
    OVERSEAS_ORDER_HISTORY,
    OVERSEAS_TRANSACTION_HISTORY,
    BackfillPartition,
)
from kis_portfolio.services.trade_cash_backfill_runtime import CheckpointingCallBudget


SEOUL = ZoneInfo("Asia/Seoul")
NEW_YORK = ZoneInfo("America/New_York")


class BackfillReconciliationError(RuntimeError):
    """Raised before publish when source coverage cannot be reconciled."""


@dataclass(frozen=True, slots=True)
class BackfillSourcePage:
    payload: dict[str, Any]
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class FetchedBackfillPartition:
    pages: tuple[BackfillSourcePage, ...]
    complete: bool
    pagination_warning: str | None = None


PartitionFetcher = Callable[
    [BackfillPartition, CheckpointingCallBudget], FetchedBackfillPartition
]


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        for candidate in (name, name.lower(), name.upper()):
            value = row.get(candidate)
            if value not in (None, ""):
                return value
    return None


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "")) if value not in (None, "") else Decimal(0)
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return [value] if isinstance(value, dict) and value else []


def _account_id(label: str) -> str:
    return hashlib.sha256(f"v1-account|{label}".encode()).hexdigest()


def _row_id(partition: BackfillPartition, row: dict[str, Any]) -> str:
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    raw = f"{partition.key}|{canonical}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _source_datetime(
    value_date: Any,
    value_time: Any,
    *,
    fallback: date,
    market: str,
) -> datetime:
    compact_date = str(value_date or fallback.isoformat()).replace("-", "")
    compact_time = str(value_time or "000000").replace(":", "").ljust(6, "0")[:6]
    try:
        parsed_date = datetime.strptime(compact_date, "%Y%m%d").date()
        parsed_time = time.fromisoformat(
            f"{compact_time[:2]}:{compact_time[2:4]}:{compact_time[4:6]}"
        )
    except ValueError:
        parsed_date, parsed_time = fallback, time.min
    zone = SEOUL if market == "KRX" else NEW_YORK
    return datetime.combine(parsed_date, parsed_time, tzinfo=zone)


def _envelope(
    source_record_id: str,
    row: dict[str, Any],
    effective_at: datetime,
    fetched_at: datetime,
    quality_status: str,
) -> SourceEnvelope:
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return SourceEnvelope(
        source_id="source.kis-open-api",
        source_record_id=source_record_id,
        observed_at=effective_at,
        fetched_at=fetched_at,
        payload=row,
        content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        quality_status=quality_status,
    )


def _trade_payload(
    partition: BackfillPartition,
    row: dict[str, Any],
    *,
    executed_at: datetime,
) -> dict[str, Any] | None:
    side_code = str(_pick(row, "sll_buy_dvsn_cd", "sll_buy_dvsn") or "")
    side = {"01": "sell", "02": "buy"}.get(side_code)
    symbol = str(_pick(row, "pdno", "ovrs_pdno", "symb") or "").strip().upper()
    order_no = str(_pick(row, "odno", "ord_no", "ovrs_odno") or "").strip()
    quantity = _decimal(_pick(row, "tot_ccld_qty", "ft_ccld_qty", "ccld_qty", "tr_qty", "qty"))
    price = _decimal(
        _pick(
            row,
            "avg_prvs",
            "pchs_avg_pric",
            "ft_ccld_unpr3",
            "ft_ccld_unpr2",
            "ovrs_stck_ccld_unpr",
            "ccld_unpr",
            "ord_unpr",
        )
    )
    if not side or not symbol or not order_no or quantity <= 0 or price <= 0:
        return None
    branch = str(_pick(row, "ord_gno_brno", "ord_gno_brno_org") or "")
    exchange = partition.exchange or str(_pick(row, "ovrs_excg_cd", "excg_cd") or "KRX")
    market = "KRX" if partition.market == "KRX" else exchange
    broker_order_id = "|".join(
        (
            partition.account_product_code,
            executed_at.date().isoformat(),
            market,
            branch,
            order_no,
        )
    )
    return {
        "account_id": _account_id(partition.account_label),
        "account_product_code": partition.account_product_code,
        "market": market,
        "instrument_id": canonical_instrument_id(market, symbol),
        "broker_order_id": broker_order_id,
        "executed_at": executed_at,
        "execution_sequence": "aggregate",
        "event_version": 1,
        "side": side,
        "quantity": quantity,
        "price": price,
        "currency": str(_pick(row, "tr_crcy_cd", "crcy_cd") or ("KRW" if market == "KRX" else "USD")),
        "quality_status": "pass",
        "correction_reason": "source_event",
        "trade_metadata": {
            "source_operation": partition.source_operation,
            "source_route": partition.source_route,
            "source_side_code": side_code,
            "individual_fills_available": False,
        },
    }


def _cash_payloads(
    partition: BackfillPartition,
    row: dict[str, Any],
    *,
    row_id: str,
    effective_at: datetime,
) -> list[dict[str, Any]]:
    side_code = str(_pick(row, "sll_buy_dvsn_cd", "sll_buy_dvsn") or "")
    currency = str(_pick(row, "tr_crcy_cd", "crcy_cd", "ovrs_crcy_cd") or "USD")
    settlement_date = _pick(row, "sttl_dt")
    settled_at = _source_datetime(
        settlement_date,
        None,
        fallback=effective_at.date(),
        market=partition.market,
    ) if settlement_date else None
    common = {
        "account_id": _account_id(partition.account_label),
        "effective_at": effective_at,
        "settled_at": settled_at,
        "knowledge_at": None,
        "currency": currency,
        "source_event_code": _pick(row, "trad_dvsn_cd", "tr_dvsn_cd"),
        "classification_source": "source",
        "link_quality": "unmatched",
        "quality_status": "pass",
        "provenance": {
            "source_operation": partition.source_operation,
            "source_route": partition.source_route,
            "candidate_order_no": _pick(row, "odno", "ord_no", "ovrs_odno"),
        },
    }
    events: list[dict[str, Any]] = []

    settlement = _decimal(_pick(row, "sttl_amt", "frcr_sttl_amt", "settlement_amount"))
    if settlement:
        event_type = "trade_settlement_out" if side_code == "02" else "trade_settlement_in" if side_code == "01" else "unknown"
        amount = -abs(settlement) if event_type == "trade_settlement_out" else abs(settlement)
        events.append({**common, "source_record_id": f"{row_id}:settlement", "event_type": event_type, "amount": amount})

    for suffix, event_type, candidates in (
        ("fee", "fee", ("frcr_fee1", "fee", "ovrs_fee", "frcr_fee")),
        ("tax", "tax", ("tax", "tax_amt", "frcr_tax")),
    ):
        amount = _decimal(_pick(row, *candidates))
        if amount:
            events.append({
                **common,
                "source_record_id": f"{row_id}:{suffix}",
                "event_type": event_type,
                "amount": -abs(amount),
            })

    domestic_fee = _decimal(_pick(row, "dmst_frcr_fee1"))
    if domestic_fee:
        events.append({
            **common,
            "source_record_id": f"{row_id}:domestic-fee",
            "event_type": "fee",
            "amount": -abs(domestic_fee),
            "currency": "KRW",
        })
    return events


def build_trade_cash_partition_handler(
    connection: duckdb.DuckDBPyConnection,
    fetch_partition: PartitionFetcher,
) -> Callable[[BackfillPartition, CheckpointingCallBudget, StageContext], StageResult]:
    """Bind guarded pages to governed observations and canonical event facts."""

    repository = V2WarehouseRepository(connection)

    def handler(
        partition: BackfillPartition,
        gate: CheckpointingCallBudget,
        context: StageContext,
    ) -> StageResult:
        fetched = fetch_partition(partition, gate)
        raw_rows = 0
        classified_rows = 0
        deferred_rows = 0
        trade_events = 0
        trade_candidates = 0
        cash_events = 0
        pending_trades: list[tuple[dict[str, Any], str]] = []
        pending_cash: list[tuple[dict[str, Any], str]] = []

        row_key = "output1" if partition.source_operation != OVERSEAS_ORDER_HISTORY else "output"
        for page in fetched.pages:
            for row in _rows(page.payload, row_key):
                raw_rows += 1
                row_id = _row_id(partition, row)
                fallback = partition.start_date
                executed_at = _source_datetime(
                    _pick(row, "ord_dt", "erlm_dt", "trad_dt", "tr_dt", "ccld_dt"),
                    _pick(row, "ord_tmd", "ord_time"),
                    fallback=fallback,
                    market=partition.market,
                )
                row_classified = False

                if partition.source_operation in {DOMESTIC_ORDER_HISTORY, OVERSEAS_ORDER_HISTORY}:
                    trade = _trade_payload(partition, row, executed_at=executed_at)
                    quality = "pass" if trade else "deferred_nonexecuted_or_incomplete_identity"
                    observation_id = repository.record_observation(
                        "dataset.trade-event",
                        _envelope(row_id, row, executed_at, page.fetched_at, quality),
                        context.run_id,
                    )
                    if trade:
                        trade["knowledge_at"] = page.fetched_at
                        pending_trades.append((trade, observation_id))
                        row_classified = True
                elif partition.source_operation == OVERSEAS_TRANSACTION_HISTORY:
                    repository.record_observation(
                        "dataset.trade-event",
                        _envelope(row_id, row, executed_at, page.fetched_at, "candidate"),
                        context.run_id,
                    )
                    trade_candidates += 1
                    row_classified = True
                    cash_payloads = _cash_payloads(
                        partition,
                        row,
                        row_id=row_id,
                        effective_at=executed_at,
                    )
                    for cash in cash_payloads:
                        cash["knowledge_at"] = page.fetched_at
                        cash_observation = repository.record_observation(
                            "dataset.cash-transaction-event",
                            _envelope(
                                cash["source_record_id"],
                                row,
                                executed_at,
                                page.fetched_at,
                                "pass",
                            ),
                            context.run_id,
                        )
                        pending_cash.append((cash, cash_observation))

                if row_classified:
                    classified_rows += 1
                else:
                    deferred_rows += 1

        row_balance_ok = classified_rows + deferred_rows == raw_rows
        pagination_ok = fetched.complete and not fetched.pagination_warning
        reconciliation = {
            "status": "pass" if row_balance_ok and pagination_ok else "failed",
            "source_operation": partition.source_operation,
            "page_count": len(fetched.pages),
            "raw_rows": raw_rows,
            "classified_rows": classified_rows,
            "deferred_rows": deferred_rows,
            "trade_events": trade_events,
            "trade_candidate_rows": trade_candidates,
            "cash_events": cash_events,
            "pagination_complete": fetched.complete,
            "pagination_warning": fetched.pagination_warning,
        }
        if not row_balance_ok:
            raise BackfillReconciliationError(f"source row reconciliation failed: {reconciliation}")
        if not pagination_ok:
            raise BackfillReconciliationError(f"pagination incomplete: {reconciliation}")

        for trade, observation_id in pending_trades:
            repository.record_trade(trade, observation_id)
        for cash, observation_id in pending_cash:
            repository.record_cash_flow(cash, observation_id)
        trade_events = len(pending_trades)
        cash_events = len(pending_cash)
        reconciliation["trade_events"] = trade_events
        reconciliation["cash_events"] = cash_events

        context.state["reconciliation"] = reconciliation
        lineage = [
            LineageEvidence(
                f"source.kis-open-api:{partition.source_operation}",
                "dataset.trade-event",
                "trade-cash-backfill-normalize",
                "1.0.0",
            )
        ]
        if partition.source_operation == OVERSEAS_TRANSACTION_HISTORY:
            lineage.append(
                LineageEvidence(
                    f"source.kis-open-api:{partition.source_operation}",
                    "dataset.cash-transaction-event",
                    "trade-cash-backfill-normalize",
                    "1.0.0",
                )
            )
        return StageResult(
            input_count=raw_rows,
            output_count=trade_events + cash_events,
            source_calls=len(fetched.pages),
            evidence={"reconciliation": reconciliation},
            quality=(
                QualityEvidence(
                    "dataset.trade-event",
                    "source-row-reconciliation",
                    "pass",
                    str(classified_rows + deferred_rows),
                    str(raw_rows),
                    {"deferred_rows": deferred_rows},
                ),
                QualityEvidence(
                    "dataset.trade-event",
                    "pagination-complete",
                    "pass",
                    str(len(fetched.pages)),
                    "within approved page budget",
                ),
            ),
            lineage=tuple(lineage),
        )

    return handler
