"""Append-only issuer, filing and financial-fact repository for ADR-025."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import duckdb

from kis_portfolio.modules.market.filings import (
    FilingRevision,
    FinancialFactRevision,
    IssuerAliasRevision,
    validate_alias,
    validate_artifact,
    validate_fact,
    validate_filing,
)
from kis_portfolio.ports.object_store import StoredObject


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _digest(prefix: str, value: Any) -> str:
    return hashlib.sha256(f"{prefix}|{_json(value)}".encode()).hexdigest()


def _has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {"api_key", "authorization", "cookie", "access_token", "secret"}:
                return True
            if _has_forbidden_key(nested):
                return True
    if isinstance(value, (list, tuple)):
        return any(_has_forbidden_key(item) for item in value)
    return False


def _official_host(source_id: str, source_url: str) -> bool:
    host = (urlparse(source_url).hostname or "").lower()
    allowed_hosts = {
        "source.opendart": {"dart.fss.or.kr", "opendart.fss.or.kr"},
        "source.sec-edgar": {"sec.gov", "www.sec.gov", "data.sec.gov"},
    }
    return host in allowed_hosts.get(source_id, set())


class FilingWarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def record_artifact_manifest(
        self,
        *,
        observation_id: str,
        stored: StoredObject,
        source_url: str,
        expanded_archive_bytes: int = 0,
        archive_members: int = 0,
        encrypted_archive: bool = False,
        archive_member_paths: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> str:
        validate_artifact(
            media_type=stored.media_type,
            byte_size=stored.byte_size,
            expanded_archive_bytes=expanded_archive_bytes,
            archive_members=archive_members,
            encrypted_archive=encrypted_archive,
            archive_member_paths=archive_member_paths,
        )
        if not stored.uri.startswith(("gs://", "fixture-private://")):
            raise ValueError("filing artifacts require a private object URI")
        observation = self.connection.execute(
            """
            SELECT dataset_id,source_id,content_hash,fetched_at
            FROM bronze.source_observations WHERE observation_id=?
            """,
            [observation_id],
        ).fetchone()
        if not observation or observation[0] != "dataset.filing-source-artifact":
            raise ValueError("filing artifact requires a governed filing observation")
        dataset_id, source_id, content_hash, fetched_at = observation
        if not _official_host(source_id, source_url):
            raise ValueError("filing artifact URL is not an allowlisted official host")
        if content_hash != stored.content_hash:
            raise ValueError("filing artifact hash does not match its source observation")
        existing = self.connection.execute(
            """
            SELECT dataset_id,source_id,private_uri,media_type,byte_size
            FROM bronze.raw_object_manifest WHERE content_hash=?
            """,
            [stored.content_hash],
        ).fetchone()
        expected = (dataset_id, source_id, stored.uri, stored.media_type, stored.byte_size)
        if existing is not None and tuple(existing) != expected:
            raise ValueError("filing object hash replay conflicts with its immutable manifest")
        document = dict(metadata or {}) | {
            "archive_members": archive_members,
            "archive_member_paths": list(archive_member_paths),
            "expanded_archive_bytes": expanded_archive_bytes,
            "hash_verified": True,
            "source_observation_id": observation_id,
        }
        if _has_forbidden_key(document):
            raise ValueError("filing artifact metadata contains forbidden credential fields")
        self.connection.execute(
            """
            INSERT INTO bronze.raw_object_manifest(
                content_hash,dataset_id,source_id,private_uri,media_type,byte_size,
                rights_class,sensitivity,source_url,source_published_at,ingested_at,metadata
            ) VALUES (?,?,?,?,?,?,'public','restricted',?,NULL,?,?)
            ON CONFLICT(content_hash) DO NOTHING
            """,
            [stored.content_hash, dataset_id, source_id, stored.uri, stored.media_type,
             stored.byte_size, source_url, fetched_at, _json(document)],
        )
        return stored.content_hash

    def record_alias(
        self,
        value: IssuerAliasRevision,
        *,
        evidence_observation_id: str,
    ) -> str:
        validate_alias(value)
        observation = self.connection.execute(
            """
            SELECT dataset_id,source_id FROM bronze.source_observations
            WHERE observation_id=?
            """,
            [evidence_observation_id],
        ).fetchone()
        if not observation or observation != (
            "dataset.filing-source-artifact", value.source_id
        ):
            raise ValueError("issuer alias requires matching governed filing evidence")
        if value.relation_quality == "verified":
            conflict = self.connection.execute(
                """
                SELECT issuer_id FROM silver.issuer_alias_revisions
                WHERE source_id=? AND alias_type=? AND alias_value=?
                  AND relation_quality='verified' AND issuer_id<>?
                  AND (source_valid_to IS NULL OR source_valid_to>?)
                  AND (? IS NULL OR source_valid_from<?)
                LIMIT 1
                """,
                [value.source_id, value.alias_type, value.alias_value, value.issuer_id,
                 value.source_valid_from, value.source_valid_to, value.source_valid_to],
            ).fetchone()
            if conflict:
                raise ValueError("verified issuer alias overlaps a different issuer")
        content = {
            "issuer_id": value.issuer_id,
            "source_id": value.source_id,
            "jurisdiction": value.jurisdiction,
            "alias_type": value.alias_type,
            "alias_value": value.alias_value,
            "market": value.market,
            "exchange_code": value.exchange_code,
            "source_valid_from": value.source_valid_from,
            "source_valid_to": value.source_valid_to,
            "relation_quality": value.relation_quality,
            "provenance": value.provenance or {},
        }
        revision_hash = _digest("issuer-alias-content", content)
        revision_id = _digest("issuer-alias-revision", content | {
            "knowledge_at": value.knowledge_at,
        })
        self.connection.execute(
            """
            INSERT INTO silver.issuer_alias_revisions(
                issuer_alias_revision_id,issuer_id,source_id,jurisdiction,alias_type,
                alias_value,market,exchange_code,source_valid_from,source_valid_to,
                observed_at,knowledge_at,evidence_observation_id,relation_quality,
                revision_hash,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source_id,alias_type,alias_value,source_valid_from,revision_hash)
            DO NOTHING
            """,
            [revision_id, value.issuer_id, value.source_id, value.jurisdiction,
             value.alias_type, value.alias_value, value.market, value.exchange_code,
             value.source_valid_from, value.source_valid_to, value.observed_at,
             value.knowledge_at, evidence_observation_id, value.relation_quality,
             revision_hash, _json(value.provenance or {})],
        )
        row = self.connection.execute(
            """
            SELECT issuer_alias_revision_id FROM silver.issuer_alias_revisions
            WHERE source_id=? AND alias_type=? AND alias_value=? AND source_valid_from=?
              AND revision_hash=?
            """,
            [value.source_id, value.alias_type, value.alias_value,
             value.source_valid_from, revision_hash],
        ).fetchone()
        return row[0]

    def record_filing(self, value: FilingRevision, *, observation_id: str) -> tuple[str, str]:
        validate_filing(value)
        observation = self.connection.execute(
            """
            SELECT dataset_id,source_id,source_record_id,content_hash,pipeline_run_id
            FROM bronze.source_observations WHERE observation_id=?
            """,
            [observation_id],
        ).fetchone()
        if not observation or observation[:4] != (
            "dataset.filing-source-artifact", value.source_id,
            value.source_filing_id, value.content_hash,
        ):
            raise ValueError("filing requires its exact governed source observation")
        manifest = self.connection.execute(
            """
            SELECT source_id,private_uri FROM bronze.raw_object_manifest
            WHERE content_hash=?
            """,
            [value.raw_object_hash],
        ).fetchone()
        if not manifest or manifest[0] != value.source_id:
            raise ValueError("filing Silver publish requires a verified private raw object")
        if not _official_host(value.source_id, value.source_url):
            raise ValueError("filing source URL is not an allowlisted official host")
        alias_type = "corp_code" if value.source_id == "source.opendart" else "cik"
        alias_value = value.issuer_id.rsplit(":", 1)[-1]
        alias = self.connection.execute(
            """
            SELECT 1 FROM silver.issuer_alias_revisions
            WHERE issuer_id=? AND source_id=? AND alias_type=? AND alias_value=?
              AND relation_quality='verified'
              AND knowledge_at<=?
              AND source_valid_from<=?
              AND (source_valid_to IS NULL OR source_valid_to>?)
            LIMIT 1
            """,
            [value.issuer_id, value.source_id, alias_type, alias_value,
             value.knowledge_at, value.source_available_at, value.source_available_at],
        ).fetchone()
        if not alias:
            raise ValueError("filing Silver publish requires a verified issuer alias")

        identity_id = _digest("filing-identity", {
            "source_id": value.source_id,
            "jurisdiction": value.jurisdiction,
            "source_filing_id": value.source_filing_id,
        })
        prior_identity = self.connection.execute(
            """
            SELECT issuer_id FROM silver.filing_identities
            WHERE source_id=? AND jurisdiction=? AND source_filing_id=?
            """,
            [value.source_id, value.jurisdiction, value.source_filing_id],
        ).fetchone()
        if prior_identity is not None and prior_identity[0] != value.issuer_id:
            raise ValueError("filing identity cannot move between issuers")
        self.connection.execute(
            """
            INSERT INTO silver.filing_identities(
                filing_identity_id,source_id,jurisdiction,source_filing_id,issuer_id,
                first_source_observation_id,first_known_at
            ) VALUES (?,?,?,?,?,?,?) ON CONFLICT(filing_identity_id) DO NOTHING
            """,
            [identity_id, value.source_id, value.jurisdiction, value.source_filing_id,
             value.issuer_id, observation_id, value.knowledge_at],
        )

        target_identity_id = None
        if value.target_source_filing_id:
            target = self.connection.execute(
                """
                SELECT filing_identity_id FROM silver.filing_identities
                WHERE source_id=? AND jurisdiction=? AND source_filing_id=? AND issuer_id=?
                """,
                [value.source_id, value.jurisdiction, value.target_source_filing_id,
                 value.issuer_id],
            ).fetchone()
            if value.relation_quality == "verified" and target is None:
                raise ValueError("verified correction target is not a known filing identity")
            target_identity_id = target[0] if target else None

        duplicate = self.connection.execute(
            """
            SELECT filing_revision_id FROM silver.filing_revisions
            WHERE filing_identity_id=? AND content_hash=?
            """,
            [identity_id, value.content_hash],
        ).fetchone()
        if duplicate:
            return identity_id, duplicate[0]
        latest = self.connection.execute(
            """
            SELECT revision,knowledge_at FROM silver.filing_revisions
            WHERE filing_identity_id=? ORDER BY knowledge_at DESC,revision DESC LIMIT 1
            """,
            [identity_id],
        ).fetchone()
        if latest and value.knowledge_at <= latest[1]:
            raise ValueError("filing knowledge_at must advance for changed content")
        revision = 1 if latest is None else int(latest[0]) + 1
        revision_id = _digest("filing-revision", {
            "filing_identity_id": identity_id,
            "content_hash": value.content_hash,
        })
        self.connection.execute(
            """
            INSERT INTO silver.filing_revisions(
                filing_revision_id,filing_identity_id,revision,content_hash,form_type,
                filing_title,fiscal_year,fiscal_period,period_start,period_end,
                statement_scope,source_url,raw_object_hash,source_available_at,
                source_time_precision,first_observed_at,fetched_at,knowledge_at,
                parser_id,parser_version,source_observation_id,relation_type,target_filing_identity_id,
                relation_quality,quality_status,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [revision_id, identity_id, revision, value.content_hash, value.form_type,
             value.filing_title, value.fiscal_year, value.fiscal_period,
             value.period_start, value.period_end, value.statement_scope,
             value.source_url, value.raw_object_hash, value.source_available_at,
             value.source_time_precision, value.first_observed_at, value.fetched_at,
             value.knowledge_at, value.parser_id, value.parser_version,
             observation_id, value.relation_type, target_identity_id, value.relation_quality,
             value.quality_status, _json(value.provenance or {})],
        )
        self._record_lineage(
            run_id=observation[4],
            input_ref=f"bronze.source_observations:{observation_id}",
            output_ref=f"silver.filing_revisions:{revision_id}",
            transform_id=value.parser_id,
            transform_version=value.parser_version,
            knowledge_at=value.knowledge_at,
        )
        return identity_id, revision_id

    def _record_lineage(
        self,
        *,
        run_id: str | None,
        input_ref: str,
        output_ref: str,
        transform_id: str,
        transform_version: str,
        knowledge_at: datetime,
    ) -> None:
        if not run_id:
            return
        lineage_id = _digest("filing-lineage", {
            "run_id": run_id,
            "input_ref": input_ref,
            "output_ref": output_ref,
            "transform_id": transform_id,
            "transform_version": transform_version,
        })
        evidence_hash = _digest("filing-lineage-evidence", {
            "input_ref": input_ref,
            "output_ref": output_ref,
        })
        self.connection.execute(
            """
            INSERT INTO control.lineage_edges(
                lineage_edge_id,run_id,input_ref,output_ref,transform_id,
                transform_version,evidence_hash,created_at
            ) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(lineage_edge_id) DO NOTHING
            """,
            [lineage_id, run_id, input_ref, output_ref, transform_id,
             transform_version, evidence_hash, knowledge_at],
        )

    def register_mapping(self, payload: dict[str, Any]) -> None:
        knowledge_at = payload["knowledge_at"]
        valid_from = payload["valid_from"]
        if knowledge_at.tzinfo is None or valid_from.tzinfo is None:
            raise ValueError("concept mapping timestamps must be timezone-aware")
        if payload.get("review_status") not in {"reviewed", "rejected"}:
            raise ValueError("concept mapping review_status must be reviewed or rejected")
        self.connection.execute(
            """
            INSERT INTO control.fundamental_concept_mappings(
                mapping_id,version,source_id,taxonomy,concept,normalized_concept,
                unit_constraint,period_type_constraint,statement_scope_constraint,
                review_status,valid_from,valid_to,knowledge_at,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(mapping_id,version) DO NOTHING
            """,
            [payload["mapping_id"], payload["version"], payload["source_id"],
             payload["taxonomy"], payload["concept"], payload["normalized_concept"],
             payload.get("unit_constraint"), payload.get("period_type_constraint"),
             payload.get("statement_scope_constraint"), payload["review_status"],
             valid_from, payload.get("valid_to"), knowledge_at,
             _json(payload.get("provenance") or {})],
        )

    def record_fact(
        self,
        filing_revision_id: str,
        value: FinancialFactRevision,
    ) -> str:
        validate_fact(value)
        filing = self.connection.execute(
            """
            SELECT revisions.source_available_at,revisions.knowledge_at,
                   revisions.quality_status,observations.pipeline_run_id
            FROM silver.filing_revisions revisions
            JOIN bronze.source_observations observations
              ON observations.observation_id=revisions.source_observation_id
            WHERE revisions.filing_revision_id=?
            """,
            [filing_revision_id],
        ).fetchone()
        if not filing:
            raise ValueError("financial fact requires a governed filing revision")
        if value.source_available_at != filing[0] or value.knowledge_at != filing[1]:
            raise ValueError("financial fact clocks must inherit from its filing revision")
        content = {
            "filing_revision_id": filing_revision_id,
            "taxonomy": value.taxonomy,
            "concept": value.concept,
            "period_start": value.period_start,
            "period_end": value.period_end,
            "period_type": value.period_type,
            "unit": value.unit,
            "statement_scope": value.statement_scope,
            "dimension_hash": value.dimension_hash,
            "raw_lexical_value": value.raw_lexical_value,
            "typed_value": value.typed_value,
            "decimals_value": value.decimals_value,
            "scale_value": value.scale_value,
        }
        fact_hash = _digest("financial-fact-content", content)
        fact_id = _digest("financial-fact-revision", content)
        self.connection.execute(
            """
            INSERT INTO silver.financial_fact_revisions(
                financial_fact_revision_id,filing_revision_id,taxonomy,concept,
                period_start,period_end,period_type,unit,statement_scope,dimension_hash,
                raw_lexical_value,typed_value,decimals_value,scale_value,
                fact_revision_hash,source_available_at,knowledge_at,quality_status,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(
                filing_revision_id,taxonomy,concept,period_start,period_end,unit,
                statement_scope,dimension_hash,fact_revision_hash
            ) DO NOTHING
            """,
            [fact_id, filing_revision_id, value.taxonomy, value.concept,
             value.period_start, value.period_end, value.period_type, value.unit,
             value.statement_scope, value.dimension_hash, value.raw_lexical_value,
             value.typed_value, value.decimals_value, value.scale_value, fact_hash,
             value.source_available_at, value.knowledge_at, value.quality_status,
             _json(value.provenance or {})],
        )
        self._record_lineage(
            run_id=filing[3],
            input_ref=f"silver.filing_revisions:{filing_revision_id}",
            output_ref=f"silver.financial_fact_revisions:{fact_id}",
            transform_id="filing-financial-fact-normalizer",
            transform_version="1.0.0",
            knowledge_at=value.knowledge_at,
        )
        return fact_id

    def filings_as_of(
        self,
        *,
        issuer_id: str,
        cutoff_at: datetime,
        query_mode: str = "system_as_of",
    ) -> list[dict[str, Any]]:
        if cutoff_at.tzinfo is None:
            raise ValueError("filing cutoff must be timezone-aware")
        if query_mode not in {"system_as_of", "retrospective_source_as_of"}:
            raise ValueError("unsupported filing query mode")
        clock = "knowledge_at" if query_mode == "system_as_of" else "source_available_at"
        rows = self.connection.execute(
            f"""
            WITH eligible AS (
                SELECT identities.source_id,identities.jurisdiction,
                       identities.source_filing_id,identities.issuer_id,revisions.*
                FROM silver.filing_identities identities
                JOIN silver.filing_revisions revisions USING(filing_identity_id)
                WHERE identities.issuer_id=? AND revisions.{clock}<=?
                QUALIFY row_number() OVER (
                    PARTITION BY revisions.filing_identity_id
                    ORDER BY revisions.{clock} DESC,revisions.knowledge_at DESC,
                             revisions.revision DESC,revisions.filing_revision_id DESC
                )=1
            )
            SELECT eligible.* EXCLUDE (recorded_at)
            FROM eligible
            WHERE NOT EXISTS (
                SELECT 1 FROM eligible correcting
                WHERE correcting.target_filing_identity_id=eligible.filing_identity_id
                  AND correcting.relation_quality='verified'
                  AND correcting.quality_status='pass'
                  AND correcting.relation_type IN ('amends','corrects','withdraws')
            )
            ORDER BY source_available_at,source_filing_id
            """,
            [issuer_id, cutoff_at],
        ).fetchall()
        columns = [item[0] for item in self.connection.description]
        return [dict(zip(columns, row, strict=True)) | {"query_mode": query_mode}
                for row in rows]

    def facts_as_of(
        self,
        *,
        issuer_id: str,
        cutoff_at: datetime,
        query_mode: str = "system_as_of",
    ) -> list[dict[str, Any]]:
        filings = self.filings_as_of(
            issuer_id=issuer_id, cutoff_at=cutoff_at, query_mode=query_mode
        )
        if not filings:
            return []
        filing_ids = [item["filing_revision_id"] for item in filings]
        placeholders = ",".join("?" for _ in filing_ids)
        clock = "facts.knowledge_at" if query_mode == "system_as_of" else "facts.source_available_at"
        rows = self.connection.execute(
            f"""
            SELECT facts.*,mappings.normalized_concept,mappings.mapping_id,
                   mappings.version AS mapping_version,
                   CASE WHEN mappings.mapping_id IS NULL THEN 'unmapped' ELSE 'reviewed' END
                       AS mapping_quality
            FROM silver.financial_fact_revisions facts
            LEFT JOIN LATERAL (
                SELECT mapping_id,version,normalized_concept
                FROM control.fundamental_concept_mappings mappings
                WHERE mappings.source_id=(
                    SELECT identities.source_id
                    FROM silver.filing_revisions revisions
                    JOIN silver.filing_identities identities USING(filing_identity_id)
                    WHERE revisions.filing_revision_id=facts.filing_revision_id
                )
                  AND mappings.taxonomy=facts.taxonomy
                  AND mappings.concept=facts.concept
                  AND mappings.review_status='reviewed'
                  AND (mappings.unit_constraint IS NULL OR mappings.unit_constraint=facts.unit)
                  AND (mappings.period_type_constraint IS NULL OR mappings.period_type_constraint=facts.period_type)
                  AND (mappings.statement_scope_constraint IS NULL OR mappings.statement_scope_constraint=facts.statement_scope)
                  AND mappings.valid_from<=?
                  AND (mappings.valid_to IS NULL OR mappings.valid_to>?)
                  AND mappings.knowledge_at<=?
                ORDER BY mappings.knowledge_at DESC,mappings.version DESC LIMIT 1
            ) mappings ON TRUE
            WHERE facts.filing_revision_id IN ({placeholders}) AND {clock}<=?
            ORDER BY facts.period_end,facts.taxonomy,facts.concept,facts.dimension_hash
            """,
            [cutoff_at, cutoff_at, cutoff_at, *filing_ids, cutoff_at],
        ).fetchall()
        columns = [item[0] for item in self.connection.description]
        return [dict(zip(columns, row, strict=True)) | {"query_mode": query_mode}
                for row in rows]
