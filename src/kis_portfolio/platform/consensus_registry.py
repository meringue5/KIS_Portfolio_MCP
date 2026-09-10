"""Runtime projection of the four approved Alpha forward-consensus contracts."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SOURCE_ID = "source.alpha-vantage-personal"
COLLECTION_ID = "collection.alpha-vantage-consensus-forward-v1"
DATASET_ID = "dataset.alpha-vantage-consensus-forward-snapshot"
PIPELINE_ID = "pipeline.alpha-vantage-consensus-forward-v1"
CONTRACT_VERSION = "1.0.0"


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _contract(path: Path, contract_id: str) -> dict[str, Any]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    candidates = [
        item for item in document.get("contracts", [])
        if item.get("id") == contract_id and item.get("version") == CONTRACT_VERSION
    ]
    if len(candidates) != 1:
        raise ValueError(f"exact consensus contract unavailable: {contract_id}")
    return candidates[0]


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ConsensusContractBundle:
    source: dict[str, Any]
    collection: dict[str, Any]
    dataset: dict[str, Any]
    pipeline: dict[str, Any]
    definition_hash: str
    activation_state: str = "inactive"


def load_consensus_contract_bundle(*, root: Path | None = None) -> ConsensusContractBundle:
    base = root or _root()
    source = _contract(base / "governance/catalog/sources.toml", SOURCE_ID)
    collection = _contract(base / "governance/catalog/collections.toml", COLLECTION_ID)
    dataset = _contract(base / "governance/catalog/datasets.toml", DATASET_ID)
    pipeline = _contract(base / "governance/catalog/pipelines.toml", PIPELINE_ID)
    contracts = (source, collection, dataset, pipeline)
    if any(item.get("status") != "approved" for item in contracts):
        raise ValueError("Alpha forward-consensus contracts must be approved but inactive")
    if source.get("canonical_role") != "secondary" or source.get("cost_class") != "free":
        raise ValueError("Alpha forward consensus must remain a free secondary source")
    if source.get("access_method", "").split(" only", 1)[0] != "Official HTTPS EARNINGS_ESTIMATES API":
        raise ValueError("Alpha forward consensus requires the exact official endpoint")
    if collection.get("source_ids") != [SOURCE_ID] or collection.get("dataset_ids") != [DATASET_ID]:
        raise ValueError("Alpha collection scope differs from the approved dedicated basket")
    if dataset.get("source_ids") != [SOURCE_ID] or dataset.get("producer_pipeline_ids") != [PIPELINE_ID]:
        raise ValueError("Alpha dataset lineage differs from the approved source and pipeline")
    if dataset.get("write_mode", "").split(";", 1)[0] != "append-only allowlisted normalized fields after complete response validation":
        raise ValueError("Alpha dataset must stay append-only and normalized-only")
    if dataset.get("sensitivity") != "restricted" or dataset.get("backup_policy") != "parquet":
        raise ValueError("Alpha dataset requires restricted private Parquet handling")
    if pipeline.get("source_ids") != [SOURCE_ID] or pipeline.get("output_dataset_ids") != [DATASET_ID]:
        raise ValueError("Alpha pipeline scope differs from the approved dedicated path")
    bundle_document = {
        "source": source,
        "collection": collection,
        "dataset": dataset,
        "pipeline": pipeline,
    }
    return ConsensusContractBundle(source, collection, dataset, pipeline, _hash(bundle_document))
