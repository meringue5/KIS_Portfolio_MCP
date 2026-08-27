CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS control;

CREATE TABLE IF NOT EXISTS control.schema_migrations (
    version VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    checksum VARCHAR NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS bronze.source_observations (
    observation_id VARCHAR PRIMARY KEY,
    dataset_id VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    source_record_id VARCHAR NOT NULL,
    idempotency_key VARCHAR NOT NULL UNIQUE,
    effective_at TIMESTAMPTZ,
    observed_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    content_hash VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    payload JSON NOT NULL,
    pipeline_run_id VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS bronze.raw_object_manifest (
    content_hash VARCHAR PRIMARY KEY,
    dataset_id VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    private_uri VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    byte_size BIGINT NOT NULL,
    rights_class VARCHAR NOT NULL,
    sensitivity VARCHAR NOT NULL,
    source_url VARCHAR,
    source_published_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS bronze.owner_research_documents (
    document_sha256 VARCHAR PRIMARY KEY,
    private_uri VARCHAR NOT NULL,
    original_filename VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    byte_size BIGINT NOT NULL,
    issuer_ids JSON,
    published_at TIMESTAMPTZ,
    provided_at TIMESTAMPTZ NOT NULL,
    rights_class VARCHAR NOT NULL,
    rights_assertion VARCHAR NOT NULL,
    intake_status VARCHAR NOT NULL,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS silver.accounts (
    account_id VARCHAR PRIMARY KEY,
    account_label VARCHAR NOT NULL UNIQUE,
    account_type VARCHAR NOT NULL,
    base_currency VARCHAR NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    provenance JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.instruments (
    instrument_id VARCHAR PRIMARY KEY,
    market VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    name VARCHAR,
    asset_type VARCHAR NOT NULL,
    currency VARCHAR NOT NULL,
    issuer_id VARCHAR,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    classification_quality VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    UNIQUE(market, symbol, valid_from)
);

CREATE TABLE IF NOT EXISTS silver.position_snapshots (
    account_id VARCHAR NOT NULL,
    instrument_id VARCHAR NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    quantity DECIMAL(28, 10) NOT NULL,
    average_cost DECIMAL(28, 8),
    cost_currency VARCHAR,
    source_observation_id VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY(account_id, instrument_id, as_of)
);

CREATE TABLE IF NOT EXISTS silver.cash_snapshots (
    account_id VARCHAR NOT NULL,
    currency VARCHAR NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    amount DECIMAL(28, 8) NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY(account_id, currency, as_of)
);

CREATE TABLE IF NOT EXISTS silver.trade_events (
    trade_event_id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL,
    instrument_id VARCHAR NOT NULL,
    side VARCHAR NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL,
    quantity DECIMAL(28, 10) NOT NULL,
    price DECIMAL(28, 8) NOT NULL,
    currency VARCHAR NOT NULL,
    broker_order_id VARCHAR NOT NULL,
    event_version INTEGER NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    UNIQUE(account_id, broker_order_id, event_version)
);

CREATE TABLE IF NOT EXISTS silver.cash_flow_events (
    cash_flow_event_id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    amount DECIMAL(28, 8) NOT NULL,
    currency VARCHAR NOT NULL,
    source_record_id VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    UNIQUE(account_id, source_record_id)
);

CREATE TABLE IF NOT EXISTS silver.purchase_lots (
    lot_id VARCHAR PRIMARY KEY,
    trade_event_id VARCHAR NOT NULL UNIQUE,
    account_id VARCHAR NOT NULL,
    instrument_id VARCHAR NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    original_quantity DECIMAL(28, 10) NOT NULL,
    remaining_quantity DECIMAL(28, 10) NOT NULL,
    unit_cost DECIMAL(28, 8) NOT NULL,
    currency VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.trade_threads (
    thread_id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL,
    instrument_id VARCHAR NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    title VARCHAR,
    status VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    provenance JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS silver.trade_thread_lots (
    thread_id VARCHAR NOT NULL,
    lot_id VARCHAR NOT NULL,
    allocation_revision INTEGER NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL,
    linkage_quality VARCHAR NOT NULL,
    PRIMARY KEY(thread_id, lot_id, allocation_revision)
);

CREATE TABLE IF NOT EXISTS silver.sell_allocation_revisions (
    allocation_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    sell_trade_event_id VARCHAR NOT NULL,
    lot_id VARCHAR NOT NULL,
    allocated_quantity DECIMAL(28, 10) NOT NULL,
    allocation_method VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(allocation_id, revision, lot_id)
);

CREATE TABLE IF NOT EXISTS silver.trade_journal_revisions (
    journal_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    thread_id VARCHAR,
    trade_event_id VARCHAR,
    body VARCHAR NOT NULL,
    authored_by VARCHAR NOT NULL,
    authored_at TIMESTAMPTZ NOT NULL,
    expected_prior_revision INTEGER,
    PRIMARY KEY(journal_id, revision)
);

CREATE TABLE IF NOT EXISTS silver.price_bars_daily (
    instrument_id VARCHAR NOT NULL,
    session_date DATE NOT NULL,
    price_basis VARCHAR NOT NULL,
    open DECIMAL(28, 8), high DECIMAL(28, 8), low DECIMAL(28, 8), close DECIMAL(28, 8),
    volume BIGINT,
    source_observation_id VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY(instrument_id, session_date, price_basis)
);

CREATE TABLE IF NOT EXISTS silver.fx_rates_daily (
    base_currency VARCHAR NOT NULL,
    quote_currency VARCHAR NOT NULL,
    rate_date DATE NOT NULL,
    rate_type VARCHAR NOT NULL,
    rate DECIMAL(28, 10) NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY(base_currency, quote_currency, rate_date, rate_type)
);

CREATE TABLE IF NOT EXISTS silver.etf_constituent_snapshots (
    etf_instrument_id VARCHAR NOT NULL,
    source_date DATE NOT NULL,
    file_hash VARCHAR NOT NULL,
    constituent_ordinal INTEGER NOT NULL,
    constituent_instrument_id VARCHAR,
    constituent_name VARCHAR NOT NULL,
    instrument_type VARCHAR NOT NULL,
    weight_pct DECIMAL(18, 8),
    currency VARCHAR,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY(etf_instrument_id, source_date, file_hash, constituent_ordinal)
);

CREATE TABLE IF NOT EXISTS silver.filing_events (
    issuer_id VARCHAR NOT NULL,
    filing_id VARCHAR NOT NULL,
    document_version VARCHAR NOT NULL,
    filing_type VARCHAR NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    source_id VARCHAR NOT NULL,
    raw_object_hash VARCHAR,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY(issuer_id, filing_id, document_version)
);

CREATE TABLE IF NOT EXISTS silver.financial_facts (
    issuer_id VARCHAR NOT NULL,
    filing_id VARCHAR NOT NULL,
    taxonomy VARCHAR NOT NULL,
    concept VARCHAR NOT NULL,
    period_end DATE NOT NULL,
    unit VARCHAR NOT NULL,
    dimension_hash VARCHAR NOT NULL,
    value DECIMAL(38, 8),
    knowledge_at TIMESTAMPTZ NOT NULL,
    mapping_provenance JSON,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY(issuer_id, filing_id, taxonomy, concept, period_end, unit, dimension_hash)
);

CREATE TABLE IF NOT EXISTS silver.dividend_events (
    dividend_event_id VARCHAR PRIMARY KEY,
    instrument_id VARCHAR NOT NULL,
    account_id VARCHAR,
    event_type VARCHAR NOT NULL,
    event_date DATE NOT NULL,
    gross_amount DECIMAL(28, 8),
    tax_amount DECIMAL(28, 8),
    net_amount DECIMAL(28, 8),
    currency VARCHAR,
    source_fact_id VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    UNIQUE(instrument_id, account_id, event_type, event_date, source_fact_id)
);

CREATE TABLE IF NOT EXISTS silver.macro_observations (
    series_contract_id VARCHAR NOT NULL,
    observation_period DATE NOT NULL,
    realtime_start DATE NOT NULL,
    source_revision VARCHAR NOT NULL,
    value DECIMAL(38, 10),
    unit VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    quality_status VARCHAR NOT NULL,
    PRIMARY KEY(series_contract_id, observation_period, realtime_start, source_revision)
);

CREATE TABLE IF NOT EXISTS silver.owner_research_extractions (
    document_sha256 VARCHAR NOT NULL,
    extractor_id VARCHAR NOT NULL,
    extractor_version VARCHAR NOT NULL,
    extraction_revision INTEGER NOT NULL,
    locator VARCHAR NOT NULL,
    text_content VARCHAR,
    structured_content JSON,
    created_at TIMESTAMPTZ NOT NULL,
    quality_status VARCHAR NOT NULL,
    sensitivity VARCHAR NOT NULL,
    PRIMARY KEY(document_sha256, extractor_id, extractor_version, extraction_revision, locator)
);

CREATE TABLE IF NOT EXISTS gold.portfolio_daily_state (
    evaluation_date DATE NOT NULL,
    evaluation_slot VARCHAR NOT NULL,
    account_id VARCHAR NOT NULL,
    instrument_id VARCHAR NOT NULL,
    aggregate_level VARCHAR NOT NULL,
    quantity DECIMAL(28, 10),
    value_krw DECIMAL(28, 2) NOT NULL,
    cost_krw DECIMAL(28, 2),
    unrealized_pnl_krw DECIMAL(28, 2),
    contribution_pct DECIMAL(18, 8),
    allocation_pct DECIMAL(18, 8),
    as_of TIMESTAMPTZ NOT NULL,
    input_watermarks JSON NOT NULL,
    quality_status VARCHAR NOT NULL,
    lineage_hash VARCHAR NOT NULL,
    PRIMARY KEY(evaluation_date, evaluation_slot, account_id, instrument_id, aggregate_level)
);

CREATE TABLE IF NOT EXISTS control.pipeline_definitions (
    pipeline_id VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    contract_status VARCHAR NOT NULL,
    definition_hash VARCHAR NOT NULL,
    definition JSON NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY(pipeline_id, version)
);

CREATE TABLE IF NOT EXISTS control.pipeline_runs (
    run_id VARCHAR PRIMARY KEY,
    pipeline_id VARCHAR NOT NULL,
    pipeline_version VARCHAR NOT NULL,
    logical_date DATE NOT NULL,
    slot VARCHAR NOT NULL,
    partition_key VARCHAR NOT NULL,
    idempotency_key VARCHAR NOT NULL UNIQUE,
    status VARCHAR NOT NULL,
    source_calls INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    error_code VARCHAR,
    error_message VARCHAR
);

CREATE TABLE IF NOT EXISTS control.pipeline_stage_runs (
    run_id VARCHAR NOT NULL,
    stage_name VARCHAR NOT NULL,
    stage_order INTEGER NOT NULL,
    status VARCHAR NOT NULL,
    attempt INTEGER NOT NULL,
    input_count BIGINT NOT NULL DEFAULT 0,
    output_count BIGINT NOT NULL DEFAULT 0,
    source_calls INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    evidence JSON,
    error_message VARCHAR,
    PRIMARY KEY(run_id, stage_name)
);

CREATE TABLE IF NOT EXISTS control.quality_results (
    quality_result_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,
    dataset_id VARCHAR NOT NULL,
    rule_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    observed_value VARCHAR,
    expected_value VARCHAR,
    details JSON,
    evaluated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS control.lineage_edges (
    lineage_edge_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,
    input_ref VARCHAR NOT NULL,
    output_ref VARCHAR NOT NULL,
    transform_id VARCHAR NOT NULL,
    transform_version VARCHAR NOT NULL,
    evidence_hash VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS control.watermarks (
    pipeline_id VARCHAR NOT NULL,
    partition_key VARCHAR NOT NULL,
    watermark_type VARCHAR NOT NULL,
    watermark_value VARCHAR NOT NULL,
    run_id VARCHAR NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(pipeline_id, partition_key, watermark_type)
);
