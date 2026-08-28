#!/usr/bin/env python3
"""Validate the repository-local Project Operating System contract."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
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
RELATIONSHIP_FIELDS = {
    "milestone_ref",
    "delivery_refs",
    "parent_work_item",
    "depends_on",
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


def split_refs(value: str) -> list[str]:
    if not value or value.lower() == "none":
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def check_delivery_item_ids(root: Path, errors: list[str]) -> None:
    path = root / "docs/design/kis-portfolio-v2-delivery-plan.md"
    if not path.is_file():
        errors.append(f"missing required file: {path.relative_to(root)}")
        return
    item_ids = re.findall(
        r"^\s*-\s+`(V2-W\d{4})`",
        path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    duplicates = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
    if duplicates:
        errors.append(
            f"{path.relative_to(root)}: duplicate delivery item ids {', '.join(duplicates)}"
        )


def check_milestone_registry(
    root: Path,
    work_item_fields: dict[str, dict[str, str]],
    work_item_texts: dict[str, str],
    errors: list[str],
) -> None:
    path = root / "governance/project/milestones.toml"
    if not path.is_file():
        errors.append(f"missing required file: {path.relative_to(root)}")
        return
    try:
        registry = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"{path.relative_to(root)}: invalid TOML: {exc}")
        return

    if registry.get("schema_version") != 1:
        errors.append(f"{path.relative_to(root)}: schema_version must be 1")
    if registry.get("allocation_policy") != "append_only_max_plus_one":
        errors.append(
            f"{path.relative_to(root)}: allocation_policy must be append_only_max_plus_one"
        )

    milestones = registry.get("milestones", [])
    registered_items = registry.get("work_items", [])
    subitems = registry.get("subitems", [])
    if not isinstance(milestones, list) or not isinstance(registered_items, list):
        errors.append(f"{path.relative_to(root)}: milestones and work_items must be arrays")
        return

    milestone_by_id: dict[str, dict] = {}
    for milestone in milestones:
        milestone_id = milestone.get("id", "") if isinstance(milestone, dict) else ""
        if not re.fullmatch(r"MS-(?:\d{3}|[A-Z][A-Z0-9-]*)", milestone_id):
            errors.append(f"{path.relative_to(root)}: invalid milestone id {milestone_id!r}")
            continue
        if milestone_id in milestone_by_id:
            errors.append(f"{path.relative_to(root)}: duplicate milestone id {milestone_id}")
        milestone_by_id[milestone_id] = milestone

    for milestone_id, milestone in milestone_by_id.items():
        if milestone.get("status") not in VALID_STATUSES:
            errors.append(f"{path.relative_to(root)}: {milestone_id} invalid status")
        dependencies = milestone.get("depends_on")
        if not isinstance(dependencies, list):
            errors.append(f"{path.relative_to(root)}: {milestone_id} depends_on must be an array")
            continue
        for dependency in dependencies:
            if dependency not in milestone_by_id:
                errors.append(
                    f"{path.relative_to(root)}: {milestone_id} unknown milestone dependency "
                    f"{dependency!r}"
                )
            if dependency == milestone_id:
                errors.append(f"{path.relative_to(root)}: {milestone_id} cannot depend on itself")

    visiting_milestones: set[str] = set()
    visited_milestones: set[str] = set()

    def visit_milestone(milestone_id: str, trail: list[str]) -> None:
        if milestone_id in visited_milestones:
            return
        if milestone_id in visiting_milestones:
            errors.append(
                f"{path.relative_to(root)}: milestone dependency cycle "
                f"{' -> '.join(trail + [milestone_id])}"
            )
            return
        visiting_milestones.add(milestone_id)
        dependencies = milestone_by_id[milestone_id].get("depends_on", [])
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if dependency in milestone_by_id:
                    visit_milestone(dependency, trail + [milestone_id])
        visiting_milestones.remove(milestone_id)
        visited_milestones.add(milestone_id)

    for milestone_id in milestone_by_id:
        visit_milestone(milestone_id, [])

    item_by_id: dict[str, dict] = {}
    identity_owner: dict[str, str] = {}
    sequence_owner: dict[tuple[str, int], str] = {}
    for item in registered_items:
        item_id = item.get("id", "") if isinstance(item, dict) else ""
        if not re.fullmatch(r"WI-\d{3,}", item_id):
            errors.append(f"{path.relative_to(root)}: invalid registered Work Item id {item_id!r}")
            continue
        if item_id in item_by_id:
            errors.append(f"{path.relative_to(root)}: duplicate Work Item id {item_id}")
        item_by_id[item_id] = item

        identity = item.get("identity", "")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identity):
            errors.append(f"{path.relative_to(root)}: {item_id} invalid identity {identity!r}")
        elif identity in identity_owner:
            errors.append(
                f"{path.relative_to(root)}: duplicate identity {identity} for "
                f"{identity_owner[identity]} and {item_id}"
            )
        else:
            identity_owner[identity] = item_id

        milestone_id = item.get("milestone_id", "")
        if milestone_id not in milestone_by_id:
            errors.append(f"{path.relative_to(root)}: {item_id} unknown milestone {milestone_id!r}")
        sequence = item.get("sequence")
        if not isinstance(sequence, int) or sequence < 1:
            errors.append(f"{path.relative_to(root)}: {item_id} sequence must be a positive integer")
        else:
            sequence_key = (milestone_id, sequence)
            if sequence_key in sequence_owner:
                errors.append(
                    f"{path.relative_to(root)}: duplicate sequence {sequence} in {milestone_id} "
                    f"for {sequence_owner[sequence_key]} and {item_id}"
                )
            sequence_owner[sequence_key] = item_id

    for milestone_id, milestone in milestone_by_id.items():
        declared = milestone.get("work_item_ids", [])
        actual = [
            item["id"]
            for item in sorted(
                (
                    item
                    for item in registered_items
                    if isinstance(item, dict) and item.get("milestone_id") == milestone_id
                ),
                key=lambda item: item.get("sequence", 0),
            )
        ]
        if declared != actual:
            errors.append(
                f"{path.relative_to(root)}: {milestone_id} work_item_ids must match sequence order; "
                f"declared={declared!r} actual={actual!r}"
            )

    for item_id, item in item_by_id.items():
        fields = work_item_fields.get(item_id)
        if fields is None:
            errors.append(f"{path.relative_to(root)}: {item_id} has no Work Item file")
            continue
        missing_relationships = sorted(RELATIONSHIP_FIELDS - fields.keys())
        if missing_relationships:
            errors.append(
                f"{item_id}: missing relationship fields {', '.join(missing_relationships)}"
            )
            continue
        expected_parent = item.get("parent_id", "") or "none"
        comparisons = {
            "title": item.get("title", ""),
            "milestone_ref": item.get("milestone_id", ""),
            "parent_work_item": expected_parent,
        }
        for field, expected in comparisons.items():
            if fields.get(field, "") != expected:
                errors.append(
                    f"{item_id}: {field} mismatch; file={fields.get(field, '')!r} "
                    f"registry={expected!r}"
                )
        if split_refs(fields.get("delivery_refs", "")) != item.get("delivery_refs", []):
            errors.append(f"{item_id}: delivery_refs mismatch with milestone registry")
        if split_refs(fields.get("depends_on", "")) != item.get("depends_on", []):
            errors.append(f"{item_id}: depends_on mismatch with milestone registry")
        if "## Sub-items" not in work_item_texts.get(item_id, ""):
            errors.append(f"{item_id}: missing heading ## Sub-items")

        for dependency in item.get("depends_on", []):
            if dependency not in item_by_id:
                errors.append(f"{path.relative_to(root)}: {item_id} unknown dependency {dependency}")
            if dependency == item_id:
                errors.append(f"{path.relative_to(root)}: {item_id} cannot depend on itself")
        parent_id = item.get("parent_id", "")
        if parent_id and parent_id not in item_by_id:
            errors.append(f"{path.relative_to(root)}: {item_id} unknown parent {parent_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str, trail: list[str]) -> None:
        if item_id in visited:
            return
        if item_id in visiting:
            errors.append(
                f"{path.relative_to(root)}: dependency cycle {' -> '.join(trail + [item_id])}"
            )
            return
        visiting.add(item_id)
        for dependency in item_by_id[item_id].get("depends_on", []):
            if dependency in item_by_id:
                visit(dependency, trail + [item_id])
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in item_by_id:
        visit(item_id, [])

    subitem_ids: set[str] = set()
    for subitem in subitems if isinstance(subitems, list) else []:
        subitem_id = subitem.get("id", "") if isinstance(subitem, dict) else ""
        parent_id = subitem.get("parent_id", "") if isinstance(subitem, dict) else ""
        if subitem_id in subitem_ids:
            errors.append(f"{path.relative_to(root)}: duplicate sub-item id {subitem_id}")
        subitem_ids.add(subitem_id)
        if parent_id not in item_by_id:
            errors.append(f"{path.relative_to(root)}: {subitem_id} unknown parent {parent_id!r}")
            continue
        if not re.fullmatch(re.escape(parent_id) + r"-S\d{2,}", subitem_id):
            errors.append(f"{path.relative_to(root)}: invalid sub-item id {subitem_id!r}")
        if subitem.get("status") not in VALID_STATUSES:
            errors.append(f"{path.relative_to(root)}: {subitem_id} invalid status")
        if subitem_id not in work_item_texts.get(parent_id, ""):
            errors.append(f"{path.relative_to(root)}: {subitem_id} missing from parent Work Item")

    registered_numbers = [int(item_id.split("-")[1]) for item_id in item_by_id]
    if registered_numbers:
        registry_floor = min(registered_numbers)
        for item_id in work_item_fields:
            number = int(item_id.split("-")[1])
            if number >= registry_floor and item_id not in item_by_id:
                errors.append(f"{item_id}: missing from milestone registry")


def check(root: Path) -> list[str]:
    errors: list[str] = []
    required_files = [
        "docs/governance/project-operating-system.md",
        "docs/governance/data-governance-harness.md",
        "docs/traceability.md",
        "docs/milestones/README.md",
        "docs/work-items/TEMPLATE.md",
        "governance/project/milestones.toml",
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
        [
            "Project Operating System",
            "Data Governance Harness",
            ".agent/skills/kis-project-os/SKILL.md",
            "governance/project/milestones.toml",
        ],
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
    work_item_fields: dict[str, dict[str, str]] = {}
    work_item_texts: dict[str, str] = {}
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
            if item_id:
                if item_id in work_item_fields:
                    errors.append(f"duplicate Work Item file for {item_id}")
                work_item_fields[item_id] = fields
                work_item_texts[item_id] = text
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

    check_delivery_item_ids(root, errors)
    check_milestone_registry(root, work_item_fields, work_item_texts, errors)

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
