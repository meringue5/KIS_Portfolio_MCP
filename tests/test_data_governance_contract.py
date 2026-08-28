from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = (
    REPO_ROOT
    / ".agent"
    / "skills"
    / "kis-data-governance"
    / "scripts"
    / "check_data_governance.py"
)


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_data_governance", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_harness(target: Path) -> None:
    required_paths = [
        "AGENTS.md",
        "ARCHITECTURE.md",
        "SPEC.md",
        "scripts/check.sh",
        "docs/data-catalog.md",
        "docs/traceability.md",
        "docs/governance/data-governance-harness.md",
        "governance/contract-schema.toml",
        "governance/catalog/sources.toml",
        "governance/catalog/collections.toml",
        "governance/catalog/datasets.toml",
        "governance/catalog/metrics.toml",
        "governance/catalog/pipelines.toml",
        ".agent/skills/kis-data-governance/SKILL.md",
    ]
    for relative in required_paths:
        source = REPO_ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    # Fixture tests replace the source/dataset/collection registries below. Keep the
    # independently tested pipeline registry empty so repository contracts cannot
    # leak unresolved references into these isolated positive/negative cases.
    (target / "governance/catalog/pipelines.toml").write_text("schema_version = 1\n", encoding="utf-8")


def test_current_repository_satisfies_data_governance_contract():
    checker = _load_checker()

    assert checker.check(REPO_ROOT) == []


def test_governance_accepts_approved_source_dataset_and_collection(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_harness(target)
    (target / "governance/catalog/sources.toml").write_text(
        '''schema_version = 1

[[contracts]]
id = "source.kis"
version = "1.0.0"
status = "approved"
owner = "owner"
description = "KIS fixture source."
decision_refs = ["ADR-023"]
provider = "Korea Investment and Securities"
canonical_role = "canonical"
access_method = "REST API"
auth_class = "oauth"
license_class = "account-private"
sensitivity = "confidential"
region = "KR"
cost_class = "routine"
rate_limit_policy = "bounded fixture policy"
availability_slo = "daily close"
''',
        encoding="utf-8",
    )
    (target / "governance/catalog/datasets.toml").write_text(
        '''schema_version = 1

[[contracts]]
id = "dataset.portfolio-snapshot"
version = "1.0.0"
status = "approved"
owner = "owner"
description = "Portfolio fixture dataset."
decision_refs = ["ADR-023"]
layer = "bronze"
source_ids = ["source.kis"]
input_dataset_ids = []
purpose = "Preserve account observations."
grain = "one account observation per fetch"
natural_key = ["id"]
time_semantics = "fetched_at and effective_at"
write_mode = "append-only"
schema_contract = "fixture schema"
sensitivity = "confidential"
retention_policy = "indefinite canonical observation"
backup_policy = "parquet"
freshness_slo = "daily close"
quality_rules = ["id unique", "fetched_at not null"]
producer_pipeline_ids = []
consumer_ids = ["portfolio analysis"]
''',
        encoding="utf-8",
    )
    (target / "governance/catalog/collections.toml").write_text(
        '''schema_version = 1

[[contracts]]
id = "collection.initial-holdings"
version = "1.0.0"
status = "approved"
owner = "owner"
description = "Initial holdings fixture basket."
decision_refs = ["ADR-023"]
scope = "owned domestic and US holdings"
source_ids = ["source.kis"]
dataset_ids = ["dataset.portfolio-snapshot"]
priority = "required"
history_policy = "daily from activation"
schedule_policy = "market close"
trigger_policy = "platform scheduler"
cost_budget = "routine free-tier envelope"
acceptance_rules = ["five trading days terminal"]
''',
        encoding="utf-8",
    )

    assert checker.check(target) == []


def test_governance_rejects_unapproved_and_unresolved_dataset(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_harness(target)
    (target / "governance/catalog/datasets.toml").write_text(
        '''schema_version = 1

[[contracts]]
id = "dataset.example"
version = "1.0.0"
status = "active"
owner = "owner"
description = "Negative contract fixture."
decision_refs = []
layer = "silver"
source_ids = ["source.missing"]
input_dataset_ids = []
purpose = "Exercise reference validation."
grain = "one row per example"
natural_key = ["id"]
time_semantics = "effective_at"
write_mode = "upsert"
schema_contract = "fixture"
sensitivity = "internal"
retention_policy = "indefinite"
backup_policy = "parquet"
freshness_slo = "daily"
quality_rules = ["primary key unique"]
producer_pipeline_ids = []
consumer_ids = ["fixture"]
''',
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("requires decision_refs" in error for error in errors)
    assert any("references unknown id 'source.missing'" in error for error in errors)
