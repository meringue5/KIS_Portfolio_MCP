"""Load governed metric contracts into the runtime registry."""

from __future__ import annotations

import tomllib
from pathlib import Path

from kis_portfolio.modules.monitoring import MetricDefinition, MetricRegistry


DEFAULT_METRIC_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "governance" / "catalog" / "metrics.toml"


def load_metric_registry(path: Path | None = None) -> MetricRegistry:
    document = tomllib.loads((path or DEFAULT_METRIC_CONTRACT_PATH).read_text(encoding="utf-8"))
    definitions = [
        MetricDefinition.from_document(contract)
        for contract in document.get("contracts", [])
        if contract.get("status") in {"approved", "active"}
    ]
    return MetricRegistry(definitions)
