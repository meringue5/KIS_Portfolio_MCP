"""Bounded append-only classification sync for currently held overseas instruments."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

import duckdb
import httpx

from kis_portfolio.account_registry import get_account, scoped_account_env
from kis_portfolio.adapters.outbound.instrument_warehouse import InstrumentWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.overseas_instrument_info import fetch_overseas_instrument_info
from kis_portfolio.services.sec_issuer_info import (
    classify_overseas_issuer,
    fetch_sec_issuer_info,
    fetch_sec_ticker_ciks,
)


US_MARKETS = frozenset({"NAS", "NYS", "AMS"})
MAX_INSTRUMENTS = 8


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _envelope(
    *, source_id: str, source_record_id: str, payload: dict[str, Any], observed_at: datetime
) -> SourceEnvelope:
    return SourceEnvelope(
        source_id=source_id,
        source_record_id=source_record_id,
        observed_at=observed_at,
        fetched_at=observed_at,
        payload=payload,
        content_hash=hashlib.sha256(_canonical(payload).encode()).hexdigest(),
        quality_status="pass",
    )


def _held_unknowns(
    connection: duckdb.DuckDBPyConnection,
    *, logical_date: date,
    source_slot: str,
) -> tuple[dict[str, Any], ...]:
    rows = connection.execute(
        """
        SELECT DISTINCT i.instrument_id,i.market,i.symbol,i.name,i.currency
        FROM gold.portfolio_daily_state p
        JOIN silver.instruments_current i USING(instrument_id)
        WHERE p.evaluation_date=? AND p.evaluation_slot=?
          AND p.aggregate_level='position' AND p.quantity>0
          AND i.market IN ('NAS','NYS','AMS') AND i.asset_type='unknown'
        ORDER BY i.instrument_id
        """,
        [logical_date, source_slot],
    ).fetchall()
    if len(rows) > MAX_INSTRUMENTS:
        raise RuntimeError("held overseas classification exceeds bounded scope")
    return tuple({
        "instrument_id": str(row[0]), "market": str(row[1]), "symbol": str(row[2]),
        "name": row[3], "currency": str(row[4]),
    } for row in rows)


async def _collect(
    instruments: tuple[dict[str, Any], ...],
    *,
    sec_user_agent: str,
) -> tuple[tuple[dict[str, Any], Any, Any, Any], ...]:
    symbols = tuple(str(item["symbol"]) for item in instruments)
    account = get_account("brokerage")
    async with httpx.AsyncClient(timeout=20.0) as client:
        cik_by_symbol = await fetch_sec_ticker_ciks(
            symbols=symbols, user_agent=sec_user_agent, client=client,
        )
        kis_by_symbol = {}
        with scoped_account_env(account):
            for item in instruments:
                kis_by_symbol[item["symbol"]] = await fetch_overseas_instrument_info(
                    market=item["market"], symbol=item["symbol"], client=client,
                )
        sec_by_cik = {}
        for cik in sorted(set(cik_by_symbol.values())):
            sec_by_cik[cik] = await fetch_sec_issuer_info(
                cik=cik, user_agent=sec_user_agent, client=client,
            )
    return tuple(
        (
            item,
            kis_by_symbol[item["symbol"]],
            sec_by_cik[cik_by_symbol[item["symbol"]]],
            classify_overseas_issuer(
                symbol=item["symbol"],
                kis=kis_by_symbol[item["symbol"]],
                sec=sec_by_cik[cik_by_symbol[item["symbol"]]],
            ),
        )
        for item in instruments
    )


def sync_held_overseas_classifications(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    source_slot: str,
    sec_user_agent: str,
) -> dict[str, Any]:
    """Resolve only current unknown holdings; never rewrite an earlier version."""
    instruments = _held_unknowns(
        connection, logical_date=logical_date, source_slot=source_slot
    )
    if not instruments:
        return {
            "status": "skipped", "reason": "no_unknown_held_overseas_instrument",
            "instrument_count": 0, "source_call_count": 0,
        }
    collected = asyncio.run(_collect(instruments, sec_user_agent=sec_user_agent))
    observed_at = datetime.now(UTC)
    warehouse = V2WarehouseRepository(connection)
    versions = InstrumentWarehouseRepository(connection)
    evidence_hashes: list[str] = []
    resolved = 0
    for item, kis, sec, classification in collected:
        kis_payload = {
            "market": kis.market,
            "symbol": kis.symbol,
            "product_type_code": kis.product_type_code,
            "product_class_code": kis.product_class_code,
            "product_class_name": kis.product_class_name,
            "overseas_stock_division_code": kis.overseas_stock_division_code,
            "overseas_stock_product_group": kis.overseas_stock_product_group,
            "etf_risk_indicator_code": kis.etf_risk_indicator_code,
            "tracking_multiple": kis.tracking_multiple,
            "raw_content_hash": hashlib.sha256(_canonical(kis.raw).encode()).hexdigest(),
        }
        kis_observation = warehouse.record_observation(
            "dataset.instrument-master",
            _envelope(
                source_id="source.kis-open-api",
                source_record_id=f"kis-product-info:{kis.market}:{kis.symbol}:{logical_date}",
                payload=kis_payload,
                observed_at=observed_at,
            ),
            f"instrument-classification:{logical_date}:{source_slot}",
        )
        sec_payload = {
            "cik": sec.cik,
            "name": sec.name,
            "sic": sec.sic,
            "sic_description": sec.sic_description,
            "tickers": list(sec.tickers),
            "raw_content_hash": hashlib.sha256(_canonical(sec.raw).encode()).hexdigest(),
        }
        sec_observation = warehouse.record_observation(
            "dataset.instrument-master",
            _envelope(
                source_id="source.sec-edgar",
                source_record_id=f"sec-submissions:{sec.cik}:{logical_date}",
                payload=sec_payload,
                observed_at=observed_at,
            ),
            f"instrument-classification:{logical_date}:{source_slot}",
        )
        instrument = {
            **item,
            "asset_type": classification.asset_type,
            "economic_exposure": "unknown",
            "issuer_id": classification.issuer_id,
            "as_of": observed_at,
            "valid_from": observed_at,
            "knowledge_at": observed_at,
            "classification_source": classification.source,
            "classification_quality": classification.quality,
            "metadata": {
                **classification.evidence,
                "kis_source_observation_id": kis_observation,
                "sec_source_observation_id": sec_observation,
            },
        }
        warehouse.upsert_instrument(instrument, sec_observation)
        versions.record_version(instrument, sec_observation)
        evidence_hashes.append(hashlib.sha256(_canonical({
            "instrument_id": item["instrument_id"],
            "classification": classification.asset_type,
            "issuer_id": classification.issuer_id,
            "kis": kis_payload,
            "sec": sec_payload,
        }).encode()).hexdigest())
        resolved += classification.asset_type != "unknown"
    return {
        "status": "succeeded",
        "instrument_count": len(instruments),
        "resolved_count": resolved,
        "unresolved_count": len(instruments) - resolved,
        "source_call_count": 1 + len(instruments) + len({item[2].cik for item in collected}),
        "evidence_hash": hashlib.sha256("|".join(sorted(evidence_hashes)).encode()).hexdigest(),
    }
