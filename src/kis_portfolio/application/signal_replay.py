"""Bounded, read-only price-history projection into the WI-029 replay contract."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal, localcontext
from typing import Any, Protocol

from kis_portfolio.modules.monitoring import CalibrationResult, SignalObservation, calibrate_replay


MAX_REPLAY_ROWS = 200_000


class ReplayQueryPort(Protocol):
    """Minimal read-only query port supplied by a warehouse adapter."""

    def execute(self, query: str, parameters: list[object] | None = None) -> Any: ...


def _asset_class(value: object) -> str:
    normalized = str(value or "unknown").strip().lower()
    return {
        "equity": "stock",
        "stock": "stock",
        "etf": "etf",
        "reit": "reit",
        "leveraged": "leveraged",
        "leveraged_etf": "leveraged",
        "inverse": "inverse",
        "inverse_etf": "inverse",
    }.get(normalized, "unknown")


def _mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _population_stddev(values: list[Decimal]) -> Decimal | None:
    mean = _mean(values)
    if mean is None:
        return None
    variance = sum(((value - mean) ** 2 for value in values), Decimal("0")) / Decimal(len(values))
    with localcontext() as context:
        context.prec = 40
        return variance.sqrt()


def _wilder_rsi(closes: list[Decimal]) -> Decimal | None:
    if len(closes) < 15:
        return None
    selected = closes[-120:]
    changes = [selected[index] - selected[index - 1] for index in range(1, len(selected))]
    gains = [max(change, Decimal("0")) for change in changes]
    losses = [max(-change, Decimal("0")) for change in changes]
    average_gain = sum(gains[:14], Decimal("0")) / Decimal("14")
    average_loss = sum(losses[:14], Decimal("0")) / Decimal("14")
    for gain, loss in zip(gains[14:], losses[14:], strict=True):
        average_gain = (average_gain * Decimal("13") + gain) / Decimal("14")
        average_loss = (average_loss * Decimal("13") + loss) / Decimal("14")
    if average_gain == 0 and average_loss == 0:
        return Decimal("50")
    if average_loss == 0:
        return Decimal("100")
    return Decimal("100") - Decimal("100") / (Decimal("1") + average_gain / average_loss)


def _bollinger_percent_b(closes: list[Decimal]) -> Decimal | None:
    if len(closes) < 20:
        return None
    selected = closes[-20:]
    mean = _mean(selected)
    deviation = _population_stddev(selected)
    assert mean is not None and deviation is not None
    lower = mean - Decimal("2") * deviation
    upper = mean + Decimal("2") * deviation
    return Decimal("0.5") if upper == lower else (selected[-1] - lower) / (upper - lower)


def _slot(market: str) -> str:
    return "us-close" if market.upper() in {"NAS", "NYSE", "AMEX", "USA", "US"} else "kr-1600"


def load_price_replay_observations(
    connection: ReplayQueryPort,
    *,
    start_date: date,
    end_date: date,
) -> tuple[SignalObservation, ...]:
    """Read a bounded latest-revision price window without publishing metrics or candidates."""
    if end_date < start_date:
        raise ValueError("replay end precedes start")
    row_count = int(connection.execute(
        """
        SELECT count(*) FROM silver.price_bar_revisions_daily
        WHERE price_basis='adjusted' AND session_date BETWEEN ? AND ?
        """,
        [start_date, end_date],
    ).fetchone()[0])
    if row_count > MAX_REPLAY_ROWS:
        raise RuntimeError("price replay exceeds the bounded row budget")
    rows = connection.execute(
        """
        WITH selected AS (
            SELECT p.*
            FROM silver.price_bar_revisions_daily p
            WHERE p.price_basis='adjusted' AND p.session_date BETWEEN ? AND ?
            QUALIFY row_number() OVER (
                PARTITION BY p.instrument_id,p.session_date,p.price_basis
                ORDER BY p.knowledge_at DESC,p.recorded_at DESC,p.revision_hash DESC
            )=1
        )
        SELECT s.instrument_id,s.session_date,s.close,s.volume,s.effective_at,
               s.quality_status,s.reconstruction_mode,
               coalesce(i.asset_type,'unknown') AS asset_type,
               coalesce(i.market,'UNKNOWN') AS market
        FROM selected s
        LEFT JOIN silver.instruments_current i USING(instrument_id)
        ORDER BY s.instrument_id,s.session_date
        """,
        [start_date, end_date],
    ).fetchall()
    grouped: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[0])].append(row)
    observations: list[SignalObservation] = []
    for instrument_id in sorted(grouped):
        history: list[tuple[date, Decimal, Decimal | None]] = []
        returns: list[Decimal] = []
        for row in grouped[instrument_id]:
            session_date = row[1]
            close = Decimal(str(row[2])) if row[2] is not None else None
            volume = Decimal(str(row[3])) if row[3] is not None else None
            if close is None or close <= 0:
                continue
            prior_close = history[-1][1] if history else None
            daily_return = None if prior_close is None else close / prior_close - Decimal("1")
            if daily_return is not None:
                returns.append(daily_return)
            history.append((session_date, close, volume))
            closes = [item[1] for item in history]
            volumes = [item[2] for item in history[-20:] if item[2] is not None]
            volume_mean = _mean(volumes) if len(volumes) == min(20, len(history)) else None
            volume_ratio = (
                volume / volume_mean
                if volume is not None and volume_mean not in {None, Decimal("0")} and len(history) >= 20
                else None
            )
            reconstruction_mode = str(row[6])
            provenance = (
                "historical_live"
                if reconstruction_mode == "operational_strict"
                else "retrospective_reconstructed"
            )
            quality = str(row[5])
            if reconstruction_mode not in {"operational_strict", "retrospective_reconstructed"}:
                quality = "unsupported_reconstruction_mode"
            market = str(row[8])
            evaluation_slot = _slot(market)
            effective_at = datetime.combine(
                session_date,
                time(21, 0) if evaluation_slot == "us-close" else time(7, 0),
                tzinfo=UTC,
            )
            observations.append(SignalObservation(
                subject_id=instrument_id,
                asset_class=_asset_class(row[7]),
                evaluation_at=effective_at,
                evaluation_slot=evaluation_slot,
                session_key=f"{market.lower()}:{session_date.isoformat()}",
                quality_status=quality,
                provenance_mode=provenance,
                valid_bar_count=len(history),
                daily_return=daily_return,
                vol20=_population_stddev(returns[-20:]) if len(returns) >= 20 else None,
                volume_ratio20=volume_ratio,
                close=close,
                sma20=_mean(closes[-20:]) if len(closes) >= 20 else None,
                sma50=_mean(closes[-50:]) if len(closes) >= 50 else None,
                sma120=_mean(closes[-120:]) if len(closes) >= 120 else None,
                rsi14=_wilder_rsi(closes),
                bollinger_percent_b=_bollinger_percent_b(closes),
            ))
    return tuple(observations)


def calibrate_price_history(
    connection: ReplayQueryPort,
    *,
    start_date: date,
    end_date: date,
) -> CalibrationResult:
    return calibrate_replay(load_price_replay_observations(
        connection, start_date=start_date, end_date=end_date
    ))
