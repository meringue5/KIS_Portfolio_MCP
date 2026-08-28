CREATE TABLE IF NOT EXISTS silver.trade_thread_risk_plan_revisions (
    risk_plan_revision_id VARCHAR PRIMARY KEY,
    risk_plan_id VARCHAR NOT NULL,
    thread_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    revision_hash VARCHAR NOT NULL,
    reference_price DECIMAL(28, 8) NOT NULL CHECK (reference_price > 0),
    stop_price DECIMAL(28, 8) NOT NULL CHECK (stop_price > 0),
    currency VARCHAR NOT NULL,
    risk_budget_ratio DECIMAL(18, 10) NOT NULL CHECK (
        risk_budget_ratio > 0 AND risk_budget_ratio <= 0.0200000000
    ),
    effective_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    authored_by VARCHAR NOT NULL CHECK (authored_by = 'owner'),
    authority_source VARCHAR NOT NULL CHECK (
        authority_source IN ('owner_direct', 'owner_confirmed')
    ),
    expected_prior_revision INTEGER NOT NULL CHECK (expected_prior_revision >= 0),
    advice_metadata JSON NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (stop_price < reference_price),
    UNIQUE(risk_plan_id, revision),
    UNIQUE(risk_plan_id, revision_hash),
    UNIQUE(thread_id, revision)
);

CREATE TABLE IF NOT EXISTS control.owner_review_items (
    review_item_id VARCHAR PRIMARY KEY,
    review_type VARCHAR NOT NULL CHECK (
        review_type IN (
            'missing_thread_risk_plan', 'missing_trade_journal',
            'sell_allocation_confirmation', 'unresolved_sell_allocation'
        )
    ),
    subject_type VARCHAR NOT NULL CHECK (
        subject_type IN ('trade_thread', 'sell_allocation')
    ),
    subject_id VARCHAR NOT NULL,
    identity_hash VARCHAR NOT NULL UNIQUE,
    first_seen_at TIMESTAMPTZ NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS control.owner_review_item_revisions (
    review_item_revision_id VARCHAR PRIMARY KEY,
    review_item_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    review_status VARCHAR NOT NULL CHECK (
        review_status IN ('open', 'answered', 'dismissed')
    ),
    reason_code VARCHAR NOT NULL,
    question VARCHAR NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    actor_type VARCHAR NOT NULL CHECK (actor_type IN ('system', 'owner')),
    expected_prior_revision INTEGER NOT NULL CHECK (expected_prior_revision >= 0),
    resolution_ref VARCHAR,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (review_status = 'open' OR resolution_ref IS NOT NULL),
    UNIQUE(review_item_id, revision)
);

CREATE OR REPLACE VIEW silver.trade_thread_risk_plans_current AS
SELECT *
FROM silver.trade_thread_risk_plan_revisions
QUALIFY row_number() OVER (
    PARTITION BY thread_id
    ORDER BY knowledge_at DESC, revision DESC, risk_plan_revision_id DESC
) = 1;

CREATE OR REPLACE VIEW control.owner_review_items_current AS
SELECT
    items.review_item_id,
    items.review_type,
    items.subject_type,
    items.subject_id,
    items.identity_hash,
    items.first_seen_at,
    items.provenance AS identity_provenance,
    revisions.review_item_revision_id,
    revisions.revision,
    revisions.review_status,
    revisions.reason_code,
    revisions.question,
    revisions.knowledge_at,
    revisions.actor_type,
    revisions.expected_prior_revision,
    revisions.resolution_ref,
    revisions.provenance,
    revisions.recorded_at
FROM control.owner_review_items items
JOIN control.owner_review_item_revisions revisions USING (review_item_id)
QUALIFY row_number() OVER (
    PARTITION BY items.review_item_id
    ORDER BY revisions.knowledge_at DESC, revisions.revision DESC,
             revisions.review_item_revision_id DESC
) = 1;
