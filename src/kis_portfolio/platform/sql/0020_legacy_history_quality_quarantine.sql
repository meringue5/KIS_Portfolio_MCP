CREATE OR REPLACE VIEW gold.portfolio_daily_summary AS
SELECT
    evaluation_date,
    evaluation_slot,
    CASE
        WHEN evaluation_slot = 'v1-latest' THEN NULL
        WHEN count_if(coalesce(lower(trim(quality_status)), '') NOT IN ('pass', 'passed')) > 0 THEN NULL
        ELSE sum(value_krw)
    END AS total_value_krw,
    CASE
        WHEN evaluation_slot = 'v1-latest' THEN 'legacy_unassessed'
        WHEN count_if(coalesce(lower(trim(quality_status)), '') NOT IN ('pass', 'passed')) > 0 THEN 'degraded'
        ELSE 'pass'
    END AS quality_status,
    max(as_of) AS as_of
FROM gold.portfolio_daily_state
WHERE aggregate_level IN ('position', 'cash')
GROUP BY evaluation_date, evaluation_slot;
