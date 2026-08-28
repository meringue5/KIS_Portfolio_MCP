"""Governed, bounded dual-basis price-history collection."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import duckdb
import httpx

from kis_portfolio.account_registry import get_account, scoped_account_env
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.auth import get_access_token
from kis_portfolio.clients.kis import AUTH_TYPE, CONTENT_TYPE, DOMAIN, request_kis
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import (
    LineageEvidence,
    ManagedPipelineRunner,
    PipelineDefinition,
    PipelineStage,
    QualityEvidence,
    StageContext,
    StageResult,
)
from kis_portfolio.ports.source import SourceEnvelope


PIPELINE_ID = "pipeline.price-history-v2"
PIPELINE_VERSION = "1.0.0"
DATASET_ID = "dataset.price-bar-daily"
DOMESTIC_ENDPOINT = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
OVERSEAS_ENDPOINT = "/uapi/overseas-price/v1/quotations/dailyprice"
DOMESTIC_TR_ID = "FHKST03010100"
OVERSEAS_TR_ID = "HHDFS76240000"
PRICE_BASES = ("raw", "adjusted")


class PriceHistoryError(RuntimeError):
    """Raised when a price partition cannot be collected without ambiguity."""


@dataclass(frozen=True, slots=True)
class PricePartition:
    instrument_id: str
    market: str
    symbol: str
    start_date: date
    end_date: date
    price_basis: str

    @property
    def endpoint(self) -> str:
        return DOMESTIC_ENDPOINT if self.market == "KRX" else OVERSEAS_ENDPOINT

    @property
    def request_option(self) -> str:
        if self.market == "KRX":
            return "1" if self.price_basis == "raw" else "0"
        return "0" if self.price_basis == "raw" else "1"

    @property
    def key(self) -> str:
        return (
            f"{self.instrument_id}|{self.start_date.isoformat()}|"
            f"{self.end_date.isoformat()}|{self.price_basis}"
        )


@dataclass(frozen=True, slots=True)
class PricePage:
    payload: dict[str, Any]
    continuation: str = ""


class PricePageFetcher(Protocol):
    async def fetch_page(
        self,
        partition: PricePartition,
        *,
        cursor_end: date,
        continuation: str,
    ) -> PricePage: ...


class KISPricePageFetcher:
    """KIS HTTP adapter. Credentials stay in the scoped runtime environment."""

    async def fetch_page(
        self,
        partition: PricePartition,
        *,
        cursor_end: date,
        continuation: str,
    ) -> PricePage:
        headers = {
            "content-type": CONTENT_TYPE,
            "appkey": os.environ["KIS_APP_KEY"],
            "appsecret": os.environ["KIS_APP_SECRET"],
            "tr_id": DOMESTIC_TR_ID if partition.market == "KRX" else OVERSEAS_TR_ID,
        }
        if continuation:
            headers["tr_cont"] = continuation
        if partition.market == "KRX":
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": partition.symbol,
                "FID_INPUT_DATE_1": partition.start_date.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": cursor_end.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": partition.request_option,
            }
        else:
            params = {
                "AUTH": "",
                "EXCD": partition.market,
                "SYMB": partition.symbol,
                "GUBN": "0",
                "BYMD": cursor_end.strftime("%Y%m%d"),
                "MODP": partition.request_option,
            }
        async with httpx.AsyncClient() as client:
            token = await get_access_token(client, DOMAIN)
            headers["authorization"] = f"{AUTH_TYPE} {token}"
            response = await request_kis(
                client,
                "GET",
                f"{DOMAIN}{partition.endpoint}",
                policy="history",
                headers=headers,
                params=params,
            )
        if response.status_code != 200:
            raise PriceHistoryError(
                f"KIS price page failed: market={partition.market} status={response.status_code}"
            )
        return PricePage(response.json(), response.headers.get("tr_cont", ""))


@dataclass(slots=True)
class CallBudget:
    maximum: int
    used: int = 0

    def reserve(self) -> None:
        if self.used >= self.maximum:
            raise PriceHistoryError(f"physical call budget exhausted: {self.used}/{self.maximum}")
        self.used += 1


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _row_date(row: dict[str, Any], market: str) -> date | None:
    raw = row.get("stck_bsop_date") if market == "KRX" else row.get("xymd")
    if not raw:
        return None
    return datetime.strptime(str(raw), "%Y%m%d").date()


def _page_rows(page: PricePage, market: str) -> list[dict[str, Any]]:
    rows = page.payload.get("output2") or []
    if isinstance(rows, dict):
        rows = [rows] if rows else []
    if not isinstance(rows, list):
        raise PriceHistoryError("price page output2 must be a list or object")
    return [row for row in rows if isinstance(row, dict) and _row_date(row, market)]


def _normalized_bar(row: dict[str, Any], partition: PricePartition, fetched_at: datetime) -> dict[str, Any]:
    session_date = _row_date(row, partition.market)
    if session_date is None:
        raise PriceHistoryError("price row has no session date")
    if partition.market == "KRX":
        values = {
            "open": row.get("stck_oprc"), "high": row.get("stck_hgpr"),
            "low": row.get("stck_lwpr"), "close": row.get("stck_clpr"),
            "volume": row.get("acml_vol"),
        }
    else:
        values = {
            "open": row.get("open"), "high": row.get("high"),
            "low": row.get("low"), "close": row.get("clos"), "volume": row.get("tvol"),
        }
    try:
        numeric = {key: (int(value) if key == "volume" else float(value)) for key, value in values.items()}
    except (TypeError, ValueError) as exc:
        raise PriceHistoryError(f"non-numeric OHLCV row for {partition.instrument_id}") from exc
    if numeric["volume"] < 0:
        raise PriceHistoryError(f"negative volume for {partition.instrument_id} {session_date}")
    if not (
        numeric["high"] >= max(numeric["open"], numeric["low"], numeric["close"])
        and numeric["low"] <= min(numeric["open"], numeric["high"], numeric["close"])
    ):
        raise PriceHistoryError(f"invalid OHLC ordering for {partition.instrument_id} {session_date}")
    return {
        "instrument_id": partition.instrument_id,
        "session_date": session_date,
        "price_basis": partition.price_basis,
        **numeric,
        "knowledge_at": fetched_at,
        "endpoint": partition.endpoint,
        "request_option": partition.request_option,
        "volume_basis": "provider-reported-unadjusted",
        "reconstruction_mode": "retrospective_reconstructed",
        "quality_status": "pass",
        "metadata": {"market": partition.market, "symbol": partition.symbol},
    }


async def collect_price_partition(
    repository: V2WarehouseRepository,
    partition: PricePartition,
    *,
    fetcher: PricePageFetcher,
    run_id: str,
    budget: CallBudget,
    max_pages: int = 10,
) -> dict[str, Any]:
    if partition.price_basis not in PRICE_BASES:
        raise ValueError("price_basis must be raw or adjusted")
    cursor_end = partition.end_date
    continuation = ""
    seen_cursors: set[date] = set()
    page_count = 0
    normalized_count = 0
    session_dates: set[date] = set()

    while cursor_end >= partition.start_date:
        if page_count >= max_pages:
            raise PriceHistoryError(f"max pages reached before coverage: {partition.key}")
        if cursor_end in seen_cursors:
            raise PriceHistoryError(f"price cursor stalled: {partition.key} at {cursor_end}")
        seen_cursors.add(cursor_end)
        budget.reserve()
        fetched_at = datetime.now(UTC)
        page = await fetcher.fetch_page(
            partition, cursor_end=cursor_end, continuation=continuation,
        )
        page_count += 1
        rows = _page_rows(page, partition.market)
        raw_document = {
            "request": {
                "instrument_id": partition.instrument_id,
                "market": partition.market,
                "symbol": partition.symbol,
                "start_date": partition.start_date,
                "cursor_end": cursor_end,
                "price_basis": partition.price_basis,
                "endpoint": partition.endpoint,
                "request_option": partition.request_option,
                "continuation": continuation,
            },
            "response": page.payload,
            "response_continuation": page.continuation,
        }
        raw_json = _canonical_json(raw_document)
        envelope = SourceEnvelope(
            source_id="source.kis-open-api",
            source_record_id=f"{partition.key}|page={page_count}|cursor={cursor_end.isoformat()}",
            observed_at=fetched_at,
            fetched_at=fetched_at,
            payload=raw_document,
            content_hash=hashlib.sha256(raw_json.encode()).hexdigest(),
            quality_status="pass",
        )
        observation_id = repository.record_observation(DATASET_ID, envelope, run_id)
        dated_rows = [(row, _row_date(row, partition.market)) for row in rows]
        in_range = [row for row, row_date in dated_rows if partition.start_date <= row_date <= partition.end_date]
        for row in in_range:
            bar = _normalized_bar(row, partition, fetched_at)
            repository.upsert_price_bar(bar, observation_id)
            session_dates.add(bar["session_date"])
            normalized_count += 1

        if not dated_rows:
            break
        oldest = min(row_date for _, row_date in dated_rows)
        if oldest <= partition.start_date:
            break
        has_more = len(rows) >= 100 or page.continuation in {"M", "F"}
        if not has_more:
            break
        next_cursor = oldest - timedelta(days=1)
        if next_cursor >= cursor_end:
            raise PriceHistoryError(f"price cursor did not move backward: {partition.key}")
        cursor_end = next_cursor
        continuation = "N" if partition.market != "KRX" and page.continuation in {"M", "F"} else ""

    return {
        "partition_key": partition.key,
        "market": partition.market,
        "symbol": partition.symbol,
        "price_basis": partition.price_basis,
        "page_count": page_count,
        "normalized_count": normalized_count,
        "distinct_session_count": len(session_dates),
        "first_session": min(session_dates).isoformat() if session_dates else None,
        "last_session": max(session_dates).isoformat() if session_dates else None,
    }


def _business_days(start_date: date, end_date: date) -> int:
    days = (end_date - start_date).days + 1
    return sum((start_date + timedelta(days=offset)).weekday() < 5 for offset in range(max(days, 0)))


def plan_held_price_backfill(
    connection: duckdb.DuckDBPyConnection,
    *,
    start_date: date,
    end_date: date,
    max_pages_per_partition: int = 10,
    max_physical_calls: int = 400,
) -> tuple[list[PricePartition], dict[str, Any]]:
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    rows = connection.execute("""
        WITH latest AS (
            SELECT account_id, instrument_id, quantity
            FROM silver.position_snapshots
            QUALIFY row_number() OVER (
                PARTITION BY account_id, instrument_id ORDER BY as_of DESC, source_observation_id DESC
            ) = 1
        ), held AS (
            SELECT instrument_id, sum(quantity) AS quantity FROM latest
            GROUP BY instrument_id HAVING sum(quantity) > 0
        )
        SELECT i.instrument_id, upper(i.market), i.symbol
        FROM held h JOIN silver.instruments i USING(instrument_id)
        WHERE upper(i.market) IN ('KRX', 'NAS', 'NYS', 'AMS')
        ORDER BY i.instrument_id
    """).fetchall()
    partitions = [
        PricePartition(instrument_id, market, symbol, start_date, end_date, basis)
        for instrument_id, market, symbol in rows for basis in PRICE_BASES
    ]
    estimated_pages_each = min(max_pages_per_partition, max(1, math.ceil(_business_days(start_date, end_date) / 100)))
    estimated_calls = len(partitions) * estimated_pages_each
    if estimated_calls > max_physical_calls:
        raise PriceHistoryError(
            f"planned physical call budget exceeded: {estimated_calls}/{max_physical_calls}"
        )
    return partitions, {
        "instrument_count": len(rows),
        "partition_count": len(partitions),
        "estimated_pages_per_partition": estimated_pages_each,
        "estimated_physical_calls": estimated_calls,
        "max_physical_calls": max_physical_calls,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def _build_pipeline(
    connection: duckdb.DuckDBPyConnection,
    *,
    partitions: list[PricePartition],
    fetcher: PricePageFetcher,
    max_pages_per_partition: int,
    max_physical_calls: int,
) -> PipelineDefinition:
    repository = V2WarehouseRepository(connection)

    def plan(context: StageContext) -> StageResult:
        context.state["partitions"] = partitions
        return StageResult(
            output_count=len(partitions),
            evidence={"partition_keys": [partition.key for partition in partitions]},
        )

    def collect(context: StageContext) -> StageResult:
        active = context.state.get("partitions") or partitions
        budget = CallBudget(max_physical_calls)

        async def collect_all() -> list[dict[str, Any]]:
            summaries = []
            for partition in active:
                summaries.append(await collect_price_partition(
                    repository,
                    partition,
                    fetcher=fetcher,
                    run_id=context.run_id,
                    budget=budget,
                    max_pages=max_pages_per_partition,
                ))
            return summaries

        summaries = asyncio.run(collect_all())
        context.state["summaries"] = summaries
        return StageResult(
            input_count=len(active),
            output_count=sum(item["normalized_count"] for item in summaries),
            source_calls=budget.used,
            evidence={"partitions": summaries},
            lineage=(LineageEvidence(
                "bronze.source_observations", "silver.price_bar_revisions_daily",
                "kis-price-page-normalize", PIPELINE_VERSION,
            ),),
        )

    def quality(context: StageContext) -> StageResult:
        summaries = context.state.get("summaries")
        if summaries is None:
            row = connection.execute(
                "SELECT evidence FROM control.pipeline_stage_runs WHERE run_id=? AND stage_name='collect-land-normalize'",
                [context.run_id],
            ).fetchone()
            evidence = json.loads(row[0]) if row and isinstance(row[0], str) else (row[0] if row else {})
            summaries = evidence.get("partitions", [])
        empty = [item["partition_key"] for item in summaries if item["distinct_session_count"] == 0]
        status = "pass" if not empty else "fail"
        if empty:
            raise PriceHistoryError(f"empty price partitions: {len(empty)}")
        return StageResult(
            input_count=len(summaries),
            output_count=len(summaries),
            quality=(QualityEvidence(
                DATASET_ID, "held-partition-nonempty", status,
                str(len(summaries) - len(empty)), str(len(summaries)), {"empty": empty},
            ),),
        )

    def publish(context: StageContext) -> StageResult:
        for partition in partitions:
            connection.execute("""
                INSERT INTO control.watermarks VALUES (?, ?, 'session_date', ?, ?, current_timestamp)
                ON CONFLICT(pipeline_id, partition_key, watermark_type) DO UPDATE SET
                    watermark_value=excluded.watermark_value, run_id=excluded.run_id,
                    updated_at=excluded.updated_at
            """, [PIPELINE_ID, partition.key, partition.end_date.isoformat(), context.run_id])
        return StageResult(input_count=len(partitions), output_count=len(partitions))

    return PipelineDefinition(
        pipeline_id=PIPELINE_ID,
        version=PIPELINE_VERSION,
        stages=(
            PipelineStage("plan", plan),
            PipelineStage("collect-land-normalize", collect),
            PipelineStage("quality", quality),
            PipelineStage("publish", publish),
        ),
        source_call_budget=max_physical_calls,
    )


def run_held_price_backfill(
    connection: duckdb.DuckDBPyConnection,
    *,
    start_date: date,
    end_date: date,
    dry_run: bool = True,
    fetcher: PricePageFetcher | None = None,
    max_pages_per_partition: int = 10,
    max_physical_calls: int = 400,
) -> dict[str, Any]:
    MigrationRunner(connection).require("0005")
    partitions, plan = plan_held_price_backfill(
        connection,
        start_date=start_date,
        end_date=end_date,
        max_pages_per_partition=max_pages_per_partition,
        max_physical_calls=max_physical_calls,
    )
    if dry_run:
        return {"status": "dry_run", **plan, "partition_keys": [item.key for item in partitions]}
    if not partitions:
        return {"status": "skipped", "reason": "no-held-instruments", **plan}
    plan_hash = hashlib.sha256("\n".join(item.key for item in partitions).encode()).hexdigest()[:16]
    active_fetcher = fetcher or KISPricePageFetcher()
    definition = _build_pipeline(
        connection,
        partitions=partitions,
        fetcher=active_fetcher,
        max_pages_per_partition=max_pages_per_partition,
        max_physical_calls=max_physical_calls,
    )
    runner = ManagedPipelineRunner(connection)
    if fetcher is not None:
        outcome = runner.run(
            definition,
            logical_date=end_date,
            slot="backfill",
            partition_key=f"held-{start_date.isoformat()}-{end_date.isoformat()}-{plan_hash}",
        )
    else:
        quote_account = get_account("brokerage")
        with scoped_account_env(quote_account):
            outcome = runner.run(
                definition,
                logical_date=end_date,
                slot="backfill",
                partition_key=f"held-{start_date.isoformat()}-{end_date.isoformat()}-{plan_hash}",
            )
    return {
        "status": outcome.status,
        "run_id": outcome.run_id,
        "reused": outcome.reused,
        "source_calls": outcome.source_calls,
        **plan,
    }
