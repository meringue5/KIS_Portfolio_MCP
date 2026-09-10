from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.filing_fixtures import (
    normalize_financial_fact,
    normalize_opendart_filing,
    normalize_sec_filing,
)
from kis_portfolio.adapters.outbound.filing_warehouse import FilingWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.modules.market.filings import IssuerAliasRevision, validate_artifact
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.filing_actuals import (
    FilingCallPlan,
    publish_partition_watermark,
    record_partition_quality,
    validate_call_plan,
)
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


BASE = datetime(2026, 9, 10, 3, tzinfo=UTC)


class FixturePrivateObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, payload: bytes, *, dataset_id: str, partition: str, media_type: str) -> StoredObject:
        digest = hashlib.sha256(payload).hexdigest()
        uri = f"fixture-private://{dataset_id}/{partition}/{digest}"
        created = uri not in self.objects
        self.objects[uri] = payload
        return StoredObject(uri, digest, len(payload), media_type, created)

    def download(self, uri: str, destination: Path, *, expected_sha256: str | None = None) -> Path:
        payload = self.objects[uri]
        digest = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("downloaded object SHA-256 does not match manifest")
        destination.write_bytes(payload)
        return destination


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    return connection


def _artifact(
    connection: duckdb.DuckDBPyConnection,
    *,
    source_id: str,
    source_record_id: str,
    payload: dict,
    observed_at: datetime,
    fetched_at: datetime,
    source_url: str,
    media_type: str = "application/json",
) -> tuple[str, str]:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    observation_id = V2WarehouseRepository(connection).record_observation(
        "dataset.filing-source-artifact",
        SourceEnvelope(
            source_id=source_id,
            source_record_id=source_record_id,
            observed_at=observed_at,
            fetched_at=fetched_at,
            payload=payload,
            content_hash=digest,
        ),
        "filing-fixture-run",
    )
    FilingWarehouseRepository(connection).record_artifact_manifest(
        observation_id=observation_id,
        stored=StoredObject(
            uri=f"fixture-private://filings/{digest}",
            content_hash=digest,
            byte_size=len(encoded),
            media_type=media_type,
            created=True,
        ),
        source_url=source_url,
        metadata={"fixture": True},
    )
    return observation_id, digest


def _alias(
    connection: duckdb.DuckDBPyConnection,
    *,
    observation_id: str,
    source_id: str,
    issuer_id: str,
    alias_type: str,
    alias_value: str,
    knowledge_at: datetime,
) -> str:
    return FilingWarehouseRepository(connection).record_alias(
        IssuerAliasRevision(
            issuer_id=issuer_id,
            source_id=source_id,
            jurisdiction="KR" if source_id == "source.opendart" else "US",
            alias_type=alias_type,
            alias_value=alias_value,
            market="KRX" if source_id == "source.opendart" else "NASDAQ",
            source_valid_from=datetime(2000, 1, 1, tzinfo=UTC),
            observed_at=knowledge_at,
            knowledge_at=knowledge_at,
            relation_quality="verified",
            provenance={"fixture": True},
        ),
        evidence_observation_id=observation_id,
    )


