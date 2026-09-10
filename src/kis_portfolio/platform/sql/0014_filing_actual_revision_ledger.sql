-- WI-037 / ADR-025: additive filing actual and fundamental revision ledger.
-- The legacy 0001 foundations are intentionally preserved and must still be empty.
SELECT CASE
    WHEN (SELECT count(*) FROM silver.filing_events) = 0
     AND (SELECT count(*) FROM silver.financial_facts) = 0
    THEN TRUE
    ELSE error('migration 0014 requires empty legacy filing foundations')
END;

CREATE TABLE IF NOT EXISTS silver.issuer_alias_revisions (
    issuer_alias_revision_id VARCHAR PRIMARY KEY,
    issuer_id VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    jurisdiction VARCHAR NOT NULL,
    alias_type VARCHAR NOT NULL,
    alias_value VARCHAR NOT NULL,
    market VARCHAR,
    exchange_code VARCHAR,
    source_valid_from TIMESTAMPTZ NOT NULL,
    source_valid_to TIMESTAMPTZ,
    observed_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    evidence_observation_id VARCHAR NOT NULL,
    relation_quality VARCHAR NOT NULL,
    revision_hash VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(source_id, alias_type, alias_value, source_valid_from, revision_hash)
);

CREATE TABLE IF NOT EXISTS silver.filing_identities (
    filing_identity_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    jurisdiction VARCHAR NOT NULL,
    source_filing_id VARCHAR NOT NULL,
    issuer_id VARCHAR NOT NULL,
    first_source_observation_id VARCHAR NOT NULL,
    first_known_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(source_id, jurisdiction, source_filing_id)
);

CREATE TABLE IF NOT EXISTS silver.filing_revisions (
    filing_revision_id VARCHAR PRIMARY KEY,
    filing_identity_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    content_hash VARCHAR NOT NULL,
    form_type VARCHAR NOT NULL,
    filing_title VARCHAR,
    fiscal_year INTEGER,
    fiscal_period VARCHAR,
    period_start DATE,
    period_end DATE,
    statement_scope VARCHAR,
    source_url VARCHAR NOT NULL,
    raw_object_hash VARCHAR NOT NULL,
    source_available_at TIMESTAMPTZ NOT NULL,
    source_time_precision VARCHAR NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    parser_id VARCHAR NOT NULL,
    parser_version VARCHAR NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    relation_type VARCHAR NOT NULL,
    target_filing_identity_id VARCHAR,
    relation_quality VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(filing_identity_id, revision),
    UNIQUE(filing_identity_id, content_hash)
);

CREATE TABLE IF NOT EXISTS control.fundamental_concept_mappings (
    mapping_id VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    taxonomy VARCHAR NOT NULL,
    concept VARCHAR NOT NULL,
    normalized_concept VARCHAR NOT NULL,
    unit_constraint VARCHAR,
    period_type_constraint VARCHAR,
    statement_scope_constraint VARCHAR,
    review_status VARCHAR NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    knowledge_at TIMESTAMPTZ NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY(mapping_id, version)
);

CREATE TABLE IF NOT EXISTS silver.financial_fact_revisions (
    financial_fact_revision_id VARCHAR PRIMARY KEY,
    filing_revision_id VARCHAR NOT NULL,
    taxonomy VARCHAR NOT NULL,
    concept VARCHAR NOT NULL,
    period_start DATE,
    period_end DATE NOT NULL,
    period_type VARCHAR NOT NULL,
    unit VARCHAR NOT NULL,
    statement_scope VARCHAR NOT NULL,
    dimension_hash VARCHAR NOT NULL,
    raw_lexical_value VARCHAR NOT NULL,
    typed_value DECIMAL(38, 8),
    decimals_value INTEGER,
    scale_value INTEGER,
    fact_revision_hash VARCHAR NOT NULL,
    source_available_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(
        filing_revision_id, taxonomy, concept, period_start, period_end, unit,
        statement_scope, dimension_hash, fact_revision_hash
    )
);

CREATE OR REPLACE VIEW silver.issuer_source_aliases_current AS
SELECT * EXCLUDE (row_number_value)
FROM (
    SELECT aliases.*,
           row_number() OVER (
               PARTITION BY source_id, alias_type, alias_value
               ORDER BY knowledge_at DESC, source_valid_from DESC,
                        issuer_alias_revision_id DESC
           ) AS row_number_value
    FROM silver.issuer_alias_revisions aliases
)
WHERE row_number_value = 1;

CREATE OR REPLACE VIEW silver.filing_revisions_current AS
WITH latest AS (
    SELECT * EXCLUDE (row_number_value)
    FROM (
        SELECT revisions.*,
               row_number() OVER (
                   PARTITION BY filing_identity_id
                   ORDER BY knowledge_at DESC, revision DESC, filing_revision_id DESC
               ) AS row_number_value
        FROM silver.filing_revisions revisions
    )
    WHERE row_number_value = 1
)
SELECT latest.*,
       EXISTS (
           SELECT 1 FROM latest correcting
           WHERE correcting.target_filing_identity_id = latest.filing_identity_id
             AND correcting.relation_quality = 'verified'
             AND correcting.quality_status = 'pass'
             AND correcting.relation_type IN ('amends', 'corrects', 'withdraws')
       ) AS is_superseded
FROM latest;

CREATE OR REPLACE VIEW control.fundamental_concept_mappings_current AS
SELECT * EXCLUDE (row_number_value)
FROM (
    SELECT mappings.*,
           row_number() OVER (
               PARTITION BY mapping_id
               ORDER BY knowledge_at DESC, valid_from DESC, version DESC
           ) AS row_number_value
    FROM control.fundamental_concept_mappings mappings
)
WHERE row_number_value = 1;

CREATE OR REPLACE VIEW silver.financial_fact_revisions_current AS
SELECT * EXCLUDE (row_number_value)
FROM (
    SELECT facts.*,
           row_number() OVER (
               PARTITION BY filing_revision_id, taxonomy, concept, period_start,
                            period_end, unit, statement_scope, dimension_hash
               ORDER BY knowledge_at DESC, financial_fact_revision_id DESC
           ) AS row_number_value
    FROM silver.financial_fact_revisions facts
)
WHERE row_number_value = 1;
