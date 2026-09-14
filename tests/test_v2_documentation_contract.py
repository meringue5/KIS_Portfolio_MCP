import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts/check_v2_documentation.py"
SPEC = importlib.util.spec_from_file_location("check_v2_documentation", SCRIPT)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def test_every_repository_v1_document_has_a_safe_disposition_and_navigation_resolves():
    errors, counts = CHECKER.check(PROJECT_ROOT, CHECKER.DEFAULT_MANIFEST)

    assert errors == []
    assert counts["canonical_v2"] > 0
    assert counts["retained_historical_evidence"] > 0
    assert counts["superseded_redirect"] == 1
    assert counts["approved_deletion_candidate"] == 0


def test_manifest_does_not_use_broad_deletion_rules(tmp_path: Path):
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        """
schema_version = 1
scan_pattern = "V1"
classifications = ["approved_deletion_candidate"]
production_change_authorized = false
[[rules]]
id = "unsafe"
classification = "approved_deletion_candidate"
globs = ["docs/*.md"]
""".strip(),
        encoding="utf-8",
    )

    errors, _ = CHECKER.check(PROJECT_ROOT, manifest)

    assert "unsafe: deletion candidates require exact paths" in errors
