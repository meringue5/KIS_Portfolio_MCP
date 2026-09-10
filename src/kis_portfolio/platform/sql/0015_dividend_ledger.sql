-- WI-038 / ADR-026: additive dividend action, entitlement and cash-link ledgers.
-- The legacy 0001 foundation is preserved and must remain empty.
SELECT CASE
    WHEN (SELECT count(*) FROM silver.dividend_events) = 0
    THEN TRUE
    ELSE error('migration 0015 requires empty legacy dividend foundation')
END;

CREATE TABLE IF NOT EXISTS silver.dividend_actions (
    dividend_action_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL,
    jurisdiction VARCHAR NOT NULL,
    issuer_id VARCHAR NOT NULL,
    instrument_id VARCHAR NOT NULL,
    source_action_id VARCHAR NOT NULL,
    first_source_observation_id VARCHAR NOT NULL,
    first_known_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(source_id, jurisdiction, issuer_id, instrument_id, source_action_id)
);

CREATE TABLE IF NOT EXISTS silver.dividend_action_revisions (
    dividend_action_revision_id VARCHAR PRIMARY KEY,
    dividend_action_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    revision_hash VARCHAR NOT NULL,
    action_type VARCHAR NOT NULL,
    action_status VARCHAR NOT NULL,
    certainty VARCHAR NOT NULL,
    amount_per_share DECIMAL(28, 10),
    currency VARCHAR,
    declaration_date DATE,
    ex_date DATE,
    record_date DATE,
    payable_date DATE,
    cancellation_date DATE,
    source_available_at TIMESTAMPTZ NOT NULL,
    source_time_precision VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    filing_revision_id VARCHAR,
    correction_target_revision_id VARCHAR,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(dividend_action_id, revision),
    UNIQUE(dividend_action_id, revision_hash)
);

CREATE TABLE IF NOT EXISTS silver.dividend_entitlements (
    dividend_entitlement_id VARCHAR PRIMARY KEY,
    dividend_action_id VARCHAR NOT NULL,
    account_id VARCHAR NOT NULL,
    first_known_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(dividend_action_id, account_id)
);

CREATE TABLE IF NOT EXISTS silver.dividend_entitlement_revisions (
    dividend_entitlement_revision_id VARCHAR PRIMARY KEY,
    dividend_entitlement_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    revision_hash VARCHAR NOT NULL,
    basis VARCHAR NOT NULL,
    eligibility_date DATE,
    eligible_quantity DECIMAL(28, 10),
    rate_per_share DECIMAL(28, 10),
    expected_gross DECIMAL(28, 8),
    expected_tax DECIMAL(28, 8),
    expected_net DECIMAL(28, 8),
    currency VARCHAR,
    coverage_status VARCHAR NOT NULL,
    source_observation_id VARCHAR,
    position_evidence_id VARCHAR,
    corporate_action_revision_id VARCHAR,
    knowledge_at TIMESTAMPTZ NOT NULL,
    correction_target_revision_id VARCHAR,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(dividend_entitlement_id, revision),
    UNIQUE(dividend_entitlement_id, revision_hash)
);

CREATE TABLE IF NOT EXISTS silver.dividend_receipt_links (
    dividend_receipt_link_id VARCHAR PRIMARY KEY,
    dividend_action_id VARCHAR NOT NULL,
    dividend_entitlement_id VARCHAR,
    cash_flow_event_id VARCHAR,
    relation_key VARCHAR NOT NULL,
    first_known_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(dividend_action_id, relation_key)
);

CREATE TABLE IF NOT EXISTS silver.dividend_receipt_link_revisions (
    dividend_receipt_link_revision_id VARCHAR PRIMARY KEY,
    dividend_receipt_link_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    revision_hash VARCHAR NOT NULL,
    link_status VARCHAR NOT NULL,
    allocated_receipt_amount DECIMAL(28, 8),
    currency VARCHAR,
    reason VARCHAR NOT NULL,
    rule_version VARCHAR NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    correction_target_revision_id VARCHAR,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(dividend_receipt_link_id, revision),
    UNIQUE(dividend_receipt_link_id, revision_hash)
);

CREATE TABLE IF NOT EXISTS silver.cash_flow_event_amount_components (
    cash_amount_component_revision_id VARCHAR PRIMARY KEY,
    cash_flow_event_id VARCHAR NOT NULL,
    component_type VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    amount DECIMAL(28, 8) NOT NULL,
    currency VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    source_observation_id VARCHAR NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    correction_target_revision_id VARCHAR,
    quality_status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(cash_flow_event_id, component_type, revision)
);

CREATE OR REPLACE VIEW silver.dividend_actions_current AS
SELECT * EXCLUDE (row_number_value)
FROM (
    SELECT revisions.*,
           row_number() OVER (
               PARTITION BY dividend_action_id
               ORDER BY knowledge_at DESC, revision DESC, dividend_action_revision_id DESC
           ) AS row_number_value
    FROM silver.dividend_action_revisions revisions
)
WHERE row_number_value = 1;

