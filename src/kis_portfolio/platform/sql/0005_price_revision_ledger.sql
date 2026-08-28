CREATE TABLE IF NOT EXISTS silver.price_bar_revisions_daily (
    instrument_id VARCHAR NOT NULL,
    session_date DATE NOT NULL,
    price_basis VARCHAR NOT NULL,
    revision_hash VARCHAR NOT NULL,
    open DECIMAL(28, 8),
    high DECIMAL(28, 8),
    low DECIMAL(28, 8),
    close DECIMAL(28, 8),
    volume BIGINT,
    effective_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    endpoint VARCHAR NOT NULL,
    request_option VARCHAR NOT NULL,
    volume_basis VARCHAR NOT NULL,
    reconstruction_mode VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    metadata JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY(instrument_id, session_date, price_basis, revision_hash)
);

ALTER TABLE silver.price_bars_daily ADD COLUMN IF NOT EXISTS effective_at TIMESTAMPTZ;
ALTER TABLE silver.price_bars_daily ADD COLUMN IF NOT EXISTS knowledge_at TIMESTAMPTZ;
ALTER TABLE silver.price_bars_daily ADD COLUMN IF NOT EXISTS revision_hash VARCHAR;
ALTER TABLE silver.price_bars_daily ADD COLUMN IF NOT EXISTS endpoint VARCHAR;
ALTER TABLE silver.price_bars_daily ADD COLUMN IF NOT EXISTS request_option VARCHAR;
ALTER TABLE silver.price_bars_daily ADD COLUMN IF NOT EXISTS volume_basis VARCHAR;
ALTER TABLE silver.price_bars_daily ADD COLUMN IF NOT EXISTS reconstruction_mode VARCHAR;
