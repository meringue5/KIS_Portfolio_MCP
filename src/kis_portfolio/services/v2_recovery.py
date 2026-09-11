"""Reusable V2 Parquet recovery primitives for local and managed operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.db.catalog import v2_backup_table_names, v2_object_by_qualified_name
from kis_portfolio.platform.migrations import MigrationRunner, discover_migrations


TABLES = v2_backup_table_names()


def _applied_migration_prefix(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[list[dict[str, str]], tuple[str, ...], tuple[str, ...]]:
    """Return the verified migration prefix and its expected backup surface.

    Production backup is read-only.  The source ledger is compared with the
    immutable repository migrations, while a scratch database derives the exact
    table/view surface for that prefix.  This lets an older, still-supported
    production schema be backed up completely without pretending later objects
    already exist.
    """

    rows = connection.execute(
        "SELECT version, name, checksum FROM control.schema_migrations ORDER BY version"
    ).fetchall()
    discovered = discover_migrations(Path(__file__).parents[1] / "platform" / "sql")
    expected_prefix = discovered[: len(rows)]
    if not rows or len(rows) > len(discovered):
        raise RuntimeError("source migration ledger is not a supported non-empty prefix")
    manifest_rows: list[dict[str, str]] = []
    for actual, expected in zip(rows, expected_prefix, strict=True):
        version, name, checksum = map(str, actual)
        if (version, name, checksum) != (expected.version, expected.name, expected.checksum):
            raise RuntimeError(f"source migration ledger mismatch at version {version}")
        manifest_rows.append({"version": version, "name": name, "checksum": checksum})

    scratch = duckdb.connect(":memory:")
    try:
        MigrationRunner(scratch).apply(through=manifest_rows[-1]["version"])
        present = {
            f"{schema}.{name}": object_type
            for schema, name, object_type in scratch.execute(
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema IN ('bronze','silver','gold','control')
                """
            ).fetchall()
        }
    finally:
        scratch.close()
    tables = tuple(name for name in TABLES if present.get(name) == "BASE TABLE")
    views = tuple(
        name
        for name, item in v2_object_by_qualified_name().items()
        if item.object_type == "view" and present.get(name) == "VIEW"
    )
    return manifest_rows, tables, views


