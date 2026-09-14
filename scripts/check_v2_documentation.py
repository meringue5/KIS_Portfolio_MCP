"""Verify that every tracked Markdown document mentioning V1 has a disposition."""

from __future__ import annotations

import argparse
from collections import Counter
from fnmatch import fnmatchcase
from pathlib import Path
import re
import subprocess
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "governance/project/v1-document-disposition.toml"


def _repository_markdown(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return sorted(set(path for path in result.stdout.splitlines() if path))


def _check_navigation_links(root: Path, paths: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for path in paths:
        source = root / path
        if not source.is_file():
            errors.append(f"missing canonical navigation document: {path}")
            continue
        for target in link_pattern.findall(source.read_text(encoding="utf-8")):
            target = target.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "#")):
                continue
            resolved = (source.parent / target).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                errors.append(f"{path}: local link escapes repository: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{path}: broken local link: {target}")
    return errors


def _matching_rule(path: str, rules: list[dict[str, object]]) -> dict[str, object] | None:
    for rule in rules:
        if path in rule.get("paths", []):
            return rule
        if any(fnmatchcase(path, pattern) for pattern in rule.get("globs", [])):
            return rule
    return None


def check(root: Path = PROJECT_ROOT, manifest_path: Path = DEFAULT_MANIFEST) -> tuple[list[str], Counter[str]]:
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    allowed = set(manifest["classifications"])
    rules = manifest["rules"]
    pattern = re.compile(manifest["scan_pattern"])
    errors: list[str] = []
    counts: Counter[str] = Counter()

    if manifest.get("production_change_authorized") is not False:
        errors.append("documentation disposition must not authorize production changes")

    for rule in rules:
        classification = rule.get("classification")
        if classification not in allowed:
            errors.append(f"{rule.get('id', '<unknown>')}: invalid classification {classification!r}")
        if classification == "approved_deletion_candidate" and rule.get("globs"):
            errors.append(f"{rule.get('id', '<unknown>')}: deletion candidates require exact paths")
        for path in rule.get("paths", []):
            if not (root / path).is_file():
                errors.append(f"{rule.get('id', '<unknown>')}: missing exact path {path}")

    for path in _repository_markdown(root):
        text = (root / path).read_text(encoding="utf-8")
        if not pattern.search(text):
            continue
        rule = _matching_rule(path, rules)
        if rule is None:
            errors.append(f"unclassified V1-era document: {path}")
            continue
        counts[str(rule["classification"])] += 1

    errors.extend(_check_navigation_links(root, ("README.md", "docs/README.md")))

    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    errors, counts = check(args.root.resolve(), args.manifest.resolve())
    if errors:
        for error in errors:
            print(error)
        return 1
    summary = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
    print(f"V2 documentation contract check passed. {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
