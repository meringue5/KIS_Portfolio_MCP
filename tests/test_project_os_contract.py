from __future__ import annotations

import importlib.util
import re
import shutil
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = (
    REPO_ROOT
    / ".agent"
    / "skills"
    / "kis-project-os"
    / "scripts"
    / "check_project_os.py"
)


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_project_os", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_project_os_fixture(target: Path) -> None:
    required_paths = [
        "AGENTS.md",
        "docs/governance/project-operating-system.md",
        "docs/governance/data-governance-harness.md",
        "docs/milestones/README.md",
        "docs/design/kis-portfolio-v2-delivery-plan.md",
        "docs/traceability.md",
        "docs/work-items/TEMPLATE.md",
        "governance/project/milestones.toml",
        ".agent/skills/kis-project-os/SKILL.md",
        ".agent/skills/kis-data-governance/SKILL.md",
        "scripts/check.sh",
        ".githooks/pre-commit",
        ".githooks/pre-push",
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/change-request.yml",
        ".github/ISSUE_TEMPLATE/architecture-change.yml",
        ".github/ISSUE_TEMPLATE/incident-data-quality.yml",
    ]
    required_paths.extend(
        str(path.relative_to(REPO_ROOT))
        for path in sorted((REPO_ROOT / "docs/work-items").glob("WI-*.md"))
    )
    for relative in required_paths:
        source = REPO_ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def test_current_repository_satisfies_project_os_contract():
    checker = _load_checker()

    assert checker.check(REPO_ROOT) == []


def test_current_milestone_baseline_supports_continuous_isolated_overlap():
    registry = tomllib.loads(
        (REPO_ROOT / "governance/project/milestones.toml").read_text(encoding="utf-8")
    )
    milestones = {item["id"]: item for item in registry["milestones"]}

    assert registry["schema_version"] == 2
    assert milestones["MS-002"]["status"] == "stabilizing"
    assert milestones["MS-002"]["rollback_policy"] == "append_only_feedback"
    assert milestones["MS-003"]["status"] == "in_progress"
    assert milestones["MS-003"]["implementation_gate"] == [
        {"milestone_id": "MS-002", "minimum_status": "stabilizing"}
    ]
    assert milestones["MS-003"]["production_gate"] == [
        {"milestone_id": "MS-002", "minimum_status": "closed"}
    ]
    assert milestones["MS-003"]["overlap_mode"] == "continuous_isolated"
    assert milestones["MS-003"]["overlap_work_item_ids"] == [
        "WI-035", "WI-037", "WI-038", "WI-039", "WI-040", "WI-041",
        "WI-042", "WI-043", "WI-044", "WI-045",
    ]
    assert milestones["MS-004"]["implementation_gate"] == [
        {"milestone_id": "MS-003", "minimum_status": "stabilizing"}
    ]


def test_initial_v2_alert_chain_preserves_but_excludes_etf_work():
    registry = tomllib.loads(
        (REPO_ROOT / "governance/project/milestones.toml").read_text(encoding="utf-8")
    )
    work_items = {item["id"]: item for item in registry["work_items"]}

    assert "WI-026" in next(
        milestone["work_item_ids"] for milestone in registry["milestones"] if milestone["id"] == "MS-002"
    )
    assert work_items["WI-027"]["depends_on"] == ["WI-009", "WI-017", "WI-026"]
    assert work_items["WI-028"]["depends_on"] == ["WI-019", "WI-023", "WI-025", "WI-033"]
    assert "status: rejected" in (
        REPO_ROOT / "docs/work-items/WI-026-etf-constituent-forward-collection.md"
    ).read_text(encoding="utf-8")
    assert "status: rejected" in (
        REPO_ROOT / "docs/work-items/WI-027-nested-etf-look-through.md"
    ).read_text(encoding="utf-8")


