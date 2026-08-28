CREATE TABLE IF NOT EXISTS control.alert_rule_versions (
    rule_id VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    contract_status VARCHAR NOT NULL CHECK (contract_status IN ('approved', 'active')),
    definition_hash VARCHAR NOT NULL,
    minimum_delivery_severity VARCHAR NOT NULL CHECK (
        minimum_delivery_severity IN ('warning', 'critical')
    ),
    delivery_mode VARCHAR NOT NULL CHECK (delivery_mode IN ('off', 'shadow', 'external')),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    definition JSON NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    PRIMARY KEY(rule_id, version)
);

CREATE TABLE IF NOT EXISTS gold.alert_candidates (
    candidate_id VARCHAR PRIMARY KEY,
    alert_identity VARCHAR NOT NULL,
    rule_id VARCHAR NOT NULL,
    rule_version VARCHAR NOT NULL,
    subject_type VARCHAR NOT NULL,
    subject_id VARCHAR NOT NULL,
    evaluation_date DATE NOT NULL,
    evaluation_slot VARCHAR NOT NULL CHECK (
        evaluation_slot IN ('kr-1000', 'kr-1430', 'kr-1600', 'us-close')
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

CREATE TABLE IF NOT EXISTS control.alert_state_revisions (
    state_revision_id VARCHAR PRIMARY KEY,
    alert_identity VARCHAR NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    episode INTEGER NOT NULL CHECK (episode >= 0),
    transition_type VARCHAR NOT NULL CHECK (
        transition_type IN (
            'initial_normal', 'entered', 'updated', 'escalated', 'deescalated',
            'recovered', 'reentered'
        )
    ),
    prior_state VARCHAR CHECK (prior_state IS NULL OR prior_state IN ('normal', 'active')),
    current_state VARCHAR NOT NULL CHECK (current_state IN ('normal', 'active')),
    prior_severity VARCHAR CHECK (
        prior_severity IS NULL OR prior_severity IN ('normal', 'watch', 'warning', 'critical')
    ),
    current_severity VARCHAR NOT NULL CHECK (
        current_severity IN ('normal', 'watch', 'warning', 'critical')
    ),
    state_fingerprint VARCHAR NOT NULL,
    candidate_id VARCHAR NOT NULL,
    delivery_required BOOLEAN NOT NULL,
    delivery_severity VARCHAR NOT NULL CHECK (
        delivery_severity IN ('normal', 'watch', 'warning', 'critical')
    ),
    knowledge_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(alert_identity, revision),
    UNIQUE(candidate_id)
);

CREATE TABLE IF NOT EXISTS control.alert_candidate_outcomes (
    candidate_id VARCHAR PRIMARY KEY,
    outcome_type VARCHAR NOT NULL CHECK (
        outcome_type IN ('transition', 'no_change', 'suppressed_quality', 'out_of_order')
    ),
    state_revision_id VARCHAR,
    evaluated_against_revision INTEGER NOT NULL CHECK (evaluated_against_revision >= 0),
    processed_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (
        (outcome_type = 'transition' AND state_revision_id IS NOT NULL) OR
        (outcome_type != 'transition' AND state_revision_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS control.alert_dispatch_claims (
    dispatch_id VARCHAR PRIMARY KEY,
    candidate_id VARCHAR NOT NULL,
    channel VARCHAR NOT NULL CHECK (channel IN ('shadow', 'telegram')),
    destination_ref VARCHAR NOT NULL,
    claim_status VARCHAR NOT NULL CHECK (
        claim_status IN ('claimed', 'retryable', 'completed', 'unknown', 'permanent_failure')
    ),
    claimant_id VARCHAR NOT NULL,
    lease_token_digest VARCHAR NOT NULL,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error_code VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(candidate_id, channel, destination_ref)
);

CREATE TABLE IF NOT EXISTS control.alert_delivery_attempts (
    attempt_id VARCHAR PRIMARY KEY,
    dispatch_id VARCHAR NOT NULL,
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    outcome VARCHAR NOT NULL CHECK (
        outcome IN ('sent', 'retryable_failure', 'permanent_failure', 'unknown')
    ),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    response_ref_hash VARCHAR,
    error_code VARCHAR,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (completed_at >= started_at),
    UNIQUE(dispatch_id, attempt_no)
);

CREATE OR REPLACE VIEW control.alert_states_current AS
SELECT *
FROM control.alert_state_revisions
QUALIFY row_number() OVER (
    PARTITION BY alert_identity
    ORDER BY revision DESC, knowledge_at DESC, state_revision_id DESC
) = 1;
