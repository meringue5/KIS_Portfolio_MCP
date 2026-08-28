CREATE OR REPLACE VIEW gold.portfolio_daily_summary AS
SELECT
    evaluation_date,
    evaluation_slot,
    sum(value_krw) AS total_value_krw,
    CASE WHEN count_if(quality_status <> 'passed') > 0 THEN 'degraded' ELSE 'passed' END AS quality_status,
    max(as_of) AS as_of
FROM gold.portfolio_daily_state
WHERE aggregate_level IN ('position', 'cash')
GROUP BY evaluation_date, evaluation_slot;