def test_opendart_day_precision_fact_and_mapping_are_point_in_time() -> None:
    connection = _connection()
    payload = {
        "rcept_no": "20260910000001",
        "rcept_dt": "20260910",
        "report_nm": "반기보고서",
        "reprt_code": "11012",
        "bsns_year": "2026",
        "period_end": "20260630",
        "fs_div": "CFS",
    }
    observation_id, digest = _artifact(
        connection,
        source_id="source.opendart",
        source_record_id=payload["rcept_no"],
        payload=payload,
        observed_at=BASE,
        fetched_at=BASE,
        source_url="https://opendart.fss.or.kr/api/list.json",
    )
    issuer_id = "KR:DART:00126380"
    alias_id = _alias(
        connection,
        observation_id=observation_id,
        source_id="source.opendart",
        issuer_id=issuer_id,
        alias_type="corp_code",
        alias_value="00126380",
        knowledge_at=BASE,
    )
    repository = FilingWarehouseRepository(connection)
    filing = normalize_opendart_filing(
        payload,
        corp_code="00126380",
        observed_at=BASE,
        fetched_at=BASE,
        raw_object_hash=digest,
    )
    assert filing.source_available_at == datetime(2026, 9, 10, 15, tzinfo=UTC)
    identity_id, revision_id = repository.record_filing(filing, observation_id=observation_id)
    assert repository.record_filing(filing, observation_id=observation_id) == (
        identity_id,
        revision_id,
    )
    fact = normalize_financial_fact(
        {
            "taxonomy": "dart",
            "concept": "ifrs-full_Revenue",
            "period_start": "20260101",
            "period_end": "20260630",
            "unit": "KRW",
            "value": "123456789",
            "decimals": "0",
            "dimensions": {"Consolidation": "CFS"},
        },
        source_available_at=filing.source_available_at,
        knowledge_at=filing.knowledge_at,
        statement_scope="CFS",
    )
    fact_id = repository.record_fact(revision_id, fact)
    assert repository.record_fact(revision_id, fact) == fact_id
    assert connection.execute(
        "SELECT count(*) FROM control.lineage_edges WHERE run_id='filing-fixture-run'"
    ).fetchone()[0] == 2

    before_mapping = repository.facts_as_of(
        issuer_id=issuer_id, cutoff_at=BASE + timedelta(minutes=1)
    )
    assert before_mapping[0]["taxonomy"] == "dart"
    assert before_mapping[0]["concept"] == "ifrs-full_Revenue"
    assert before_mapping[0]["typed_value"] == Decimal("123456789")
    assert before_mapping[0]["mapping_quality"] == "unmapped"

    mapping_at = BASE + timedelta(hours=1)
    repository.register_mapping({
        "mapping_id": "mapping.revenue.dart",
        "version": "1.0.0",
        "source_id": "source.opendart",
        "taxonomy": "dart",
        "concept": "ifrs-full_Revenue",
        "normalized_concept": "revenue",
        "unit_constraint": "KRW",
        "period_type_constraint": "duration",
        "statement_scope_constraint": "CFS",
        "review_status": "reviewed",
        "valid_from": BASE,
        "knowledge_at": mapping_at,
        "provenance": {"owner_review": "fixture"},
    })
    mapped = repository.facts_as_of(
        issuer_id=issuer_id, cutoff_at=mapping_at
    )
    assert mapped[0]["normalized_concept"] == "revenue"
    assert mapped[0]["mapping_version"] == "1.0.0"
    assert connection.execute(
        "SELECT relation_quality FROM silver.issuer_source_aliases_current"
    ).fetchone() == ("verified",)
    assert alias_id
    connection.close()


def test_sec_verified_amendment_supersedes_only_after_the_selected_clock() -> None:
    connection = _connection()
    repository = FilingWarehouseRepository(connection)
    cik = "0000320193"
    issuer_id = f"US:SEC:{cik}"
    base_payload = {
        "accessionNumber": "0000320193-26-000001",
        "acceptanceDateTime": "20260909090000",
        "form": "10-Q",
        "reportDate": "20260630",
        "periodStart": "20260401",
        "primaryDocument": "base.htm",
    }
    base_observation, base_hash = _artifact(
        connection,
        source_id="source.sec-edgar",
        source_record_id=base_payload["accessionNumber"],
        payload=base_payload,
        observed_at=BASE,
        fetched_at=BASE,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/base.htm",
    )
    _alias(
        connection,
        observation_id=base_observation,
        source_id="source.sec-edgar",
        issuer_id=issuer_id,
        alias_type="cik",
        alias_value=cik,
        knowledge_at=BASE,
    )
    base = normalize_sec_filing(
        base_payload,
        cik=cik,
        observed_at=BASE,
        fetched_at=BASE,
        raw_object_hash=base_hash,
    )
    _, base_revision_id = repository.record_filing(base, observation_id=base_observation)

    amendment_known = BASE + timedelta(days=1)
    amendment_payload = {
        "accessionNumber": "0000320193-26-000002",
        "acceptanceDateTime": "20260909100000",
        "form": "10-Q/A",
        "reportDate": "20260630",
        "periodStart": "20260401",
        "primaryDocument": "amendment.htm",
    }
    amendment_observation, amendment_hash = _artifact(
        connection,
        source_id="source.sec-edgar",
        source_record_id=amendment_payload["accessionNumber"],
        payload=amendment_payload,
        observed_at=amendment_known,
        fetched_at=amendment_known,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/amendment.htm",
    )
    amendment = normalize_sec_filing(
        amendment_payload,
        cik=cik,
        observed_at=amendment_known,
        fetched_at=amendment_known,
        raw_object_hash=amendment_hash,
        target_accession_number=base_payload["accessionNumber"],
        verified_relation=True,
    )
    _, amendment_revision_id = repository.record_filing(
        amendment, observation_id=amendment_observation
    )

    system_before = repository.filings_as_of(
        issuer_id=issuer_id, cutoff_at=BASE + timedelta(hours=1)
    )
    assert [item["filing_revision_id"] for item in system_before] == [base_revision_id]
    system_after = repository.filings_as_of(
        issuer_id=issuer_id, cutoff_at=amendment_known
    )
    assert [item["filing_revision_id"] for item in system_after] == [amendment_revision_id]
    retrospective = repository.filings_as_of(
        issuer_id=issuer_id,
        cutoff_at=datetime(2026, 9, 9, 11, tzinfo=UTC),
        query_mode="retrospective_source_as_of",
    )
    assert [item["filing_revision_id"] for item in retrospective] == [amendment_revision_id]
    assert retrospective[0]["query_mode"] == "retrospective_source_as_of"
    assert connection.execute(
        "SELECT is_superseded FROM silver.filing_revisions_current WHERE filing_revision_id=?",
        [base_revision_id],
    ).fetchone() == (True,)
    connection.close()


