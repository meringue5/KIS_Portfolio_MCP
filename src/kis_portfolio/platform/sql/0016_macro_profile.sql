-- WI-039 / ADR-027: exact definitions, heterogeneous observation revisions and profile snapshots.
-- The legacy 0001 foundation is preserved and must remain empty.
SELECT CASE
    WHEN (SELECT count(*) FROM silver.macro_observations) = 0
    THEN TRUE
    ELSE error('migration 0016 requires empty legacy macro foundation')
END;

CREATE TABLE IF NOT EXISTS control.macro_series_definitions (
    series_contract_id VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    definition_hash VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    provider_series_id VARCHAR NOT NULL,
    source_owner VARCHAR NOT NULL,
    source_license_class VARCHAR NOT NULL,
    region VARCHAR NOT NULL,
    concept VARCHAR NOT NULL,
    native_frequency VARCHAR NOT NULL,
    native_unit VARCHAR NOT NULL,
    seasonal_adjustment VARCHAR NOT NULL,
    vintage_capability VARCHAR NOT NULL,
    publication_cadence VARCHAR NOT NULL,
    expected_lag VARCHAR NOT NULL,
    history_start VARCHAR NOT NULL,
    rights_note VARCHAR NOT NULL,
    attribution VARCHAR NOT NULL,
    permitted_consumers JSON NOT NULL,
    transform_policy VARCHAR NOT NULL,
    activation_state VARCHAR NOT NULL,
    valid_from DATE NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY(series_contract_id, version),
    UNIQUE(source_id, provider_series_id, version)
);

CREATE TABLE IF NOT EXISTS silver.macro_observation_revisions (
    macro_observation_revision_id VARCHAR PRIMARY KEY,
    series_contract_id VARCHAR NOT NULL,
    series_contract_version VARCHAR NOT NULL,
    definition_hash VARCHAR NOT NULL,
    observation_period VARCHAR NOT NULL,
    revision_kind VARCHAR NOT NULL,
    revision_key VARCHAR NOT NULL,
    native_value DECIMAL(38, 12),
    missing_reason VARCHAR,
    native_unit VARCHAR NOT NULL,
    native_frequency VARCHAR NOT NULL,
    seasonal_adjustment VARCHAR NOT NULL,
    source_realtime_start DATE,
    source_realtime_end DATE,
    source_available_at TIMESTAMPTZ,
    source_time_precision VARCHAR,
    knowledge_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    request_id VARCHAR NOT NULL,
    pipeline_run_id VARCHAR,
    partition_key VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    rights_status VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(series_contract_id, observation_period, revision_kind, revision_key)
);

CREATE OR REPLACE VIEW silver.macro_observations_current AS
SELECT * EXCLUDE (row_number_value)
FROM (
    SELECT revisions.*,
           row_number() OVER (
               PARTITION BY series_contract_id, observation_period
               ORDER BY knowledge_at DESC, fetched_at DESC,
                        macro_observation_revision_id DESC
           ) AS row_number_value
    FROM silver.macro_observation_revisions revisions
)
WHERE row_number_value = 1;

CREATE OR REPLACE VIEW silver.macro_observations_as_of AS
SELECT revisions.*,
       lead(knowledge_at) OVER (
           PARTITION BY series_contract_id, observation_period
           ORDER BY knowledge_at, fetched_at, macro_observation_revision_id
       ) AS next_knowledge_at
FROM silver.macro_observation_revisions revisions;

CREATE TABLE IF NOT EXISTS gold.macro_profile_snapshots (
    macro_profile_snapshot_id VARCHAR PRIMARY KEY,
    profile_id VARCHAR NOT NULL,
    profile_version VARCHAR NOT NULL,
    evaluation_at TIMESTAMPTZ NOT NULL,
    metric_set_version VARCHAR NOT NULL,
    query_mode VARCHAR NOT NULL,
    definition_set_hash VARCHAR NOT NULL,
    series_revision_lineage JSON NOT NULL,
    metric_values JSON NOT NULL,
    missing_coverage JSON NOT NULL,
    rights_summary JSON NOT NULL,
    attribution JSON NOT NULL,
    quality_status VARCHAR NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(profile_id, profile_version, evaluation_at, metric_set_version)
);
