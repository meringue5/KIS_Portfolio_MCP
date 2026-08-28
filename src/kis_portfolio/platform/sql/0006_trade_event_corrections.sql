CREATE TABLE IF NOT EXISTS silver.trade_event_revisions (
    trade_event_revision_id VARCHAR PRIMARY KEY,
    source_trade_event_id VARCHAR NOT NULL,
    account_id VARCHAR NOT NULL,
    market VARCHAR NOT NULL,
    product_code VARCHAR NOT NULL,
    instrument_id VARCHAR NOT NULL,
    broker_order_id VARCHAR NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL,
    execution_sequence VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    side VARCHAR NOT NULL,
    quantity DECIMAL(28, 10) NOT NULL,
    price DECIMAL(28, 8) NOT NULL,
    currency VARCHAR NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    correction_reason VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    metadata JSON NOT NULL,
    UNIQUE(source_trade_event_id, revision),
    UNIQUE(account_id, market, product_code, broker_order_id, executed_at, execution_sequence, revision)
);

CREATE OR REPLACE VIEW silver.trade_events_current AS
SELECT
    trade_event_revision_id AS trade_event_id,
    source_trade_event_id,
    account_id,
    market,
    product_code,
    instrument_id,
    broker_order_id,
    executed_at,
    execution_sequence,
    revision,
    side,
    quantity,
    price,
    currency,
    knowledge_at,
    source_observation_id,
    correction_reason,
    quality_status,
    metadata
FROM silver.trade_event_revisions
QUALIFY row_number() OVER (
    PARTITION BY source_trade_event_id ORDER BY revision DESC, knowledge_at DESC, trade_event_revision_id DESC
) = 1;

CREATE OR REPLACE VIEW silver.purchase_lots_current AS
SELECT lots.*
FROM silver.purchase_lots lots
JOIN silver.trade_events_current events
  ON events.source_trade_event_id = lots.trade_event_id
WHERE events.side = 'buy' AND events.quality_status = 'pass';
