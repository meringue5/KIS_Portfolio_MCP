ALTER TABLE control.alert_rule_versions
ADD COLUMN IF NOT EXISTS minimum_delivery_rank SMALLINT DEFAULT 1;

CREATE TABLE IF NOT EXISTS control.alert_calibration_runs (
    calibration_run_id VARCHAR PRIMARY KEY,
    rule_set_id VARCHAR NOT NULL,
    rule_set_version VARCHAR NOT NULL,
    replay_start DATE NOT NULL,
    replay_end DATE NOT NULL,
    run_status VARCHAR NOT NULL CHECK (
        run_status IN ('draft', 'review_ready', 'approved', 'rejected')
    ),
    source_mode VARCHAR NOT NULL CHECK (
        source_mode IN ('historical_live', 'retrospective_reconstructed', 'mixed')
    ),
    observation_count INTEGER NOT NULL CHECK (observation_count >= 0),
    eligible_count INTEGER NOT NULL CHECK (eligible_count >= 0),
    alert_count INTEGER NOT NULL CHECK (alert_count >= 0),
    report_hash VARCHAR NOT NULL UNIQUE,
    report JSON NOT NULL,
    owner_review_hash VARCHAR,
    owner_reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (replay_end >= replay_start),
    CHECK (eligible_count <= observation_count),
    CHECK (alert_count <= eligible_count)
);

CREATE TABLE IF NOT EXISTS control.alert_shadow_windows (
    shadow_window_id VARCHAR PRIMARY KEY,
    rule_set_id VARCHAR NOT NULL,
    rule_set_version VARCHAR NOT NULL,
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    window_status VARCHAR NOT NULL CHECK (
        window_status IN ('collecting', 'review_ready', 'verified', 'rejected')
    ),
    expected_session_count INTEGER NOT NULL CHECK (expected_session_count >= 0),
    observed_session_count INTEGER NOT NULL CHECK (observed_session_count >= 0),
    candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
    duplicate_suppressed_count INTEGER NOT NULL CHECK (duplicate_suppressed_count >= 0),
    quality_suppressed_count INTEGER NOT NULL CHECK (quality_suppressed_count >= 0),
    sensitive_violation_count INTEGER NOT NULL CHECK (sensitive_violation_count >= 0),
    external_send_count INTEGER NOT NULL DEFAULT 0 CHECK (external_send_count = 0),
    owner_review_complete BOOLEAN NOT NULL DEFAULT FALSE,
    summary_hash VARCHAR NOT NULL,
    summary JSON NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (window_end >= window_start),
    CHECK (observed_session_count <= expected_session_count)
);

CREATE TABLE IF NOT EXISTS control.alert_rule_approval_revisions (
    approval_revision_id VARCHAR PRIMARY KEY,
    rule_id VARCHAR NOT NULL,
    rule_version VARCHAR NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    decision VARCHAR NOT NULL CHECK (decision IN ('approved', 'rejected', 'revoked')),
    actor_type VARCHAR NOT NULL CHECK (actor_type = 'owner'),
    calibration_run_id VARCHAR,
    shadow_window_id VARCHAR,
    evidence_hash VARCHAR NOT NULL,
    rationale_code VARCHAR NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (
        decision != 'approved' OR
        (calibration_run_id IS NOT NULL AND shadow_window_id IS NOT NULL)
    ),
    UNIQUE(rule_id, rule_version, revision)
);
