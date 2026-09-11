"""Executable V1-to-V2 Remote MCP migration contract for WI-044."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Disposition = Literal["consolidated", "async", "unsupported"]


@dataclass(frozen=True, slots=True)
class ToolMigration:
    v1_tool: str
    v2_tools: tuple[str, ...]
    disposition: Disposition
    reason_code: str
    guidance: str

    def unsupported_response(self) -> dict[str, object] | None:
        if self.disposition != "unsupported":
            return None
        return {
            "status": "unsupported",
            "capability": self.v1_tool,
            "reason_code": self.reason_code,
            "message": self.guidance,
            "replacement_tools": [],
        }


@dataclass(frozen=True, slots=True)
class RemoteMigrationManifest:
    schema_version: str
    v2_tools: tuple[str, ...]
    entries: tuple[ToolMigration, ...]

    def by_v1_tool(self) -> dict[str, ToolMigration]:
        return {entry.v1_tool: entry for entry in self.entries}


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[3] / "governance" / "project" / "remote-mcp-v2-migration.toml"


def load_remote_migration_manifest(path: Path | None = None) -> RemoteMigrationManifest:
    selected = path or default_manifest_path()
    with selected.open("rb") as handle:
        payload = tomllib.load(handle)
    entries = tuple(
        ToolMigration(
            v1_tool=str(item["v1_tool"]),
            v2_tools=tuple(str(value) for value in item["v2_tools"]),
            disposition=item["disposition"],
            reason_code=str(item["reason_code"]),
            guidance=str(item["guidance"]),
        )
        for item in payload["mappings"]
    )
    manifest = RemoteMigrationManifest(
        schema_version=str(payload["schema_version"]),
        v2_tools=tuple(str(value) for value in payload["v2_tools"]),
        entries=entries,
    )
    _validate(manifest)
    return manifest


def _validate(manifest: RemoteMigrationManifest) -> None:
    if manifest.schema_version != "1.0.0":
        raise ValueError("unsupported migration manifest schema")
    v1_names = [entry.v1_tool for entry in manifest.entries]
    if not v1_names or len(v1_names) != len(set(v1_names)):
        raise ValueError("V1 migration entries must be non-empty and unique")
    v2_names = set(manifest.v2_tools)
    if len(v2_names) != len(manifest.v2_tools):
        raise ValueError("V2 tool names must be unique")
    for entry in manifest.entries:
        if entry.disposition not in {"consolidated", "async", "unsupported"}:
            raise ValueError(f"invalid disposition: {entry.v1_tool}")
        if entry.disposition == "unsupported":
            if entry.v2_tools or not entry.reason_code.startswith("unsupported_"):
                raise ValueError(f"invalid unsupported mapping: {entry.v1_tool}")
        elif not entry.v2_tools or not set(entry.v2_tools).issubset(v2_names):
            raise ValueError(f"invalid V2 mapping: {entry.v1_tool}")
