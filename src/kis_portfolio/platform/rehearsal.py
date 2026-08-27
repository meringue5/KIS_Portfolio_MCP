"""Synthetic end-to-end pipeline wiring used by local pre-production rehearsals."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from kis_portfolio.adapters.outbound.fixture_source import FixtureSourceAdapter
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.pipeline import (
    LineageEvidence,
    PipelineDefinition,
    PipelineStage,
    QualityEvidence,
    StageContext,
    StageResult,
)
from kis_portfolio.ports.source import SourceEnvelope


DATASET_BY_TYPE = {
    "account": "dataset.portfolio-position-observation",
    "instrument": "dataset.instrument-master",
    "position": "dataset.portfolio-position-observation",
    "cash": "dataset.portfolio-position-observation",
    "trade": "dataset.trade-event",
    "price": "dataset.price-bar-daily",
    "fx": "dataset.fx-rate-daily",
}


def build_owned_portfolio_fixture_pipeline(
    source: FixtureSourceAdapter,
    repository: V2WarehouseRepository,
) -> PipelineDefinition:
    def collect(context: StageContext) -> StageResult:
        envelopes = source.collect({})
        for envelope in envelopes:
            repository.record_observation(DATASET_BY_TYPE[envelope.payload["type"]], envelope, context.run_id)
        return StageResult(
            output_count=len(envelopes),
            source_calls=1,
            evidence={"fixture": source.path.name, "content_hashes": [item.content_hash for item in envelopes]},
            lineage=tuple(
                LineageEvidence(f"{source.source_id}:{item.source_record_id}", DATASET_BY_TYPE[item.payload["type"]], "fixture-collect", "1.0.0")
                for item in envelopes
            ),
        )

    def normalize(context: StageContext) -> StageResult:
        rows = repository.connection.execute("""
            SELECT observation_id, source_id, source_record_id, observed_at, fetched_at,
                   content_hash, quality_status, payload
            FROM bronze.source_observations WHERE pipeline_run_id=? ORDER BY source_record_id
        """, [context.run_id]).fetchall()
        normalized = 0
        for row in rows:
            payload: dict[str, Any] = json.loads(row[7]) if isinstance(row[7], str) else row[7]
            envelope = SourceEnvelope(row[1], row[2], row[3], row[4], payload, row[5], row[6])
            observation_id = row[0]
            record_type = payload["type"]
            if record_type == "account":
                repository.upsert_account(payload, observation_id)
            elif record_type == "instrument":
                repository.upsert_instrument(payload, observation_id)
            elif record_type == "position":
                repository.upsert_position(payload, observation_id)
            elif record_type == "cash":
                repository.upsert_cash(payload, observation_id)
            elif record_type == "trade":
                repository.record_trade_with_lot(payload, observation_id)
            elif record_type == "price":
                repository.upsert_price_bar(payload, observation_id)
            elif record_type == "fx":
                repository.upsert_fx_rate(payload, observation_id)
            else:
                raise ValueError(f"unsupported fixture record type: {record_type}")
            normalized += 1
        return StageResult(
            input_count=len(rows),
            output_count=normalized,
            lineage=(LineageEvidence("bronze.source_observations", "silver.canonical-ledger", "fixture-normalize", "1.0.0"),),
        )

    def quality(context: StageContext) -> StageResult:
        position_count = repository.table_count("silver.position_snapshots")
        price_count = repository.table_count("silver.price_bars_daily")
        status = "pass" if position_count > 0 and price_count > 0 else "fail"
        if status == "fail":
            raise ValueError("fixture requires at least one position and matching price")
        return StageResult(
            input_count=position_count + price_count,
            output_count=position_count,
            quality=(QualityEvidence(
                "dataset.portfolio-daily-state", "fixture-position-price-coverage", status,
                f"positions={position_count},prices={price_count}", "positions>0,prices>0",
            ),),
        )

    def publish(context: StageContext) -> StageResult:
        count = repository.materialize_daily_state(
            evaluation_date=context.logical_date,
            slot=context.slot,
            as_of=datetime.combine(context.logical_date, datetime.min.time(), tzinfo=UTC),
        )
        return StageResult(
            output_count=count,
            lineage=(LineageEvidence("silver.position_snapshots+silver.price_bars_daily+silver.fx_rates_daily", "gold.portfolio_daily_state", "fixture-publish", "1.0.0"),),
        )

    return PipelineDefinition(
        pipeline_id="pipeline.owned-portfolio-core-v2",
        version="1.0.0",
        stages=(
            PipelineStage("collect-land", collect),
            PipelineStage("normalize", normalize),
            PipelineStage("quality", quality),
            PipelineStage("publish", publish),
        ),
        source_call_budget=5,
    )
