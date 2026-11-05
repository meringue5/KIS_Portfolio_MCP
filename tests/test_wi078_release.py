from pathlib import Path

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services import wi078_release as release
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


@pytest.mark.parametrize("fail_phase", [None, "pre", "post"])
def test_slot_migration_preserves_rows_and_requires_recoverable_backup(tmp_path, monkeypatch, fail_phase):
    path = tmp_path / "source.duckdb"
    with duckdb.connect(str(path)) as connection:
        MigrationRunner(connection).apply(through="0023")
        connection.execute("""INSERT INTO gold.alert_candidates VALUES (
            'candidate','identity','rule','1.0.0','instrument','synthetic',date '2026-11-05','kr-1430',
            'session',current_timestamp,'normal','normal','fingerprint','pass','lineage','{}','run',current_timestamp
        )""")
        before = release.fingerprints(connection)
    monkeypatch.setenv("KIS_DB_MODE", "motherduck")
    monkeypatch.setenv("KIS_RELEASE_GIT_SHA", "a" * 40)
    monkeypatch.setenv("KIS_RELEASE_IMAGE_DIGEST", "sha256:" + "b" * 64)

    def backup(*, connection, store, root, label):
        if fail_phase == label:
            raise RuntimeError("injected_backup_failure")
        manifest = export_v2_backup(connection, root / label, database="fixture")
        restored_path = root / f"{label}.duckdb"
        restore_v2_backup(root / label, restored_path)
        return manifest, dict(byte_size=1, index_sha256="synthetic", object_count=81), restored_path

    monkeypatch.setattr(release, "_backup_round_trip", backup)
    run = lambda: release.run_wi078_release(
        bucket="private-fixture", connection_factory=lambda: duckdb.connect(str(path)),
        store_factory=lambda _: object())
    if fail_phase:
        with pytest.raises(RuntimeError, match="injected_backup_failure"):
            run()
    else:
        result = run()
        assert result["applied_migrations"] == ["0024"]
        assert result["preserved_tables"] == len(before)
        assert run()["applied_migrations"] == []
    with duckdb.connect(str(path)) as connection:
        assert release.fingerprints(connection) == before
        assert ("0024" in MigrationRunner(connection).applied()) == (fail_phase != "pre")
