#!/usr/bin/env python3
"""Validate WI-035 review artifacts and emit deterministic JSON decisions."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

from kis_portfolio.platform.production_guardrails import (
    GuardrailValidationError,
    evaluate_cost_snapshot,
    plan_artifact_cleanup,
    validate_inventory,
    validate_release_manifest,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GuardrailValidationError((f"{path} must contain a JSON object",))
    return value


def _timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--as-of must include a timezone")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("validate-inventory")
    inventory.add_argument("inventory", type=Path)

    release = subparsers.add_parser("validate-release")
    release.add_argument("manifest", type=Path)

    cost = subparsers.add_parser("evaluate-cost")
    cost.add_argument("snapshot", type=Path)
    cost.add_argument("--as-of")

    cleanup = subparsers.add_parser("plan-cleanup")
    cleanup.add_argument("inventory", type=Path)
    cleanup.add_argument("manifest", type=Path)
    cleanup.add_argument("--as-of")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-inventory":
            output = validate_inventory(_load(args.inventory))
        elif args.command == "validate-release":
            output = validate_release_manifest(_load(args.manifest))
        elif args.command == "evaluate-cost":
            output = evaluate_cost_snapshot(
                _load(args.snapshot), as_of=_timestamp(args.as_of)
            ).as_dict()
        else:
            output = plan_artifact_cleanup(
                _load(args.inventory),
                _load(args.manifest),
                as_of=_timestamp(args.as_of),
            )
    except (GuardrailValidationError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "errors": getattr(exc, "errors", [str(exc)])}))
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
