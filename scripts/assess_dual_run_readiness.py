#!/usr/bin/env python3
"""Assess supplied WI-045 evidence without any production side effect."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from kis_portfolio.platform.dual_run_readiness import assess_dual_run_readiness
from kis_portfolio.platform.production_guardrails import GuardrailValidationError


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("release_manifest", type=Path)
    parser.add_argument("cost_snapshot", type=Path)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    try:
        as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        if as_of.tzinfo is None:
            raise ValueError("--as-of must include a timezone")
        decision = assess_dual_run_readiness(
            _load(args.evidence),
            _load(args.release_manifest),
            _load(args.cost_snapshot),
            as_of=as_of,
        )
    except (GuardrailValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "errors": list(getattr(exc, "errors", [str(exc)]))}))
        return 2
    print(json.dumps(decision.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if decision.status == "pass" else 3


if __name__ == "__main__":
    sys.exit(main())
