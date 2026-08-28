CREATE TABLE IF NOT EXISTS silver.position_episodes (
    episode_id VARCHAR PRIMARY KEY,
    account_id VARCHAR NOT NULL,
    opening_instrument_id VARCHAR NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    identity_hash VARCHAR NOT NULL UNIQUE,
    first_run_id VARCHAR NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS silver.position_episode_revisions (
    position_episode_revision_id VARCHAR PRIMARY KEY,
    episode_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    instrument_id VARCHAR NOT NULL,
    episode_status VARCHAR NOT NULL CHECK (episode_status IN ('open', 'closed')),
    closed_at TIMESTAMPTZ,
    reconstruction_start_at TIMESTAMPTZ NOT NULL,
    reconstruction_cutoff_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    current_quantity DECIMAL(28, 10) NOT NULL CHECK (current_quantity >= 0),
    replayed_quantity DECIMAL(28, 10) NOT NULL,
    inferred_opening_quantity DECIMAL(28, 10) CHECK (
        inferred_opening_quantity IS NULL OR inferred_opening_quantity > 0
    ),
    evidence_provenance VARCHAR CHECK (
        evidence_provenance IS NULL OR evidence_provenance IN ('actual', 'manual', 'inferred_opening')
    ),
    reconstruction_status VARCHAR NOT NULL CHECK (
        reconstruction_status IN (
            'reconstructed', 'inferred_opening', 'provisional', 'not_assessed',
            'reconciliation_exception'
        )
    ),
    coverage_quality_result_id VARCHAR,
    blockers JSON NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (reconstruction_start_at < reconstruction_cutoff_at),
    CHECK (closed_at IS NULL OR closed_at >= reconstruction_start_at),
    UNIQUE(episode_id, revision)
);

CREATE TABLE IF NOT EXISTS silver.purchase_lot_identities (
    lot_id VARCHAR PRIMARY KEY,
    episode_id VARCHAR NOT NULL,
    account_id VARCHAR NOT NULL,
    opening_instrument_id VARCHAR NOT NULL,
    opening_trade_event_id VARCHAR,
    opened_at TIMESTAMPTZ NOT NULL,
    evidence_provenance VARCHAR NOT NULL CHECK (
        evidence_provenance IN ('actual', 'manual', 'inferred_opening')
    ),
    identity_hash VARCHAR NOT NULL UNIQUE,
    first_run_id VARCHAR NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (
        evidence_provenance <> 'actual' OR opening_trade_event_id IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS silver.purchase_lot_revisions (
    purchase_lot_revision_id VARCHAR PRIMARY KEY,
    lot_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    revision_hash VARCHAR NOT NULL,
    effective_quantity DECIMAL(28, 10) NOT NULL CHECK (effective_quantity > 0),
    remaining_quantity DECIMAL(28, 10) NOT NULL CHECK (remaining_quantity >= 0),
    effective_unit_cost DECIMAL(28, 8),
    currency VARCHAR NOT NULL,
    reconstruction_status VARCHAR NOT NULL CHECK (
        reconstruction_status IN (
            'reconstructed', 'inferred_opening', 'provisional', 'not_assessed',
            'reconciliation_exception'
        )
    ),
    effective_at TIMESTAMPTZ NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    cause_type VARCHAR NOT NULL CHECK (
        cause_type IN (
            'buy_trade', 'inferred_opening', 'sell_allocation',
            'corporate_action', 'manual_correction'
        )
    ),
    cause_ref VARCHAR NOT NULL,
    quality_status VARCHAR NOT NULL,
    blockers JSON NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (remaining_quantity <= effective_quantity),
    UNIQUE(lot_id, revision),
    UNIQUE(lot_id, revision_hash)
);

CREATE TABLE IF NOT EXISTS silver.sell_allocation_sets (
    allocation_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    revision_hash VARCHAR NOT NULL,
    sell_trade_event_id VARCHAR NOT NULL,
    account_id VARCHAR NOT NULL,
    instrument_id VARCHAR NOT NULL,
    episode_id VARCHAR NOT NULL,
    allocation_method VARCHAR NOT NULL CHECK (
        allocation_method IN ('explicit_lot', 'explicit_thread_fifo', 'inferred_fifo')
    ),
    requested_quantity DECIMAL(28, 10) NOT NULL CHECK (requested_quantity > 0),
    allocated_quantity DECIMAL(28, 10) NOT NULL CHECK (allocated_quantity >= 0),
    unallocated_quantity DECIMAL(28, 10) NOT NULL CHECK (unallocated_quantity >= 0),
    allocation_status VARCHAR NOT NULL CHECK (
        allocation_status IN ('complete', 'reconciliation_exception')
    ),
    knowledge_at TIMESTAMPTZ NOT NULL,
    created_by VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    blockers JSON NOT NULL,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (allocated_quantity + unallocated_quantity = requested_quantity),
    PRIMARY KEY(allocation_id, revision),
    UNIQUE(allocation_id, revision_hash),
    UNIQUE(sell_trade_event_id, revision)
);

CREATE TABLE IF NOT EXISTS control.reconstruction_exceptions (
    exception_id VARCHAR PRIMARY KEY,
    partition_key VARCHAR NOT NULL,
    episode_id VARCHAR,
    exception_type VARCHAR NOT NULL,
    identity_hash VARCHAR NOT NULL UNIQUE,
    first_run_id VARCHAR NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS control.reconstruction_exception_revisions (
    reconstruction_exception_revision_id VARCHAR PRIMARY KEY,
    exception_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    exception_status VARCHAR NOT NULL CHECK (
        exception_status IN ('open', 'resolved', 'superseded')
    ),
    reason VARCHAR NOT NULL,
    evidence_refs JSON NOT NULL,
    knowledge_at TIMESTAMPTZ NOT NULL,
    resolution_ref VARCHAR,
    provenance JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (exception_status = 'open' OR resolution_ref IS NOT NULL),
    UNIQUE(exception_id, revision)
);

CREATE OR REPLACE VIEW silver.position_episodes_current AS
SELECT
    episodes.episode_id,
    episodes.account_id,
    episodes.opening_instrument_id,
    episodes.opened_at,
    episodes.identity_hash,
    episodes.first_run_id,
    revisions.position_episode_revision_id,
    revisions.revision,
    revisions.instrument_id,
    revisions.episode_status,
    revisions.closed_at,
    revisions.reconstruction_start_at,
    revisions.reconstruction_cutoff_at,
    revisions.knowledge_at,
    revisions.current_quantity,
    revisions.replayed_quantity,
    revisions.inferred_opening_quantity,
    revisions.evidence_provenance,
    revisions.reconstruction_status,
    revisions.coverage_quality_result_id,
    revisions.blockers,
    revisions.provenance,
    revisions.recorded_at
FROM silver.position_episodes episodes
JOIN silver.position_episode_revisions revisions USING (episode_id)
QUALIFY row_number() OVER (
    PARTITION BY episodes.episode_id
    ORDER BY revisions.knowledge_at DESC, revisions.revision DESC,
             revisions.position_episode_revision_id DESC
) = 1;

CREATE OR REPLACE VIEW silver.purchase_lot_states_current AS
SELECT
    lots.lot_id,
    lots.episode_id,
    lots.account_id,
    lots.opening_instrument_id,
    episodes.instrument_id,
    lots.opening_trade_event_id,
    lots.opened_at,
    lots.evidence_provenance,
    lots.identity_hash,
    lots.first_run_id,
    revisions.purchase_lot_revision_id,
    revisions.revision,
    revisions.revision_hash,
    revisions.effective_quantity,
    revisions.remaining_quantity,
    revisions.effective_unit_cost,
    revisions.currency,
    revisions.reconstruction_status,
    revisions.effective_at,
    revisions.knowledge_at,
    revisions.cause_type,
    revisions.cause_ref,
    revisions.quality_status,
    revisions.blockers,
    revisions.provenance,
    revisions.recorded_at
FROM silver.purchase_lot_identities lots
JOIN silver.purchase_lot_revisions revisions USING (lot_id)
JOIN silver.position_episodes_current episodes USING (episode_id)
QUALIFY row_number() OVER (
    PARTITION BY lots.lot_id
    ORDER BY revisions.knowledge_at DESC, revisions.revision DESC,
             revisions.purchase_lot_revision_id DESC
) = 1;

CREATE OR REPLACE VIEW silver.sell_allocations_current AS
WITH current_sets AS (
    SELECT *
    FROM silver.sell_allocation_sets
    QUALIFY row_number() OVER (
        PARTITION BY allocation_id
        ORDER BY knowledge_at DESC, revision DESC, revision_hash DESC
    ) = 1
)
SELECT
    sets.allocation_id,
    sets.revision,
    sets.revision_hash,
    sets.sell_trade_event_id,
    sets.account_id,
    sets.instrument_id,
    sets.episode_id,
    sets.allocation_method,
    sets.requested_quantity,
    sets.allocated_quantity,
    sets.unallocated_quantity,
    sets.allocation_status,
    sets.knowledge_at,
    sets.created_by,
    sets.reason,
    sets.blockers,
    sets.provenance,
    slices.lot_id,
    slices.allocated_quantity AS lot_allocated_quantity,
    slices.quality_status AS slice_quality_status,
    sets.recorded_at
FROM current_sets sets
LEFT JOIN silver.sell_allocation_revisions slices
  ON slices.allocation_id = sets.allocation_id
 AND slices.revision = sets.revision;

CREATE OR REPLACE VIEW control.reconstruction_exceptions_current AS
SELECT
    exceptions.exception_id,
    exceptions.partition_key,
    exceptions.episode_id,
    exceptions.exception_type,
    exceptions.identity_hash,
    exceptions.first_run_id,
    exceptions.first_seen_at,
    revisions.reconstruction_exception_revision_id,
    revisions.revision,
    revisions.exception_status,
    revisions.reason,
    revisions.evidence_refs,
    revisions.knowledge_at,
    revisions.resolution_ref,
    revisions.provenance,
    revisions.recorded_at
FROM control.reconstruction_exceptions exceptions
JOIN control.reconstruction_exception_revisions revisions USING (exception_id)
QUALIFY row_number() OVER (
    PARTITION BY exceptions.exception_id
    ORDER BY revisions.knowledge_at DESC, revisions.revision DESC,
             revisions.reconstruction_exception_revision_id DESC
) = 1;