def test_candidate_correction_does_not_silently_supersede() -> None:
    connection = _connection()
    repository = FilingWarehouseRepository(connection)
    base_payload = {
        "rcept_no": "20260910000010",
        "rcept_dt": "20260909",
        "report_nm": "사업보고서",
        "reprt_code": "11011",
    }
    base_observation, base_hash = _artifact(
        connection,
        source_id="source.opendart",
        source_record_id=base_payload["rcept_no"],
        payload=base_payload,
        observed_at=BASE,
        fetched_at=BASE,
        source_url="https://opendart.fss.or.kr/api/list.json",
    )
    issuer_id = "KR:DART:00126380"
    _alias(
        connection,
        observation_id=base_observation,
        source_id="source.opendart",
        issuer_id=issuer_id,
        alias_type="corp_code",
        alias_value="00126380",
        knowledge_at=BASE,
    )
    base = normalize_opendart_filing(
        base_payload,
        corp_code="00126380",
        observed_at=BASE,
        fetched_at=BASE,
        raw_object_hash=base_hash,
    )
    repository.record_filing(base, observation_id=base_observation)
    corrected_payload = base_payload | {
        "rcept_no": "20260910000011",
        "report_nm": "[정정] 사업보고서",
    }
    corrected_observation, corrected_hash = _artifact(
        connection,
        source_id="source.opendart",
        source_record_id=corrected_payload["rcept_no"],
        payload=corrected_payload,
        observed_at=BASE + timedelta(minutes=1),
        fetched_at=BASE + timedelta(minutes=1),
        source_url="https://opendart.fss.or.kr/api/list.json",
    )
    candidate = normalize_opendart_filing(
        corrected_payload,
        corp_code="00126380",
        observed_at=BASE + timedelta(minutes=1),
        fetched_at=BASE + timedelta(minutes=1),
        raw_object_hash=corrected_hash,
    )
    repository.record_filing(candidate, observation_id=corrected_observation)
    visible = repository.filings_as_of(
        issuer_id=issuer_id, cutoff_at=BASE + timedelta(minutes=2)
    )
    assert len(visible) == 2
    assert {item["quality_status"] for item in visible} == {"pass", "partial"}
    connection.close()


def test_silver_publish_fails_closed_without_manifest_or_verified_alias() -> None:
    connection = _connection()
    payload = {
        "accessionNumber": "0000320193-26-000010",
        "acceptanceDateTime": "20260910010000",
        "form": "10-K",
        "reportDate": "20260630",
        "primaryDocument": "x.htm",
    }
    encoded = json.dumps(payload, sort_keys=True).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    observation_id = V2WarehouseRepository(connection).record_observation(
        "dataset.filing-source-artifact",
        SourceEnvelope(
            "source.sec-edgar", payload["accessionNumber"], BASE, BASE,
            payload, digest,
        ),
    )
    filing = normalize_sec_filing(
        payload,
        cik="0000320193",
        observed_at=BASE,
        fetched_at=BASE,
        raw_object_hash=digest,
    )
    repository = FilingWarehouseRepository(connection)
    with pytest.raises(ValueError, match="private raw object"):
        repository.record_filing(filing, observation_id=observation_id)
    repository.record_artifact_manifest(
        observation_id=observation_id,
        stored=StoredObject(
            "fixture-private://x", digest, len(encoded), "application/json", True
        ),
        source_url="https://data.sec.gov/submissions/CIK0000320193.json",
    )
    with pytest.raises(ValueError, match="verified issuer alias"):
        repository.record_filing(filing, observation_id=observation_id)
    connection.close()


