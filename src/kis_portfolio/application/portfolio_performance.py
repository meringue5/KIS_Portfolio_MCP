"""Point-in-time Modified Dietz, contribution, wealth and drawdown evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from kis_portfolio.adapters.outbound.metric_warehouse import MetricWarehouseRepository
from kis_portfolio.modules.monitoring import (
    MetricFormulaRegistry,
    MetricInput,
    MetricValue,
    PointInTimeMetricEngine,
    RECONCILIATION_TOLERANCE,
    register_portfolio_performance_formulas,
)
from kis_portfolio.platform.metric_contracts import load_metric_registry


RETURN_METRIC = "metric.portfolio-return-modified-dietz"
CONTRIBUTION_METRIC = "metric.portfolio-component-contribution-modified-dietz"
RESIDUAL_METRIC = "metric.portfolio-contribution-residual"
WEALTH_METRIC = "metric.portfolio-wealth-index"
DRAWDOWN_METRIC = "metric.portfolio-drawdown"
METRIC_VERSION = "1.0.0"
PORTFOLIO_SUBJECT_ID = "owner"

EXTERNAL_FLOW_TYPES = frozenset({"owner_deposit", "owner_withdrawal"})
LINKED_INTERNAL_FLOW_TYPES = frozenset({
    "internal_transfer_in", "internal_transfer_out",
    "trade_settlement_in", "trade_settlement_out", "fx_in", "fx_out",
})


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def _parse_json(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return json.loads(str(value))


def _parse_datetime(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("coverage timestamps must be timezone-aware")
    return parsed


def performance_account_scope_hash(accounts: frozenset[str]) -> str:
    """Build the non-reversible account-scope identity expected by cash coverage evidence."""
    return _hash("account-scope-v1", *sorted(accounts))


@dataclass(frozen=True, slots=True)
class PortfolioState:
    evaluation_date: date
    evaluation_slot: str
    as_of: datetime
    accounts: frozenset[str]
    components: dict[str, Decimal]
    component_lineage: dict[str, str]
    rows: tuple[MetricInput, ...]
    quality_status: str | None


@dataclass(frozen=True, slots=True)
class ExternalFlow:
    event_id: str
    component_id: str
    amount_krw: Decimal
    effective_at: datetime
    knowledge_at: datetime
    lineage_hash: str


@dataclass(frozen=True, slots=True)
class PerformanceChainState:
    available: bool = True
    wealth_index: Decimal = Decimal("1.0000000000")
    high_water: Decimal = Decimal("1.0000000000")
    wealth_lineage_hash: str = "wealth-base-1"


@dataclass(frozen=True, slots=True)
class PerformancePeriodOutcome:
    quality_status: str
    values: tuple[MetricValue, ...]
    chain_state: PerformanceChainState


def build_portfolio_performance_engine() -> PointInTimeMetricEngine:
    formulas = MetricFormulaRegistry()
    register_portfolio_performance_formulas(formulas)
    return PointInTimeMetricEngine(load_metric_registry(), formulas)


def inspect_portfolio_performance_readiness(
    connection: Any,
) -> dict[str, object]:
    """Return aggregate-only W0502 readiness evidence without identities or writes."""
    state = connection.execute("""
        SELECT count(*), count(DISTINCT evaluation_date), count(DISTINCT evaluation_slot),
               count_if(quality_status='pass'), count_if(quality_status<>'pass'),
               min(evaluation_date), max(evaluation_date)
        FROM gold.portfolio_daily_state
    """).fetchone()
    cash = connection.execute("""
        SELECT count(*),
               coalesce(count_if(event_type='unknown'), 0),
               coalesce(count_if(event_type IN ('owner_deposit', 'owner_withdrawal')), 0),
               coalesce(count_if(event_type IN ('owner_deposit', 'owner_withdrawal') AND currency<>'KRW'), 0),
               coalesce(count_if(
                   event_type IN (
                       'internal_transfer_in', 'internal_transfer_out',
                       'trade_settlement_in', 'trade_settlement_out', 'fx_in', 'fx_out'
                   ) AND link_quality NOT IN ('explicit', 'reconciled')
               ), 0)
        FROM silver.cash_flow_events_current
    """).fetchone()
    coverage_pass = connection.execute("""
        SELECT count(*) FROM control.quality_results
        WHERE dataset_id='dataset.cash-transaction-event'
          AND rule_id='external-cash-flow-coverage' AND status='pass'
    """).fetchone()[0]
    calendar_exists = connection.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema='main' AND table_name='market_calendar'
    """).fetchone()[0]
    calendar = (0, None, None)
    if calendar_exists:
        calendar = connection.execute("""
            SELECT count(*), min(trade_date), max(trade_date)
            FROM main.market_calendar WHERE lower(market)='krx'
        """).fetchone()
    open_reconstruction_exceptions = connection.execute(
        "SELECT count(*) FROM control.reconstruction_exceptions_current WHERE exception_status='open'"
    ).fetchone()[0]
    blockers: list[str] = []
    if int(state[1]) < 2:
        blockers.append("insufficient_portfolio_state_history")
    if int(state[4]) > 0:
        blockers.append("non_pass_portfolio_state_rows")
    if int(coverage_pass) == 0:
        blockers.append("missing_external_cash_flow_coverage")
    if int(cash[1]) > 0:
        blockers.append("unclassified_cash_flows")
    if int(cash[3]) > 0:
        blockers.append("unsupported_non_krw_owner_flows")
    if int(cash[4]) > 0:
        blockers.append("unreconciled_internal_cash_flows")
    if int(calendar[0]) == 0:
        blockers.append("missing_krx_calendar_coverage")
    return {
        "status": "ready" if not blockers else "blocked",
        "publish_ready": not blockers,
        "blockers": blockers,
        "portfolio_state": {
            "rows": int(state[0]),
            "dates": int(state[1]),
            "slots": int(state[2]),
            "pass_rows": int(state[3]),
            "non_pass_rows": int(state[4]),
            "min_date": state[5].isoformat() if state[5] else None,
            "max_date": state[6].isoformat() if state[6] else None,
        },
        "cash_events": {
            "rows": int(cash[0]),
            "unknown": int(cash[1]),
            "external_owner": int(cash[2]),
            "unsupported_non_krw_owner": int(cash[3]),
            "unreconciled_internal": int(cash[4]),
            "passing_coverage_results": int(coverage_pass),
        },
        "krx_calendar": {
            "rows": int(calendar[0]),
            "min_date": calendar[1].isoformat() if calendar[1] else None,
            "max_date": calendar[2].isoformat() if calendar[2] else None,
        },
        "known_gaps": {
            "open_reconstruction_exceptions": int(open_reconstruction_exceptions),
        },
        "side_effects": "none",
    }


