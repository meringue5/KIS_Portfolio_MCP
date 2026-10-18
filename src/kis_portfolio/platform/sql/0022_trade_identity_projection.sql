-- WI-064: repair representation drift under the existing executed-order natural key.
-- A link requires immutable KIS source evidence; equal price/time/quantity alone is insufficient.
CREATE OR REPLACE VIEW silver.trade_event_identity_aliases AS
WITH evidence AS (
    SELECT r.*, b.payload,
           json_extract_string(b.payload, '$.order_no') AS old_order,
           json_extract_string(b.payload, '$.order_branch_no') AS old_branch,
           replace(json_extract_string(b.payload, '$.order_date'), '-', '') AS old_date,
           json_extract_string(b.payload, '$.order_time') AS old_time,
           json_extract_string(b.payload, '$.symbol') AS old_symbol,
           json_extract_string(b.payload, '$.side_code') AS old_side,
           try_cast(json_extract_string(b.payload, '$.filled_qty') AS DECIMAL(28,10)) AS old_qty,
           try_cast(json_extract_string(b.payload, '$.avg_price') AS DECIMAL(28,8)) AS old_price,
           json_extract_string(b.payload, '$.odno') AS new_order,
           json_extract_string(b.payload, '$.ord_gno_brno') AS new_branch,
           json_extract_string(b.payload, '$.ord_dt') AS new_date,
           json_extract_string(b.payload, '$.ord_tmd') AS new_time,
           json_extract_string(b.payload, '$.pdno') AS new_symbol,
           json_extract_string(b.payload, '$.sll_buy_dvsn_cd') AS new_side,
           try_cast(json_extract_string(b.payload, '$.tot_ccld_qty') AS DECIMAL(28,10)) AS new_qty,
           try_cast(json_extract_string(b.payload, '$.avg_prvs') AS DECIMAL(28,8)) AS new_price
    FROM silver.trade_event_revisions r
    JOIN bronze.source_observations b ON b.observation_id=r.source_observation_id
    WHERE b.dataset_id='dataset.trade-event' AND b.source_id='source.kis-open-api'
      AND r.market='KRX' AND r.execution_sequence='aggregate'
), candidates AS (
    SELECT DISTINCT old.source_trade_event_id AS legacy_id, new.source_trade_event_id AS collected_id
    FROM evidence old JOIN evidence new
      ON old.account_id=new.account_id AND old.market=new.market
     AND old.product_code=new.product_code AND old.instrument_id=new.instrument_id
     AND old.executed_at=new.executed_at AND old.execution_sequence=new.execution_sequence
     AND old.currency=new.currency AND old.side=new.side
     AND old.quantity=new.quantity AND old.price=new.price
     AND old.old_order=new.new_order AND old.old_branch=new.new_branch
     AND old.old_date=new.new_date AND old.old_time=new.new_time
     AND old.old_symbol=new.new_symbol AND old.old_side=new.new_side
     AND old.old_qty=new.new_qty AND old.old_price=new.new_price
    WHERE old.source_observation_id LIKE 'v1-domestic-order-%'
      AND old.correction_reason='v1_import_contract'
      AND old.source_trade_event_id<>new.source_trade_event_id
      AND coalesce(old.old_order,'')<>'' AND coalesce(old.old_branch,'')<>''
      AND regexp_full_match(old.old_date, '[0-9]{8}')
      AND regexp_full_match(old.old_time, '[0-9]{6}')
      AND coalesce(old.old_symbol,'')<>'' AND old.old_side IN ('01','02')
      AND old.side=CASE old.old_side WHEN '01' THEN 'sell' WHEN '02' THEN 'buy' END
      AND old.old_qty>0 AND old.old_price>0
      AND old.quantity=old.old_qty AND old.price=old.old_price
      AND old.instrument_id='v1|KRX|' || old.old_symbol
      AND strftime(timezone('Asia/Seoul', old.executed_at), '%Y%m%d%H%M%S')=old.old_date || old.old_time
      AND old.broker_order_id=substr(old.old_date,1,4) || '-' || substr(old.old_date,5,2) || '-' ||
          substr(old.old_date,7,2) || '|' || old.old_branch || '|' || old.old_order
      AND new.broker_order_id=new.product_code || '|' || substr(new.new_date,1,4) || '-' ||
          substr(new.new_date,5,2) || '-' || substr(new.new_date,7,2) || '|KRX|' ||
          new.new_branch || '|' || new.new_order
), links AS (
    -- Ambiguous source identities remain separate for investigation; never guess.
    SELECT * FROM candidates
    QUALIFY count(*) OVER (PARTITION BY legacy_id)=1
        AND count(*) OVER (PARTITION BY collected_id)=1
)
SELECT ids.source_trade_event_id,
       coalesce(links.legacy_id, ids.source_trade_event_id) AS canonical_source_trade_event_id
FROM (SELECT DISTINCT source_trade_event_id FROM silver.trade_event_revisions) ids
LEFT JOIN links ON links.collected_id=ids.source_trade_event_id;

CREATE OR REPLACE VIEW silver.trade_events_current AS
WITH latest_per_source AS (
    SELECT * FROM silver.trade_event_revisions
    QUALIFY row_number() OVER (
        PARTITION BY source_trade_event_id ORDER BY revision DESC, knowledge_at DESC, trade_event_revision_id DESC
    )=1
)
SELECT r.trade_event_revision_id AS trade_event_id,
       aliases.canonical_source_trade_event_id AS source_trade_event_id,
       r.account_id, r.market, r.product_code, r.instrument_id, r.broker_order_id,
       r.executed_at, r.execution_sequence, r.revision, r.side, r.quantity, r.price,
       r.currency, r.knowledge_at, r.source_observation_id, r.correction_reason, r.quality_status, r.metadata
FROM latest_per_source r
JOIN silver.trade_event_identity_aliases aliases USING (source_trade_event_id)
QUALIFY row_number() OVER (
    PARTITION BY aliases.canonical_source_trade_event_id
    ORDER BY r.knowledge_at DESC, r.revision DESC, r.trade_event_revision_id DESC
)=1;

CREATE OR REPLACE VIEW silver.purchase_lots_current AS
SELECT lots.*
FROM silver.purchase_lots lots
JOIN silver.trade_event_identity_aliases aliases ON aliases.source_trade_event_id=lots.trade_event_id
JOIN silver.trade_events_current events ON events.source_trade_event_id=aliases.canonical_source_trade_event_id
WHERE events.side='buy' AND events.quality_status='pass'
QUALIFY row_number() OVER (
    PARTITION BY aliases.canonical_source_trade_event_id
    ORDER BY CASE WHEN lots.trade_event_id=aliases.canonical_source_trade_event_id THEN 0 ELSE 1 END, lots.lot_id
)=1;
