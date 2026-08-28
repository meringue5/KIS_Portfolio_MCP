"""Reusable V2 Parquet recovery primitives for local and managed operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.db.catalog import v2_backup_table_names, v2_object_by_qualified_name
from kis_portfolio.platform.migrations import MigrationRunner


TABLES = v2_backup_table_names()


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
    manifest: dict[str, Any] = {
        "manifest_version": 2,
        "created_at": datetime.now(UTC).isoformat(),
        "database": database,
        "tables": {},
        "object_bytes_included": False,
    }
    connection.execute("BEGIN TRANSACTION")
    try:
        for qualified in TABLES:
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
    if source_manifest.get("manifest_version") != 2:
        raise RuntimeError("only V2 backup manifest version 2 is supported")
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
    if manifest.get("manifest_version") != 2:
        raise RuntimeError("unsupported V2 backup manifest")
    manifest_tables = set(manifest.get("tables", {}))
    expected_tables = set(TABLES)
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
        MigrationRunner(connection).apply()
        for qualified, record in manifest["tables"].items():
            if qualified not in allowed or allowed[qualified].object_type != "table":
                raise RuntimeError(f"manifest contains unmanaged V2 table: {qualified}")
            path = root / record["path"]
            connection.execute(f"INSERT INTO {qualified} SELECT * FROM read_parquet({_quote(path)})")
            actual = int(connection.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0])
            if actual != record["rows"]:
                raise RuntimeError(f"row-count mismatch for {qualified}: {actual} != {record['rows']}")
            restored += 1
        for qualified, item in allowed.items():
            if item.object_type == "view":
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
    }
