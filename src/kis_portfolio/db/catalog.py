"""Machine-readable data object registry for warehouse governance checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataObject:
    name: str
    object_type: str
    layer: str
    target_schema: str
    write_mode: str
    backup_policy: str
    sensitivity: str
    purpose: str
    grain: str
    key: str
    physical_schema: str = "main"

    @property
    def qualified_name(self) -> str:
        return f"{self.physical_schema}.{self.name}"


DATA_OBJECTS = (
    DataObject(
        "schema_migrations", "table", "control", "control", "migration ledger",
        "excluded", "internal", "Applied database migration versions.",
        "one row per migration version", "version",
    ),
    DataObject(
        "market_calendar", "table", "control", "control", "upsert",
        "parquet", "internal", "Market open and close calendar used by batch jobs.",
        "one row per market and trade date", "market, trade_date",
    ),
    DataObject(
        "instrument_master", "table", "control", "control", "upsert",
        "parquet", "internal", "KIS instrument master used for classification.",
        "one row per symbol and market", "symbol, market",
    ),
    DataObject(
        "instrument_classification_overrides", "table", "control", "control", "upsert",
        "parquet", "confidential", "Local exposure classification overrides.",
        "one row per symbol and market", "symbol, market",
    ),
    DataObject(
        "portfolio_snapshots", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Domestic and pension balance observations with raw KIS JSON.",
        "one account observation per fetch", "id",
    ),
    DataObject(
        "overseas_asset_snapshots", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Overseas balance and deposit observations with feeder aggregates.",
        "one overseas account observation per overview refresh", "id",
    ),
    DataObject(
        "order_history", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Domestic order query observations with raw response JSON.",
        "one account and query-range observation per fetch", "id",
    ),
    DataObject(
        "overseas_order_history", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Overseas order query observations with raw response JSON.",
        "one account and query-filter observation per fetch", "id",
    ),
    DataObject(
        "overseas_transaction_history", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Overseas transaction query observations with raw response JSON.",
        "one account and query-filter observation per fetch", "id",
    ),
    DataObject(
        "overseas_settlement_balance_snapshots", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Overseas settlement-basis balance observations.",
        "one account and base-date observation per fetch", "id",
    ),
    DataObject(
        "trade_profit_history", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Domestic or overseas profit report observations.",
        "one account, market, and requested-period observation", "id",
    ),
    DataObject(
        "price_history", "table", "silver", "silver", "insert-ignore; adjusted resync updates",
        "parquet", "internal", "Normalized domestic and overseas price history cache.",
        "one symbol, exchange, and market date", "symbol, exchange, date",
    ),
    DataObject(
        "exchange_rate_history", "table", "silver", "silver", "insert-ignore",
        "parquet", "internal", "Normalized exchange-rate history cache.",
        "one currency, date, and period", "currency, date, period",
    ),
    DataObject(
        "asset_overview_snapshots", "table", "silver", "silver", "append-only",
        "parquet", "confidential", "Canonical total-asset aggregate snapshots in KRW.",
        "one canonical portfolio overview per refresh", "id",
    ),
    DataObject(
        "asset_holding_snapshots", "table", "silver", "silver", "append-only",
        "parquet", "confidential", "Normalized holdings and cash rows for an overview snapshot.",
        "one holding or cash row per overview snapshot", "id; overview_snapshot_id is parent",
    ),
    DataObject(
        "domestic_orders", "table", "silver", "silver", "upsert",
        "parquet", "confidential", "Canonical domestic order and fill state.",
        "one KIS domestic order identity", "account_id, account_product_code, order_date, order_branch_no, order_no",
    ),
    DataObject(
        "overseas_orders", "table", "silver", "silver", "upsert",
        "parquet", "confidential", "Canonical overseas order and fill state.",
        "one KIS overseas order identity", "account_id, account_product_code, order_date, exchange_code, order_branch_no, order_no",
    ),
    DataObject(
        "overseas_transactions", "table", "silver", "silver", "upsert",
        "parquet", "confidential", "Canonical normalized overseas transactions.",
        "one stable raw transaction identity", "account_id, account_product_code, transaction_hash",
    ),
    DataObject(
        "portfolio_daily_snapshots", "view", "gold", "gold", "derived view",
        "excluded", "confidential", "Latest domestic or pension account snapshot for each day.",
        "one account and day", "account_id, account_type, snap_date",
    ),
    DataObject(
        "asset_overview_daily_snapshots", "view", "gold", "gold", "derived view",
        "excluded", "confidential", "Latest canonical total-asset overview for each day.",
        "one portfolio and day", "snap_date",
    ),
    DataObject(
        "kis_api_access_tokens", "table", "security", "security", "upsert",
        "excluded", "restricted", "Encrypted short-lived KIS API token cache.",
        "one account, account type, and app-key cache identity", "cache_key",
    ),
    DataObject(
        "auth_users", "table", "security", "security", "upsert",
        "excluded", "restricted", "Authorized MCP owner user records.",
        "one application user", "id; primary_email is unique",
    ),
    DataObject(
        "auth_identities", "table", "security", "security", "upsert",
        "excluded", "restricted", "OAuth provider identities linked to users.",
        "one provider subject", "id; provider, provider_subject is unique",
    ),
    DataObject(
        "oauth_clients", "table", "security", "security", "upsert",
        "excluded", "restricted", "Static and dynamically registered OAuth clients.",
        "one OAuth client", "client_id",
    ),
    DataObject(
        "oauth_grants", "table", "security", "security", "upsert and revoke",
        "excluded", "restricted", "User consent grants for OAuth clients and scopes.",
        "one user, client, and normalized scope", "id; user_id, client_id, scope is unique",
    ),
    DataObject(
        "oauth_authorization_codes", "table", "security", "security", "insert and consume",
        "excluded", "restricted", "Hashed one-time OAuth authorization codes.",
        "one authorization code", "id; code_digest is unique",
    ),
    DataObject(
        "oauth_tokens", "table", "security", "security", "insert and revoke",
        "excluded", "restricted", "Hashed OAuth access and refresh token state.",
        "one issued token", "id; token_digest is unique",
    ),
)


# V2 objects are governed separately from the V1 runtime allowlist. They are created only by
# ``kis-portfolio-migrate``; V1 ``init_schema`` and the current backup job do not touch them.
V2_DATA_OBJECTS = (
    DataObject("source_observations", "table", "bronze", "bronze", "append-only", "parquet", "confidential", "Immutable source envelopes for replay.", "one source record observation", "idempotency_key", "bronze"),
    DataObject("raw_object_manifest", "table", "bronze", "bronze", "content-addressed", "object", "restricted", "Private raw-object identity and rights manifest.", "one content hash", "content_hash", "bronze"),
    DataObject("owner_research_documents", "table", "bronze", "bronze", "content-addressed", "object", "restricted", "Owner-provided PDF metadata and private object identity.", "one PDF content hash", "document_sha256", "bronze"),
    DataObject("accounts", "table", "silver", "silver", "versioned upsert", "parquet", "confidential", "Canonical account identities.", "one account identity", "account_id", "silver"),
    DataObject("instruments", "table", "silver", "silver", "versioned upsert", "parquet", "internal", "Canonical instrument identity versions.", "one instrument identity", "instrument_id", "silver"),
    DataObject("instrument_versions", "table", "silver", "silver", "append-only versions", "parquet", "internal", "Point-in-time asset type and classification evidence.", "one instrument classification version", "instrument_id, valid_from", "silver"),
    DataObject("instrument_versions_effective", "view", "silver", "silver", "derived validity intervals", "excluded", "internal", "Instrument versions with derived valid_to intervals.", "one instrument classification interval", "instrument_id, valid_from", "silver"),
    DataObject("instruments_current", "view", "silver", "silver", "latest version projection", "excluded", "internal", "Latest governed classification for each instrument.", "one instrument", "instrument_id", "silver"),
    DataObject("position_snapshots", "table", "silver", "silver", "idempotent upsert", "parquet", "confidential", "Canonical position observations.", "one account instrument and as-of", "account_id, instrument_id, as_of", "silver"),
    DataObject("cash_snapshots", "table", "silver", "silver", "idempotent upsert", "parquet", "confidential", "Canonical cash observations.", "one account currency and as-of", "account_id, currency, as_of", "silver"),
    DataObject("trade_events", "table", "silver", "silver", "append-only versions", "parquet", "confidential", "Canonical executed-order events.", "one broker order event version", "trade_event_id", "silver"),
    DataObject("trade_event_revisions", "table", "silver", "silver", "append-only corrections", "parquet", "confidential", "Revision-aware broker event identity and corrected side projection.", "one source trade event correction revision", "source_trade_event_id, revision", "silver"),
    DataObject("trade_events_current", "view", "silver", "silver", "latest revision projection", "excluded", "confidential", "Latest governed revision of each broker trade event.", "one source trade event", "source_trade_event_id", "silver"),
    DataObject("cash_flow_events", "table", "silver", "silver", "append-only events", "parquet", "confidential", "Immutable source cash-event identity and monetary fact.", "one broker or provenance-tagged manual cash event", "cash_flow_event_id; account_id, source_id, source_record_id is unique", "silver"),
    DataObject("cash_flow_event_revisions", "table", "silver", "silver", "append-only classification revisions", "parquet", "confidential", "Point-in-time cash-event classification and reversible trade linkage revisions.", "one cash event classification revision", "cash_flow_event_id, revision", "silver"),
    DataObject("cash_flow_events_current", "view", "silver", "silver", "latest knowledge projection", "excluded", "confidential", "Latest governed classification for each immutable cash event.", "one cash event", "cash_flow_event_id", "silver"),
    DataObject("position_episodes", "table", "silver", "silver", "append-only identities", "parquet", "confidential", "Stable account instrument ownership-episode identities.", "one continuous non-zero ownership episode", "episode_id; identity_hash is unique", "silver"),
    DataObject("position_episode_revisions", "table", "silver", "silver", "append-only reconstruction revisions", "parquet", "confidential", "Versioned position reconstruction outcomes and blockers.", "one position episode reconstruction revision", "episode_id, revision", "silver"),
    DataObject("position_episodes_current", "view", "silver", "silver", "latest knowledge projection", "excluded", "confidential", "Latest reconstruction revision for each position episode.", "one position episode", "episode_id", "silver"),
    DataObject("purchase_lots", "table", "silver", "silver", "append-only open; derived balance", "parquet", "confidential", "Buy-order purchase lots.", "one executed buy order", "lot_id", "silver"),
    DataObject("purchase_lots_current", "view", "silver", "silver", "corrected buy-only projection", "excluded", "confidential", "Purchase lots whose current trade revision is a valid buy.", "one currently valid buy lot", "lot_id", "silver"),
    DataObject("purchase_lot_identities", "table", "silver", "silver", "append-only identities", "parquet", "confidential", "Canonical actual manual or inferred-opening purchase-lot identities.", "one purchase lot identity within an episode", "lot_id; identity_hash is unique", "silver"),
    DataObject("purchase_lot_revisions", "table", "silver", "silver", "append-only state revisions", "parquet", "confidential", "Versioned effective and remaining lot quantity cost and quality.", "one purchase lot state revision", "lot_id, revision", "silver"),
    DataObject("purchase_lot_states_current", "view", "silver", "silver", "latest knowledge projection", "excluded", "confidential", "Latest reconstructed state for each canonical purchase lot.", "one purchase lot identity", "lot_id", "silver"),
    DataObject("trade_threads", "table", "silver", "silver", "versioned upsert", "parquet", "confidential", "Owner investment-decision threads.", "one investment thread", "thread_id", "silver"),
    DataObject("trade_thread_lots", "table", "silver", "silver", "append-only revisions", "parquet", "confidential", "Versioned lot-to-thread links.", "one thread lot allocation revision", "thread_id, lot_id, allocation_revision", "silver"),
    DataObject("sell_allocation_revisions", "table", "silver", "silver", "append-only revisions", "parquet", "confidential", "Explicit or inferred sell-to-lot allocation revisions.", "one allocation lot revision", "allocation_id, revision, lot_id", "silver"),
    DataObject("sell_allocation_sets", "table", "silver", "silver", "append-only whole revisions", "parquet", "confidential", "Whole sell-allocation revision headers and unresolved quantities.", "one sell allocation revision", "allocation_id, revision; sell_trade_event_id, revision is unique", "silver"),
    DataObject("sell_allocations_current", "view", "silver", "silver", "latest whole revision projection", "excluded", "confidential", "Latest whole allocation revision with zero or more lot slices.", "one current sell allocation lot slice or unresolved header", "allocation_id, lot_id", "silver"),
    DataObject("trade_journal_revisions", "table", "silver", "silver", "append-only revisions", "parquet", "confidential", "Owner-authored trade journal history.", "one journal revision", "journal_id, revision", "silver"),
    DataObject("price_bars_daily", "table", "silver", "silver", "idempotent upsert", "parquet", "internal", "Raw and adjusted daily OHLCV.", "one instrument session and basis", "instrument_id, session_date, price_basis", "silver"),
    DataObject("price_bar_revisions_daily", "table", "silver", "silver", "append-only content revisions", "parquet", "internal", "Point-in-time price observations with endpoint-specific basis provenance.", "one instrument session basis and content revision", "instrument_id, session_date, price_basis, revision_hash", "silver"),
    DataObject("corporate_actions", "table", "silver", "silver", "append-only identities", "parquet", "internal", "Immutable source corporate-action identities.", "one source corporate-action identity", "source_id, source_record_id", "silver"),
    DataObject("corporate_action_revisions", "table", "silver", "silver", "append-only content revisions", "parquet", "internal", "Point-in-time corporate-action terms and status revisions.", "one action content revision", "corporate_action_id, revision_hash", "silver"),
    DataObject("corporate_action_adjustment_effects", "table", "silver", "silver", "append-only effects", "parquet", "internal", "Explicit price quantity and instrument adjustment effects tied to one action revision.", "one action revision and typed adjustment effect", "corporate_action_revision_id, effect_type, input_instrument_id, output_instrument_id", "silver"),
    DataObject("corporate_actions_current", "view", "silver", "silver", "latest knowledge projection", "excluded", "internal", "Latest governed revision for each corporate action.", "one corporate-action identity", "corporate_action_id", "silver"),
    DataObject("fx_rates_daily", "table", "silver", "silver", "idempotent upsert", "parquet", "internal", "Daily FX observations.", "one pair date and rate type", "base_currency, quote_currency, rate_date, rate_type", "silver"),
    DataObject("etf_constituent_snapshots", "table", "silver", "silver", "append-only snapshots", "parquet", "internal", "Official ETF constituent snapshots.", "one ETF file constituent row", "etf_instrument_id, source_date, file_hash, constituent_ordinal", "silver"),
    DataObject("filing_events", "table", "silver", "silver", "append-only versions", "parquet", "internal", "Filing identity and correction events.", "one issuer filing document version", "issuer_id, filing_id, document_version", "silver"),
    DataObject("financial_facts", "table", "silver", "silver", "append-only facts", "parquet", "internal", "Point-in-time normalized financial facts.", "one filing taxonomy fact", "issuer_id, filing_id, taxonomy, concept, period_end, unit, dimension_hash", "silver"),
    DataObject("dividend_events", "table", "silver", "silver", "append-only events", "parquet", "confidential", "Declared entitled received and corrected dividends.", "one dividend state event", "dividend_event_id", "silver"),
    DataObject("macro_observations", "table", "silver", "silver", "append-only vintages", "parquet", "internal", "Governed macro observations and vintages.", "one series period vintage revision", "series_contract_id, observation_period, realtime_start, source_revision", "silver"),
    DataObject("owner_research_extractions", "table", "silver", "silver", "append-only versions", "object", "restricted", "Versioned page or section extraction with document lineage.", "one document extractor revision locator", "document_sha256, extractor_id, extractor_version, extraction_revision, locator", "silver"),
    DataObject("portfolio_daily_state", "table", "gold", "gold", "idempotent materialization", "parquet", "confidential", "Quality-gated daily canonical portfolio state.", "one date slot account instrument aggregate", "evaluation_date, evaluation_slot, account_id, instrument_id, aggregate_level", "gold"),
    DataObject("metric_values", "table", "gold", "gold", "idempotent append; conflicting replay rejected", "parquet", "confidential", "Versioned point-in-time metric values with quality and lineage.", "one metric version subject and evaluation timestamp", "metric_id, metric_version, subject_type, subject_id, evaluation_at", "gold"),
    DataObject("portfolio_daily_summary", "view", "gold", "gold", "derived view", "excluded", "confidential", "Daily portfolio summary read model.", "one date and slot", "evaluation_date, evaluation_slot", "gold"),
    DataObject("schema_migrations", "table", "control", "control", "migration ledger", "excluded", "internal", "Checksum-verified V2 migration versions.", "one migration version", "version", "control"),
    DataObject("pipeline_definitions", "table", "control", "control", "versioned upsert", "parquet", "internal", "Managed pipeline definitions.", "one pipeline version", "pipeline_id, version", "control"),
    DataObject("metric_definitions", "table", "control", "control", "versioned upsert", "parquet", "internal", "Approved metric contract definitions and immutable hashes.", "one metric contract version", "metric_id, version", "control"),
    DataObject("pipeline_runs", "table", "control", "control", "idempotent claim", "parquet", "internal", "Pipeline logical-run ledger.", "one logical pipeline run key", "idempotency_key", "control"),
    DataObject("pipeline_stage_runs", "table", "control", "control", "resumable upsert", "parquet", "internal", "Stage attempt and resume evidence.", "one run and stage", "run_id, stage_name", "control"),
    DataObject("quality_results", "table", "control", "control", "append-only", "parquet", "internal", "Dataset quality rule evidence.", "one run dataset rule evaluation", "quality_result_id", "control"),
    DataObject("lineage_edges", "table", "control", "control", "append-only", "parquet", "internal", "Input-output transform lineage.", "one run lineage edge", "lineage_edge_id", "control"),
    DataObject("watermarks", "table", "control", "control", "upsert", "parquet", "internal", "Pipeline partition watermarks.", "one pipeline partition watermark type", "pipeline_id, partition_key, watermark_type", "control"),
    DataObject("reconstruction_exceptions", "table", "control", "control", "append-only identities", "parquet", "internal", "Stable reconstruction exception identities without raw account scope.", "one partition episode and exception type", "exception_id; identity_hash is unique", "control"),
    DataObject("reconstruction_exception_revisions", "table", "control", "control", "append-only review revisions", "parquet", "internal", "Versioned reconstruction exception status evidence and resolution.", "one reconstruction exception review revision", "exception_id, revision", "control"),
    DataObject("reconstruction_exceptions_current", "view", "control", "control", "latest knowledge projection", "excluded", "internal", "Latest status and evidence for each reconstruction exception.", "one reconstruction exception", "exception_id", "control"),
    DataObject("etf_instrument_routes", "table", "control", "control", "versioned exact allowlist", "parquet", "internal", "Exact instrument to fixture or approved ETF provider route projection.", "one instrument route interval", "instrument_id, valid_from", "control"),
    DataObject("pipeline_run_summary", "view", "control", "control", "derived view", "excluded", "internal", "Pipeline status read model.", "one pipeline run", "run_id", "control"),
)


def managed_object_names(object_type: str | None = None) -> tuple[str, ...]:
    return tuple(
        item.name
        for item in DATA_OBJECTS
        if object_type is None or item.object_type == object_type
    )


def backup_table_names() -> tuple[str, ...]:
    return tuple(
        item.name
        for item in DATA_OBJECTS
        if item.object_type == "table" and item.backup_policy == "parquet"
    )


def object_by_name() -> dict[str, DataObject]:
    return {item.name: item for item in DATA_OBJECTS}


def v2_object_by_qualified_name() -> dict[str, DataObject]:
    return {item.qualified_name: item for item in V2_DATA_OBJECTS}


def v2_backup_table_names() -> tuple[str, ...]:
    return tuple(
        item.qualified_name
        for item in V2_DATA_OBJECTS
        if item.object_type == "table" and item.backup_policy in {"parquet", "object"}
    )