def _validate_manifest_migrations(
    records: Any,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if not isinstance(records, list) or not records:
        raise RuntimeError("version-aware V2 backup has no source migration prefix")
    discovered = discover_migrations(Path(__file__).parents[1] / "platform" / "sql")
    expected_prefix = discovered[: len(records)]
    if len(records) > len(discovered):
        raise RuntimeError("version-aware V2 backup has an unsupported migration prefix")
    for record, expected in zip(records, expected_prefix, strict=True):
        if not isinstance(record, dict) or set(record) != {"version", "name", "checksum"}:
            raise RuntimeError("version-aware V2 backup has invalid migration evidence")
        if (record["version"], record["name"], record["checksum"]) != (
            expected.version,
            expected.name,
            expected.checksum,
        ):
            raise RuntimeError(f"backup migration evidence mismatch at version {record.get('version')}")
    scratch = duckdb.connect(":memory:")
    try:
        MigrationRunner(scratch).apply(through=records[-1]["version"])
        present = {
            f"{schema}.{name}": object_type
            for schema, name, object_type in scratch.execute(
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema IN ('bronze','silver','gold','control')
                """
            ).fetchall()
        }
    finally:
        scratch.close()
    tables = tuple(name for name in TABLES if present.get(name) == "BASE TABLE")
    views = tuple(
        name
        for name, item in v2_object_by_qualified_name().items()
        if item.object_type == "view" and present.get(name) == "VIEW"
    )
    return str(records[-1]["version"]), tables, views


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def export_v2_backup(
    connection: duckdb.DuckDBPyConnection,
    output_dir: Path,
    *,
    database: str,
) -> dict[str, Any]:
    """Export the governed V2 table allowlist to a new private directory."""

    root = output_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    migrations, source_tables, _ = _applied_migration_prefix(connection)
    source_present = {
        f"{schema}.{name}"
        for schema, name in connection.execute(
            """
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_type='BASE TABLE'
              AND table_schema IN ('bronze','silver','gold','control')
            """
        ).fetchall()
    }
    missing = sorted(set(source_tables) - source_present)
    unexpected = sorted((source_present & set(TABLES)) - set(source_tables))
    if missing or unexpected:
        raise RuntimeError(
            f"source backup surface does not match migration prefix: missing={missing}, unexpected={unexpected}"
        )
    manifest: dict[str, Any] = {
        "manifest_version": 3,
        "created_at": datetime.now(UTC).isoformat(),
        "database": database,
        "source_migrations": migrations,
        "tables": {},
        "object_bytes_included": False,
    }
    connection.execute("BEGIN TRANSACTION")
    try:
        for qualified in source_tables:
            schema, table = qualified.split(".", 1)
            directory = root / schema
            directory.mkdir(exist_ok=True, mode=0o700)
            path = directory / f"{table}.parquet"
            rows = int(connection.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0])
            connection.execute(f"COPY (SELECT * FROM {qualified}) TO {_quote(path)} (FORMAT PARQUET)")
            path.chmod(0o600)
            manifest["tables"][qualified] = {"rows": rows, "path": f"{schema}/{table}.parquet"}
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest_path.chmod(0o600)
    return manifest


def upload_v2_backup(store: GCSObjectStore, backup_dir: Path) -> dict[str, Any]:
    """Upload one complete V2 backup and return its content-addressed index."""

    root = backup_dir.expanduser().resolve()
    source_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("manifest_version") not in {2, 3}:
        raise RuntimeError("only V2 backup manifest versions 2 and 3 are supported")
    objects = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        result = store.put_file(
            path,
            dataset_id="backup.v2",
            partition=root.name,
            media_type="application/json" if path.suffix == ".json" else "application/vnd.apache.parquet",
        )
        objects.append({
            "relative_path": relative,
            "uri": result.uri,
            "sha256": result.content_hash,
            "byte_size": result.byte_size,
        })
    index = {
        "backup_manifest_version": 1,
        "source_backup": root.name,
        "source_manifest_version": source_manifest["manifest_version"],
        "objects": objects,
    }
    result = store.put_bytes(
        json.dumps(index, sort_keys=True).encode(),
        dataset_id="backup.v2-index",
        partition=root.name,
        media_type="application/json",
    )
    return {
        "status": "uploaded",
        "object_count": len(objects),
        "byte_size": sum(item["byte_size"] for item in objects),
        "index_uri": result.uri,
        "index_sha256": result.content_hash,
    }


def download_v2_backup(
    store: GCSObjectStore,
    *,
    index_uri: str,
    index_sha256: str,
    destination: Path,
) -> dict[str, Any]:
    """Download and hash-verify a content-addressed V2 backup index."""

    target_root = destination.expanduser().resolve()
    if target_root.exists() and any(target_root.iterdir()):
        raise RuntimeError("restore destination must be absent or empty")
    target_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    index_path = target_root / ".recovery-index.json"
    store.download(index_uri, index_path, expected_sha256=index_sha256)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index_path.unlink()
    for item in index["objects"]:
        path = (target_root / item["relative_path"]).resolve()
        if target_root not in path.parents:
            raise RuntimeError("backup index contains an unsafe relative path")
        store.download(item["uri"], path, expected_sha256=item["sha256"])
        path.chmod(0o600)
    return {
        "status": "restored",
        "object_count": len(index["objects"]),
        "byte_size": sum(item["byte_size"] for item in index["objects"]),
        "destination": str(target_root),
    }


def restore_v2_backup(backup_dir: Path, database_path: Path | str) -> dict[str, Any]:
    """Restore a complete manifest to a fresh local DuckDB and verify counts/views."""

    root = backup_dir.expanduser().resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest_version = manifest.get("manifest_version")
    if manifest_version not in {2, 3}:
        raise RuntimeError("unsupported V2 backup manifest")
    manifest_tables = set(manifest.get("tables", {}))
    if manifest_version == 3:
        through_migration, expected_table_order, expected_views = _validate_manifest_migrations(
            manifest.get("source_migrations")
        )
        expected_tables = set(expected_table_order)
    else:
        through_migration = None
        expected_tables = set(TABLES)
        expected_views = tuple(
            name for name, item in v2_object_by_qualified_name().items() if item.object_type == "view"
        )
    if manifest_tables != expected_tables:
        missing = sorted(expected_tables - manifest_tables)
        extra = sorted(manifest_tables - expected_tables)
        raise RuntimeError(f"incomplete V2 backup manifest: missing={missing}, extra={extra}")

    in_memory = str(database_path) == ":memory:"
    target = None if in_memory else Path(database_path).expanduser().resolve()
    if target is not None and target.exists():
        raise RuntimeError("restore target must not already exist")
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    allowed = v2_object_by_qualified_name()
    connection = duckdb.connect(":memory:" if target is None else str(target))
    restored = 0
    try:
        MigrationRunner(connection).apply(through=through_migration)
        for qualified, record in manifest["tables"].items():
            if qualified not in allowed or allowed[qualified].object_type != "table":
                raise RuntimeError(f"manifest contains unmanaged V2 table: {qualified}")
            path = root / record["path"]
            connection.execute(f"INSERT INTO {qualified} SELECT * FROM read_parquet({_quote(path)})")
            actual = int(connection.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0])
            if actual != record["rows"]:
                raise RuntimeError(f"row-count mismatch for {qualified}: {actual} != {record['rows']}")
            restored += 1
        for qualified in expected_views:
            connection.execute(f"SELECT count(*) FROM {qualified}").fetchone()
    finally:
        connection.close()
    if target is not None:
        target.chmod(0o600)
    return {
        "status": "verified",
        "tables": restored,
        "database": ":memory:" if target is None else str(target),
        "object_bytes_included": bool(manifest.get("object_bytes_included")),
        "through_migration": through_migration or "latest",
    }
