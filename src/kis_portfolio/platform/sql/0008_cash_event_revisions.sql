ALTER TABLE silver.cash_flow_events ADD COLUMN IF NOT EXISTS source_id VARCHAR;
ALTER TABLE silver.cash_flow_events ADD COLUMN IF NOT EXISTS source_observation_id VARCHAR;
ALTER TABLE silver.cash_flow_events ADD COLUMN IF NOT EXISTS source_event_code VARCHAR;
ALTER TABLE silver.cash_flow_events ADD COLUMN IF NOT EXISTS settled_at TIMESTAMPTZ;
ALTER TABLE silver.cash_flow_events ADD COLUMN IF NOT EXISTS knowledge_at TIMESTAMPTZ;
ALTER TABLE silver.cash_flow_events ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ;
ALTER TABLE silver.cash_flow_events ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMPTZ;
ALTER TABLE silver.cash_flow_events ADD COLUMN IF NOT EXISTS provenance JSON;

CREATE TABLE IF NOT EXISTS silver.cash_flow_event_revisions (
    cash_flow_event_revision_id VARCHAR PRIMARY KEY,
    cash_flow_event_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    event_type VARCHAR NOT NULL,
    classification_source VARCHAR NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    linked_trade_event_id VARCHAR,
    link_quality VARCHAR NOT NULL,
    correction_reason VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    UNIQUE(cash_flow_event_id, revision)
);

CREATE OR REPLACE VIEW silver.cash_flow_events_current AS
SELECT
    events.cash_flow_event_id,
    events.account_id,
    revisions.event_type,
    events.effective_at,
    events.settled_at,
    events.amount,
    events.currency,
    events.source_id,
    events.source_record_id,
    events.source_event_code,
    events.source_observation_id,
    events.knowledge_at AS event_knowledge_at,
    events.fetched_at,
    events.recorded_at AS event_recorded_at,
    events.quality_status AS event_quality_status,
    events.provenance AS event_provenance,
    revisions.revision,
    revisions.classification_source,
    revisions.knowledge_at AS classification_knowledge_at,
    revisions.recorded_at AS classification_recorded_at,
    revisions.linked_trade_event_id,
    revisions.link_quality,
    revisions.correction_reason,
    revisions.quality_status AS classification_quality_status,
    revisions.provenance AS classification_provenance
FROM silver.cash_flow_events events
JOIN silver.cash_flow_event_revisions revisions USING (cash_flow_event_id)
QUALIFY row_number() OVER (
    PARTITION BY events.cash_flow_event_id
    ORDER BY revisions.knowledge_at DESC, revisions.revision DESC,
             revisions.cash_flow_event_revision_id DESC
) = 1;
