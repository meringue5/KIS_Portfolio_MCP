-- WI-078: expand slot constraint; retain all prior candidates and identities.
CREATE TABLE gold.alert_candidates_078 (
    candidate_id VARCHAR PRIMARY KEY,
    alert_identity VARCHAR NOT NULL,
    rule_id VARCHAR NOT NULL,
    rule_version VARCHAR NOT NULL,
    subject_type VARCHAR NOT NULL,
    subject_id VARCHAR NOT NULL,
    evaluation_date DATE NOT NULL,
    evaluation_slot VARCHAR NOT NULL CHECK (
        evaluation_slot IN ('kr-1000', 'kr-1400', 'kr-1430', 'kr-1600', 'us-close')
    ),
    session_key VARCHAR NOT NULL,
    evaluation_at TIMESTAMPTZ NOT NULL,
    signal_state VARCHAR NOT NULL CHECK (signal_state IN ('normal', 'active')),
    severity VARCHAR NOT NULL CHECK (severity IN ('normal', 'watch', 'warning', 'critical')),
    state_fingerprint VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    input_lineage_hash VARCHAR NOT NULL,
    public_context JSON NOT NULL,
    evaluation_run_id VARCHAR NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(rule_id, rule_version, subject_type, subject_id, session_key, evaluation_slot)
);

INSERT INTO gold.alert_candidates_078 SELECT * FROM gold.alert_candidates;
DROP TABLE gold.alert_candidates;
ALTER TABLE gold.alert_candidates_078 RENAME TO alert_candidates;
