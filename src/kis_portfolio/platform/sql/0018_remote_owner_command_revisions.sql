CREATE TABLE IF NOT EXISTS silver.trade_thread_command_revisions (
    command_revision_id VARCHAR PRIMARY KEY,
    thread_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    change_kind VARCHAR NOT NULL,
    change_document JSON NOT NULL,
    authored_by VARCHAR NOT NULL,
    client_id VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,
    idempotency_key_hash VARCHAR NOT NULL,
    authored_at TIMESTAMPTZ NOT NULL,
    expected_prior_revision INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(thread_id, revision),
    UNIQUE(authored_by, client_id, idempotency_key_hash)
);
