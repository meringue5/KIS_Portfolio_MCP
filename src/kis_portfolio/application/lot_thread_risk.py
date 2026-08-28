"""Point-in-time lot path, episode path and owner-stop risk evaluation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from kis_portfolio.adapters.outbound.metric_warehouse import MetricWarehouseRepository
from kis_portfolio.adapters.outbound.thread_risk_review_warehouse import ThreadRiskReviewWarehouse
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.modules.monitoring import (
    MetricFormulaRegistry,
    MetricInput,
    MetricValue,
    PointInTimeMetricEngine,
    register_lot_thread_risk_formulas,
)
from kis_portfolio.platform.metric_contracts import load_metric_registry


LOT_MFE = "metric.lot-mfe-adjusted-price"
LOT_MAE = "metric.lot-mae-adjusted-price"
EPISODE_HIGH = "metric.position-episode-high-adjusted-price"
EPISODE_DRAWDOWN = "metric.position-episode-drawdown-adjusted-price"
THREAD_PLANNED_LOSS = "metric.thread-planned-loss-krw"
THREAD_RISK_RATIO = "metric.thread-risk-ratio"
INSTRUMENT_PLANNED_LOSS = "metric.instrument-planned-loss-krw"
INSTRUMENT_RISK_RATIO = "metric.instrument-risk-ratio"
METRIC_VERSION = "1.0.0"


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class EpisodeFact:
    episode_id: str
    account_id: str
    instrument_id: str
    opened_at: datetime
    closed_at: datetime | None
    current_quantity: Decimal
    knowledge_at: datetime
    reconstruction_status: str
    lineage_hash: str


@dataclass(frozen=True, slots=True)
class LotFact:
    lot_id: str
    episode_id: str
    account_id: str
    instrument_id: str
    opened_at: datetime
    remaining_quantity: Decimal
    unit_cost: Decimal | None
    currency: str
    effective_at: datetime
    knowledge_at: datetime
    reconstruction_status: str
    quality_status: str
    lineage_hash: str


def build_lot_thread_risk_engine() -> PointInTimeMetricEngine:
    formulas = MetricFormulaRegistry()
    register_lot_thread_risk_formulas(formulas)
    return PointInTimeMetricEngine(load_metric_registry(), formulas)


def inspect_lot_thread_risk_readiness(connection: Any) -> dict[str, object]:
    """Return aggregate-only W0504 publish readiness without writes or identities."""
    required_objects = {
        ("silver", "position_episodes_current"),
        ("silver", "purchase_lot_states_current"),
        ("silver", "trade_thread_risk_plans_current"),
        ("silver", "price_bar_revisions_daily"),
        ("gold", "portfolio_daily_state"),
    }
    existing = {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            """
            SELECT table_schema,table_name FROM information_schema.tables
            WHERE table_catalog=current_database()
              AND table_schema IN ('silver','gold','control')
            """
        ).fetchall()
    }
    missing = sorted(f"{schema}.{name}" for schema, name in required_objects - existing)
    zero_pair = (0, 0)
    episodes = zero_pair
    lots = (0, 0, 0)
    links = (0, 0, 0)
    plans = 0
    prices = zero_pair
    state = (0, 0, 0, 0)
    open_exceptions = 0
    if ("silver", "position_episodes_current") in existing:
        episodes = connection.execute(
            """
            SELECT count(*),coalesce(count_if(
                reconstruction_status='reconstructed' AND current_quantity>0
            ),0) FROM silver.position_episodes_current
            """
        ).fetchone()
    if ("silver", "purchase_lot_states_current") in existing:
        lots = connection.execute(
            """
            SELECT count(*),coalesce(count_if(
                reconstruction_status='reconstructed' AND quality_status='pass'
            ),0),coalesce(count_if(remaining_quantity>0),0)
            FROM silver.purchase_lot_states_current
            """
        ).fetchone()
    if (
        ("silver", "purchase_lot_states_current") in existing
        and ("silver", "trade_thread_lots") in existing
    ):
        links = connection.execute(
            """
            WITH latest_links AS (
                SELECT lot_id,count(*) link_count
                FROM silver.trade_thread_lots links
                WHERE allocation_revision=(
                    SELECT max(candidate.allocation_revision)
                    FROM silver.trade_thread_lots candidate
                    WHERE candidate.lot_id=links.lot_id
                )
                GROUP BY lot_id
            )
            SELECT count(*),coalesce(count_if(coalesce(link_count,0)=1),0),
                   count(DISTINCT CASE WHEN link_count=1 THEN thread_id END)
            FROM silver.purchase_lot_states_current lots
            LEFT JOIN (
                SELECT counted.lot_id,counted.link_count,min(links.thread_id) thread_id
                FROM latest_links counted
                JOIN silver.trade_thread_lots links USING(lot_id)
                WHERE links.allocation_revision=(
                    SELECT max(candidate.allocation_revision)
                    FROM silver.trade_thread_lots candidate
                    WHERE candidate.lot_id=links.lot_id
                )
                GROUP BY counted.lot_id,counted.link_count
            ) selected USING(lot_id)
            WHERE remaining_quantity>0
            """
        ).fetchone()
    if ("silver", "trade_thread_risk_plans_current") in existing:
        plans = connection.execute(
            "SELECT count(*) FROM silver.trade_thread_risk_plans_current"
        ).fetchone()[0]
    if ("silver", "price_bar_revisions_daily") in existing:
        prices = connection.execute(
            """
            SELECT count(*),count(DISTINCT instrument_id) FROM silver.price_bar_revisions_daily
            WHERE price_basis='adjusted' AND reconstruction_mode='operational_strict'
              AND quality_status='pass'
            """
        ).fetchone()
    if ("gold", "portfolio_daily_state") in existing:
        state = connection.execute(
            """
            SELECT count(*),coalesce(count_if(quality_status='pass'),0),
                   count(DISTINCT evaluation_date),
                   (SELECT count(*) FROM (
                       SELECT evaluation_date,evaluation_slot
                       FROM gold.portfolio_daily_state
                       GROUP BY evaluation_date,evaluation_slot
                       HAVING count_if(quality_status<>'pass')=0
                   ))
            FROM gold.portfolio_daily_state
            """
        ).fetchone()
    if ("control", "reconstruction_exceptions_current") in existing:
        open_exceptions = connection.execute(
            "SELECT count(*) FROM control.reconstruction_exceptions_current "
            "WHERE exception_status='open'"
        ).fetchone()[0]

    blockers: list[str] = []
    if missing:
        blockers.append("required_objects_missing")
    if int(episodes[1]) == 0:
        blockers.append("no_reconstructed_open_episodes")
    if int(lots[1]) == 0 or int(lots[2]) == 0:
        blockers.append("no_passing_open_lots")
    if int(links[0]) != int(links[1]):
        blockers.append("thread_link_coverage_incomplete")
    if int(plans) < int(links[2]):
        blockers.append("owner_risk_plan_coverage_incomplete")
    if int(prices[1]) == 0:
        blockers.append("adjusted_price_coverage_missing")
    if int(state[3]) == 0:
        blockers.append("no_fully_passing_canonical_slot")
    if int(open_exceptions) > 0:
        blockers.append("open_reconstruction_exceptions")
    return {
        "status": "ready" if not blockers else "blocked",
        "publish_ready": not blockers,
        "blockers": blockers,
        "target_objects": {
            "expected": len(required_objects),
            "present": len(required_objects) - len(missing),
            "missing_count": len(missing),
        },
        "episodes": {"rows": int(episodes[0]), "reconstructed_open": int(episodes[1])},
        "lots": {
            "rows": int(lots[0]), "reconstructed_pass": int(lots[1]), "open": int(lots[2])
        },
        "thread_links": {
            "open_lots": int(links[0]), "exactly_one": int(links[1]),
            "covered_threads": int(links[2]),
        },
        "owner_plans": {"current_rows": int(plans)},
        "adjusted_prices": {"rows": int(prices[0]), "instruments": int(prices[1])},
        "canonical_state": {
            "rows": int(state[0]), "pass_rows": int(state[1]), "dates": int(state[2]),
            "fully_passing_slots": int(state[3]),
        },
        "known_gaps": {"open_reconstruction_exceptions": int(open_exceptions)},
        "side_effects": "none",
    }


class LotThreadRiskEvaluator:
    def __init__(
        self,
        connection: Any,
        *,
        metric_repository: MetricWarehouseRepository | None = None,
        engine: PointInTimeMetricEngine | None = None,
    ) -> None:
        self.connection = connection
        self.metric_repository = metric_repository or MetricWarehouseRepository(connection)
        self.price_repository = V2WarehouseRepository(connection)
        self.plan_repository = ThreadRiskReviewWarehouse(connection)
        self.engine = engine or build_lot_thread_risk_engine()

    def _episodes(self, evaluation_at: datetime) -> tuple[EpisodeFact, ...]:
        rows = self.connection.execute(
            """
            WITH selected AS (
                SELECT * FROM silver.position_episode_revisions
                WHERE knowledge_at<=? AND reconstruction_cutoff_at<=?
                QUALIFY row_number() OVER (
                    PARTITION BY episode_id
                    ORDER BY knowledge_at DESC,revision DESC,position_episode_revision_id DESC
                )=1
            )
            SELECT identities.episode_id,identities.account_id,selected.instrument_id,
                   identities.opened_at,selected.closed_at,selected.current_quantity,
                   selected.knowledge_at,selected.reconstruction_status,
                   identities.identity_hash,selected.position_episode_revision_id
            FROM silver.position_episodes identities
            JOIN selected USING(episode_id)
            ORDER BY identities.episode_id
            """,
            [evaluation_at, evaluation_at],
        ).fetchall()
        return tuple(EpisodeFact(
            str(row[0]), str(row[1]), str(row[2]), row[3], row[4], Decimal(str(row[5])),
            row[6], str(row[7]), _hash(row[8], row[9]),
        ) for row in rows)

    def _lots(self, evaluation_at: datetime) -> tuple[LotFact, ...]:
        rows = self.connection.execute(
            """
            WITH selected AS (
                SELECT * FROM silver.purchase_lot_revisions
                WHERE knowledge_at<=? AND effective_at<=?
                QUALIFY row_number() OVER (
                    PARTITION BY lot_id
                    ORDER BY knowledge_at DESC,revision DESC,purchase_lot_revision_id DESC
                )=1
            )
            SELECT identities.lot_id,identities.episode_id,identities.account_id,
                   episodes.instrument_id,identities.opened_at,selected.remaining_quantity,
                   selected.effective_unit_cost,selected.currency,selected.effective_at,
                   selected.knowledge_at,selected.reconstruction_status,selected.quality_status,
                   identities.identity_hash,selected.revision_hash
            FROM silver.purchase_lot_identities identities
            JOIN selected USING(lot_id)
            JOIN (
                SELECT episode_id,instrument_id FROM silver.position_episode_revisions
                WHERE knowledge_at<=? AND reconstruction_cutoff_at<=?
                QUALIFY row_number() OVER (
                    PARTITION BY episode_id
                    ORDER BY knowledge_at DESC,revision DESC,position_episode_revision_id DESC
                )=1
            ) episodes USING(episode_id)
            ORDER BY identities.lot_id
            """,
            [evaluation_at, evaluation_at, evaluation_at, evaluation_at],
        ).fetchall()
        return tuple(LotFact(
            str(row[0]), str(row[1]), str(row[2]), str(row[3]), row[4], Decimal(str(row[5])),
            Decimal(str(row[6])) if row[6] is not None else None, str(row[7]), row[8], row[9],
            str(row[10]), str(row[11]), _hash(row[12], row[13]),
        ) for row in rows)

    def _thread_links(self, evaluation_at: datetime) -> dict[str, tuple[str, ...]]:
        rows = self.connection.execute(
            """
            WITH maximum AS (
                SELECT lot_id,max(allocation_revision) AS revision
                FROM silver.trade_thread_lots WHERE linked_at<=? GROUP BY lot_id
            )
            SELECT links.lot_id,links.thread_id
            FROM silver.trade_thread_lots links
            JOIN maximum ON maximum.lot_id=links.lot_id
                        AND maximum.revision=links.allocation_revision
            WHERE links.linked_at<=?
            ORDER BY links.lot_id,links.thread_id
            """,
            [evaluation_at, evaluation_at],
        ).fetchall()
        result: dict[str, list[str]] = {}
        for lot_id, thread_id in rows:
            result.setdefault(str(lot_id), []).append(str(thread_id))
        return {key: tuple(values) for key, values in result.items()}

    def _portfolio_state(
        self,
        evaluation_at: datetime,
        evaluation_slot: str,
    ) -> tuple[str | None, Decimal, MetricInput | None, dict[tuple[str, str], Decimal]]:
        rows = self.connection.execute(
            """
            SELECT account_id,instrument_id,aggregate_level,quantity,value_krw,as_of,
                   quality_status,lineage_hash
            FROM gold.portfolio_daily_state
            WHERE evaluation_date=? AND evaluation_slot=?
            ORDER BY account_id,aggregate_level,instrument_id
            """,
            [evaluation_at.date(), evaluation_slot],
        ).fetchall()
        if not rows:
            return "missing_portfolio_state", Decimal("0"), None, {}
        as_of_values = {row[5] for row in rows}
        state_at = max(as_of_values)
        total = sum((Decimal(str(row[4])) for row in rows), Decimal("0"))
        lineage = _hash("portfolio-state", *sorted(str(row[7]) for row in rows))
        total_input = MetricInput(
            "role=total_assets|portfolio", total, state_at, state_at, "pass", lineage
        )
        if state_at > evaluation_at:
            return "future_portfolio_state", total, total_input, {}
        if len(as_of_values) != 1:
            return "mixed_portfolio_state_cutoff", total, total_input, {}
        non_pass = sorted({str(row[6]) for row in rows if str(row[6]) != "pass"})
        if non_pass:
            return "portfolio_state_non_pass", total, total_input, {}
        state_accounts = {str(row[0]) for row in rows}
        required_accounts = {str(row[0]) for row in self.connection.execute(
            """
            SELECT account_id FROM silver.accounts
            WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?)
            """,
            [state_at, state_at],
        ).fetchall()}
        if not required_accounts or state_accounts != required_accounts:
            return "portfolio_account_coverage_mismatch", total, total_input, {}
        if total <= 0:
            return "non_positive_total_assets", total, total_input, {}
        quantities: dict[tuple[str, str], Decimal] = {}
        for account_id, instrument_id, level, quantity, *_rest in rows:
            if level == "position" and quantity is not None:
                key = (str(account_id), str(instrument_id))
                quantities[key] = quantities.get(key, Decimal("0")) + Decimal(str(quantity))
        return None, total, total_input, quantities

    def _base_quality(
        self,
        episodes: tuple[EpisodeFact, ...],
        lots: tuple[LotFact, ...],
        links: dict[str, tuple[str, ...]],
        state_quantities: dict[tuple[str, str], Decimal],
    ) -> str | None:
        if any(item.reconstruction_status != "reconstructed" for item in episodes):
            return "episode_reconstruction_non_pass"
        if any(
            item.reconstruction_status != "reconstructed" or item.quality_status != "pass"
            for item in lots
        ):
            return "lot_reconstruction_non_pass"
        episode_quantities: dict[str, Decimal] = {}
        open_scope_quantities: dict[tuple[str, str], Decimal] = {}
        episode_by_id = {item.episode_id: item for item in episodes}
        for lot in lots:
            episode_quantities[lot.episode_id] = (
                episode_quantities.get(lot.episode_id, Decimal("0")) + lot.remaining_quantity
            )
        for episode in episodes:
            if episode_quantities.get(episode.episode_id, Decimal("0")) != episode.current_quantity:
                return "lot_quantity_reconciliation_failed"
            if episode.current_quantity > 0:
                key = (episode.account_id, episode.instrument_id)
                open_scope_quantities[key] = open_scope_quantities.get(key, Decimal("0")) + episode.current_quantity
        if open_scope_quantities != state_quantities:
            return "canonical_position_quantity_mismatch"
        for lot in lots:
            if lot.remaining_quantity > 0 and len(links.get(lot.lot_id, ())) != 1:
                return "thread_link_coverage_mismatch"
            if lot.episode_id not in episode_by_id:
                return "lot_episode_missing"
        return None

    @staticmethod
    def _fact_input(role: str, subject_id: str, fact: LotFact | EpisodeFact, value: Decimal) -> MetricInput:
        effective = fact.effective_at if isinstance(fact, LotFact) else fact.opened_at
        return MetricInput(
            f"role={role}|{subject_id}", value, effective, fact.knowledge_at,
            "pass", fact.lineage_hash,
        )

    @staticmethod
    def _bar_input(role: str, instrument_id: str, bar: dict[str, Any], value: object) -> MetricInput:
        return MetricInput(
            f"role={role}|{instrument_id}|{bar['session_date']}|{bar['revision_hash']}",
            Decimal(str(value)), bar["effective_at"], bar["knowledge_at"],
            str(bar["quality_status"]), str(bar["revision_hash"]),
        )

    def _bars(
        self,
        instrument_id: str,
        start_at: datetime,
        end_at: datetime,
        evaluation_at: datetime,
    ) -> tuple[list[dict[str, Any]], str | None]:
        bars = self.price_repository.get_price_bars_as_of(
            instrument_id=instrument_id,
            start_date=start_at.date(),
            end_date=end_at.date(),
            price_basis="adjusted",
            evaluation_at=evaluation_at,
            replay_mode="operational_strict",
        )
        if not bars:
            return [], "missing_adjusted_price_path"
        if any(item["reconstruction_mode"] != "operational_strict" for item in bars):
            return bars, "retrospective_price_path"
        if any(item["quality_status"] != "pass" for item in bars):
            return bars, "price_path_non_pass"
        if any(item["high"] is None or item["low"] is None or item["close"] is None for item in bars):
            return bars, "missing_price_path_field"
        return bars, None

    def _fx_input(self, currency: str, evaluation_at: datetime) -> tuple[MetricInput | None, str | None]:
        if currency == "KRW":
            return MetricInput(
                "role=fx_rate|KRW", Decimal("1"), evaluation_at, evaluation_at,
                "pass", _hash("fx", "KRW", "1"),
            ), None
        row = self.connection.execute(
            """
            SELECT rates.rate,rates.rate_date,rates.quality_status,observations.fetched_at,
                   rates.source_observation_id
            FROM silver.fx_rates_daily rates
            JOIN bronze.source_observations observations
              ON observations.observation_id=rates.source_observation_id
            WHERE rates.base_currency=? AND rates.quote_currency='KRW'
              AND rates.rate_type='close' AND rates.rate_date<=?
              AND observations.fetched_at<=?
            ORDER BY rates.rate_date DESC,observations.fetched_at DESC LIMIT 1
            """,
            [currency, evaluation_at.date(), evaluation_at],
        ).fetchone()
        if row is None:
            return None, "missing_point_in_time_fx"
        rate, rate_date, quality, fetched_at, observation_id = row
        if quality != "pass":
            return None, "fx_non_pass"
        return MetricInput(
            f"role=fx_rate|{currency}|{rate_date}", Decimal(str(rate)), fetched_at,
            fetched_at, "pass", _hash("fx", observation_id, rate),
        ), None

    def _unavailable(
        self,
        metric_id: str,
        subject_type: str,
        subject_id: str,
        evaluation_at: datetime,
        evaluation_slot: str,
        evaluation_run_id: str,
        quality_status: str,
        inputs: tuple[MetricInput, ...] = (),
    ) -> MetricValue:
        return self.engine.unavailable(
            metric_id=metric_id, version=METRIC_VERSION, subject_type=subject_type,
            subject_id=subject_id, evaluation_at=evaluation_at,
            evaluation_slot=evaluation_slot, quality_status=quality_status,
            inputs=inputs, evaluation_run_id=evaluation_run_id,
        )

    def _evaluate(
        self,
        metric_id: str,
        subject_type: str,
        subject_id: str,
        evaluation_at: datetime,
        evaluation_slot: str,
        evaluation_run_id: str,
        inputs: tuple[MetricInput, ...],
    ) -> MetricValue:
        return self.engine.evaluate(
            metric_id=metric_id, version=METRIC_VERSION, subject_type=subject_type,
            subject_id=subject_id, evaluation_at=evaluation_at,
            evaluation_slot=evaluation_slot, inputs=inputs,
            evaluation_run_id=evaluation_run_id,
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

    def evaluate_and_store(
        self,
        *,
        evaluation_at: datetime,
        evaluation_slot: str,
        evaluation_run_id: str,
    ) -> tuple[MetricValue, ...]:
        if evaluation_at.tzinfo is None:
            raise ValueError("evaluation_at must be timezone-aware")
        episodes = self._episodes(evaluation_at)
        lots = self._lots(evaluation_at)
        links = self._thread_links(evaluation_at)
        state_quality, _total_assets, total_input, state_quantities = self._portfolio_state(
            evaluation_at, evaluation_slot
        )
        base_quality = state_quality or self._base_quality(episodes, lots, links, state_quantities)
        episode_by_id = {item.episode_id: item for item in episodes}
        values: list[MetricValue] = []

        for lot in lots:
            episode = episode_by_id[lot.episode_id]
            path_end = min(
                evaluation_at,
                episode.closed_at or evaluation_at,
                lot.effective_at if lot.remaining_quantity == 0 else evaluation_at,
            )
            bars, path_quality = self._bars(
                lot.instrument_id, lot.opened_at, path_end, evaluation_at
            )
            quality = base_quality or path_quality or ("missing_lot_unit_cost" if lot.unit_cost is None else None)
            evidence = (self._fact_input(
                "entry_price", lot.lot_id, lot, lot.unit_cost or Decimal("0")
            ),)
            high_inputs = evidence + tuple(
                self._bar_input("path_high", lot.instrument_id, bar, bar["high"]) for bar in bars
            )
            low_inputs = evidence + tuple(
                self._bar_input("path_low", lot.instrument_id, bar, bar["low"]) for bar in bars
            )
            for metric_id, metric_inputs in ((LOT_MFE, high_inputs), (LOT_MAE, low_inputs)):
                values.append(
                    self._unavailable(
                        metric_id, "purchase_lot", lot.lot_id, evaluation_at, evaluation_slot,
                        evaluation_run_id, quality, metric_inputs,
                    ) if quality else self._evaluate(
                        metric_id, "purchase_lot", lot.lot_id, evaluation_at, evaluation_slot,
                        evaluation_run_id, metric_inputs,
                    )
                )

        for episode in episodes:
            path_end = min(evaluation_at, episode.closed_at or evaluation_at)
            bars, path_quality = self._bars(
                episode.instrument_id, episode.opened_at, path_end, evaluation_at
            )
            quality = base_quality or path_quality
            high_inputs = tuple(
                self._bar_input("path_high", episode.instrument_id, bar, bar["high"]) for bar in bars
            )
            if quality:
                high = self._unavailable(
                    EPISODE_HIGH, "position_episode", episode.episode_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, quality, high_inputs,
                )
                drawdown_inputs = high_inputs
                drawdown = self._unavailable(
                    EPISODE_DRAWDOWN, "position_episode", episode.episode_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, quality, drawdown_inputs,
                )
            else:
                high = self._evaluate(
                    EPISODE_HIGH, "position_episode", episode.episode_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, high_inputs,
                )
                last = bars[-1]
                drawdown_inputs = (
                    self._bar_input("current_close", episode.instrument_id, last, last["close"]),
                    MetricInput(
                        f"role=episode_high|{episode.episode_id}", high.value or Decimal("0"),
                        high.effective_at, evaluation_at, "pass", high.lineage_hash,
                    ),
                )
                drawdown = self._evaluate(
                    EPISODE_DRAWDOWN, "position_episode", episode.episode_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, drawdown_inputs,
                )
            values.extend((high, drawdown))

        thread_lots: dict[str, list[LotFact]] = {}
        for lot in lots:
            if lot.remaining_quantity > 0 and len(links.get(lot.lot_id, ())) == 1:
                thread_lots.setdefault(links[lot.lot_id][0], []).append(lot)
        thread_losses: dict[str, list[MetricValue]] = {}
        for thread_id, selected_lots in sorted(thread_lots.items()):
            instrument_ids = {item.instrument_id for item in selected_lots}
            quality = base_quality
            if len(instrument_ids) != 1:
                quality = quality or "thread_instrument_scope_mismatch"
            instrument_id = sorted(instrument_ids)[0]
            plan = self.plan_repository.risk_plan_as_of(
                thread_id=thread_id, evaluation_at=evaluation_at
            )
            if plan is None:
                quality = quality or "missing_owner_risk_plan"
            currencies = {item.currency for item in selected_lots}
            if plan is not None:
                currencies.add(str(plan["currency"]))
            if len(currencies) != 1:
                quality = quality or "thread_currency_mismatch"
            currency = sorted(currencies)[0]
            fx_input, fx_quality = self._fx_input(currency, evaluation_at)
            quality = quality or fx_quality
            quantity_inputs = tuple(
                self._fact_input("open_quantity", item.lot_id, item, item.remaining_quantity)
                for item in selected_lots
            )
            plan_inputs: tuple[MetricInput, ...] = ()
            if plan is not None:
                plan_inputs = (
                    MetricInput(
                        f"role=reference_price|{thread_id}", Decimal(str(plan["reference_price"])),
                        plan["effective_at"], plan["knowledge_at"], "pass",
                        _hash("risk-plan", plan["risk_plan_revision_id"]),
                    ),
                    MetricInput(
                        f"role=stop_price|{thread_id}", Decimal(str(plan["stop_price"])),
                        plan["effective_at"], plan["knowledge_at"], "pass",
                        _hash("risk-plan", plan["risk_plan_revision_id"]),
                    ),
                )
            loss_inputs = quantity_inputs + plan_inputs + ((fx_input,) if fx_input else ())
            if quality:
                loss = self._unavailable(
                    THREAD_PLANNED_LOSS, "trade_thread", thread_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, quality, loss_inputs,
                )
                ratio = self._unavailable(
                    THREAD_RISK_RATIO, "trade_thread", thread_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, quality, loss_inputs,
                )
            else:
                loss = self._evaluate(
                    THREAD_PLANNED_LOSS, "trade_thread", thread_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, loss_inputs,
                )
                assert total_input is not None
                ratio_inputs = (
                    MetricInput(
                        f"role=planned_loss|{thread_id}", loss.value or Decimal("0"),
                        loss.effective_at, evaluation_at, "pass", loss.lineage_hash,
                    ),
                    total_input,
                )
                ratio = self._evaluate(
                    THREAD_RISK_RATIO, "trade_thread", thread_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, ratio_inputs,
                )
            values.extend((loss, ratio))
            thread_losses.setdefault(instrument_id, []).append(loss)

        for instrument_id, losses in sorted(thread_losses.items()):
            quality = base_quality
            if any(item.value is None for item in losses):
                quality = quality or "incomplete_thread_risk"
            aggregate_inputs = tuple(MetricInput(
                f"role=thread_planned_loss|{item.subject_id}", item.value or Decimal("0"),
                item.effective_at, evaluation_at, item.quality_status, item.lineage_hash,
            ) for item in losses)
            if quality:
                planned = self._unavailable(
                    INSTRUMENT_PLANNED_LOSS, "instrument", instrument_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, quality, aggregate_inputs,
                )
                ratio = self._unavailable(
                    INSTRUMENT_RISK_RATIO, "instrument", instrument_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, quality, aggregate_inputs,
                )
            else:
                planned = self._evaluate(
                    INSTRUMENT_PLANNED_LOSS, "instrument", instrument_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, aggregate_inputs,
                )
                assert total_input is not None
                ratio_inputs = (
                    MetricInput(
                        f"role=planned_loss|{instrument_id}", planned.value or Decimal("0"),
                        planned.effective_at, evaluation_at, "pass", planned.lineage_hash,
                    ),
                    total_input,
                )
                ratio = self._evaluate(
                    INSTRUMENT_RISK_RATIO, "instrument", instrument_id, evaluation_at,
                    evaluation_slot, evaluation_run_id, ratio_inputs,
                )
            values.extend((planned, ratio))
        result = tuple(values)
        self._write_atomic(result)
        return result
