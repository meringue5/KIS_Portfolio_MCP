CREATE TABLE IF NOT EXISTS silver.instrument_versions (
    instrument_version_id VARCHAR PRIMARY KEY,
    instrument_id VARCHAR NOT NULL,
    market VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    name VARCHAR,
    asset_type VARCHAR NOT NULL,
    economic_exposure VARCHAR NOT NULL,
    currency VARCHAR NOT NULL,
    issuer_id VARCHAR,
    valid_from TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    classification_source VARCHAR NOT NULL,
    classification_quality VARCHAR NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    metadata JSON NOT NULL,
    UNIQUE(instrument_id, valid_from),
    UNIQUE(instrument_id, knowledge_at, classification_source)
);

CREATE OR REPLACE VIEW silver.instrument_versions_effective AS
SELECT
    *,
    lead(valid_from) OVER (
        PARTITION BY instrument_id ORDER BY valid_from, knowledge_at, instrument_version_id
    ) AS valid_to
FROM silver.instrument_versions;

CREATE OR REPLACE VIEW silver.instruments_current AS
SELECT * EXCLUDE (valid_to)
FROM silver.instrument_versions_effective
QUALIFY row_number() OVER (
    PARTITION BY instrument_id ORDER BY valid_from DESC, knowledge_at DESC, instrument_version_id DESC
) = 1;

CREATE TABLE IF NOT EXISTS control.etf_instrument_routes (
    route_id VARCHAR PRIMARY KEY,
    instrument_id VARCHAR NOT NULL,
    market VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    profile_id VARCHAR NOT NULL,
    provider_product_key VARCHAR NOT NULL,
    product_key_kind VARCHAR NOT NULL,
    activation_state VARCHAR NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    knowledge_at TIMESTAMPTZ NOT NULL,
    contract_version VARCHAR NOT NULL,
    metadata JSON NOT NULL,
    UNIQUE(instrument_id, valid_from)
);
