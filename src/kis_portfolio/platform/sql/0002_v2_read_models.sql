CREATE OR REPLACE VIEW gold.portfolio_daily_summary AS
SELECT
    evaluation_date,
    evaluation_slot,
    sum(value_krw) AS total_value_krw,
    min(quality_status) AS quality_status,
    max(as_of) AS as_of
FROM gold.portfolio_daily_state
WHERE aggregate_level = 'position'
GROUP BY evaluation_date, evaluation_slot;

CREATE OR REPLACE VIEW control.pipeline_run_summary AS
SELECT
    r.run_id,
    r.pipeline_id,
    r.pipeline_version,
    r.logical_date,
    r.slot,
    r.partition_key,
    r.status,
    r.source_calls,
    count(s.stage_name) AS stage_count,
    count(s.stage_name) FILTER (WHERE s.status = 'succeeded') AS succeeded_stage_count,
    r.started_at,
    r.finished_at
FROM control.pipeline_runs r
LEFT JOIN control.pipeline_stage_runs s ON s.run_id = r.run_id
GROUP BY ALL;
