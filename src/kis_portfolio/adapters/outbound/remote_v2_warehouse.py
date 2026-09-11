"""Production MotherDuck/DuckDB query adapter for the Remote MCP V2 surface."""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import duckdb

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
    ) -> dict[str, Any]:
        missing = self._coverage(items, dataset_id)
        observed_at = as_of or datetime.now(UTC)
        return {
            "schema_version": "2.0.0",
            "as_of": observed_at,
            "source": {"mode": "stored", "dataset_id": dataset_id},
            "freshness": {"status": "available" if items else "unavailable", "as_of": observed_at},
            "quality": {"status": "pass" if items else "partial", "row_count": len(items)},
            "missing_coverage": missing,
            "lineage_ref": lineage_ref,
            "request_id": "pending",
            "data": data,
        }

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
                   p.instrument_id, i.name AS instrument_name, i.asset_type,
                   p.aggregate_level, p.quantity, p.value_krw, p.cost_krw,
                   p.unrealized_pnl_krw, p.contribution_pct, p.allocation_pct,
                   p.as_of, p.quality_status
            FROM gold.portfolio_daily_state p
            JOIN selected s ON p.as_of=s.as_of
            JOIN silver.accounts a ON a.account_id=p.account_id
            LEFT JOIN silver.instruments_current i ON i.instrument_id=p.instrument_id
            WHERE (? IS NULL OR a.account_label=?)
            ORDER BY a.account_label, p.aggregate_level, p.value_krw DESC NULLS LAST
            """,
            [request.as_of, request.as_of, request.account_alias, request.account_alias,
             request.account_alias, request.account_alias],
        )
        if not request.include_holdings:
            rows = [row for row in rows if row.get("aggregate_level") != "instrument"]
        as_of = _latest_datetime(rows, "as_of")
        total_rows = [
            row for row in rows if row.get("aggregate_level") in {"position", "cash"}
        ]
        summary = None
        if total_rows:
            summary = {
                "evaluation_date": total_rows[0]["evaluation_date"],
                "evaluation_slot": total_rows[0]["evaluation_slot"],
                "total_value_krw": sum(row["value_krw"] for row in total_rows),
                "quality_status": (
                    "degraded"
                    if any(row.get("quality_status") != "passed" for row in total_rows)
                    else "passed"
                ),
                "as_of": as_of,
            }
        return self._envelope(
            data={"summary": summary, "positions": rows},
            items=rows,
            dataset_id="dataset.portfolio-daily-state",
            as_of=as_of,
            lineage_ref="gold.portfolio_daily_state",
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
                   sum(p.value_krw) AS total_value_krw,
                   CASE WHEN count_if(p.quality_status <> 'passed') > 0
                        THEN 'degraded' ELSE 'passed' END AS quality_status,
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
        return self._envelope(
            data={"grain": request.grain, "history": rows}, items=rows,
            dataset_id="dataset.portfolio-daily-state", as_of=_latest_datetime(rows, "as_of"),
            lineage_ref="gold.portfolio_daily_summary",
        )

    def _get_market_snapshot(self, request: MarketSnapshotRequest) -> dict[str, Any]:
        if request.market == "FX":
            rows = self._rows(
                """SELECT base_currency, quote_currency, rate_date, rate_type, rate, quality_status
                   FROM silver.fx_rates_daily
                   WHERE base_currency=? OR (base_currency || quote_currency)=?
                   ORDER BY rate_date DESC LIMIT 1""",
                [request.instrument_id, request.instrument_id],
            )
            as_of = _latest_datetime(rows, "rate_date")
        else:
            rows = self._rows(
                """SELECT instrument_id, session_date, price_basis, open, high, low, close,
                          volume, effective_at, knowledge_at, quality_status
                   FROM silver.price_bars_daily WHERE instrument_id=?
                   ORDER BY session_date DESC, knowledge_at DESC LIMIT 2""",
                [request.instrument_id],
            )
            as_of = _latest_datetime(rows, "knowledge_at")
        return self._envelope(
            data={"snapshot": rows[0] if rows else None}, items=rows,
            dataset_id="dataset.market-snapshot", as_of=as_of,
            lineage_ref="silver.price_bars_daily|silver.fx_rates_daily",
        )

    def _get_market_history(self, request: MarketHistoryRequest) -> dict[str, Any]:
        if request.market == "FX":
            rows = self._rows(
                """SELECT base_currency, quote_currency, rate_date, rate_type, rate, quality_status
                   FROM silver.fx_rates_daily
                   WHERE (base_currency=? OR (base_currency || quote_currency)=?)
                     AND rate_date BETWEEN ? AND ? ORDER BY rate_date LIMIT ?""",
                [request.instrument_id, request.instrument_id, request.start_date, request.end_date, request.limit],
            )
            as_of = _latest_datetime(rows, "rate_date")
        else:
            basis = "adjusted" if request.adjusted else "raw"
            rows = self._rows(
                """SELECT instrument_id, session_date, price_basis, open, high, low, close,
                          volume, effective_at, knowledge_at, quality_status
                   FROM silver.price_bars_daily
                   WHERE instrument_id=? AND price_basis=? AND session_date BETWEEN ? AND ?
                   ORDER BY session_date LIMIT ?""",
                [request.instrument_id, basis, request.start_date, request.end_date, request.limit],
            )
            as_of = _latest_datetime(rows, "knowledge_at")
        return self._envelope(
            data={"history": rows}, items=rows, dataset_id="dataset.price-bar-daily",
            as_of=as_of, lineage_ref="silver.price_bars_daily|silver.fx_rates_daily",
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
        return self._envelope(
            data={"events": rows, "next_cursor": None}, items=rows,
            dataset_id="dataset.trade-event", as_of=_latest_datetime(rows, "knowledge_at"),
            lineage_ref="silver.trade_events_current",
        )

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
        return self._envelope(
            data={"scenario": request.scenario, "actuals": actuals, "consensus": forecasts},
            items=items, dataset_id="dataset.fundamental-outlook",
            as_of=_latest_datetime(items, "knowledge_at", "fetched_at"),
            lineage_ref="silver.financial_fact_revisions_current|silver.alpha_vantage_consensus_forward_latest",
        )

    def _get_exposure_analysis(self, request: ExposureAnalysisRequest) -> dict[str, Any]:
        rows = self._rows(
            """
            WITH latest AS (
                SELECT max(p.as_of) AS as_of FROM gold.portfolio_daily_state p
                JOIN silver.accounts a ON a.account_id=p.account_id
                WHERE (? IS NULL OR p.as_of<=?) AND (? IS NULL OR a.account_label=?)
            )
            SELECT a.account_label, coalesce(i.asset_type, 'unknown') AS asset_type,
                   coalesce(i.economic_exposure, 'unknown') AS economic_exposure,
                   sum(p.value_krw) AS value_krw, sum(p.allocation_pct) AS allocation_pct,
                   max(p.as_of) AS as_of
            FROM gold.portfolio_daily_state p
            JOIN latest l ON p.as_of=l.as_of
            JOIN silver.accounts a ON a.account_id=p.account_id
            LEFT JOIN silver.instruments_current i ON i.instrument_id=p.instrument_id
            WHERE p.aggregate_level='instrument' AND (? IS NULL OR a.account_label=?)
            GROUP BY a.account_label, asset_type, economic_exposure
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
        return self._envelope(
            data={"direct": rows, "macro": macro[0] if macro else None}, items=rows,
            dataset_id="dataset.exposure-analysis", as_of=_latest_datetime(rows, "as_of"),
            lineage_ref="gold.portfolio_daily_state|gold.macro_profile_snapshots",
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
            [request.dataset_id, request.run_id, request.run_id, request.as_of, request.as_of,
             request.lookback_days, request.limit],
        )
        return self._envelope(
            data={"results": rows, "next_cursor": None}, items=rows,
            dataset_id="control.quality-results", as_of=_latest_datetime(rows, "evaluated_at"),
            lineage_ref="control.quality_results",
        )

    def _get_pipeline_run(self, request: PipelineRunRequest) -> dict[str, Any]:
        rows = self._rows(
            """
            SELECT run_id, pipeline_id, pipeline_version, logical_date, slot, partition_key,
                   status, source_calls, stage_count, succeeded_stage_count, started_at, finished_at
            FROM control.pipeline_run_summary
            WHERE (? IS NULL OR run_id=?) AND (? IS NULL OR pipeline_id=?)
              AND started_at<=coalesce(?, current_timestamp)
              AND started_at>=coalesce(?, current_timestamp)-(? * INTERVAL '1 day')
            ORDER BY started_at DESC LIMIT ?
            """,
            [request.run_id, request.run_id, request.pipeline_id, request.pipeline_id,
             request.as_of, request.as_of, request.lookback_days, request.limit],
        )
        return self._envelope(
            data={"runs": rows, "next_cursor": None}, items=rows,
            dataset_id="control.pipeline-runs", as_of=_latest_datetime(rows, "finished_at", "started_at"),
            lineage_ref="control.pipeline_run_summary",
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
