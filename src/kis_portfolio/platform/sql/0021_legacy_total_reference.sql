-- DEC-062 / ADR-033: additive noncanonical references; native state/quarantine unchanged.
CREATE TABLE IF NOT EXISTS silver.portfolio_legacy_total_reference (
    observation_date DATE NOT NULL,
    recovery_version VARCHAR NOT NULL,
    input_content_hash VARCHAR NOT NULL CHECK (length(input_content_hash)=64),
    recorded_total_krw DECIMAL(28,2) NOT NULL CHECK (recorded_total_krw>=0),
    reference_total_krw DECIMAL(28,2),
    added_foreign_value_krw DECIMAL(28,2) NOT NULL CHECK (added_foreign_value_krw>=0),
    valuation_kind VARCHAR NOT NULL CHECK (valuation_kind IN ('recorded_reference','estimated_reference','unavailable_total')),
    assumptions JSON NOT NULL,
    coverage_reasons JSON NOT NULL,
    original_snapshot_at VARCHAR NOT NULL,
    fx_provenance JSON,
    knowledge_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    source_object_hash VARCHAR NOT NULL CHECK (length(source_object_hash)=64),
    canonical BOOLEAN NOT NULL DEFAULT false CHECK (canonical=false),
    PRIMARY KEY (observation_date,recovery_version,input_content_hash),
    CHECK ((valuation_kind='unavailable_total' AND reference_total_krw IS NULL)
        OR (valuation_kind<>'unavailable_total' AND reference_total_krw IS NOT NULL AND reference_total_krw=recorded_total_krw+added_foreign_value_krw))
);