CREATE OR REPLACE VIEW silver.dividend_entitlements_current AS
SELECT * EXCLUDE (row_number_value)
FROM (
    SELECT revisions.*,
           row_number() OVER (
               PARTITION BY dividend_entitlement_id
               ORDER BY knowledge_at DESC, revision DESC, dividend_entitlement_revision_id DESC
           ) AS row_number_value
    FROM silver.dividend_entitlement_revisions revisions
)
WHERE row_number_value = 1;

CREATE OR REPLACE VIEW silver.dividend_receipt_links_current AS
SELECT * EXCLUDE (row_number_value)
FROM (
    SELECT revisions.*,
           row_number() OVER (
               PARTITION BY dividend_receipt_link_id
               ORDER BY knowledge_at DESC, revision DESC, dividend_receipt_link_revision_id DESC
           ) AS row_number_value
    FROM silver.dividend_receipt_link_revisions revisions
)
WHERE row_number_value = 1;

CREATE OR REPLACE VIEW gold.dividend_monthly_native AS
WITH component_current AS (
    SELECT * EXCLUDE (row_number_value)
    FROM (
        SELECT components.*,
               row_number() OVER (
                   PARTITION BY cash_flow_event_id, component_type
                   ORDER BY knowledge_at DESC, revision DESC, cash_amount_component_revision_id DESC
               ) AS row_number_value
        FROM silver.cash_flow_event_amount_components components
    )
    WHERE row_number_value = 1
), component_pivot AS (
    SELECT cash_flow_event_id,
           max(amount) FILTER (WHERE component_type='gross') AS gross_amount,
           max(amount) FILTER (WHERE component_type='tax') AS tax_amount,
           max(amount) FILTER (WHERE component_type='net') AS net_amount,
           count(DISTINCT component_type) AS sourced_component_count
    FROM component_current
    GROUP BY cash_flow_event_id
)
SELECT date_trunc('month', cash.effective_at)::DATE AS received_month,
       cash.account_id,
       actions.instrument_id,
       cash.currency,
       sum(coalesce(links.allocated_receipt_amount, cash.amount)) AS received_cash_amount,
       sum(CASE WHEN links.allocated_receipt_amount IS NULL THEN components.gross_amount
                ELSE components.gross_amount*abs(links.allocated_receipt_amount)/nullif(abs(cash.amount),0) END) AS sourced_gross_amount,
       sum(CASE WHEN links.allocated_receipt_amount IS NULL THEN components.tax_amount
                ELSE components.tax_amount*abs(links.allocated_receipt_amount)/nullif(abs(cash.amount),0) END) AS sourced_tax_amount,
       sum(CASE WHEN links.allocated_receipt_amount IS NULL THEN components.net_amount
                ELSE components.net_amount*abs(links.allocated_receipt_amount)/nullif(abs(cash.amount),0) END) AS sourced_net_amount,
       count(DISTINCT cash.cash_flow_event_id) AS received_count,
       count(DISTINCT links.dividend_receipt_link_id) AS link_count,
       CASE WHEN min(coalesce(components.sourced_component_count, 0)) = 3
            THEN 'complete' ELSE 'partial' END AS component_coverage,
       CASE WHEN bool_and(links.link_status IN ('exact','reconciled'))
            THEN 'complete' ELSE 'partial' END AS reconciliation_coverage
FROM silver.dividend_receipt_links identities
JOIN silver.dividend_receipt_links_current links USING (dividend_receipt_link_id)
JOIN silver.dividend_actions actions USING (dividend_action_id)
JOIN silver.cash_flow_events_current cash
  ON cash.cash_flow_event_id = identities.cash_flow_event_id
LEFT JOIN component_pivot components ON components.cash_flow_event_id=cash.cash_flow_event_id
WHERE links.link_status IN ('exact','reconciled','partial')
  AND cash.event_type = 'dividend'
GROUP BY received_month, cash.account_id, actions.instrument_id, cash.currency;

CREATE OR REPLACE VIEW gold.dividend_monthly_krw AS
SELECT native.*,
       CASE WHEN native.currency='KRW' THEN native.received_cash_amount
            ELSE native.received_cash_amount * fx.rate END AS received_cash_amount_krw,
       CASE WHEN native.currency='KRW' THEN DATE '1970-01-01' ELSE fx.rate_date END AS fx_rate_date,
       CASE WHEN native.currency='KRW' THEN 1 ELSE fx.rate END AS fx_rate,
       CASE WHEN native.currency='KRW' THEN 'native_krw'
            WHEN fx.rate IS NOT NULL THEN 'governed_close_projection'
            ELSE 'unavailable' END AS conversion_label
FROM gold.dividend_monthly_native native
LEFT JOIN LATERAL (
    SELECT rate_date, rate
    FROM silver.fx_rates_daily
    WHERE base_currency=native.currency AND quote_currency='KRW'
      AND rate_type='close' AND rate_date<=last_day(native.received_month)
      AND quality_status='pass'
    ORDER BY rate_date DESC
    LIMIT 1
) fx ON TRUE;
