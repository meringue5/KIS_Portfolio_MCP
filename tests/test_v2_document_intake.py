from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.document_store import DocumentIntakeError, OwnerResearchIntake
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.document import ExtractionUnit


class StaticExtractor:
    extractor_id = "fixture-extractor"
    extractor_version = "1.0.0"

    def extract(self, path: Path) -> tuple[ExtractionUnit, ...]:
        assert path.name.endswith(".pdf")
        return (
            ExtractionUnit("page:1", "Synthetic private research text."),
            ExtractionUnit("page:2/table:1", structured={"metric": "revenue", "value": 100}),
        )


def test_owner_pdf_intake_is_private_content_addressed_and_restricted(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "documents.duckdb"))
    MigrationRunner(con).apply()
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.4\nsynthetic fixture only\n%%EOF")
    private_root = tmp_path / "private"
    intake = OwnerResearchIntake(con, private_root)
    first = intake.ingest(
        source,
        rights_assertion="Owner confirms lawful personal analysis rights.",
        processing_allowed=True,
        extractor=StaticExtractor(),
        issuer_ids=("fixture-issuer",),
    )
    assert first.intake_status == "accepted"
    assert first.extraction_units == 2
    stored = private_root / "objects" / "sha256" / first.document_sha256[:2] / f"{first.document_sha256}.pdf"
    assert stored.read_bytes() == source.read_bytes()
    assert oct(stored.stat().st_mode & 0o777) == "0o600"
    assert "private_uri" not in intake.metadata(first.document_sha256)
    with pytest.raises(PermissionError):
        intake.extraction(first.document_sha256, owner_authorized=False)
    assert len(intake.extraction(first.document_sha256, owner_authorized=True)) == 2

    duplicate = intake.ingest(
        source,
        rights_assertion="Owner confirms lawful personal analysis rights.",
        processing_allowed=True,
        extractor=StaticExtractor(),
    )
    assert duplicate.intake_status == "duplicate"
    assert con.execute("SELECT count(*) FROM bronze.owner_research_documents").fetchone()[0] == 1
    con.close()


def test_owner_pdf_intake_rejects_non_pdf_and_disallowed_processing(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "reject.duckdb"))
    MigrationRunner(con).apply()
    intake = OwnerResearchIntake(con, tmp_path / "private")
    fake = tmp_path / "fake.pdf"
    fake.write_text("not a PDF", encoding="utf-8")
    with pytest.raises(DocumentIntakeError, match="not a PDF"):
        intake.ingest(fake, rights_assertion="owner", processing_allowed=True)
    real = tmp_path / "real.pdf"
    real.write_bytes(b"%PDF-1.4\n%%EOF")
    with pytest.raises(DocumentIntakeError, match="do not permit"):
        intake.ingest(real, rights_assertion="owner", processing_allowed=False)
    con.close()
