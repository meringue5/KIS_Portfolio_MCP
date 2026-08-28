"""Governed production adapter for the first owned-portfolio V2 pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

from kis_portfolio.account_registry import load_account_registry, scoped_account_env
from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.pipeline import (
    LineageEvidence,
    ManagedPipelineRunner,
    PipelineDefinition,
    PipelineStage,
    QualityEvidence,
    StageContext,
    StageResult,
)
from kis_portfolio.ports.object_store import ObjectStorePort
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.account import fetch_balance_snapshot
from kis_portfolio.services import kis_api
from kis_portfolio.security.redaction import redact_nested


SEOUL = ZoneInfo("Asia/Seoul")
PIPELINE_ID = "pipeline.owned-portfolio-core-v2"
PIPELINE_VERSION = "1.0.0"
ALLOWED_SLOTS = frozenset({"kr-1000", "kr-1430", "kr-1600"})


def _decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value).replace(",", "")) if value not in (None, "") else Decimal(default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _account_id(label: str) -> str:
    return hashlib.sha256(f"v1-account|{label}".encode()).hexdigest()


def _instrument_id(market: str, symbol: str) -> str:
    return f"v1|{market}|{symbol}"


def _envelope(source_record_id: str, payload: dict[str, Any], observed_at: datetime) -> SourceEnvelope:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return SourceEnvelope(
        source_id="source.kis-open-api",
        source_record_id=source_record_id,
        observed_at=observed_at,
        fetched_at=datetime.now(UTC),
        payload=payload,
        content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        quality_status="pass",
    )


def calendar_gate(connection: duckdb.DuckDBPyConnection, logical_date: date) -> tuple[bool, str]:
    row = connection.execute(
        "SELECT is_open, note FROM main.market_calendar WHERE lower(market)='krx' AND trade_date=?",
        [logical_date],
    ).fetchone()
    if row is None:
        return False, "calendar_missing"
    return (True, "market_open") if row[0] else (False, f"market_closed:{row[1] or 'declared'}")


async def _collect_sources(slot: str) -> dict[str, Any]:
    accounts = load_account_registry()
    domestic = []
    calls = 0
    for account in accounts:
        with scoped_account_env(account):
            result = await fetch_balance_snapshot(save_snapshot=True, return_metadata=True)
        domestic.append({
            "account_label": account.label,
            "account_type": account.account_type,
            "snapshot_id": result.get("saved_snapshot_id"),
            "raw": result["raw"],
            "observed_at": datetime.now(UTC),
        })
        calls += 1

    overseas: dict[str, Any] = {}
    overseas_deposit: dict[str, Any] = {}
    if slot == "kr-1000":
        brokerage = next(account for account in accounts if account.label == "brokerage")
        with scoped_account_env(brokerage):
            overseas = await kis_api.inquery_overseas_balance("ALL")
            overseas_deposit = await kis_api.inquery_overseas_deposit("02", "000")
        calls += 9  # eight exchange checks plus one deposit observation

    domestic_symbols = sorted({
        str(row.get("pdno") or "").strip()
        for item in domestic for row in (item["raw"].get("output1") or [])
        if str(row.get("pdno") or "").strip()
    })
    overseas_symbols = sorted({
        (market, str(row.get("ovrs_pdno") or "").strip())
        for market, result in overseas.items() if isinstance(result, dict)
        for row in (result.get("output1") or [])
        if str(row.get("ovrs_pdno") or "").strip()
    })
    quote_account = next(account for account in accounts if account.label == "brokerage")
    ymd = datetime.now(SEOUL).strftime("%Y%m%d")
    with scoped_account_env(quote_account):
        for symbol in domestic_symbols:
            await kis_api.inquery_stock_history(symbol, ymd, ymd)
            calls += 1
        if slot == "kr-1000":
            market_map = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}
            for market, symbol in overseas_symbols:
                await kis_api.inquery_overseas_stock_history(symbol, market_map.get(market, market[:3]), ymd)
                calls += 1
            await kis_api.inquery_exchange_rate_history("USD", ymd, ymd)
            calls += 1
    return {
        "domestic": domestic,
        "overseas": overseas,
        "overseas_deposit": overseas_deposit,
        "source_calls": calls,
        "domestic_symbols": domestic_symbols,
        "overseas_symbols": overseas_symbols,
    }


def build_owned_portfolio_pipeline(
    connection: duckdb.DuckDBPyConnection,
    *,
    object_store: ObjectStorePort,
) -> PipelineDefinition:
    repository = V2WarehouseRepository(connection)

    def collect(context: StageContext) -> StageResult:
        collected = asyncio.run(_collect_sources(context.slot))
        context.state["collected"] = collected
        safe_bundle = {
            "slot": context.slot,
            "logical_date": context.logical_date.isoformat(),
            "domestic": [
                {"account_label": item["account_label"], "account_type": item["account_type"],
                 "raw": item["raw"], "observed_at": item["observed_at"]}
                for item in collected["domestic"]
            ],
            "overseas": collected["overseas"],
            "overseas_deposit": collected.get("overseas_deposit", {}),
        }
        payload = json.dumps(redact_nested(safe_bundle), ensure_ascii=False, sort_keys=True, default=str).encode()
        stored = object_store.put_bytes(
            payload,
            dataset_id="dataset.portfolio-position-observation",
            partition=f"{context.logical_date.isoformat()}-{context.slot}",
            media_type="application/json",
        )
        connection.execute("""
            INSERT INTO bronze.raw_object_manifest(
                content_hash, dataset_id, source_id, private_uri, media_type, byte_size,
                rights_class, sensitivity, metadata
            ) VALUES (?, 'dataset.portfolio-position-observation', 'source.kis-open-api', ?, ?, ?,
                      'private-owner-use', 'confidential', ?)
            ON CONFLICT(content_hash) DO NOTHING
        """, [stored.content_hash, stored.uri, stored.media_type, stored.byte_size,
              json.dumps({"pipeline_run_id": context.run_id, "slot": context.slot})])
        context.state["raw_object"] = stored
        return StageResult(
            output_count=len(collected["domestic"]) + len(collected["overseas"]),
            source_calls=collected["source_calls"],
            evidence={"raw_object_hash": stored.content_hash, "raw_object_created": stored.created},
            lineage=(LineageEvidence("source.kis-open-api", stored.uri, "kis-raw-bundle", "1.0.0"),),
        )

    def normalize(context: StageContext) -> StageResult:
        collected = context.state.get("collected")
        if not collected:
            row = connection.execute("""
                SELECT evidence FROM control.pipeline_stage_runs
                WHERE run_id=? AND stage_name='collect-land' AND status='succeeded'
            """, [context.run_id]).fetchone()
            evidence = json.loads(row[0]) if row and isinstance(row[0], str) else (row[0] if row else None)
            if not evidence or not evidence.get("raw_object_hash"):
                raise RuntimeError("successful collect stage has no landed-object resume evidence")
            manifest = connection.execute(
                "SELECT private_uri FROM bronze.raw_object_manifest WHERE content_hash=?",
                [evidence["raw_object_hash"]],
            ).fetchone()
            if not manifest:
                raise RuntimeError("landed-object manifest is missing for stage resume")
            with tempfile.TemporaryDirectory(prefix="kis-v2-resume-") as temp_dir:
                path = object_store.download(
                    manifest[0], Path(temp_dir) / "bundle.json",
                    expected_sha256=evidence["raw_object_hash"],
                )
                bundle = json.loads(path.read_text(encoding="utf-8"))
            for item in bundle["domestic"]:
                item["observed_at"] = datetime.fromisoformat(item["observed_at"])
                item.setdefault("account_type", "REAL")
            collected = {
                "domestic": bundle["domestic"], "overseas": bundle["overseas"],
                "overseas_deposit": bundle.get("overseas_deposit", {}),
                "source_calls": 0, "domestic_symbols": [], "overseas_symbols": [],
            }
            context.state["collected"] = collected
        normalized = 0
        for item in collected["domestic"]:
            observed = item["observed_at"]
            label = item["account_label"]
            raw = item["raw"]
            account_payload = {
                "account_id": _account_id(label), "account_label": label,
                "account_type": item["account_type"], "base_currency": "KRW", "as_of": observed,
            }
            account_obs = repository.record_observation(
                "dataset.portfolio-position-observation",
                _envelope(f"{context.run_id}:{label}:account", account_payload, observed), context.run_id,
            )
            repository.upsert_account(account_payload, account_obs)
            holdings_value = Decimal(0)
            for row in raw.get("output1") or []:
                symbol = str(row.get("pdno") or "").strip()
                quantity = _decimal(row.get("hldg_qty") or row.get("cblc_qty"))
                if not symbol or quantity <= 0:
                    continue
                instrument = {
                    "instrument_id": _instrument_id("KRX", symbol), "market": "KRX", "symbol": symbol,
                    "name": row.get("prdt_name"), "asset_type": "unknown", "currency": "KRW",
                    "as_of": observed, "classification_quality": "kis-balance",
                }
                instrument_obs = repository.record_observation(
                    "dataset.instrument-master",
                    _envelope(f"{context.run_id}:{label}:{symbol}:instrument", instrument, observed), context.run_id,
                )
                repository.upsert_instrument(instrument, instrument_obs)
                position = {
                    "account_id": account_payload["account_id"], "instrument_id": instrument["instrument_id"],
                    "as_of": observed, "quantity": quantity,
                    "average_cost": _decimal(row.get("pchs_avg_pric")), "cost_currency": "KRW",
                    "quality_status": "pass",
                }
                position_obs = repository.record_observation(
                    "dataset.portfolio-position-observation",
                    _envelope(f"{context.run_id}:{label}:{symbol}:position", position, observed), context.run_id,
                )
                repository.upsert_position(position, position_obs)
                holdings_value += _decimal(row.get("evlu_amt"))
                normalized += 2
            summary = raw.get("output2") or {}
            if isinstance(summary, list):
                summary = summary[0] if summary else {}
            total = _decimal(summary.get("tot_evlu_amt") or summary.get("tot_asst_amt"))
            cash = max(total - holdings_value, Decimal(0))
            cash_payload = {
                "account_id": account_payload["account_id"], "currency": "KRW", "as_of": observed,
                "amount": cash, "quality_status": "pass" if total else "degraded",
            }
            cash_obs = repository.record_observation(
                "dataset.portfolio-position-observation",
                _envelope(f"{context.run_id}:{label}:cash", cash_payload, observed), context.run_id,
            )
            repository.upsert_cash(cash_payload, cash_obs)
            normalized += 2

        if collected.get("overseas"):
            account_id = _account_id("brokerage")
            observed = datetime.now(UTC)
            for market, result in collected["overseas"].items():
                if not isinstance(result, dict):
                    continue
                normalized_market = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}.get(market, market[:3])
                for row in result.get("output1") or []:
                    symbol = str(row.get("ovrs_pdno") or "").strip()
                    quantity = _decimal(row.get("ovrs_cblc_qty") or row.get("cblc_qty"))
                    if not symbol or quantity <= 0:
                        continue
                    currency = str(row.get("tr_crcy_cd") or "USD")
                    instrument = {
                        "instrument_id": _instrument_id(normalized_market, symbol),
                        "market": normalized_market, "symbol": symbol, "name": row.get("ovrs_item_name"),
                        "asset_type": "unknown", "currency": currency, "as_of": observed,
                        "classification_quality": "kis-overseas-balance",
                    }
                    instrument_obs = repository.record_observation(
                        "dataset.instrument-master",
                        _envelope(f"{context.run_id}:brokerage:{normalized_market}:{symbol}:instrument", instrument, observed),
                        context.run_id,
                    )
                    repository.upsert_instrument(instrument, instrument_obs)
                    position = {
                        "account_id": account_id, "instrument_id": instrument["instrument_id"], "as_of": observed,
                        "quantity": quantity, "average_cost": _decimal(row.get("pchs_avg_pric")),
                        "cost_currency": currency, "quality_status": "pass",
                    }
                    position_obs = repository.record_observation(
                        "dataset.portfolio-position-observation",
                        _envelope(f"{context.run_id}:brokerage:{normalized_market}:{symbol}:position", position, observed),
                        context.run_id,
                    )
                    repository.upsert_position(position, position_obs)
                    normalized += 2
            for row in collected.get("overseas_deposit", {}).get("통화별_잔고", []):
                currency = str(row.get("crcy_cd") or "").strip()
                amount = _decimal(row.get("frcr_dncl_amt_2") or row.get("frcr_drwg_psbl_amt_1"))
                if not currency or amount == 0:
                    continue
                cash_payload = {
                    "account_id": account_id, "currency": currency, "as_of": observed,
                    "amount": amount, "quality_status": "pass",
                }
                cash_obs = repository.record_observation(
                    "dataset.portfolio-position-observation",
                    _envelope(f"{context.run_id}:brokerage:{currency}:cash", cash_payload, observed), context.run_id,
                )
                repository.upsert_cash(cash_payload, cash_obs)
                normalized += 1

        lower_date = context.logical_date - timedelta(days=7)
        price_rows = connection.execute("""
            SELECT exchange, symbol, date, open, high, low, close, volume
            FROM main.price_history WHERE date BETWEEN ? AND ?
        """, [lower_date, context.logical_date]).fetchall()
        for market, symbol, session_date, open_, high, low, close, volume in price_rows:
            normalized_market = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}.get(market, market)
            instrument_id = _instrument_id(normalized_market, symbol)
            payload = {
                "instrument_id": instrument_id, "session_date": session_date, "price_basis": "raw",
                "open": open_, "high": high, "low": low, "close": close, "volume": volume,
                "quality_status": "pass",
            }
            obs = repository.record_observation(
                "dataset.price-bar-daily",
                _envelope(f"{context.run_id}:price:{normalized_market}:{symbol}:{session_date}", payload, datetime.now(UTC)),
                context.run_id,
            )
            repository.upsert_price_bar(payload, obs)
            normalized += 1
        fx_rows = connection.execute("""
            SELECT currency, date, rate FROM main.exchange_rate_history
            WHERE date BETWEEN ? AND ?
        """, [lower_date, context.logical_date]).fetchall()
        for currency, rate_date, rate in fx_rows:
            payload = {
                "base_currency": currency, "quote_currency": "KRW", "rate_date": rate_date,
                "rate_type": "close", "rate": rate, "quality_status": "pass",
            }
            obs = repository.record_observation(
                "dataset.fx-rate-daily",
                _envelope(f"{context.run_id}:fx:{currency}:{rate_date}", payload, datetime.now(UTC)), context.run_id,
            )
            repository.upsert_fx_rate(payload, obs)
            normalized += 1
        context.state["normalized_count"] = normalized
        return StageResult(
            input_count=len(collected["domestic"]), output_count=normalized,
            lineage=(LineageEvidence("bronze.source_observations", "silver.portfolio+market", "owned-portfolio-normalize", "1.0.0"),),
        )

    def quality(context: StageContext) -> StageResult:
        collected = context.state.get("collected") or {}
        account_count = len(collected.get("domestic", []))
        expected = len(load_account_registry())
        status = "pass" if account_count == expected else "fail"
        if status == "fail":
            raise RuntimeError(f"account coverage failed: {account_count}/{expected}")
        return StageResult(
            input_count=context.state.get("normalized_count", 0), output_count=account_count,
            quality=(QualityEvidence(
                "dataset.portfolio-position-observation", "configured-account-coverage", status,
                str(account_count), str(expected), {"slot": context.slot},
            ),),
        )

    def publish(context: StageContext) -> StageResult:
        count = repository.materialize_daily_state(
            evaluation_date=context.logical_date, slot=context.slot, as_of=datetime.now(UTC),
        )
        connection.execute("""
            INSERT INTO control.watermarks VALUES (?, ?, 'logical_date', ?, ?, current_timestamp)
            ON CONFLICT(pipeline_id, partition_key, watermark_type) DO UPDATE SET
                watermark_value=excluded.watermark_value, run_id=excluded.run_id, updated_at=excluded.updated_at
        """, [PIPELINE_ID, context.partition_key, context.logical_date.isoformat(), context.run_id])
        return StageResult(
            output_count=count,
            lineage=(LineageEvidence("silver.position+cash+price+fx", "gold.portfolio_daily_state", "owned-portfolio-publish", "1.0.0"),),
        )

    return PipelineDefinition(
        pipeline_id=PIPELINE_ID,
        version=PIPELINE_VERSION,
        stages=(
            PipelineStage("collect-land", collect), PipelineStage("normalize", normalize),
            PipelineStage("quality", quality), PipelineStage("publish", publish),
        ),
        source_call_budget=64,
    )


def run_owned_portfolio_pipeline(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    slot: str,
    partition_key: str = "all-accounts",
    object_store: ObjectStorePort | None = None,
) -> dict[str, Any]:
    if slot not in ALLOWED_SLOTS:
        raise ValueError(f"slot must be one of {sorted(ALLOWED_SLOTS)}")
    allowed, reason = calendar_gate(connection, logical_date)
    if not allowed:
        return {"status": "skipped", "reason": reason, "logical_date": logical_date.isoformat(), "slot": slot}
    if object_store is None:
        bucket = os.environ.get("KIS_GCS_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("KIS_GCS_BUCKET is required for managed V2 collection")
        object_store = GCSObjectStore(bucket)
    definition = build_owned_portfolio_pipeline(connection, object_store=object_store)
    runner = ManagedPipelineRunner(connection)
    logical_key = runner.logical_key(definition, logical_date, slot, partition_key)
    state_store = None
    claim = None
    if os.environ.get("KIS_STATE_BACKEND", "motherduck").lower() == "firestore":
        from kis_portfolio.platform.state_runtime import get_state_store
        state_store = get_state_store()
        claim = state_store.claim(f"pipeline:{logical_key}", f"job:{os.getpid()}", timedelta(minutes=30))
        if not claim.acquired:
            return {"status": "in_progress", "reused": True, "logical_key": logical_key}
        state_store.put("run_requests", logical_key, {
            "pipeline_id": PIPELINE_ID, "version": PIPELINE_VERSION,
            "logical_date": logical_date.isoformat(), "slot": slot, "partition_key": partition_key,
            "status": "running", "requested_at": datetime.now(UTC),
        })
    try:
        outcome = runner.run(
            definition, logical_date=logical_date, slot=slot, partition_key=partition_key, state={},
        )
        if state_store:
            state_store.put("run_requests", logical_key, {
                "pipeline_id": PIPELINE_ID, "version": PIPELINE_VERSION,
                "logical_date": logical_date.isoformat(), "slot": slot, "partition_key": partition_key,
                "status": outcome.status, "run_id": outcome.run_id, "source_calls": outcome.source_calls,
                "finished_at": datetime.now(UTC),
            })
        return {
            "status": outcome.status, "run_id": outcome.run_id, "reused": outcome.reused,
            "source_calls": outcome.source_calls, "logical_key": logical_key,
        }
    finally:
        if state_store and claim:
            state_store.release(f"pipeline:{logical_key}", claim.owner_id, claim.fencing_token)
