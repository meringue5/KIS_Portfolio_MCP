from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".agent/skills/kis-warehouse-contract/scripts/inspect_portfolio_db.py"
SPEC = importlib.util.spec_from_file_location("inspect_portfolio_db", SCRIPT)
assert SPEC and SPEC.loader
INSPECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTOR)


def _drift() -> dict:
    return {
        "missing_managed_objects": [],
        "unmanaged_objects": [
            {"schema": "main", "name": "cash_flow", "type": "table"},
        ],
        "managed_column_drift": [
            {
                "schema": "main",
                "name": "asset_overview_daily_snapshots",
                "missing_columns": ["quality_status"],
                "extra_columns": [],
                "type_mismatches": [],
            }
        ],
    }


def _registry() -> dict:
    return {
        "schema_version": 1,
        "production_change_authorized": False,
        "exceptions": [
            {
                "kind": "unmanaged_object",
                "schema": "main",
                "name": "cash_flow",
                "object_type": "table",
                "owner": "owner",
                "expires_on": date(2026, 12, 14),
                "next_action": "Open a separately approved Work Item.",
            },
            {
                "kind": "managed_column_drift",
                "schema": "main",
                "name": "asset_overview_daily_snapshots",
                "missing_columns": ["quality_status"],
                "extra_columns": [],
                "type_mismatches": [],
                "owner": "owner",
                "expires_on": date(2026, 12, 14),
                "next_action": "Open a separately approved migration Work Item.",
            },
        ],
    }


def test_exact_current_drift_exceptions_pass_without_authorizing_change() -> None:
    result = INSPECTOR.review_drift_exceptions(
        _drift(), _registry(), observed_on=date(2026, 9, 14)
    )

    assert result == {
        "status": "pass",
        "registered_exception_count": 2,
        "unregistered_drift": [],
        "expired_exceptions": [],
        "stale_exceptions": [],
        "missing_managed_objects": [],
        "blockers": [],
        "production_change_authorized": False,
    }


def test_changed_fingerprint_blocks() -> None:
    drift = _drift()
    drift["unmanaged_objects"][0]["type"] = "view"

    result = INSPECTOR.review_drift_exceptions(
        drift, _registry(), observed_on=date(2026, 9, 14)
    )

    assert result["status"] == "block"
    assert result["unregistered_drift"] == ["main.cash_flow"]
    assert result["stale_exceptions"] == ["main.cash_flow"]


def test_expired_ownerless_and_missing_managed_object_block() -> None:
    registry = _registry()
    registry["exceptions"][0]["owner"] = ""
    drift = _drift()
    drift["missing_managed_objects"] = ["gold.portfolio_daily_state"]

    result = INSPECTOR.review_drift_exceptions(
        drift, registry, observed_on=date(2027, 1, 1)
    )

    assert result["status"] == "block"
    assert sorted(result["expired_exceptions"]) == [
        "main.asset_overview_daily_snapshots",
        "main.cash_flow",
    ]
    assert "owner missing: main.cash_flow" in result["blockers"]
    assert "missing managed object: gold.portfolio_daily_state" in result["blockers"]


def test_repository_registry_is_non_authorizing_and_current() -> None:
    registry = INSPECTOR.load_drift_exception_registry()

    assert registry["work_item_id"] == "WI-051"
    assert registry["production_change_authorized"] is False
    assert len(registry["exceptions"]) == 4
    assert all(item["owner"] == "owner" for item in registry["exceptions"])
    assert all(item["expires_on"] == date(2026, 12, 14) for item in registry["exceptions"])
