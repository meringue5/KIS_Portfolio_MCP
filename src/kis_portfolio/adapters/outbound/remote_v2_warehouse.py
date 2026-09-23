"""Production MotherDuck/DuckDB query adapter for the Remote MCP V2 surface."""

from __future__ import annotations

import tomllib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import duckdb

from kis_portfolio.application.portfolio_quality import (
    PortfolioQualityComponent,
    component_quality_reasons,
    evaluate_portfolio_capabilities,
)
from kis_portfolio.common.values import rows_to_dicts
from kis_portfolio.services.remote_read_surface import (
    V2_READ_TOOL_NAMES,
    DataCatalogRequest,
    DataQualityRequest,
    DividendSummaryRequest,
    ExposureAnalysisRequest,
    FundamentalOutlookRequest,
    JournalReviewQueueRequest,
    MarketHistoryRequest,
    MarketSnapshotRequest,
    PerformanceHistoryRequest,
    PipelineRunRequest,
    PortfolioOverviewRequest,
    PositionAnalysisRequest,
    ReadActor,
    RemoteReadError,
    SignalStatusRequest,
    TradeLedgerRequest,
    TradeThreadRequest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
PUBLIC_PIPELINE_ALIASES = {
    "portfolio-refresh": "pipeline.owned-portfolio-core-v2",
}
PUBLIC_DATASET_ALIASES = {
    "price-bar-daily": "dataset.price-bar-daily",
}
KR_MARKETS = frozenset({"KR", "KRX"})
US_MARKETS = frozenset({"US", "NAS", "NYS", "AMS", "NASDAQ", "NYSE", "AMEX"})


class WarehouseReadQueryPort:
    """Serve the approved V2 catalog from governed read models only.

    This adapter never exposes account ids, provider payloads, raw objects, or
    source credentials. Empty optional datasets are returned as explicit
    partial coverage instead of being presented as complete zeroes.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection, *, repo_root: Path = PROJECT_ROOT) -> None:
        self.connection = connection
        self.repo_root = repo_root

    def capabilities(self) -> frozenset[str]:
        return frozenset(V2_READ_TOOL_NAMES)

    async def query(self, tool_name: str, request: object, actor: ReadActor) -> Mapping[str, Any]:
        handler = getattr(self, f"_{tool_name.replace('-', '_')}", None)
        if handler is None or tool_name not in V2_READ_TOOL_NAMES:
            raise RemoteReadError("unknown_read_tool")
        return handler(request)

    def _rows(self, sql: str, params: list[object] | None = None) -> list[dict[str, Any]]:
        return rows_to_dicts(self.connection.execute(sql, params or []))

    @staticmethod
    def _coverage(items: list[dict[str, Any]], dataset_id: str) -> list[dict[str, Any]]:
        if items:
            return []
        return [{"dataset_id": dataset_id, "reason": "no_governed_rows"}]

    def _envelope(
        self,
        *,
        data: dict[str, Any],
        items: list[dict[str, Any]],
        dataset_id: str,
        as_of: datetime | None = None,
        lineage_ref: str | None = None,
        missing_coverage: list[dict[str, Any]] | None = None,
        quality_status: str | None = None,
    ) -> dict[str, Any]:
        missing = self._coverage(items, dataset_id) if missing_coverage is None else missing_coverage
        observed_at = as_of or datetime.now(UTC)
        return {
            "schema_version": "2.0.0",
            "as_of": observed_at,
            "source": {"mode": "stored", "dataset_id": dataset_id},
            "freshness": {"status": "available" if items else "unavailable", "as_of": observed_at},
            "quality": {"status": quality_status or ("pass" if items else "partial"), "row_count": len(items)},
            "missing_coverage": missing,
            "lineage_ref": lineage_ref,
            "request_id": "pending",
            "data": data,
        }

    def _resolve_market_instrument_id(self, instrument_ref: str, market: str) -> str:
        value = instrument_ref.strip().upper()
        if market == "FX":
            return value.replace("/", "").replace("-", "")

        if value.startswith("V1|"):
            parts = value.split("|")
            if len(parts) != 3:
                raise RemoteReadError("invalid_instrument_reference")
            stored_market = parts[1]
            if (market == "KR" and stored_market != "KRX") or (
                market == "US" and stored_market not in {"NAS", "NYS", "AMS"}
            ):
                raise RemoteReadError("instrument_market_mismatch")
            return f"v1|{parts[1]}|{parts[2]}"

        prefix = None
        symbol = value
        if ":" in value:
            prefix, symbol = value.split(":", 1)
        if not symbol or "|" in symbol:
            raise RemoteReadError("invalid_instrument_reference")

        if market == "KR":
            if prefix is not None and prefix not in KR_MARKETS:
                raise RemoteReadError("instrument_market_mismatch")
            return f"v1|KRX|{symbol}"

        if prefix is not None and prefix not in US_MARKETS:
            raise RemoteReadError("instrument_market_mismatch")
        explicit_market = {
            "NASDAQ": "NAS", "NYSE": "NYS", "AMEX": "AMS",
            "NAS": "NAS", "NYS": "NYS", "AMS": "AMS",
        }.get(prefix or "")
        if explicit_market:
            return f"v1|{explicit_market}|{symbol}"

        candidates = self._rows(
            """
            SELECT DISTINCT instrument_id FROM (
                SELECT instrument_id, market, symbol FROM silver.instruments_current
                UNION ALL
                SELECT instrument_id, split_part(instrument_id, '|', 2) AS market,
                       split_part(instrument_id, '|', 3) AS symbol
                FROM silver.price_bars_daily
            ) candidates
            WHERE upper(symbol)=? AND market IN ('NAS','NYS','AMS')
            ORDER BY instrument_id
            """,
            [symbol],
        )
        ids = [str(row["instrument_id"]) for row in candidates]
        if not ids:
            raise RemoteReadError("unknown_instrument_reference")
        if len(ids) > 1:
            raise RemoteReadError("ambiguous_instrument_reference")
        return ids[0]

    @staticmethod
    def _resolve_pipeline_id(pipeline_ref: str) -> str:
        value = pipeline_ref.strip()
        if value in PUBLIC_PIPELINE_ALIASES:
            return PUBLIC_PIPELINE_ALIASES[value]
        if value.startswith("pipeline."):
            return value
        raise RemoteReadError("unknown_pipeline_reference")

    @staticmethod
    def _resolve_dataset_id(dataset_ref: str) -> str:
        value = dataset_ref.strip()
        if value in PUBLIC_DATASET_ALIASES:
            return PUBLIC_DATASET_ALIASES[value]
        if value.startswith("dataset."):
            return value
        raise RemoteReadError("unknown_dataset_reference")

    def _get_portfolio_overview(self, request: PortfolioOverviewRequest) -> dict[str, Any]:
        rows = self._rows(
            """
            WITH selected AS (
                SELECT max(p.as_of) AS as_of
                FROM gold.portfolio_daily_state p
                JOIN silver.accounts a ON a.account_id=p.account_id
                WHERE (? IS NULL OR p.as_of<=?)
                  AND (? IS NULL OR a.account_label=?)
            )
            SELECT p.evaluation_date, p.evaluation_slot, a.account_label,
                   p.instrument_id, coalesce(i.name,b.name) AS instrument_name, i.asset_type,
                   p.aggregate_level, p.quantity, p.value_krw, p.cost_krw,
                   p.unrealized_pnl_krw, p.contribution_pct, p.allocation_pct,
                   p.as_of, p.quality_status,
                   coalesce(i.market,b.market) AS _market,
                   coalesce(i.currency,b.currency) AS _currency,
                   json_extract_string(p.input_watermarks,'$.fx_date') AS _fx_date
            FROM gold.portfolio_daily_state p
            JOIN selected s ON p.as_of=s.as_of
            JOIN silver.accounts a ON a.account_id=p.account_id
            LEFT JOIN silver.instruments_current i ON i.instrument_id=p.instrument_id
            LEFT JOIN silver.instruments b ON b.instrument_id=p.instrument_id
            WHERE (? IS NULL OR a.account_label=?)
            ORDER BY a.account_label, p.aggregate_level, p.value_krw DESC NULLS LAST
            """,
            [request.as_of, request.as_of, request.account_alias, request.account_alias,
             request.account_alias, request.account_alias],
        )
        as_of = _latest_datetime(rows, "as_of")
        evaluation_date = rows[0]["evaluation_date"] if rows else None
        prior_open = self.connection.execute(
            "SELECT max(trade_date) FROM control.market_calendar "
            "WHERE lower(market)='krx' AND is_open AND trade_date<?",
            [evaluation_date],
        ).fetchone()[0] if evaluation_date else None
        earliest_fx_date = prior_open or evaluation_date
        missing: list[dict[str, Any]] = []
        quality_components: list[PortfolioQualityComponent] = []
        for row in rows:
            currency = str(row.pop("_currency") or (
                str(row["instrument_id"]).split("|", 1)[1]
                if row["aggregate_level"] == "cash" and "|" in str(row["instrument_id"])
                else "UNKNOWN"
            )).upper()
            market = str(row.pop("_market") or "").upper()
            fx_date = row.pop("_fx_date")
            component = PortfolioQualityComponent(
                account_ref=str(row["account_label"]),
                aggregate_level=str(row["aggregate_level"]),
                market=market,
                currency=currency,
                value_krw=Decimal(str(row["value_krw"] or 0)),
                quality_status=str(row["quality_status"]),
                fx_date=fx_date,
            )
            if component.aggregate_level in {"position", "cash"}:
                quality_components.append(component)
            row_reasons = component_quality_reasons(
                component,
                evaluation_date=evaluation_date,
                earliest_fx_date=earliest_fx_date,
            ) if evaluation_date and earliest_fx_date else ("missing_evaluation_date",)
            if row_reasons:
                row["quality_status"] = "degraded"
                for reason in row_reasons:
                    dataset_id = {
                        "unknown_currency": "dataset.instrument-master",
                        "fx_input_stale": "dataset.fx-rate-daily",
                    }.get(reason, "dataset.portfolio-daily-state")
                    missing.append({"dataset_id": dataset_id, "reason": reason})
            if row["quality_status"] != "pass":
                for field in ("value_krw", "cost_krw", "unrealized_pnl_krw", "contribution_pct", "allocation_pct"):
                    row[field] = None
        total_rows = [
            row for row in rows if row.get("aggregate_level") in {"position", "cash"}
        ]
        observed_aliases = {str(row["account_label"]) for row in total_rows}
        expected_aliases = {
            str(account[0]) for account in self.connection.execute(
                "SELECT account_label FROM silver.accounts "
                "WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?) "
                "AND (? IS NULL OR account_label=?)",
                [as_of, as_of, request.account_alias, request.account_alias],
            ).fetchall()
        } if as_of else set()
        if observed_aliases != expected_aliases:
            missing.append({"dataset_id": "dataset.portfolio-daily-state", "reason": "account_coverage_gap"})
        capability = evaluate_portfolio_capabilities(
            quality_components,
            expected_accounts=expected_aliases,
            evaluation_date=evaluation_date,
            earliest_fx_date=earliest_fx_date,
        ) if evaluation_date and earliest_fx_date else None
        complete = bool(capability and capability.complete)
        summary = None
        if total_rows:
            summary = {
                "evaluation_date": total_rows[0]["evaluation_date"],
                "evaluation_slot": total_rows[0]["evaluation_slot"],
                "total_value_krw": capability.complete_total_krw if capability else None,
                "verified_krw_listed_positions_krw": (
                    capability.verified_krw_listed_positions_krw if capability else Decimal("0")
                ),
                "verified_krw_listed_positions_count": (
                    capability.verified_krw_listed_positions_count if capability else 0
                ),
                "quality_status": "pass" if complete else "degraded",
                "as_of": as_of,
            }
        quality_rows = rows
        response_rows = rows if request.include_holdings else []
        missing = list({(item["dataset_id"], item["reason"]): item for item in missing}.values())
        return self._envelope(
            data={"summary": summary, "positions": response_rows},
            items=quality_rows,
            dataset_id="dataset.portfolio-daily-state",
            as_of=as_of,
            lineage_ref="gold.portfolio_daily_state",
            missing_coverage=missing if quality_rows else None,
            quality_status="pass" if complete else "partial",
        )

    def _get_position_analysis(self, request: PositionAnalysisRequest) -> dict[str, Any]:
        rows = self._rows(
            """
            SELECT a.account_label, p.instrument_id, i.name AS instrument_name,
                   p.quantity, p.average_cost, p.cost_currency, p.as_of,
                   p.quality_status
            FROM silver.position_snapshots p
            JOIN silver.accounts a ON a.account_id=p.account_id
            LEFT JOIN silver.instruments_current i ON i.instrument_id=p.instrument_id
            WHERE p.as_of=(
                SELECT max(p2.as_of) FROM silver.position_snapshots p2
                WHERE p2.account_id=p.account_id AND p2.instrument_id=p.instrument_id
                  AND (? IS NULL OR p2.as_of<=?)
            )
              AND (? IS NULL OR p.instrument_id=?)
              AND (? IS NULL OR a.account_label=?)
            ORDER BY p.as_of DESC, a.account_label, p.instrument_id
            LIMIT ?
            """,
            [request.as_of, request.as_of, request.instrument_id, request.instrument_id,
             request.account_alias, request.account_alias, request.limit],
        )
        return self._envelope(
            data={"positions": rows}, items=rows, dataset_id="dataset.portfolio-position-observation",
            as_of=_latest_datetime(rows, "as_of"), lineage_ref="silver.position_snapshots",
        )

    def _get_performance_history(self, request: PerformanceHistoryRequest) -> dict[str, Any]:
        if request.grain != "daily":
            raise RemoteReadError("unsupported_performance_grain")
        rows = self._rows(
            """
            SELECT p.evaluation_date, p.evaluation_slot,
                   CASE WHEN count_if(p.quality_status <> 'pass') > 0
                        THEN NULL ELSE sum(p.value_krw) END AS total_value_krw,
                   CASE WHEN count_if(p.quality_status <> 'pass') > 0
                        THEN 'degraded' ELSE 'pass' END AS quality_status,
                   max(p.as_of) AS as_of
            FROM gold.portfolio_daily_state p
            JOIN silver.accounts a ON a.account_id=p.account_id
            WHERE p.aggregate_level IN ('position', 'cash')
              AND p.evaluation_date BETWEEN ? AND ?
              AND (? IS NULL OR a.account_label=?)
            GROUP BY p.evaluation_date, p.evaluation_slot
            ORDER BY p.evaluation_date, p.evaluation_slot LIMIT ?
            """,
            [request.start_date, request.end_date, request.account_alias,
             request.account_alias, request.limit],
        )
        missing = [
            {"dataset_id": "dataset.portfolio-daily-state", "reason": "degraded_history_rows"}
        ] if any(row["quality_status"] != "pass" for row in rows) else None
        return self._envelope(
            data={"grain": request.grain, "history": rows}, items=rows,
            dataset_id="dataset.portfolio-daily-state", as_of=_latest_datetime(rows, "as_of"),
            lineage_ref="gold.portfolio_daily_summary",
            missing_coverage=missing,
            quality_status="partial" if missing else None,
        )

    def _get_market_snapshot(self, request: MarketSnapshotRequest) -> dict[str, Any]:
        if request.market == "FX":
            instrument_id = self._resolve_market_instrument_id(request.instrument_id, request.market)
            rows = self._rows(
                """SELECT base_currency, quote_currency, rate_date, rate_type, rate, quality_status
                   FROM silver.fx_rates_daily
                   WHERE base_currency=? OR (base_currency || quote_currency)=?
                   ORDER BY rate_date DESC LIMIT 1""",
                [instrument_id, instrument_id],
            )
            as_of = _latest_datetime(rows, "rate_date")
            dataset_id = "dataset.fx-rate-daily"
            lineage_ref = "silver.fx_rates_daily"
        else:
            instrument_id = self._resolve_market_instrument_id(request.instrument_id, request.market)
            rows = self._rows(
                """SELECT instrument_id, session_date, price_basis, open, high, low, close,
                          volume, effective_at, knowledge_at, quality_status
                   FROM silver.price_bars_daily WHERE instrument_id=? AND price_basis='raw'
                   ORDER BY session_date DESC, knowledge_at DESC LIMIT 1""",
                [instrument_id],
            )
            as_of = _latest_datetime(rows, "knowledge_at")
            dataset_id = "dataset.price-bar-daily"
            lineage_ref = "silver.price_bars_daily"
        return self._envelope(
            data={"snapshot": rows[0] if rows else None}, items=rows,
            dataset_id=dataset_id, as_of=as_of, lineage_ref=lineage_ref,
        )

    def _get_market_history(self, request: MarketHistoryRequest) -> dict[str, Any]:
        if request.market == "FX":
            instrument_id = self._resolve_market_instrument_id(request.instrument_id, request.market)
            rows = self._rows(
                """SELECT base_currency, quote_currency, rate_date, rate_type, rate, quality_status
                   FROM silver.fx_rates_daily
                   WHERE (base_currency=? OR (base_currency || quote_currency)=?)
                     AND rate_date BETWEEN ? AND ? ORDER BY rate_date LIMIT ?""",
                [instrument_id, instrument_id, request.start_date, request.end_date, request.limit],
            )
            as_of = _latest_datetime(rows, "rate_date")
            dataset_id = "dataset.fx-rate-daily"
            lineage_ref = "silver.fx_rates_daily"
        else:
            instrument_id = self._resolve_market_instrument_id(request.instrument_id, request.market)
            basis = "adjusted" if request.adjusted else "raw"
            rows = self._rows(
                """SELECT instrument_id, session_date, price_basis, open, high, low, close,
                          volume, effective_at, knowledge_at, quality_status
                   FROM silver.price_bars_daily
                   WHERE instrument_id=? AND price_basis=? AND session_date BETWEEN ? AND ?
                   ORDER BY session_date LIMIT ?""",
                [instrument_id, basis, request.start_date, request.end_date, request.limit],
            )
            as_of = _latest_datetime(rows, "knowledge_at")
            dataset_id = "dataset.price-bar-daily"
            lineage_ref = "silver.price_bars_daily"
        return self._envelope(
            data={"history": rows}, items=rows, dataset_id=dataset_id,
            as_of=as_of, lineage_ref=lineage_ref,
        )

    def _get_trade_ledger(self, request: TradeLedgerRequest) -> dict[str, Any]:
        if request.cursor is not None:
            raise RemoteReadError("unsupported_cursor")
        rows = self._rows(
            """
            SELECT a.account_label, t.trade_event_id, t.market, t.instrument_id,
                   t.executed_at, t.execution_sequence, t.side, t.quantity, t.price,
                   t.currency, t.revision, t.knowledge_at, t.quality_status
            FROM silver.trade_events_current t
            JOIN silver.accounts a ON a.account_id=t.account_id
            WHERE cast(t.executed_at AS DATE) BETWEEN ? AND ?
              AND (? IS NULL OR a.account_label=?)
              AND (? IS NULL OR t.instrument_id=?)
            ORDER BY t.executed_at DESC, t.execution_sequence DESC LIMIT ?
            """,
            [request.start_date, request.end_date, request.account_alias, request.account_alias,
             request.instrument_id, request.instrument_id, request.limit],
        )
        dataset_state = self._rows(
            """SELECT count(*) AS row_count, max(knowledge_at) AS latest_knowledge_at
               FROM silver.trade_events_current"""
        )[0]
        coverage_state = self._rows(
            """SELECT min(try_cast(watermark_value AS DATE)) AS coverage_through,
                      max(updated_at) AS updated_at
               FROM control.watermarks
               WHERE pipeline_id='pipeline.trade-cash-backfill-v2'
                 AND watermark_type='source_end_date_v1'"""
        )[0]
        dataset_has_rows = int(dataset_state["row_count"] or 0) > 0
        coverage_through = coverage_state["coverage_through"]
        coverage_date = (
            date.fromisoformat(coverage_through)
            if isinstance(coverage_through, str)
            else coverage_through
        )
        coverage_complete = bool(
            coverage_date is not None and coverage_date >= request.end_date
        )
        result_status = (
            "matched" if rows and coverage_complete else
            "matched_with_coverage_gap" if rows else
            "no_events_in_query_window" if coverage_complete else
            "collection_coverage_gap" if dataset_has_rows or coverage_through else
            "no_governed_rows"
        )
        missing: list[dict[str, Any]] = []
        if not coverage_complete:
            missing.append({
                "dataset_id": "dataset.trade-event",
                "reason": (
                    "collection_watermark_before_query_end"
                    if coverage_through is not None
                    else "collection_watermark_missing"
                ),
            })
        result = self._envelope(
            data={
                "query": {
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "result_status": result_status,
                    "coverage_through": coverage_through,
                },
                "events": rows,
                "next_cursor": None,
            },
            items=rows,
            dataset_id="dataset.trade-event",
            as_of=(
                _latest_datetime(rows, "knowledge_at")
                or dataset_state["latest_knowledge_at"]
                or coverage_state["updated_at"]
            ),
            lineage_ref="silver.trade_events_current",
            missing_coverage=missing,
            quality_status="pass" if coverage_complete else "partial",
        )
        if dataset_has_rows or coverage_through is not None:
            result["freshness"]["status"] = "available"
        return result

    def _get_trade_thread(self, request: TradeThreadRequest) -> dict[str, Any]:
        if request.cursor is not None:
            raise RemoteReadError("unsupported_cursor")
        rows = self._rows(
            """
            SELECT a.account_label, t.thread_id, t.instrument_id, t.opened_at,
                   t.closed_at, t.title, t.status, t.revision
            FROM silver.trade_threads t
            JOIN silver.accounts a ON a.account_id=t.account_id
            WHERE (? IS NULL OR t.thread_id=?)
              AND (? IS NULL OR t.instrument_id=?)
              AND (? IS NULL OR a.account_label=?)
              AND (? IS NULL OR t.opened_at<=?)
            ORDER BY t.opened_at DESC LIMIT ?
            """,
            [request.thread_id, request.thread_id, request.instrument_id, request.instrument_id,
             request.account_alias, request.account_alias, request.as_of, request.as_of, request.limit],
        )
        revisions = self._rows(
            """SELECT thread_id, revision, change_kind, change_document, authored_at,
                      expected_prior_revision, recorded_at
               FROM silver.trade_thread_command_revisions
               WHERE (? IS NULL OR thread_id=?)
               ORDER BY authored_at DESC LIMIT ?""",
            [request.thread_id, request.thread_id, request.limit],
        )
        return self._envelope(
            data={"threads": rows, "revisions": revisions, "next_cursor": None}, items=rows + revisions,
            dataset_id="dataset.trade-thread", as_of=_latest_datetime(rows, "opened_at"),
            lineage_ref="silver.trade_threads",
        )

    def _get_dividend_summary(self, request: DividendSummaryRequest) -> dict[str, Any]:
        rows = self._rows(
            """
            SELECT d.received_month, a.account_label, d.instrument_id, d.currency,
                   d.received_cash_amount, d.sourced_gross_amount, d.sourced_tax_amount,
                   d.sourced_net_amount, d.component_coverage, d.reconciliation_coverage,
                   d.received_cash_amount_krw, d.conversion_label
            FROM gold.dividend_monthly_krw d
            JOIN silver.accounts a ON a.account_id=d.account_id
            WHERE d.received_month BETWEEN date_trunc('month', ?) AND date_trunc('month', ?)
              AND (? IS NULL OR a.account_label=?)
              AND (? IS NULL OR d.instrument_id=?)
              AND (? IS NULL OR d.currency=?)
            ORDER BY d.received_month, a.account_label, d.instrument_id
            """,
            [request.start_date, request.end_date, request.account_alias, request.account_alias,
             request.instrument_id, request.instrument_id, request.currency, request.currency],
        )
        return self._envelope(
            data={"monthly": rows}, items=rows, dataset_id="dataset.dividend-ledger",
            as_of=_latest_datetime(rows, "received_month"), lineage_ref="gold.dividend_monthly_krw",
        )

    def _get_fundamental_outlook(self, request: FundamentalOutlookRequest) -> dict[str, Any]:
        actuals = self._rows(
            """
            SELECT f.taxonomy, f.concept, f.period_start, f.period_end, f.period_type,
                   f.unit, f.statement_scope, f.typed_value, f.knowledge_at, f.quality_status
            FROM silver.financial_fact_revisions_current f
            JOIN silver.filing_revisions_current fr ON fr.filing_revision_id=f.filing_revision_id
            JOIN silver.filing_identities fi ON fi.filing_identity_id=fr.filing_identity_id
            JOIN silver.instruments_current i ON i.issuer_id=fi.issuer_id
            WHERE i.instrument_id=? AND (? IS NULL OR f.knowledge_at<=?)
            ORDER BY f.period_end DESC, f.knowledge_at DESC LIMIT 200
            """,
            [request.instrument_id, request.as_of, request.as_of],
        )
        forecasts = self._rows(
            """
            SELECT c.provider_forecast_date, c.horizon, c.metric, c.estimate_average,
                   c.estimate_high, c.estimate_low, c.analyst_count, c.fetched_at,
                   c.quality_status
            FROM silver.alpha_vantage_consensus_forward_latest c
            JOIN silver.instruments_current i ON i.issuer_id=c.issuer_id
            WHERE i.instrument_id=? AND (? IS NULL OR c.fetched_at<=?)
            ORDER BY c.provider_forecast_date DESC, c.horizon, c.metric LIMIT 200
            """,
            [request.instrument_id, request.as_of, request.as_of],
        )
        items = actuals + forecasts
        dataset_counts = self._rows(
            """SELECT
                   (SELECT count(*) FROM silver.financial_fact_revisions_current) AS actual_count,
                   (SELECT count(*) FROM silver.alpha_vantage_consensus_forward_latest) AS forecast_count
            """
        )[0]
        missing: list[dict[str, Any]] = []
        if not actuals:
            missing.append({
                "dataset_id": "dataset.financial-fact",
                "reason": (
                    "no_rows_for_instrument"
                    if int(dataset_counts["actual_count"] or 0) > 0
                    else "approved_inactive"
                ),
            })
        if not forecasts:
            missing.append({
                "dataset_id": "dataset.alpha-vantage-consensus-forward-snapshot",
                "reason": (
                    "no_rows_for_instrument"
                    if int(dataset_counts["forecast_count"] or 0) > 0
                    else "approved_inactive"
                ),
            })
        return self._envelope(
            data={"scenario": request.scenario, "actuals": actuals, "consensus": forecasts},
            items=items, dataset_id="dataset.fundamental-outlook",
            as_of=_latest_datetime(items, "knowledge_at", "fetched_at"),
            lineage_ref="silver.financial_fact_revisions_current|silver.alpha_vantage_consensus_forward_latest",
            missing_coverage=missing,
            quality_status="partial" if missing else "pass",
        )

    def _get_exposure_analysis(self, request: ExposureAnalysisRequest) -> dict[str, Any]:
        rows = self._rows(
            """
            WITH latest AS (
                SELECT max(p.as_of) AS as_of FROM gold.portfolio_daily_state p
                JOIN silver.accounts a ON a.account_id=p.account_id
                WHERE (? IS NULL OR p.as_of<=?) AND (? IS NULL OR a.account_label=?)
            )
            SELECT a.account_label, p.instrument_id, i.name AS instrument_name,
                   coalesce(i.asset_type, 'unknown') AS asset_type,
                   coalesce(i.economic_exposure, 'unknown') AS economic_exposure,
                   sum(p.value_krw) AS value_krw, sum(p.allocation_pct) AS allocation_pct,
                   max(p.as_of) AS as_of
            FROM gold.portfolio_daily_state p
            JOIN latest l ON p.as_of=l.as_of
            JOIN silver.accounts a ON a.account_id=p.account_id
            LEFT JOIN silver.instruments_current i ON i.instrument_id=p.instrument_id
            WHERE p.aggregate_level='position' AND (? IS NULL OR a.account_label=?)
            GROUP BY a.account_label, p.instrument_id, i.name, asset_type, economic_exposure
            ORDER BY value_krw DESC
            """,
            [request.as_of, request.as_of, request.account_alias, request.account_alias,
             request.account_alias, request.account_alias],
        )
        macro = []
        if request.include_macro:
            macro = self._rows(
                """SELECT profile_id, profile_version, evaluation_at, metric_set_version,
                          metric_values, missing_coverage, rights_summary, attribution, quality_status
                   FROM gold.macro_profile_snapshots
                   WHERE (? IS NULL OR evaluation_at<=?) ORDER BY evaluation_at DESC LIMIT 1""",
                [request.as_of, request.as_of],
            )
        macro_dataset_count = 0
        if request.include_macro and not macro:
            macro_dataset_count = int(self.connection.execute(
                "SELECT count(*) FROM gold.macro_profile_snapshots"
            ).fetchone()[0])
        missing = [] if rows else [{"dataset_id": "dataset.portfolio-daily-state", "reason": "no_governed_rows"}]
        if request.include_macro and not macro:
            missing.append({
                "dataset_id": "dataset.macro-profile-snapshot",
                "reason": (
                    "no_rows_at_or_before_cutoff"
                    if macro_dataset_count > 0
                    else "approved_inactive"
                ),
            })
        missing.append({
            "dataset_id": "dataset.etf-constituent-snapshot",
            "reason": "unsupported_initial_v2",
        })
        return self._envelope(
            data={"direct": rows, "macro": macro[0] if macro else None}, items=rows,
            dataset_id="dataset.portfolio-daily-state", as_of=_latest_datetime(rows, "as_of"),
            lineage_ref="gold.portfolio_daily_state|gold.macro_profile_snapshots",
            missing_coverage=missing,
            quality_status="partial" if missing else "pass",
        )

    def _get_signal_status(self, request: SignalStatusRequest) -> dict[str, Any]:
        rows = self._rows(
            """
            SELECT s.alert_identity AS signal_id, s.current_state AS signal_state,
                   s.current_severity AS severity, s.transition_type, s.revision,
                   s.episode, s.knowledge_at, s.delivery_required, s.delivery_severity
            FROM control.alert_states_current s
            LEFT JOIN gold.alert_candidates c ON c.candidate_id=s.candidate_id
            WHERE (? IS NULL OR s.alert_identity=?)
              AND (? IS NULL OR c.subject_id=?)
              AND (? IS NULL OR s.knowledge_at<=?)
            ORDER BY s.knowledge_at DESC LIMIT ?
            """,
            [request.signal_id, request.signal_id, request.instrument_id, request.instrument_id,
             request.as_of, request.as_of, request.limit],
        )
        return self._envelope(
            data={"signals": rows, "next_cursor": None}, items=rows,
            dataset_id="dataset.signal-state", as_of=_latest_datetime(rows, "knowledge_at"),
            lineage_ref="control.alert_states_current",
        )

    def _get_data_catalog(self, request: DataCatalogRequest) -> dict[str, Any]:
        filename = {
            "source": "sources.toml", "dataset": "datasets.toml", "pipeline": "pipelines.toml",
        }.get(request.kind)
        records: list[dict[str, Any]] = []
        if filename:
            document = tomllib.loads((self.repo_root / "governance/catalog" / filename).read_text(encoding="utf-8"))
            for record in document.get("contracts", []):
                identifier = str(record.get("id") or record.get(f"{request.kind}_id") or "")
                if record.get("status") not in {"approved", "active"}:
                    continue
                if request.item_id and identifier != request.item_id:
                    continue
                records.append({
                    "id": identifier,
                    "status": record.get("status"),
                    "version": record.get("version"),
                    "description": record.get("description") or record.get("title"),
                })
        elif request.kind == "macro_series":
            records = self._rows(
                """SELECT series_contract_id AS id, version, activation_state AS status,
                          region, concept, native_frequency, native_unit, attribution
                   FROM control.macro_series_definitions
                   WHERE (? IS NULL OR series_contract_id=?) ORDER BY series_contract_id LIMIT ?""",
                [request.item_id, request.item_id, request.limit],
            )
        elif request.kind == "metric":
            records = self._rows(
                """SELECT metric_id AS id, version, contract_status AS status
                   FROM control.metric_definitions WHERE (? IS NULL OR metric_id=?)
                   ORDER BY metric_id, version LIMIT ?""",
                [request.item_id, request.item_id, request.limit],
            )
        else:
            records = _object_catalog(self.repo_root, request.item_id)
        records = records[: request.limit]
        return self._envelope(
            data={"kind": request.kind, "items": records, "next_cursor": None}, items=records,
            dataset_id="control.governance-catalog", lineage_ref="governance/catalog",
        )

    def _get_data_quality(self, request: DataQualityRequest) -> dict[str, Any]:
        dataset_id = self._resolve_dataset_id(request.dataset_id)
        rows = self._rows(
            """
            SELECT q.run_id, q.dataset_id, q.rule_id, q.status, q.observed_value,
                   q.expected_value, q.details, q.evaluated_at
            FROM control.quality_results q
            WHERE q.dataset_id=? AND (? IS NULL OR q.run_id=?)
              AND q.evaluated_at<=coalesce(?, current_timestamp)
              AND q.evaluated_at>=coalesce(?, current_timestamp)-(? * INTERVAL '1 day')
            ORDER BY q.evaluated_at DESC, q.rule_id LIMIT ?
            """,
            [dataset_id, request.run_id, request.run_id, request.as_of, request.as_of,
             request.lookback_days, request.limit],
        )
        missing = [] if rows else [{
            "dataset_id": dataset_id,
            "reason": "no_quality_evidence_in_window",
        }]
        statuses = {str(row["status"]).lower() for row in rows}
        if not rows:
            quality_status = "partial"
        elif statuses & {"fail", "failed", "error", "unavailable"}:
            quality_status = "failed"
        elif statuses == {"pass"}:
            quality_status = "pass"
        else:
            quality_status = "partial"
        return self._envelope(
            data={"results": rows, "next_cursor": None}, items=rows,
            dataset_id="dataset.data-quality-evidence", as_of=_latest_datetime(rows, "evaluated_at"),
            lineage_ref="control.quality_results",
            missing_coverage=missing,
            quality_status=quality_status,
        )

    def _get_pipeline_run(self, request: PipelineRunRequest) -> dict[str, Any]:
        pipeline_id = self._resolve_pipeline_id(request.pipeline_id) if request.pipeline_id else None
        rows = self._rows(
            """
            SELECT s.run_id, s.pipeline_id, s.pipeline_version, s.logical_date, s.slot,
                   s.partition_key, s.status, s.source_calls, s.stage_count,
                   s.succeeded_stage_count, s.started_at, s.finished_at,
                   (SELECT count(*) FROM control.quality_results q WHERE q.run_id=s.run_id)
                       AS quality_evidence_count,
                   (SELECT count(*) FROM control.quality_results q
                       WHERE q.run_id=s.run_id AND lower(q.status)<>'pass')
                       AS failed_quality_evidence_count
            FROM control.pipeline_run_summary s
            JOIN control.pipeline_runs r ON r.run_id=s.run_id
            WHERE (? IS NULL OR s.run_id=? OR r.idempotency_key=?)
              AND (? IS NULL OR s.pipeline_id=?)
              AND s.started_at<=coalesce(?, current_timestamp)
              AND s.started_at>=coalesce(?, current_timestamp)-(? * INTERVAL '1 day')
            ORDER BY s.started_at DESC LIMIT ?
            """,
            [request.run_id, request.run_id, request.run_id,
             pipeline_id, pipeline_id,
            request.as_of, request.as_of, request.lookback_days, request.limit],
        )
        missing: list[dict[str, Any]] = []
        run_statuses = {str(row["status"]).lower() for row in rows}
        if not rows:
            quality_status = "partial"
        elif run_statuses & {"failed", "error", "cancelled"} or any(
            int(row["failed_quality_evidence_count"] or 0) > 0 for row in rows
        ):
            quality_status = "failed"
        elif any(
            row["pipeline_id"] == "pipeline.owned-portfolio-core-v2"
            and int(row["quality_evidence_count"] or 0) == 0
            for row in rows
        ):
            quality_status = "partial"
            missing.append({
                "dataset_id": "dataset.data-quality-evidence",
                "reason": "quality_evidence_missing_for_run",
            })
        elif run_statuses == {"succeeded"}:
            quality_status = "pass"
        else:
            quality_status = "partial"
        return self._envelope(
            data={
                "query": {
                    "requested_pipeline_id": request.pipeline_id,
                    "resolved_pipeline_id": pipeline_id,
                    "alias_applied": bool(
                        request.pipeline_id is not None and request.pipeline_id != pipeline_id
                    ),
                },
                "runs": rows,
                "next_cursor": None,
            },
            items=rows,
            dataset_id="dataset.pipeline-run-evidence", as_of=_latest_datetime(rows, "finished_at", "started_at"),
            lineage_ref="control.pipeline_run_summary",
            missing_coverage=missing if rows else None,
            quality_status=quality_status,
        )

    def _get_journal_review_queue(self, request: JournalReviewQueueRequest) -> dict[str, Any]:
        if request.cursor is not None:
            raise RemoteReadError("unsupported_cursor")
        if request.account_alias is not None:
            raise RemoteReadError("unsupported_review_account_filter")
        rows = self._rows(
            """
            SELECT r.review_item_id, r.review_type, r.subject_type, r.subject_id,
                   r.review_status, r.reason_code, r.question, r.knowledge_at, r.revision
            FROM control.owner_review_items_current r
            WHERE (?='all' OR r.review_status=?)
            ORDER BY r.knowledge_at DESC LIMIT ?
            """,
            [request.status, request.status, request.limit],
        )
        return self._envelope(
            data={"items": rows, "next_cursor": None}, items=rows,
            dataset_id="control.owner-review-items", as_of=_latest_datetime(rows, "knowledge_at"),
            lineage_ref="control.owner_review_items_current",
        )


def _latest_datetime(rows: list[dict[str, Any]], *keys: str) -> datetime | None:
    values: list[datetime] = []
    for row in rows:
        for key in keys:
            value = row.get(key)
            if isinstance(value, datetime):
                values.append(value if value.tzinfo else value.replace(tzinfo=UTC))
            elif isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value)
                    values.append(parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC))
                except ValueError:
                    continue
    return max(values) if values else None


def _object_catalog(repo_root: Path, item_id: str | None) -> list[dict[str, Any]]:
    from kis_portfolio.db.catalog import V2_DATA_OBJECTS

    records = []
    for item in sorted(V2_DATA_OBJECTS, key=lambda candidate: candidate.qualified_name):
        name = item.qualified_name
        if item_id and name != item_id:
            continue
        records.append({"id": name, "status": "managed", "description": "governed warehouse object"})
    return records