def test_project_os_rejects_two_in_progress_work_items(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)

    first = target / "docs/work-items/WI-000-project-operating-system.md"
    active_text = re.sub(
        r"^status: .+$",
        "status: in_progress",
        first.read_text(encoding="utf-8"),
        count=1,
        flags=re.MULTILINE,
    )
    first.write_text(active_text, encoding="utf-8")
    duplicate = target / "docs/work-items/WI-001-duplicate-active.md"
    duplicate.write_text(
        active_text
        .replace("id: WI-000", "id: WI-001", 1)
        .replace("# WI-000", "# WI-001", 1),
        encoding="utf-8",
    )
    traceability = target / "docs/traceability.md"
    traceability.write_text(
        traceability.read_text(encoding="utf-8") + "\nWI-001\n",
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("only one Work Item may be in_progress" in error for error in errors)


def test_project_os_rejects_registered_identity_drift(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "docs/work-items/WI-019-trend-volatility-metrics.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "title: Implement replay-safe trend and volatility metrics",
            "title: Silently redefined work",
            1,
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("WI-019: title mismatch" in error for error in errors)


def test_project_os_rejects_dangling_subitem_parent(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "governance/project/milestones.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'id = "WI-026-S01"\nparent_id = "WI-026"',
            'id = "WI-026-S01"\nparent_id = "WI-999"',
            1,
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("WI-026-S01 unknown parent" in error for error in errors)


def test_project_os_rejects_duplicate_delivery_item_ids(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "docs/design/kis-portfolio-v2-delivery-plan.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n- `V2-W0501` duplicate test item.\n",
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("duplicate delivery item ids V2-W0501" in error for error in errors)


def test_project_os_rejects_delivery_item_without_owner(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "governance/project/milestones.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'delivery_refs = ["V2-W0503"]',
            'delivery_refs = []',
            1,
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("delivery items without an owner V2-W0503" in error for error in errors)


def test_project_os_rejects_unknown_historical_delivery_owner(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "governance/project/milestones.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'work_item_ids = ["WI-002"]',
            'work_item_ids = ["WI-999"]',
            1,
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("V2-W0001 unknown historical owner WI-999" in error for error in errors)


def test_project_os_rejects_dangling_milestone_dependency(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "governance/project/milestones.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'id = "MS-004"\ntitle = "V2 canonicalization and V1 retirement"\n'
            'status = "proposed"\ndepends_on = ["MS-003"]',
            'id = "MS-004"\ntitle = "V2 canonicalization and V1 retirement"\n'
            'status = "proposed"\ndepends_on = ["MS-999"]',
            1,
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("MS-004 unknown milestone dependency 'MS-999'" in error for error in errors)


def test_project_os_rejects_stabilizing_work_item_without_exit_contract(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "docs/work-items/WI-055-scheduled-total-asset-digest.md"
    path.write_text(
        re.sub(
            r"^rollback_plan: .+$",
            "rollback_plan: none",
            path.read_text(encoding="utf-8"),
            count=1,
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("WI-055: stabilizing requires rollback_plan" in error for error in errors)


def test_project_os_rejects_ready_milestone_before_implementation_gate(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "governance/project/milestones.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'id = "MS-002"\ntitle = "Portfolio analytics, risk signals and Telegram delivery"\n'
            'status = "stabilizing"',
            'id = "MS-002"\ntitle = "Portfolio analytics, risk signals and Telegram delivery"\n'
            'status = "in_progress"',
            1,
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any(
        "MS-003 implementation_gate requires MS-002>=stabilizing, got in_progress" in error
        for error in errors
    )


def _activate_overlap_fixture(target: Path, item_id: str, filename: str) -> None:
    governance = target / "docs/work-items/WI-056-stabilization-lifecycle-overlap-gates.md"
    governance.write_text(
        governance.read_text(encoding="utf-8").replace(
            "status: in_progress", "status: closed", 1
        ),
        encoding="utf-8",
    )
    # The copied repository may legitimately have the current Work Item active.
    # Normalize that runtime state before constructing this synthetic one-item
    # overlap fixture, otherwise the test depends on when the suite is run.
    for candidate in (target / "docs/work-items").glob("WI-*.md"):
        if candidate.name == filename:
            continue
        candidate.write_text(
            re.sub(
                r"(?m)^status: in_progress$",
                "status: proposed",
                candidate.read_text(encoding="utf-8"),
                count=1,
            ),
            encoding="utf-8",
        )
    registry = target / "governance/project/milestones.toml"
    registry.write_text(
        registry.read_text(encoding="utf-8").replace(
            'id = "MS-GOV"\ntitle = "Project Operating System improvements"\nstatus = "in_progress"',
            'id = "MS-GOV"\ntitle = "Project Operating System improvements"\nstatus = "closed"',
            1,
        ),
        encoding="utf-8",
    )
    work_item = target / f"docs/work-items/{filename}"
    work_item.write_text(
        re.sub(
            r"(?m)^status: (?:proposed|ready|verified|stabilizing|closed)$",
            "status: in_progress",
            work_item.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )
    assert item_id in work_item.read_text(encoding="utf-8")


def test_project_os_allows_allowlisted_isolated_overlap(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    _activate_overlap_fixture(
        target, "WI-035", "WI-035-production-operations-cost-release-guardrails.md"
    )

    assert checker.check(target) == []


def test_project_os_rejects_production_effect_during_overlap(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    filename = "WI-035-production-operations-cost-release-guardrails.md"
    _activate_overlap_fixture(target, "WI-035", filename)
    path = target / f"docs/work-items/{filename}"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "production_effects: none", "production_effects: deploy", 1
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("WI-035: milestone overlap forbids deploy" in error for error in errors)


def _set_isolated_phase_metadata(path: Path) -> None:
    path.write_text(
        re.sub(
            r"(?m)^(depends_on: .+)$",
            r"\1\nexecution_scope: isolated\nproduction_effects: none",
            path.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )


def test_project_os_allows_next_dependency_ready_overlap_work_item(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    filename = "WI-037-filing-actual-fundamental-pipeline.md"
    _activate_overlap_fixture(target, "WI-037", filename)
    _set_isolated_phase_metadata(target / f"docs/work-items/{filename}")

    assert checker.check(target) == []


def test_project_os_rejects_overlap_before_work_item_dependencies_are_verified(
    tmp_path: Path,
):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    filename = "WI-038-dividend-event-ledger.md"
    _activate_overlap_fixture(target, "WI-038", filename)
    _set_isolated_phase_metadata(target / f"docs/work-items/{filename}")

    errors = checker.check(target)

    assert any("WI-038: implementation dependency WI-037" in error for error in errors)


def test_project_os_rejects_non_allowlisted_cutover_during_overlap(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    filename = "WI-046-remote-mcp-v2-production-cutover.md"
    _activate_overlap_fixture(target, "WI-046", filename)
    _set_isolated_phase_metadata(target / f"docs/work-items/{filename}")

    errors = checker.check(target)

    assert any(
        "WI-046: production gate is not satisfied and Work Item is not approved" in error
        for error in errors
    )


def test_project_os_rejects_declared_production_effect_before_gate_at_any_status(
    tmp_path: Path,
):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    path = target / "docs/work-items/WI-037-filing-actual-fundamental-pipeline.md"
    path.write_text(
        re.sub(
            r"(?m)^(depends_on: .+)$",
            r"\1\nexecution_scope: production\nproduction_effects: deploy",
            path.read_text(encoding="utf-8").replace(
                "status: proposed", "status: verified", 1
            ),
            count=1,
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any(
        "WI-037: production gate is not satisfied and forbids production_effects=deploy"
        in error
        for error in errors
    )


def test_feedback_relationship_can_close_a_recovery_loop_without_dependency_cycle(
    tmp_path: Path,
):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    registry = target / "governance/project/milestones.toml"
    registry.write_text(
        registry.read_text(encoding="utf-8").replace(
            'id = "WI-053"\nidentity = "work-item-dependency-visualization"\n'
            'title = "Publish the human-readable Work Item dependency map"\n'
            'milestone_id = "MS-GOV"\ndelivery_refs = []\ndepends_on = ["WI-052"]',
            'id = "WI-053"\nidentity = "work-item-dependency-visualization"\n'
            'title = "Publish the human-readable Work Item dependency map"\n'
            'milestone_id = "MS-GOV"\ndelivery_refs = []\ndepends_on = ["WI-052"]\n'
            'rollback_of = ["WI-056"]',
            1,
        ),
        encoding="utf-8",
    )
    work_item = target / "docs/work-items/WI-053-work-item-dependency-visualization.md"
    work_item.write_text(
        work_item.read_text(encoding="utf-8").replace(
            "depends_on: WI-052", "depends_on: WI-052\nrollback_of: WI-056", 1
        ),
        encoding="utf-8",
    )

    assert checker.check(target) == []


def test_project_os_still_rejects_structural_dependency_cycles(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    registry = target / "governance/project/milestones.toml"
    registry.write_text(
        registry.read_text(encoding="utf-8").replace(
            'id = "WI-053"\nidentity = "work-item-dependency-visualization"\n'
            'title = "Publish the human-readable Work Item dependency map"\n'
            'milestone_id = "MS-GOV"\ndelivery_refs = []\ndepends_on = ["WI-052"]',
            'id = "WI-053"\nidentity = "work-item-dependency-visualization"\n'
            'title = "Publish the human-readable Work Item dependency map"\n'
            'milestone_id = "MS-GOV"\ndelivery_refs = []\ndepends_on = ["WI-056"]',
            1,
        ),
        encoding="utf-8",
    )
    work_item = target / "docs/work-items/WI-053-work-item-dependency-visualization.md"
    work_item.write_text(
        work_item.read_text(encoding="utf-8").replace(
            "depends_on: WI-052", "depends_on: WI-056", 1
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("dependency cycle WI-053 -> WI-056 -> WI-053" in error for error in errors)


def test_project_os_rejects_unknown_feedback_target(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    _copy_project_os_fixture(target)
    registry = target / "governance/project/milestones.toml"
    registry.write_text(
        registry.read_text(encoding="utf-8").replace(
            'discovered_from = ["WI-030", "WI-055"]',
            'discovered_from = ["WI-999"]',
            1,
        ),
        encoding="utf-8",
    )
    work_item = target / "docs/work-items/WI-056-stabilization-lifecycle-overlap-gates.md"
    work_item.write_text(
        work_item.read_text(encoding="utf-8").replace(
            "discovered_from: WI-030, WI-055", "discovered_from: WI-999", 1
        ),
        encoding="utf-8",
    )

    errors = checker.check(target)

    assert any("WI-056 discovered_from unknown Work Item 'WI-999'" in error for error in errors)
