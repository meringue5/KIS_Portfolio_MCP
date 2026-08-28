#!/usr/bin/env python3
"""Validate the repository-local Project Operating System contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


VALID_STATUSES = {
    "proposed",
    "ready",
    "in_progress",
    "blocked",
    "verified",
    "closed",
    "rejected",
}
VALID_TYPES = {
    "defect",
    "clarification",
    "change",
    "architecture",
    "incident",
    "maintenance",
    "governance",
}
REQUIRED_WORK_ITEM_FIELDS = {
    "id",
    "title",
    "status",
    "type",
    "owner",
    "decision_refs",
    "requirement_refs",
    "architecture_impact",
    "data_impact",
    "security_impact",
    "cost_impact",
}
REQUIRED_WORK_ITEM_HEADINGS = {
    "## Problem and evidence",
    "## Classification and contract",
    "## Scope",
    "## Acceptance criteria",
    "## Change impact",
    "## Plan",
    "## Evidence",
    "## Closeout",
}


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening YAML frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing YAML frontmatter delimiter") from exc

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"invalid frontmatter line: {line!r}")
        fields[key.strip()] = value.strip().strip('"\'')
    return fields, text


def require_text(path: Path, needles: list[str], errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"missing required file: {path}")
        return
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            errors.append(f"{path}: missing required contract text {needle!r}")


def check(root: Path) -> list[str]:
    errors: list[str] = []
    required_files = [
        "docs/governance/project-operating-system.md",
        "docs/governance/data-governance-harness.md",
        "docs/traceability.md",
        "docs/work-items/TEMPLATE.md",
        ".agent/skills/kis-project-os/SKILL.md",
        ".agent/skills/kis-data-governance/SKILL.md",
        "scripts/check.sh",
        ".githooks/pre-commit",
        ".githooks/pre-push",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/change-request.yml",
        ".github/ISSUE_TEMPLATE/architecture-change.yml",
        ".github/ISSUE_TEMPLATE/incident-data-quality.yml",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative}")

    require_text(
        root / "docs/governance/project-operating-system.md",
        ["Project Operating System", "Project Governance", "Data Governance Harness", "scripts/check.sh"],
        errors,
    )
    require_text(
        root / "AGENTS.md",
        ["Project Operating System", "Data Governance Harness", ".agent/skills/kis-project-os/SKILL.md"],
        errors,
    )
    require_text(
        root / "scripts/check.sh",
        ["run_data_governance", "check_data_governance.py"],
        errors,
    )
    require_text(
        root / ".github/workflows/ci.yml",
        ["bash scripts/check.sh full"],
        errors,
    )

    traceability_path = root / "docs/traceability.md"
    traceability = (
        traceability_path.read_text(encoding="utf-8")
        if traceability_path.is_file()
        else ""
    )
    work_items_dir = root / "docs/work-items"
    active: list[str] = []
    tracked = 0
    if work_items_dir.is_dir():
        for path in sorted(work_items_dir.glob("WI-*.md")):
            if path.name == "TEMPLATE.md":
                continue
            tracked += 1
            try:
                fields, text = parse_frontmatter(path)
            except ValueError as exc:
                errors.append(f"{path.relative_to(root)}: {exc}")
                continue

            missing = sorted(REQUIRED_WORK_ITEM_FIELDS - fields.keys())
            if missing:
                errors.append(
                    f"{path.relative_to(root)}: missing fields {', '.join(missing)}"
                )
            item_id = fields.get("id", "")
            if not re.fullmatch(r"WI-\d{3,}", item_id):
                errors.append(f"{path.relative_to(root)}: invalid id {item_id!r}")
            elif not path.name.startswith(f"{item_id}-"):
                errors.append(
                    f"{path.relative_to(root)}: filename must start with {item_id}-"
                )
            status = fields.get("status", "")
            if status not in VALID_STATUSES:
                errors.append(f"{path.relative_to(root)}: invalid status {status!r}")
            if status == "in_progress":
                active.append(item_id or path.name)
            item_type = fields.get("type", "")
            if item_type not in VALID_TYPES:
                errors.append(f"{path.relative_to(root)}: invalid type {item_type!r}")
            missing_headings = sorted(
                heading for heading in REQUIRED_WORK_ITEM_HEADINGS if heading not in text
            )
            if missing_headings:
                errors.append(
                    f"{path.relative_to(root)}: missing headings {', '.join(missing_headings)}"
                )
            if item_id and item_id not in traceability:
                errors.append(
                    f"{path.relative_to(root)}: {item_id} missing from docs/traceability.md"
                )

    if len(active) > 1:
        errors.append(
            "only one Work Item may be in_progress; active=" + ", ".join(active)
        )

    if not errors:
        print(
            "Project OS contract check passed. "
            f"tracked_work_items={tracked} active_work_items={len(active)}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="repository root",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    errors = check(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
