"""Private local content-addressed owner research intake adapter."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from kis_portfolio.ports.document import DocumentExtractorPort


class DocumentIntakeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentIntakeResult:
    document_sha256: str
    byte_size: int
    intake_status: str
    extraction_revision: int | None
    extraction_units: int


class OwnerResearchIntake:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        private_root: Path,
        *,
        max_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        self.connection = connection
        self.private_root = private_root.resolve()
        self.max_bytes = max_bytes

    def ingest(
        self,
        source_path: Path,
        *,
        rights_assertion: str,
        processing_allowed: bool,
        extractor: DocumentExtractorPort | None = None,
        issuer_ids: tuple[str, ...] = (),
        published_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentIntakeResult:
        source_path = source_path.resolve()
        if not source_path.is_file():
            raise DocumentIntakeError("document does not exist")
        if not rights_assertion.strip():
            raise DocumentIntakeError("owner rights assertion is required")
        if not processing_allowed:
            raise DocumentIntakeError("document terms or DRM do not permit processing")
        byte_size = source_path.stat().st_size
        if byte_size <= 0 or byte_size > self.max_bytes:
            raise DocumentIntakeError(f"PDF size must be between 1 and {self.max_bytes} bytes")
        with source_path.open("rb") as handle:
            signature = handle.read(5)
        if signature != b"%PDF-":
            raise DocumentIntakeError("file is not a PDF by signature")
        digest = self._sha256(source_path)
        destination = self.private_root / "objects" / "sha256" / digest[:2] / f"{digest}.pdf"
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not destination.exists():
            shutil.copyfile(source_path, destination)
            destination.chmod(0o600)
        provided_at = datetime.now(UTC)
        private_uri = destination.relative_to(self.private_root).as_posix()
        common_metadata = metadata or {}
        self.connection.execute("""
            INSERT INTO bronze.raw_object_manifest(
                content_hash, dataset_id, source_id, private_uri, media_type, byte_size,
                rights_class, sensitivity, source_published_at, metadata
            ) VALUES (?, 'dataset.owner-research-document', 'source.owner-provided-research-document',
                      ?, 'application/pdf', ?, 'restricted', 'restricted', ?, ?)
            ON CONFLICT(content_hash) DO NOTHING
        """, [digest, private_uri, byte_size, published_at, json.dumps(common_metadata)])
        self.connection.execute("""
            INSERT INTO bronze.owner_research_documents VALUES (
                ?, ?, ?, 'application/pdf', ?, ?, ?, ?, 'restricted', ?, 'accepted', ?
            ) ON CONFLICT(document_sha256) DO NOTHING
        """, [digest, private_uri, source_path.name, byte_size, json.dumps(issuer_ids), published_at,
              provided_at, rights_assertion, json.dumps(common_metadata)])
        revision = None
        units = 0
        if extractor is not None:
            existing = self.connection.execute("""
                SELECT max(extraction_revision), count(*)
                FROM silver.owner_research_extractions
                WHERE document_sha256=? AND extractor_id=? AND extractor_version=?
            """, [digest, extractor.extractor_id, extractor.extractor_version]).fetchone()
            if existing[0] is not None:
                return DocumentIntakeResult(digest, byte_size, "duplicate", existing[0], existing[1])
            revision = 1
            extracted = extractor.extract(destination)
            for unit in extracted:
                self.connection.execute("""
                    INSERT INTO silver.owner_research_extractions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'restricted')
                """, [digest, extractor.extractor_id, extractor.extractor_version, revision, unit.locator,
                      unit.text, json.dumps(unit.structured) if unit.structured is not None else None,
                      datetime.now(UTC), unit.quality_status])
            units = len(extracted)
        return DocumentIntakeResult(digest, byte_size, "accepted", revision, units)

    def metadata(self, document_sha256: str) -> dict[str, Any] | None:
        row = self.connection.execute("""
            SELECT document_sha256, original_filename, media_type, byte_size, issuer_ids,
                   published_at, provided_at, rights_class, intake_status
            FROM bronze.owner_research_documents WHERE document_sha256=?
        """, [document_sha256]).fetchone()
        if row is None:
            return None
        names = [item[0] for item in self.connection.description]
        return dict(zip(names, row))

    def extraction(self, document_sha256: str, *, owner_authorized: bool) -> list[dict[str, Any]]:
        if not owner_authorized:
            raise PermissionError("restricted extraction requires owner authorization")
        cursor = self.connection.execute("""
            SELECT extractor_id, extractor_version, extraction_revision, locator,
                   text_content, structured_content, quality_status
            FROM silver.owner_research_extractions WHERE document_sha256=? ORDER BY locator
        """, [document_sha256])
        names = [item[0] for item in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
