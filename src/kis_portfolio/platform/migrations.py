"""Checksum-verified, explicit DuckDB/MotherDuck migration runner."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import duckdb


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    checksum: str
    sql: str
    path: Path


def discover_migrations(directory: Path) -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        stem = path.stem
        if "_" not in stem:
            raise MigrationError(f"migration name must be VERSION_name.sql: {path.name}")
        version, name = stem.split("_", 1)
        if not version.isdigit():
            raise MigrationError(f"migration version must be numeric: {path.name}")
        sql = path.read_text(encoding="utf-8")
        migrations.append(Migration(version, name, hashlib.sha256(sql.encode()).hexdigest(), sql, path))
    versions = [item.version for item in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError("duplicate migration version")
    return tuple(migrations)


class MigrationRunner:
    def __init__(self, connection: duckdb.DuckDBPyConnection, directory: Path | None = None) -> None:
        self.connection = connection
        self.directory = directory or Path(__file__).with_name("sql")

    def _bootstrap(self) -> None:
        self.connection.execute("CREATE SCHEMA IF NOT EXISTS control")
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS control.schema_migrations (
                version VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                checksum VARCHAR NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
            )
        """)

    def applied(self) -> dict[str, tuple[str, str]]:
        self._bootstrap()
        return {
            version: (name, checksum)
            for version, name, checksum in self.connection.execute(
                "SELECT version, name, checksum FROM control.schema_migrations"
            ).fetchall()
        }

    def apply(self, *, through: str | None = None) -> list[str]:
        self._bootstrap()
        applied = self.applied()
        executed: list[str] = []
        for migration in discover_migrations(self.directory):
            if through is not None and migration.version > through:
                break
            prior = applied.get(migration.version)
            if prior is not None:
                prior_name, prior_checksum = prior
                if prior_name != migration.name or prior_checksum != migration.checksum:
                    raise MigrationError(
                        f"checksum mismatch for migration {migration.version}: "
                        f"database={prior_checksum} file={migration.checksum}"
                    )
                continue
            self.connection.execute("BEGIN TRANSACTION")
            try:
                self.connection.execute(migration.sql)
                self.connection.execute(
                    "INSERT INTO control.schema_migrations(version, name, checksum) VALUES (?, ?, ?)",
                    [migration.version, migration.name, migration.checksum],
                )
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise
            executed.append(migration.version)
        return executed

    def require(self, minimum_version: str) -> None:
        applied = self.applied()
        if minimum_version not in applied:
            raise MigrationError(f"required schema version is not applied: {minimum_version}")
