from __future__ import annotations

import importlib.util
import re
import shutil
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
