CREATE TABLE IF NOT EXISTS silver.corporate_actions (
    corporate_action_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    source_record_id VARCHAR NOT NULL,
    market VARCHAR NOT NULL,
    first_source_observation_id VARCHAR NOT NULL,
    first_known_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(source_id, source_record_id)
);

CREATE TABLE IF NOT EXISTS silver.corporate_action_revisions (
    corporate_action_revision_id VARCHAR PRIMARY KEY,
    corporate_action_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    revision_hash VARCHAR NOT NULL,
    action_type VARCHAR NOT NULL,
    action_status VARCHAR NOT NULL,
    source_instrument_id VARCHAR NOT NULL,
    result_instrument_id VARCHAR,
    effective_at TIMESTAMPTZ NOT NULL,
    record_date DATE,
    ex_date DATE,
    listing_date DATE,
    pre_action_units DECIMAL(28, 12),
    post_action_units DECIMAL(28, 12),
    terms_status VARCHAR NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(corporate_action_id, revision),
    UNIQUE(corporate_action_id, revision_hash)
);

CREATE TABLE IF NOT EXISTS silver.corporate_action_adjustment_effects (
    corporate_action_effect_id VARCHAR PRIMARY KEY,
    corporate_action_revision_id VARCHAR NOT NULL,
    effect_type VARCHAR NOT NULL,
    input_instrument_id VARCHAR NOT NULL,
    output_instrument_id VARCHAR,
    factor_numerator DECIMAL(28, 12),
    factor_denominator DECIMAL(28, 12),
    effective_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(corporate_action_revision_id, effect_type, input_instrument_id, output_instrument_id)
);

CREATE OR REPLACE VIEW silver.corporate_actions_current AS
SELECT
    actions.corporate_action_id,
    actions.source_id,
    actions.source_record_id,
    actions.market,
    revisions.corporate_action_revision_id,
    revisions.revision,
    revisions.revision_hash,
    revisions.action_type,
    revisions.action_status,
    revisions.source_instrument_id,
    revisions.result_instrument_id,
    revisions.effective_at,
    revisions.record_date,
    revisions.ex_date,
    revisions.listing_date,
    revisions.pre_action_units,
    revisions.post_action_units,
    revisions.terms_status,
    revisions.knowledge_at,
    revisions.source_observation_id,
    revisions.quality_status,
    revisions.provenance,
    revisions.recorded_at
FROM silver.corporate_actions actions
JOIN silver.corporate_action_revisions revisions USING (corporate_action_id)
QUALIFY row_number() OVER (
    PARTITION BY actions.corporate_action_id
    ORDER BY revisions.knowledge_at DESC, revisions.revision DESC,
             revisions.corporate_action_revision_id DESC
) = 1;