class PortfolioPerformanceEvaluator:
    def __init__(
        self,
        connection: Any,
        metric_repository: MetricWarehouseRepository | None = None,
        engine: PointInTimeMetricEngine | None = None,
    ) -> None:
        self.connection = connection
        self.metric_repository = metric_repository or MetricWarehouseRepository(connection)
        self.engine = engine or build_portfolio_performance_engine()

    def _state(self, evaluation_date: date, slot: str) -> PortfolioState | None:
        cursor = self.connection.execute(
            """
            SELECT account_id, instrument_id, aggregate_level, value_krw, as_of,
                   quality_status, lineage_hash
            FROM gold.portfolio_daily_state
            WHERE evaluation_date=? AND evaluation_slot=?
              AND aggregate_level IN ('position', 'cash')
            ORDER BY account_id, aggregate_level, instrument_id
            """,
            [evaluation_date, slot],
        )
        records = cursor.fetchall()
        if not records:
            return None
        as_of_values = {record[4] for record in records}
        as_of = max(as_of_values)
        accounts = frozenset(str(record[0]) for record in records)
        components: dict[str, Decimal] = {}
        lineage_parts: dict[str, list[str]] = {}
        rows: list[MetricInput] = []
        non_pass = sorted({str(record[5]) for record in records if str(record[5]) != "pass"})
        for account_id, instrument_id, level, value, row_as_of, quality, lineage in records:
            component_id = f"{level}|{instrument_id}"
            components[component_id] = components.get(component_id, Decimal("0")) + Decimal(str(value))
            lineage_parts.setdefault(component_id, []).append(str(lineage))
            rows.append(MetricInput(
                ref=f"evidence=state-row|{evaluation_date.isoformat()}|{slot}|{_hash(account_id, component_id)}",
                value=Decimal(str(value)),
                effective_at=row_as_of,
                knowledge_at=row_as_of,
                quality_status=str(quality),
                lineage_hash=str(lineage),
            ))
        quality_status = None
        if len(as_of_values) != 1:
            quality_status = "mixed_state_cutoff"
        elif non_pass:
            quality_status = "input_quality_" + "_".join(non_pass)
        return PortfolioState(
            evaluation_date,
            slot,
            as_of,
            accounts,
            components,
            {key: _hash("component", key, *sorted(values)) for key, values in lineage_parts.items()},
            tuple(rows),
            quality_status,
        )

    def _required_accounts(self, as_of: datetime) -> frozenset[str]:
        return frozenset(str(row[0]) for row in self.connection.execute(
            """
            SELECT account_id FROM silver.accounts
            WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?)
            ORDER BY account_id
            """,
            [as_of, as_of],
        ).fetchall())

    def _calendar_quality(self, prior_date: date, current_date: date) -> str | None:
        exists = self.connection.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema='main' AND table_name='market_calendar'
            """
        ).fetchone()[0]
        if not exists:
            return "missing_market_calendar"
        expected_days = (current_date - prior_date).days
        if expected_days <= 0:
            return "invalid_state_order"
        rows = self.connection.execute(
            """
            SELECT trade_date, is_open FROM main.market_calendar
            WHERE lower(market)='krx' AND trade_date>? AND trade_date<=?
            ORDER BY trade_date
            """,
            [prior_date, current_date],
        ).fetchall()
        if len(rows) != expected_days:
            return "missing_market_calendar_coverage"
        open_dates = [row[0] for row in rows if row[1]]
        if open_dates != [current_date]:
            return "non_contiguous_state"
        return None

    def _cash_coverage(
        self,
        *,
        run_id: str,
        start_at: datetime,
        end_at: datetime,
        accounts: frozenset[str],
    ) -> tuple[MetricInput | None, str | None]:
        row = self.connection.execute(
            """
            SELECT quality_result_id, status, details, evaluated_at
            FROM control.quality_results
            WHERE run_id=? AND dataset_id='dataset.cash-transaction-event'
              AND rule_id='external-cash-flow-coverage' AND evaluated_at<=?
            ORDER BY evaluated_at DESC, quality_result_id DESC LIMIT 1
            """,
            [run_id, end_at],
        ).fetchone()
        if not row:
            return None, "missing_cash_flow_coverage"
        quality_id, status, details_raw, evaluated_at = row
        details = _parse_json(details_raw)
        if status != "pass":
            return None, "cash_flow_coverage_non_pass"
        try:
            covered_start = _parse_datetime(details["coverage_start"])
            covered_end = _parse_datetime(details["coverage_end"])
            account_count = int(details["account_count"])
            scope_hash = str(details["account_scope_hash"])
        except (KeyError, TypeError, ValueError):
            return None, "invalid_cash_flow_coverage"
        if covered_start > start_at or covered_end < end_at:
            return None, "cash_flow_coverage_range_mismatch"
        if account_count != len(accounts) or scope_hash != performance_account_scope_hash(accounts):
            return None, "cash_flow_coverage_scope_mismatch"
        return MetricInput(
            ref=f"evidence=cash-flow-coverage|{quality_id}",
            value=Decimal("0"),
            effective_at=end_at,
            knowledge_at=evaluated_at,
            quality_status="pass",
            lineage_hash=_hash(quality_id, status, json.dumps(details, sort_keys=True)),
        ), None

    def _cash_flows(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[tuple[ExternalFlow, ...], str | None]:
        rows = self.connection.execute(
            """
            WITH revisions AS (
                SELECT * FROM silver.cash_flow_event_revisions
                WHERE knowledge_at<=?
                QUALIFY row_number() OVER (
                    PARTITION BY cash_flow_event_id
                    ORDER BY knowledge_at DESC, revision DESC, cash_flow_event_revision_id DESC
                )=1
            )
            SELECT events.cash_flow_event_id, events.account_id, revisions.event_type,
                   events.effective_at, events.amount, events.currency,
                   events.knowledge_at, events.quality_status,
                   revisions.cash_flow_event_revision_id, revisions.revision,
                   revisions.knowledge_at, revisions.link_quality, revisions.quality_status,
                   events.source_observation_id
            FROM silver.cash_flow_events events
            JOIN revisions USING(cash_flow_event_id)
            WHERE events.effective_at>? AND events.effective_at<=?
              AND events.knowledge_at<=?
            ORDER BY events.effective_at, events.cash_flow_event_id
            """,
            [end_at, start_at, end_at, end_at],
        ).fetchall()
        flows: list[ExternalFlow] = []
        for row in rows:
            (
                event_id, account_id, event_type, effective_at, amount, currency,
                event_knowledge_at, event_quality, revision_id, revision,
                classification_knowledge_at, link_quality, classification_quality,
                source_observation_id,
            ) = row
            if event_quality != "pass" or classification_quality != "pass":
                return (), "cash_flow_input_quality"
            if event_type == "unknown":
                return (), "unclassified_cash_flow"
            if event_type in LINKED_INTERNAL_FLOW_TYPES and link_quality not in {"explicit", "reconciled"}:
                return (), "unreconciled_internal_cash_flow"
            if event_type not in EXTERNAL_FLOW_TYPES:
                continue
            amount_decimal = Decimal(str(amount))
            if event_type == "owner_deposit" and amount_decimal < 0:
                return (), "invalid_owner_flow_sign"
            if event_type == "owner_withdrawal" and amount_decimal > 0:
                return (), "invalid_owner_flow_sign"
            if currency != "KRW":
                return (), "unsupported_cash_flow_currency"
            flows.append(ExternalFlow(
                str(event_id),
                "cash|cash|KRW",
                amount_decimal,
                effective_at,
                max(event_knowledge_at, classification_knowledge_at),
                _hash(event_id, revision_id, revision, source_observation_id),
            ))
        return tuple(flows), None

    @staticmethod
    def _aggregate_input(
        role: str,
        value: Decimal,
        state: PortfolioState,
        lineage_hash: str,
        suffix: str,
    ) -> MetricInput:
        return MetricInput(
            ref=f"role={role}|{suffix}",
            value=value,
            effective_at=state.as_of,
            knowledge_at=state.as_of,
            quality_status="pass",
            lineage_hash=lineage_hash,
        )

    def _unavailable_values(
        self,
        *,
        quality_status: str,
        evaluation_at: datetime,
        evaluation_slot: str,
        evaluation_run_id: str,
        component_ids: tuple[str, ...],
        inputs: tuple[MetricInput, ...],
        chain_state: PerformanceChainState,
    ) -> PerformancePeriodOutcome:
        values = [self.engine.unavailable(
            metric_id=metric_id,
            version=METRIC_VERSION,
            subject_type="portfolio",
            subject_id=PORTFOLIO_SUBJECT_ID,
            evaluation_at=evaluation_at,
            evaluation_slot=evaluation_slot,
            quality_status=quality_status,
            inputs=inputs,
            evaluation_run_id=evaluation_run_id,
        ) for metric_id in (RETURN_METRIC, RESIDUAL_METRIC)]
        values.extend(self.engine.unavailable(
            metric_id=CONTRIBUTION_METRIC,
            version=METRIC_VERSION,
            subject_type="portfolio_component",
            subject_id=component_id,
            evaluation_at=evaluation_at,
            evaluation_slot=evaluation_slot,
            quality_status=quality_status,
            inputs=inputs,
            evaluation_run_id=evaluation_run_id,
        ) for component_id in component_ids)
        chain_quality = quality_status if chain_state.available else "chain_gap"
        values.extend(self.engine.unavailable(
            metric_id=metric_id,
            version=METRIC_VERSION,
            subject_type="portfolio",
            subject_id=PORTFOLIO_SUBJECT_ID,
            evaluation_at=evaluation_at,
            evaluation_slot=evaluation_slot,
            quality_status=chain_quality,
            inputs=inputs,
            evaluation_run_id=evaluation_run_id,
        ) for metric_id in (WEALTH_METRIC, DRAWDOWN_METRIC))
        self._write_atomic(tuple(values))
        return PerformancePeriodOutcome(
            quality_status,
            tuple(values),
            PerformanceChainState(False, chain_state.wealth_index, chain_state.high_water, chain_state.wealth_lineage_hash),
        )

    def _write_atomic(self, values: tuple[MetricValue, ...]) -> None:
        self.connection.execute("BEGIN TRANSACTION")
        try:
            for value in values:
                self.metric_repository.write_value(value)
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

    def evaluate_period_and_store(
        self,
        *,
        prior_date: date,
        current_date: date,
        evaluation_slot: str,
        cash_coverage_run_id: str,
        evaluation_run_id: str,
        chain_state: PerformanceChainState = PerformanceChainState(),
    ) -> PerformancePeriodOutcome:
        prior = self._state(prior_date, evaluation_slot)
        current = self._state(current_date, evaluation_slot)
        state_cutoffs = tuple(state.as_of for state in (prior, current) if state is not None)
        fallback_at = max(state_cutoffs) if state_cutoffs else None
        if fallback_at is None:
            raise ValueError("at least one portfolio state is required to persist a period outcome")
        component_ids = tuple(sorted(set((prior.components if prior else {})) | set((current.components if current else {}))))
        evidence_inputs = tuple((prior.rows if prior else ()) + (current.rows if current else ()))
        quality_status: str | None = None
        if prior is None:
            quality_status = "insufficient_history"
        elif current is None:
            quality_status = "missing_current_state"
        elif prior.quality_status:
            quality_status = prior.quality_status
        elif current.quality_status:
            quality_status = current.quality_status
        else:
            prior_required = self._required_accounts(prior.as_of)
            current_required = self._required_accounts(current.as_of)
            if not prior_required or prior.accounts != prior_required:
                quality_status = "prior_account_coverage_mismatch"
            elif not current_required or current.accounts != current_required:
                quality_status = "current_account_coverage_mismatch"
            elif prior.accounts != current.accounts:
                quality_status = "account_coverage_changed"
            else:
                quality_status = self._calendar_quality(prior_date, current_date)
        if quality_status:
            return self._unavailable_values(
                quality_status=quality_status,
                evaluation_at=fallback_at,
                evaluation_slot=evaluation_slot,
                evaluation_run_id=evaluation_run_id,
                component_ids=component_ids,
                inputs=evidence_inputs,
                chain_state=chain_state,
            )
        assert prior is not None and current is not None
        if current.as_of <= prior.as_of:
            return self._unavailable_values(
                quality_status="invalid_state_order",
                evaluation_at=fallback_at,
                evaluation_slot=evaluation_slot,
                evaluation_run_id=evaluation_run_id,
                component_ids=component_ids,
                inputs=evidence_inputs,
                chain_state=chain_state,
            )
        coverage_input, coverage_error = self._cash_coverage(
            run_id=cash_coverage_run_id,
            start_at=prior.as_of,
            end_at=current.as_of,
            accounts=current.accounts,
        )
        flows, flow_error = self._cash_flows(start_at=prior.as_of, end_at=current.as_of)
        quality_status = coverage_error or flow_error
        if quality_status:
            return self._unavailable_values(
                quality_status=quality_status,
                evaluation_at=current.as_of,
                evaluation_slot=evaluation_slot,
                evaluation_run_id=evaluation_run_id,
                component_ids=component_ids,
                inputs=evidence_inputs,
                chain_state=chain_state,
            )
        assert coverage_input is not None
        period_seconds = Decimal(str((current.as_of - prior.as_of).total_seconds()))
        if period_seconds <= 0:
            return self._unavailable_values(
                quality_status="invalid_state_order",
                evaluation_at=current.as_of,
                evaluation_slot=evaluation_slot,
                evaluation_run_id=evaluation_run_id,
                component_ids=component_ids,
                inputs=evidence_inputs,
                chain_state=chain_state,
            )
        beginning_total = sum(prior.components.values(), Decimal("0"))
        ending_total = sum(current.components.values(), Decimal("0"))
        beginning_lineage = _hash("beginning", *sorted(prior.component_lineage.values()))
        ending_lineage = _hash("ending", *sorted(current.component_lineage.values()))
        return_inputs: list[MetricInput] = [
            self._aggregate_input("beginning_value", beginning_total, prior, beginning_lineage, "portfolio"),
            self._aggregate_input("ending_value", ending_total, current, ending_lineage, "portfolio"),
            coverage_input,
        ]
        weighted_flow_total = Decimal("0")
        for flow in flows:
            weight = Decimal(str((current.as_of - flow.effective_at).total_seconds())) / period_seconds
            weighted = flow.amount_krw * weight
            weighted_flow_total += weighted
            return_inputs.extend((
                MetricInput(
                    f"role=external_flow|{flow.event_id}", flow.amount_krw,
                    flow.effective_at, flow.knowledge_at, "pass", flow.lineage_hash,
                ),
                MetricInput(
                    f"role=weighted_external_flow|{flow.event_id}", weighted,
                    flow.effective_at, flow.knowledge_at, "pass", _hash(flow.lineage_hash, weight),
                ),
            ))
        denominator = beginning_total + weighted_flow_total
        if denominator == 0:
            return self._unavailable_values(
                quality_status="zero_denominator",
                evaluation_at=current.as_of,
                evaluation_slot=evaluation_slot,
                evaluation_run_id=evaluation_run_id,
                component_ids=component_ids,
                inputs=tuple(return_inputs),
                chain_state=chain_state,
            )
        portfolio_return = self.engine.evaluate(
            metric_id=RETURN_METRIC,
            version=METRIC_VERSION,
            subject_type="portfolio",
            subject_id=PORTFOLIO_SUBJECT_ID,
            evaluation_at=current.as_of,
            evaluation_slot=evaluation_slot,
            inputs=tuple(return_inputs),
            evaluation_run_id=evaluation_run_id,
        )
        contributions: list[MetricValue] = []
        flow_by_component: dict[str, list[ExternalFlow]] = {}
        for flow in flows:
            flow_by_component.setdefault(flow.component_id, []).append(flow)
        for component_id in component_ids:
            component_inputs = [
                MetricInput(
                    f"role=component_beginning_value|{component_id}",
                    prior.components.get(component_id, Decimal("0")), prior.as_of, prior.as_of, "pass",
                    prior.component_lineage.get(component_id, _hash("missing-prior", component_id)),
                ),
                MetricInput(
                    f"role=component_ending_value|{component_id}",
                    current.components.get(component_id, Decimal("0")), current.as_of, current.as_of, "pass",
                    current.component_lineage.get(component_id, _hash("missing-current", component_id)),
                ),
                MetricInput(
                    f"role=portfolio_denominator|{component_id}", denominator,
                    current.as_of, current.as_of, "pass", _hash("dietz-denominator", denominator),
                ),
            ]
            for flow in flow_by_component.get(component_id, []):
                component_inputs.append(MetricInput(
                    f"role=component_external_flow|{flow.event_id}", flow.amount_krw,
                    flow.effective_at, flow.knowledge_at, "pass", flow.lineage_hash,
                ))
            contributions.append(self.engine.evaluate(
                metric_id=CONTRIBUTION_METRIC,
                version=METRIC_VERSION,
                subject_type="portfolio_component",
                subject_id=component_id,
                evaluation_at=current.as_of,
                evaluation_slot=evaluation_slot,
                inputs=tuple(component_inputs),
                evaluation_run_id=evaluation_run_id,
            ))
        residual_inputs = [MetricInput(
            "role=portfolio_return|owner", portfolio_return.value or Decimal("0"),
            current.as_of, current.as_of, "pass", portfolio_return.lineage_hash,
        )]
        residual_inputs.extend(MetricInput(
            f"role=component_contribution|{value.subject_id}", value.value or Decimal("0"),
            current.as_of, current.as_of, "pass", value.lineage_hash,
        ) for value in contributions)
        residual = self.engine.evaluate(
            metric_id=RESIDUAL_METRIC,
            version=METRIC_VERSION,
            subject_type="portfolio",
            subject_id=PORTFOLIO_SUBJECT_ID,
            evaluation_at=current.as_of,
            evaluation_slot=evaluation_slot,
            inputs=tuple(residual_inputs),
            evaluation_run_id=evaluation_run_id,
        )
        if residual.value is None or abs(residual.value) > RECONCILIATION_TOLERANCE:
            return self._unavailable_values(
                quality_status="contribution_reconciliation_failed",
                evaluation_at=current.as_of,
                evaluation_slot=evaluation_slot,
                evaluation_run_id=evaluation_run_id,
                component_ids=component_ids,
                inputs=tuple(return_inputs),
                chain_state=chain_state,
            )
        if chain_state.available:
            wealth_inputs = (
                MetricInput(
                    "role=prior_wealth|owner", chain_state.wealth_index,
                    prior.as_of, prior.as_of, "pass", chain_state.wealth_lineage_hash,
                ),
                MetricInput(
                    "role=period_return|owner", portfolio_return.value or Decimal("0"),
                    current.as_of, current.as_of, "pass", portfolio_return.lineage_hash,
                ),
            )
            wealth = self.engine.evaluate(
                metric_id=WEALTH_METRIC,
                version=METRIC_VERSION,
                subject_type="portfolio",
                subject_id=PORTFOLIO_SUBJECT_ID,
                evaluation_at=current.as_of,
                evaluation_slot=evaluation_slot,
                inputs=wealth_inputs,
                evaluation_run_id=evaluation_run_id,
            )
            high_water = max(chain_state.high_water, wealth.value or Decimal("0"))
            drawdown = self.engine.evaluate(
                metric_id=DRAWDOWN_METRIC,
                version=METRIC_VERSION,
                subject_type="portfolio",
                subject_id=PORTFOLIO_SUBJECT_ID,
                evaluation_at=current.as_of,
                evaluation_slot=evaluation_slot,
                inputs=(
                    MetricInput(
                        "role=wealth|owner", wealth.value or Decimal("0"),
                        current.as_of, current.as_of, "pass", wealth.lineage_hash,
                    ),
                    MetricInput(
                        "role=high_water|owner", high_water,
                        current.as_of, current.as_of, "pass", _hash("wealth-high-water", high_water),
                    ),
                ),
                evaluation_run_id=evaluation_run_id,
            )
            next_chain = PerformanceChainState(True, wealth.value or Decimal("0"), high_water, wealth.lineage_hash)
        else:
            wealth = self.engine.unavailable(
                metric_id=WEALTH_METRIC, version=METRIC_VERSION,
                subject_type="portfolio", subject_id=PORTFOLIO_SUBJECT_ID,
                evaluation_at=current.as_of, evaluation_slot=evaluation_slot,
                quality_status="chain_gap", inputs=(MetricInput(
                    "evidence=period-return|owner", portfolio_return.value or Decimal("0"),
                    current.as_of, current.as_of, "pass", portfolio_return.lineage_hash,
                ),), evaluation_run_id=evaluation_run_id,
            )
            drawdown = self.engine.unavailable(
                metric_id=DRAWDOWN_METRIC, version=METRIC_VERSION,
                subject_type="portfolio", subject_id=PORTFOLIO_SUBJECT_ID,
                evaluation_at=current.as_of, evaluation_slot=evaluation_slot,
                quality_status="chain_gap", inputs=(MetricInput(
                    "evidence=wealth-chain-gap|owner", Decimal("0"),
                    current.as_of, current.as_of, "pass", wealth.lineage_hash,
                ),), evaluation_run_id=evaluation_run_id,
            )
            next_chain = chain_state
        values = (portfolio_return, *contributions, residual, wealth, drawdown)
        self._write_atomic(values)
        return PerformancePeriodOutcome("pass", values, next_chain)

    def evaluate_history_and_store(
        self,
        *,
        evaluation_slot: str,
        cash_coverage_run_id: str,
        evaluation_run_id: str,
    ) -> tuple[PerformancePeriodOutcome, ...]:
        dates = [row[0] for row in self.connection.execute(
            """
            SELECT DISTINCT evaluation_date FROM gold.portfolio_daily_state
            WHERE evaluation_slot=? ORDER BY evaluation_date
            """,
            [evaluation_slot],
        ).fetchall()]
        outcomes: list[PerformancePeriodOutcome] = []
        chain = PerformanceChainState()
        for prior_date, current_date in zip(dates[:-1], dates[1:], strict=True):
            outcome = self.evaluate_period_and_store(
                prior_date=prior_date,
                current_date=current_date,
                evaluation_slot=evaluation_slot,
                cash_coverage_run_id=cash_coverage_run_id,
                evaluation_run_id=evaluation_run_id,
                chain_state=chain,
            )
            outcomes.append(outcome)
            chain = outcome.chain_state
        return tuple(outcomes)
