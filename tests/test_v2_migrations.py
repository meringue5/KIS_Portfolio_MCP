from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationError, MigrationRunner


def test_fresh_v2_migration_is_idempotent(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "fresh.duckdb"))
    runner = MigrationRunner(con)
    assert runner.apply() == [
        "0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010",
        "0011", "0012", "0013", "0014", "0015",
    ]
    assert runner.apply() == []
    runner.require("0006")
    runner.require("0007")
    runner.require("0008")
    runner.require("0009")
    runner.require("0010")
    runner.require("0011")
    runner.require("0012")
    runner.require("0013")
    runner.require("0014")
    runner.require("0015")
    schemas = {row[0] for row in con.execute("SELECT schema_name FROM information_schema.schemata").fetchall()}
    assert {"bronze", "silver", "gold", "control"} <= schemas
    assert con.execute("SELECT count(*) FROM control.schema_migrations").fetchone()[0] == 15
    con.close()


def test_filing_migration_refuses_nonempty_legacy_foundation(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "legacy-filing.duckdb"))
    runner = MigrationRunner(con)
    assert runner.apply(through="0013")[-1] == "0013"
    con.execute(
        """
        INSERT INTO silver.filing_events VALUES (
            'issuer','legacy-filing','v1','annual',current_timestamp,current_timestamp,
            'source.sec-edgar',NULL,'pass'
        )
        """
    )

    with pytest.raises(duckdb.Error, match="requires empty legacy filing foundations"):
        runner.apply()

    assert "0014" not in runner.applied()
    assert con.execute("SELECT count(*) FROM silver.filing_events").fetchone()[0] == 1
    con.close()


def test_dividend_migration_refuses_nonempty_legacy_foundation(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "legacy-dividend.duckdb"))
    runner = MigrationRunner(con)
    assert runner.apply(through="0014")[-1] == "0014"
    con.execute(
        """
        INSERT INTO silver.dividend_events VALUES (
            'legacy-dividend','instrument','account','declared',DATE '2026-09-10',
            NULL,NULL,NULL,'KRW','legacy-source-fact','pass'
        )
        """
    )

    with pytest.raises(duckdb.Error, match="requires empty legacy dividend foundation"):
        runner.apply()

    assert "0015" not in runner.applied()
    assert con.execute("SELECT count(*) FROM silver.dividend_events").fetchone()[0] == 1
    con.close()


def test_migration_failure_resumes_and_checksum_drift_fails(tmp_path: Path) -> None:
    migrations = tmp_path / "sql"
    migrations.mkdir()
    (migrations / "0001_ok.sql").write_text("CREATE TABLE first_table(id INTEGER);", encoding="utf-8")
    (migrations / "0002_bad.sql").write_text("THIS IS NOT SQL;", encoding="utf-8")
    con = duckdb.connect(str(tmp_path / "resume.duckdb"))
    runner = MigrationRunner(con, migrations)
    with pytest.raises(duckdb.Error):
        runner.apply()
    assert set(runner.applied()) == {"0001"}
    (migrations / "0002_bad.sql").write_text("CREATE TABLE second_table(id INTEGER);", encoding="utf-8")
    assert runner.apply() == ["0002"]
    (migrations / "0001_ok.sql").write_text("CREATE TABLE changed(id INTEGER);", encoding="utf-8")
    with pytest.raises(MigrationError, match="checksum mismatch"):
        runner.apply()
    con.close()
