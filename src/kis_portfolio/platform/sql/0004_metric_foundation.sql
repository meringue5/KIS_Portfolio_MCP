CREATE TABLE IF NOT EXISTS control.metric_definitions (
    metric_id VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    contract_status VARCHAR NOT NULL,
    definition_hash VARCHAR NOT NULL,
    definition JSON NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY(metric_id, version)
);

CREATE TABLE IF NOT EXISTS gold.metric_values (
    metric_id VARCHAR NOT NULL,
    metric_version VARCHAR NOT NULL,
    subject_type VARCHAR NOT NULL,
    subject_id VARCHAR NOT NULL,
    evaluation_at TIMESTAMPTZ NOT NULL,
    evaluation_slot VARCHAR NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    knowledge_cutoff_at TIMESTAMPTZ NOT NULL,
    value_decimal DECIMAL(38, 10),
    unit VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    input_refs JSON NOT NULL,
    formula_hash VARCHAR NOT NULL,
    lineage_hash VARCHAR NOT NULL,
    evaluation_run_id VARCHAR NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY(metric_id, metric_version, subject_type, subject_id, evaluation_at)
);