def test_artifact_guard_rejects_media_host_and_secret_metadata() -> None:
    connection = _connection()
    payload = {"accessionNumber": "fixture"}
    encoded = json.dumps(payload).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    observation_id = V2WarehouseRepository(connection).record_observation(
        "dataset.filing-source-artifact",
        SourceEnvelope("source.sec-edgar", "fixture", BASE, BASE, payload, digest),
    )
    repository = FilingWarehouseRepository(connection)
    with pytest.raises(ValueError, match="media type"):
        repository.record_artifact_manifest(
            observation_id=observation_id,
            stored=StoredObject("fixture-private://x", digest, len(encoded), "text/plain", True),
            source_url="https://www.sec.gov/x",
        )
    with pytest.raises(ValueError, match="official host"):
        repository.record_artifact_manifest(
            observation_id=observation_id,
            stored=StoredObject("fixture-private://x", digest, len(encoded), "application/json", True),
            source_url="https://example.com/x",
        )
    with pytest.raises(ValueError, match="credential"):
        repository.record_artifact_manifest(
            observation_id=observation_id,
            stored=StoredObject("fixture-private://x", digest, len(encoded), "application/json", True),
            source_url="https://www.sec.gov/x",
            metadata={"nested": {"api_key": "must-not-persist"}},
        )
    connection.close()


def test_private_filing_object_round_trip_keeps_exact_hash(tmp_path: Path) -> None:
    connection = _connection()
    store = FixturePrivateObjectStore()
    payload = b'{"fixture":"official-filing-document"}'
    stored = store.put_bytes(
        payload,
        dataset_id="dataset.filing-source-artifact",
        partition="source.sec-edgar",
        media_type="application/json",
    )
    observation_id = V2WarehouseRepository(connection).record_observation(
        "dataset.filing-source-artifact",
        SourceEnvelope(
            "source.sec-edgar", "fixture-document", BASE, BASE,
            {"fixture": "official-filing-document"}, stored.content_hash,
        ),
    )
    FilingWarehouseRepository(connection).record_artifact_manifest(
        observation_id=observation_id,
        stored=stored,
        source_url="https://www.sec.gov/Archives/edgar/data/fixture.json",
    )
    restored = store.download(
        stored.uri,
        tmp_path / "restored.json",
        expected_sha256=stored.content_hash,
    )
    assert restored.read_bytes() == payload
    assert connection.execute(
        "SELECT content_hash,private_uri FROM bronze.raw_object_manifest"
    ).fetchone() == (stored.content_hash, stored.uri)
    connection.close()


def test_verified_alias_cannot_overlap_a_different_issuer() -> None:
    connection = _connection()
    payload = {"rcept_no": "alias-evidence"}
    observation_id, _ = _artifact(
        connection,
        source_id="source.opendart",
        source_record_id="alias-evidence",
        payload=payload,
        observed_at=BASE,
        fetched_at=BASE,
        source_url="https://opendart.fss.or.kr/api/list.json",
    )
    _alias(
        connection,
        observation_id=observation_id,
        source_id="source.opendart",
        issuer_id="KR:DART:00126380",
        alias_type="corp_code",
        alias_value="00126380",
        knowledge_at=BASE,
    )
    with pytest.raises(ValueError, match="overlaps a different issuer"):
        _alias(
            connection,
            observation_id=observation_id,
            source_id="source.opendart",
            issuer_id="KR:DART:99999999",
            alias_type="corp_code",
            alias_value="00126380",
            knowledge_at=BASE + timedelta(seconds=1),
        )
    connection.close()


def test_call_plan_and_artifact_capacity_stop_before_execution() -> None:
    plan = FilingCallPlan(
        source_id="source.opendart",
        mode="routine",
        partition_calls={"KR:DART:00126380": 20, "KR:DART:00164779": 19},
        search_pages={"KR:DART:00126380": 2, "KR:DART:00164779": 1},
    )
    assert validate_call_plan(plan).physical_calls == 39
    assert len(plan.plan_hash) == 64
    with pytest.raises(ValueError, match="issuer physical-call budget"):
        validate_call_plan(FilingCallPlan(
            "source.opendart", "routine", {"KR:DART:00126380": 21},
            {"KR:DART:00126380": 2},
        ))
    with pytest.raises(ValueError, match="two pages"):
        validate_call_plan(FilingCallPlan(
            "source.opendart", "routine", {"KR:DART:00126380": 3},
            {"KR:DART:00126380": 3},
        ))
    with pytest.raises(ValueError, match="200 MiB"):
        validate_artifact(
            media_type="application/zip",
            byte_size=1,
            expanded_archive_bytes=200 * 1024 * 1024 + 1,
        )
    with pytest.raises(ValueError, match="encrypted"):
        validate_artifact(
            media_type="application/zip", byte_size=1, encrypted_archive=True
        )
    with pytest.raises(ValueError, match="unsafe member path"):
        validate_artifact(
            media_type="application/zip",
            byte_size=1,
            archive_members=1,
            archive_member_paths=("../escape.xml",),
        )


