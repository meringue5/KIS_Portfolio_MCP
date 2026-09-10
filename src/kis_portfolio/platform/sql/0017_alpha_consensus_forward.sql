-- WI-041: owner-only Alpha Vantage normalized forward snapshots.
-- Raw responses, provider messages and pre-activation history are intentionally absent.
CREATE TABLE IF NOT EXISTS silver.alpha_vantage_consensus_forward_snapshots (
    consensus_forward_snapshot_id VARCHAR PRIMARY KEY,
    definition_hash VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    issuer_id VARCHAR NOT NULL,
    provider_forecast_date DATE NOT NULL,
    horizon VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    estimate_average DECIMAL(38, 12) NOT NULL,
    estimate_high DECIMAL(38, 12) NOT NULL,
    estimate_low DECIMAL(38, 12) NOT NULL,
    analyst_count INTEGER NOT NULL,
    average_7_days_ago DECIMAL(38, 12),
    average_30_days_ago DECIMAL(38, 12),
    average_60_days_ago DECIMAL(38, 12),
    average_90_days_ago DECIMAL(38, 12),
    revision_up_trailing_7_days INTEGER,
    revision_up_trailing_30_days INTEGER,
    revision_down_trailing_7_days INTEGER,
    revision_down_trailing_30_days INTEGER,
    us_session_date DATE NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    source_request_ref VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE(issuer_id, provider_forecast_date, metric, horizon, fetched_at)
);

CREATE OR REPLACE VIEW silver.alpha_vantage_consensus_forward_latest AS
SELECT * EXCLUDE (row_number_value)
FROM (
    SELECT snapshots.*,
           row_number() OVER (
               PARTITION BY issuer_id, provider_forecast_date, metric, horizon
               ORDER BY fetched_at DESC, consensus_forward_snapshot_id DESC
           ) AS row_number_value
    FROM silver.alpha_vantage_consensus_forward_snapshots snapshots
)
WHERE row_number_value = 1;
