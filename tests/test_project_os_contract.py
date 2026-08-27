from __future__ import annotations

import importlib.util
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


def test_current_repository_satisfies_project_os_contract():
    checker = _load_checker()

    assert checker.check(REPO_ROOT) == []


def test_project_os_rejects_two_in_progress_work_items(tmp_path: Path):
    checker = _load_checker()
    target = tmp_path / "repo"
    required_paths = [
        "AGENTS.md",
        "docs/governance/project-operating-system.md",
        "docs/traceability.md",
        "docs/work-items/TEMPLATE.md",
        "docs/work-items/WI-000-project-operating-system.md",
        ".agent/skills/kis-project-os/SKILL.md",
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
    for relative in required_paths:
        source = REPO_ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    first = target / "docs/work-items/WI-000-project-operating-system.md"
    duplicate = target / "docs/work-items/WI-001-duplicate-active.md"
    duplicate.write_text(
        first.read_text(encoding="utf-8")
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