def test_watermark_advances_only_after_pass_and_never_moves_backwards() -> None:
    connection = _connection()
    partial_quality = record_partition_quality(
        connection,
        run_id="run-partial",
        source_id="source.sec-edgar",
        partition_key="US:SEC:0000320193",
        rule_id="filing_partition_complete",
        status="partial",
        observed_value="1/2",
        expected_value="2/2",
        evaluated_at=BASE,
    )
    assert publish_partition_watermark(
        connection,
        run_id="run-partial",
        source_id="source.sec-edgar",
        partition_key="US:SEC:0000320193",
        watermark_value="2026-09-10T01:00:00Z",
        quality_result_id=partial_quality,
        observed_at=BASE,
    ) is False
    assert connection.execute("SELECT count(*) FROM control.watermarks").fetchone()[0] == 0
    pass_quality = record_partition_quality(
        connection,
        run_id="run-pass",
        source_id="source.sec-edgar",
        partition_key="US:SEC:0000320193",
        rule_id="filing_partition_complete",
        status="pass",
        observed_value="2/2",
        expected_value="2/2",
        evaluated_at=BASE,
    )
    assert publish_partition_watermark(
        connection,
        run_id="run-pass",
        source_id="source.sec-edgar",
        partition_key="US:SEC:0000320193",
        watermark_value="2026-09-10T01:00:00Z",
        quality_result_id=pass_quality,
        observed_at=BASE,
    ) is True
    with pytest.raises(ValueError, match="cannot move backwards"):
        old_quality = record_partition_quality(
            connection,
            run_id="run-old",
            source_id="source.sec-edgar",
            partition_key="US:SEC:0000320193",
            rule_id="filing_partition_complete",
            status="pass",
            observed_value="2/2",
            expected_value="2/2",
            evaluated_at=BASE + timedelta(minutes=1),
        )
        publish_partition_watermark(
            connection,
            run_id="run-old",
            source_id="source.sec-edgar",
            partition_key="US:SEC:0000320193",
            watermark_value="2026-09-09T01:00:00Z",
            quality_result_id=old_quality,
            observed_at=BASE + timedelta(minutes=1),
        )
    assert connection.execute(
        "SELECT watermark_value,run_id FROM control.watermarks"
    ).fetchone() == ("2026-09-10T01:00:00Z", "run-pass")
    connection.close()


def test_filing_revision_tables_round_trip_through_governed_backup(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "filing-source.duckdb"))
    MigrationRunner(source).apply()
    payload = {
        "accessionNumber": "0000320193-26-000099",
        "acceptanceDateTime": "20260910010000",
        "form": "10-Q",
        "reportDate": "20260630",
        "primaryDocument": "fixture.htm",
    }
    observation_id, digest = _artifact(
        source,
        source_id="source.sec-edgar",
        source_record_id=payload["accessionNumber"],
        payload=payload,
        observed_at=BASE,
        fetched_at=BASE,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/fixture.htm",
    )
    _alias(
        source,
        observation_id=observation_id,
        source_id="source.sec-edgar",
        issuer_id="US:SEC:0000320193",
        alias_type="cik",
        alias_value="0000320193",
        knowledge_at=BASE,
    )
    filing = normalize_sec_filing(
        payload,
        cik="0000320193",
        observed_at=BASE,
        fetched_at=BASE,
        raw_object_hash=digest,
    )
    FilingWarehouseRepository(source).record_filing(filing, observation_id=observation_id)
    backup = tmp_path / "backup"
    manifest = export_v2_backup(source, backup, database="fixture")
    source.close()
    assert manifest["tables"]["silver.filing_revisions"]["rows"] == 1
    assert manifest["object_bytes_included"] is False

    restored_path = tmp_path / "filing-restored.duckdb"
    result = restore_v2_backup(backup, restored_path)
    restored = duckdb.connect(str(restored_path), read_only=True)
    assert result["status"] == "verified"
    assert restored.execute("SELECT count(*) FROM silver.issuer_alias_revisions").fetchone()[0] == 1
    assert restored.execute("SELECT count(*) FROM silver.filing_identities").fetchone()[0] == 1
    assert restored.execute("SELECT count(*) FROM silver.filing_revisions").fetchone()[0] == 1
    restored.close()
