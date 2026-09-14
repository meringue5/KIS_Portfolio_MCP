#!/usr/bin/env python3
"""Evaluate a versioned KIS Portfolio steady-state operations review."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from kis_portfolio.platform.production_guardrails import GuardrailValidationError
from kis_portfolio.platform.steady_state_operations import assess_steady_state_review


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GuardrailValidationError((f"{path} must contain a JSON object",))
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("cost_snapshot", type=Path)
    parser.add_argument("--as-of")
    args = parser.parse_args(argv)
    try:
        as_of = None
        if args.as_of:
            as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
            if as_of.tzinfo is None:
                raise ValueError("--as-of must include a timezone")
        result = assess_steady_state_review(
            _load(args.evidence), _load(args.cost_snapshot), as_of=as_of
        )
    except (GuardrailValidationError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "errors": getattr(exc, "errors", [str(exc)])}))
        return 2
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.status != "blocked" else 2


if __name__ == "__main__":
    sys.exit(main())
