CREATE TABLE IF NOT EXISTS control.market_calendar (
    market VARCHAR NOT NULL,
    trade_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL,
    open_time_local VARCHAR,
    close_time_local VARCHAR,
    timezone VARCHAR NOT NULL DEFAULT 'Asia/Seoul',
    source VARCHAR,
    note VARCHAR,
    raw_data JSON,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (market, trade_date)
);

CREATE TABLE IF NOT EXISTS control.instrument_master (
    symbol VARCHAR NOT NULL,
    market VARCHAR NOT NULL,
    standard_code VARCHAR,
    name VARCHAR,
    group_code VARCHAR,
    etp_code VARCHAR,
    idx_large_code VARCHAR,
    idx_mid_code VARCHAR,
    idx_small_code VARCHAR,
    raw_data JSON,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (symbol, market)
);

CREATE TABLE IF NOT EXISTS control.instrument_classification_overrides (
    symbol VARCHAR NOT NULL,
    market VARCHAR NOT NULL DEFAULT 'KRX',
    exposure_type VARCHAR NOT NULL,
    exposure_region VARCHAR,
    asset_subtype VARCHAR,
    reason VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (symbol, market)
);
