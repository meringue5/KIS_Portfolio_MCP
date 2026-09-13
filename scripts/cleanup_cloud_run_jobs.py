#!/usr/bin/env python3
"""Revalidate and delete the owner-approved WI-049 Cloud Run Jobs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from kis_portfolio.platform.production_guardrails import GuardrailValidationError
from kis_portfolio.platform.runtime_cleanup import execute_runtime_cleanup, load_object


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("approval", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = execute_runtime_cleanup(
            load_object(args.manifest),
            load_object(args.approval),
            apply=args.apply,
            github_actions=os.environ.get("GITHUB_ACTIONS") == "true",
            github_ref=os.environ.get("GITHUB_REF", ""),
        )
    except (GuardrailValidationError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "errors": getattr(exc, "errors", [str(exc)])}))
        return 2
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
