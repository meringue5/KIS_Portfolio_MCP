# Data Store Governance and Catalog

이 문서는 KIS Portfolio Service 데이터 저장소의 **관리 책임 문서**다. MotherDuck의
`kis_portfolio` database와 로컬 DuckDB 개발 사본에 대해 객체의 목적, 데이터 계층, grain,
키, 쓰기 정책, 민감도, 백업 여부와 스키마 전환 계획을 정의한다.

DB 객체를 추가하거나 의미를 바꿀 때는 이 문서를 먼저 또는 같은 변경에서 갱신해야 한다.
단순한 테이블 목록은 다른 문서에 복제하지 않고 이 문서를 참조한다.

이 문서는 더 넓은 [Data Governance Harness](./governance/data-governance-harness.md) 아래에서 물리 object
계약을 담당한다. source, collection basket, logical dataset, metric과 pipeline 계약은
`governance/catalog/`가 소유한다. 물리 object가 새 dataset을 구현하거나 기존 dataset의 의미를 바꾸면
`governance/catalog/datasets.toml`과 이 문서를 같은 변경에서 갱신한다.

## Authority and Scope

각 책임의 source of truth는 다음과 같다.

| 책임 | Source of truth |
| --- | --- |
| 객체 목적, grain, 계층, 민감도, 백업 정책 | 이 문서 |
| 기계 판독 가능한 객체 등록부 | `src/kis_portfolio/db/catalog.py` |
| 현재 물리 DDL과 view SQL | `src/kis_portfolio/db/schema.py` |
| 실제 쓰기/중복 처리 동작 | `src/kis_portfolio/db/repository.py`, auth/token repositories |
| 수집과 정제 흐름 | `docs/data-pipeline.md` |
| 시크릿과 인증 데이터 취급 | `docs/security-and-secrets.md` |
| Parquet 백업과 복원 절차 | `docs/backup.md` |

관리 범위는 `table_catalog = current_database() = 'kis_portfolio'`인 객체다. MotherDuck 연결에
함께 보이는 `sample_data`, `md_information_schema`, 과거 로컬/원격 database인 `my_db` 등은 이
서비스의 관리 대상이 아니다. 2026-08-28 확인한 `my_db`는 5 tables + 1 view를 가진 약 256 KiB의 초기
legacy database이며 모든 table이 0행이다. MCP·auth·세 batch Job과 repository code는 모두
`kis_portfolio`만 사용한다. `my_db`는 운영 SSOT가 아니지만 사용자 승인과 cleanup Work Item 전에는
자동 삭제하지 않는다. `schema = main`만으로 필터링하면 다른 catalog의 동명 객체가 섞이므로 운영
검사에서는 항상 catalog와 schema를 함께 제한한다.

현재 checkout이 관리하는 객체는 **25 tables + 2 views = 27 objects**다. 운영 DB에는 분기된
`codex/portfolio-pipeline-reliability`의 객체까지 적용되어 **27 tables + 3 views = 30 objects**가 있다.
현재 물리 위치는 모두 `kis_portfolio.main`이며, 아래 계층은 즉시 적용하는 논리 계약이자 향후 목표
schema다.

> 승인된 V2 목표: `docs/design/kis-portfolio-v2-system-design.md`의 V2-ADR-005는 operational Security
> state를 Seoul의 Firestore Standard database 하나와 Secret Manager로 분리한다. 이 architecture 승인은
> schema migration이나 cutover가 아니다. 별도 Work Item이 완료되기 전까지 이 문서의 현재 V1 catalog,
> registry와 live DB 계약은 그대로 유지한다.

## Layer Model

| Layer | 목표 schema | 책임 | 허용되는 쓰기 |
| --- | --- | --- | --- |
| Bronze | `bronze` | KIS 응답과 조회 시점의 관측 사실을 재처리 가능하게 보존 | append-only INSERT |
| Silver | `silver` | 정규화, 중복 제거, canonical 상태와 총자산 집계 | keyed upsert 또는 canonical append |
| Gold | `gold` | 대시보드와 분석이 직접 소비하는 일별 대표값·파생 지표 | view 또는 재생성 가능한 pipeline table |
| Control | `control` | migration, 시장 달력, 종목 기준정보와 수동 분류 규칙 | versioned migration 또는 keyed upsert |
| Security | `security` | 암호화/해시된 인증 상태와 사용자·클라이언트 권한 | 전용 repository만 쓰기 가능 |

Bronze/Silver/Gold는 데이터 품질과 소비 목적을 나타낸다. Control과 Security를 억지로
medallion 계층에 섞지 않는다. Gold는 반드시 Silver 또는 명시된 Control 기준정보에서 파생하며,
Bronze를 임의로 직접 조인해 새로운 공식 지표를 만들지 않는다.

## V2 Parallel Physical Catalog

DEC-045에 따라 기존 `main` 객체는 그대로 보존하고 V2는 explicit migration
`src/kis_portfolio/platform/sql/0001_v2_foundation.sql`과 `0002_v2_read_models.sql`로 병렬 생성한다.
V2 runtime registry는 `src/kis_portfolio/db/catalog.py`의 `V2_DATA_OBJECTS`가 소유한다. V1
`get_connection()`의 `init_schema()`는 이 객체를 만들지 않는다.

### V2 Bronze

| Object | Grain / contract | Backup / sensitivity |
| --- | --- | --- |
| `bronze.source_observations` | source record observation; content와 logical idempotency key로 append-only replay | Parquet / confidential |
| `bronze.raw_object_manifest` | private object content hash와 rights metadata | private object / restricted |
| `bronze.owner_research_documents` | owner PDF SHA-256별 immutable original identity | private object / restricted |

### V2 Silver canonical ledger

| Objects | Grain / contract | Backup / sensitivity |
| --- | --- | --- |
| `silver.accounts`, `silver.instruments` | account identity와 current instrument compatibility projection | Parquet / confidential·internal |
| `silver.instrument_versions`, `silver.instrument_versions_effective`, `silver.instruments_current` | point-in-time classification versions, derived validity interval and current read model | Parquet table + rebuild views / internal |
| `silver.position_snapshots`, `silver.cash_snapshots` | account/instrument 또는 currency/as-of 관측 | Parquet / confidential |
| `silver.trade_events`, `silver.trade_event_revisions`, `silver.cash_flow_events`, `silver.cash_flow_event_revisions` | 원천 broker event, append-only correction revision, immutable cash fact와 point-in-time cash classification revision | Parquet / confidential |
| `silver.trade_events_current`, `silver.cash_flow_events_current`, `silver.purchase_lots_current` | latest trade/cash classification revision과 corrected buy-only lot projection | Rebuild / confidential |
| `silver.position_episodes`, `silver.position_episode_revisions`, `silver.position_episodes_current` | 연속 보유 episode identity, append-only reconstruction revision과 latest projection | Parquet tables + rebuild view / confidential |
| `silver.purchase_lots`, `silver.trade_threads`, `silver.trade_thread_lots` | WI-010의 보존된 buy-order lot compatibility artifact, investment thread와 versioned link | Parquet / confidential |
| `silver.purchase_lot_identities`, `silver.purchase_lot_revisions`, `silver.purchase_lot_states_current` | actual·manual·inferred-opening canonical lot identity, append-only quantity/cost state와 latest projection | Parquet tables + rebuild view / confidential |
| `silver.sell_allocation_sets`, `silver.sell_allocation_revisions`, `silver.sell_allocations_current` | 매도별 whole allocation revision header, lot slice와 latest whole-revision projection | Parquet tables + rebuild view / confidential |
| `silver.trade_journal_revisions` | owner journal append-only revision | Parquet / confidential |
| `silver.trade_thread_risk_plan_revisions`, `silver.trade_thread_risk_plans_current` | owner-authoritative reference/stop/risk-budget revision과 latest knowledge projection; model·ATR advice는 별도 metadata | Parquet table + rebuild view / confidential |
| `silver.price_bars_daily`, `silver.fx_rates_daily` | current instrument/session/basis와 currency pair/date/rate type | Parquet / internal |
| `silver.price_bar_revisions_daily` | instrument/session/basis/content revision과 effective/knowledge/request provenance | Parquet / internal |
| `silver.corporate_actions`, `silver.corporate_action_revisions`, `silver.corporate_actions_current` | source action identity, point-in-time terms/status revision과 latest knowledge projection | Parquet tables + rebuild view / internal |
| `silver.corporate_action_adjustment_effects` | action revision별 price·quantity·instrument successor effect; factor 방향과 적용시점 명시 | Parquet / internal |
| `silver.etf_constituent_snapshots` | ETF/source date/file hash/constituent ordinal | Parquet / internal |
| `silver.filing_events`, `silver.financial_facts` | filing document version과 point-in-time taxonomy fact | Parquet / internal |
| `silver.dividend_events`, `silver.macro_observations` | dividend state event와 series/vintage/revision | Parquet / confidential·internal |
| `silver.owner_research_extractions` | document/extractor/version/revision/page·section locator | private object / restricted |

### V2 Gold and Control

| Object | Grain / contract | Backup / sensitivity |
| --- | --- | --- |
| `gold.portfolio_daily_state` | evaluation date/slot/account/instrument/aggregate level materialization | Parquet / confidential |
| `gold.metric_values` | metric/version/subject/evaluation-at point-in-time value, quality and lineage; approved definitions include portfolio value, Modified Dietz return/component contribution/residual, chain-linked wealth/drawdown, instrument-level KRW valuation-change contribution, lot MFE/MAE, position-episode high/drawdown, owner-stop thread/instrument planned loss and risk ratio, SMA20/50/120, volume SMA/ratio20, Wilder RSI14, Bollinger 20/2 context and Wilder ATR20 | Parquet / confidential |
| `gold.alert_candidates` | rule/version/opaque subject/session/slot point-in-time state, severity, quality, lineage and allowlisted redacted context | Parquet / confidential |
| `gold.portfolio_daily_summary` | date/slot portfolio read model | rebuild view / confidential |
| `control.schema_migrations` | version/name/checksum migration ledger | excluded / internal |
| `control.pipeline_definitions` | pipeline/version definition hash | Parquet / internal |
| `control.metric_definitions` | metric/version approved contract definition hash | Parquet / internal |
| `control.alert_rule_versions` | immutable rule/version hash, validity, exact numeric watch floor and off/shadow/external mode | Parquet / confidential |
| `control.alert_state_revisions`, `control.alert_states_current` | alert identity별 episode, 진입·상향·회복·재진입 append-only transition과 latest projection | Parquet table + rebuild view / confidential |
| `control.alert_candidate_outcomes` | candidate별 transition·no-change·quality/out-of-order suppression exactly-once 처리 결과 | Parquet / confidential |
| `control.alert_dispatch_claims`, `control.alert_delivery_attempts` | candidate/channel/opaque destination leased claim과 redacted terminal/retry outcome | Parquet / confidential |
| `control.alert_calibration_runs`, `control.alert_shadow_windows` | provenance-labelled 3년 replay·자산유형 threshold report와 2주 DB-only coverage/de-dup/zero-send evidence | Parquet / confidential |
| `control.alert_rule_approval_revisions` | calibration·verified shadow를 인용하는 owner approval/rejection/revocation revision | Parquet / confidential |
| `control.pipeline_runs`, `control.pipeline_stage_runs` | logical run and resumable stage evidence | Parquet / internal |
| `control.quality_results`, `control.lineage_edges`, `control.watermarks` | rule result, transform edge와 partition watermark | Parquet / internal |
| `control.reconstruction_exceptions`, `control.reconstruction_exception_revisions`, `control.reconstruction_exceptions_current` | 비식별 partition/episode 예외 identity, append-only 검토·해결 이력과 latest projection | Parquet tables + rebuild view / internal |
| `control.owner_review_items`, `control.owner_review_item_revisions`, `control.owner_review_items_current` | 누락 thread plan/journal·미확정 sell allocation review identity, append-only 상태와 latest projection | Parquet tables + rebuild view / confidential |
| `control.etf_instrument_routes` | exact instrument→provider profile route; account·quantity·valuation fields prohibited | Parquet / internal |
| `control.pipeline_run_summary` | run/stage terminal-state read model | rebuild view / internal |

총 74개 V2 object는 59 tables + 15 views다. local fresh DuckDB에서는 migration apply, 두 번째 no-op,
checksum mismatch와 중간 실패 후 resume를 자동검증한다. 운영 MotherDuck 적용은 같은 migration checksum을
사용하며 기존 `main` writer를 바꾸지 않는다. V1→V2 과거 복사는 별도 migration version과 reconciliation
evidence 없이는 실행하지 않는다.

## Bronze Catalog

| Object | Purpose and grain | Key and write contract | Producer | Backup / sensitivity |
| --- | --- | --- | --- | --- |
| `portfolio_snapshots` | 국내·연금 잔고 API 1회 조회 관측. 계좌/호출 시점 grain, 원본 `balance_data` 포함 | PK `id`; append-only | account service의 단일/전체 계좌 refresh | Parquet / confidential |
| `overseas_asset_snapshots` | 해외 잔고·예수금 조회 1회 관측과 feeder 합계. 해외계좌/overview refresh grain | PK `id`; append-only | total asset overview service | Parquet / confidential |
| `order_history` | 국내 주문체결 조회의 raw response snapshot. 계좌/상품코드/조회기간/호출 grain | PK `id`; append-only | order query service, domestic batch | Parquet / confidential |
| `overseas_order_history` | 해외 주문체결 조회 raw snapshot. 계좌/필터/호출 grain | PK `id`; append-only | overseas order service | Parquet / confidential |
| `overseas_transaction_history` | 해외 일별거래내역 raw snapshot. 계좌/필터/호출 grain | PK `id`; append-only | overseas transaction service, batch | Parquet / confidential |
| `overseas_settlement_balance_snapshots` | 해외 결제기준잔고 조회 관측. 계좌/기준일/호출 grain | PK `id`; append-only | overseas settlement service | Parquet / confidential |
| `trade_profit_history` | 국내·해외 기간손익 조회 관측. 계좌/시장/요청기간/호출 grain | PK `id`; append-only | profit service | Parquet / confidential |

Bronze의 JSON payload는 API 재처리를 위한 원본 보존 영역이다. raw token, app secret,
Authorization header는 어떤 JSON 컬럼에도 넣지 않는다. 계좌번호가 포함될 수 있으므로 모든 Bronze
백업은 confidential 데이터다.

## Silver Catalog

| Object | Purpose and grain | Key and write contract | Producer | Backup / sensitivity |
| --- | --- | --- | --- | --- |
| `price_history` | 국내·해외 종목의 정규화 OHLCV. 종목/거래소/거래일 grain | PK `(symbol, exchange, date)`; 기본 insert-ignore, adjusted resync만 update | market data service | Parquet / internal |
| `exchange_rate_history` | 통화별 정규화 환율. 통화/일자/주기 grain | PK `(currency, date, period)`; insert-ignore | exchange-rate service | Parquet / internal |
| `asset_overview_snapshots` | 원화 기준 canonical 총자산, allocation, completeness/quality. overview refresh grain | PK `id`; canonical append; `quality_status`, `quality_flags`, `is_complete`는 같은 refresh 품질 판정 | total asset overview service | Parquet / confidential |
| `asset_holding_snapshots` | canonical overview에 속한 보유종목·현금 정규화 row | PK `id`; `overview_snapshot_id`로 parent 연결; append-only | total asset overview service | Parquet / confidential |
| `domestic_orders` | 국내 주문의 최신 canonical 상태. KIS 주문 식별자 grain | PK `(account_id, account_product_code, order_date, order_branch_no, order_no)`; upsert | raw order normalization | Parquet / confidential |
| `overseas_orders` | 해외 주문의 최신 canonical 상태. KIS 해외 주문 식별자 grain | PK `(account_id, account_product_code, order_date, exchange_code, order_branch_no, order_no)`; upsert | overseas raw order normalization | Parquet / confidential |
| `overseas_transactions` | 해외 거래 정규화 row. 안정적인 raw row identity grain | PK `(account_id, account_product_code, transaction_hash)`; upsert | overseas transaction normalization | Parquet / confidential |

`asset_overview_snapshots`가 총자산의 canonical aggregate다. 국내 feeder만 담은
`portfolio_snapshots`를 글로벌 총자산 분석의 기준으로 사용하지 않는다. 종목/현금 상세 합계와 overview
합계는 같은 refresh에서 생성된다. 필수 계좌 coverage, feeder 오류와 두 합계의 차이를 검사한 결과는
`asset_overview_snapshots`의 managed quality column과 `overview_data.data_quality`에 함께 보존한다. legacy row는
소급해 `pass`로 추정하지 않고 `legacy_unassessed`/incomplete로 투영한다.

## Gold Catalog

| Object | Purpose and grain | Derivation | Consumer | Backup / sensitivity |
| --- | --- | --- | --- | --- |
| `portfolio_daily_snapshots` | 국내·연금 계좌의 일별 마지막 snapshot. 계좌/일 grain | `portfolio_snapshots`에서 `arg_max(snapshot_at)` | feeder 분석 함수 | 재생성 view / confidential |
| `asset_overview_daily_snapshots` | canonical 총자산의 일별 마지막 snapshot. 포트폴리오/일 grain | `asset_overview_snapshots`에서 `arg_max(snapshot_at)` | 글로벌 이력·변화·추세 분석 | 재생성 view / confidential |

Gold view는 백업하지 않는다. Silver/Bronze 복원 후 migration이 동일한 view를 재생성해야 한다.
새 대시보드 지표는 먼저 grain과 input contract를 이 문서에 기록한 뒤 Gold에 추가한다.

## Control Catalog

| Object | Purpose and grain | Key and write contract | Producer | Backup / sensitivity |
| --- | --- | --- | --- | --- |
| `schema_migrations` | 적용된 DB migration ledger. migration version grain | PK `version`; migration command만 INSERT | future migration runner | 제외 / internal |
| `market_calendar` | 시장별 거래일·개장/마감 기준정보. 시장/일 grain | PK `(market, trade_date)`; upsert | batch `sync-market-calendar` | Parquet / internal |
| `instrument_master` | KIS 공식 종목마스터와 분류 입력. 종목/시장 grain | PK `(symbol, market)`; bulk upsert | `scripts/sync_instrument_master.py` | Parquet / internal |
| `instrument_classification_overrides` | 해외우회투자 등 수동 분류 보정. 종목/시장 grain | PK `(symbol, market)`; 명시적 upsert | owner-approved maintenance | Parquet / confidential |

Override는 공식 master와 heuristic보다 우선하므로 변경 이유(`reason`)를 비워두지 않는 방향으로
강화한다. `schema_migrations`는 현재 생성만 되고 실질 migration runner가 아직 없으므로, 물리 schema
분리 전에 먼저 구현해야 한다.

## Security Catalog

| Object | Purpose and grain | Stored secret form | Key and write contract | Backup |
| --- | --- | --- | --- | --- |
| `kis_api_access_tokens` | KIS 계좌/app-key별 access token cache | Fernet ciphertext; encryption key는 DB 밖 | PK `cache_key`; upsert | 기본 제외 |
| `auth_users` | MCP 접근을 허용한 사용자 | email/profile PII | PK `id`, unique `primary_email`; upsert | 기본 제외 |
| `auth_identities` | 사용자와 OAuth provider subject 연결 | provider profile PII | PK `id`, unique `(provider, provider_subject)`; upsert | 기본 제외 |
| `oauth_clients` | static/dynamic OAuth client 등록 | client secret hash only | PK `client_id`; upsert | 기본 제외 |
| `oauth_grants` | 사용자·client·scope consent | raw bearer 없음 | PK `id`, unique `(user_id, client_id, scope)`; upsert/revoke | 기본 제외 |
| `oauth_authorization_codes` | 일회용 authorization code 상태 | code digest only | PK `id`, unique `code_digest`; insert/consume/revoke | 기본 제외 |
| `oauth_tokens` | MCP access/refresh token 상태 | token digest only | PK `id`, unique `token_digest`; insert/revoke | 기본 제외 |

Security 객체는 analytics SQL, MCP 일반 조회 tool, 기본 Parquet 백업에서 제외한다. 자세한 암호화,
pepper, 회전과 incident response는 `docs/security-and-secrets.md`가 담당한다.

## Column Conventions

- `id`: random UUID 문자열. 별도 natural key가 있는 Silver/Control table은 composite PK를 우선한다.
- `account_id`: KIS CANO 원문을 담을 수 있는 confidential 식별자다. MCP 응답과 로그에서는 마스킹한다.
- `account_type` / `account_label`: `ria`, `isa`, `brokerage`, `irp`, `pension` 도메인 라벨을 사용한다.
- `snapshot_at`, `fetched_at`: API 관측 시각. 현재 naive timestamp이므로 모든 writer는 같은 운영 timezone
  계약을 따라야 하며, 향후 UTC 저장 전환 시 migration이 필요하다.
- `created_at`, `updated_at`, `first_seen_at`, `last_seen_at`: row lifecycle metadata다.
- `raw_data`, `data`, `*_data`: JSON 재처리 또는 provenance 용도다. 공식 집계는 가능하면 typed column을
  사용하고, 반복 분석에서 JSON path를 canonical 계약으로 삼지 않는다.
- 금액 suffix `_krw`는 원화 환산 금액, `_foreign`은 해당 `currency` 표시 통화 금액이다.
- 비율 suffix `_pct`는 0~100 단위다.

정확한 현재 컬럼명과 타입은 `src/kis_portfolio/db/schema.py` 및 다음 명령으로 확인한다.

```bash
uv run python .agent/skills/kis-warehouse-contract/scripts/inspect_portfolio_db.py --inventory
```

inventory 결과에는 object/column metadata만 포함하고, 기본 검사는 일부 table의 건수와 freshness만
추가한다. token ciphertext, account id, OAuth digest, raw JSON 값은 출력하지 않는다.

## Physical Schema Migration Plan

현재 `main`에 모든 객체가 있는 상태를 즉시 옮기지 않는다. 런타임 시작 시 `init_schema()`가 DDL을
실행하고 여러 프로세스가 같은 MotherDuck catalog를 쓸 수 있으므로, 먼저 migration 실행권을 분리해야
한다.

### Phase 0: Govern current `main`

- `catalog.py`와 이 문서를 managed-object allowlist로 사용한다.
- 운영 검사에서 code에는 없고 DB에만 있는 객체를 drift로 보고한다.
- 신규 객체는 `main`에 임의 생성하지 않고 목표 layer/schema를 먼저 등록한다.

### Phase 1: Versioned migration runner

- `get_connection()`의 runtime auto-DDL을 schema version check와 별도 migration command로 분리한다.
- migration은 단일 writer lock, version, 적용 시각, 검증 결과를 `control.schema_migrations`에 남긴다.
- MCP/remote/batch 런타임은 필요한 schema version 미만이면 쓰기를 시작하지 않는다.

### Phase 2: Create and move namespaces

- `bronze`, `silver`, `gold`, `control`, `security` schema를 만든다.
- 객체별 copy/move 후 row count, PK uniqueness, null contract, 합계 reconciliation을 검증한다.
- repository와 analytics SQL을 schema-qualified name으로 전환한다.
- 필요한 기간 동안 `main`에는 read-only compatibility view만 두며, write target으로 사용하지 않는다.

### Phase 3: Retire `main`

- 모든 배포 target과 backup/inspection tool이 qualified schema를 사용하는지 확인한다.
- compatibility view 사용 로그와 외부 consumer를 확인한 뒤 별도 승인 migration으로 제거한다.
- `main` 신규 객체 생성은 contract check에서 실패하게 한다.

물리 이동의 완료 조건은 테스트 통과만이 아니다. MotherDuck 백업 생성, 복원 rehearsal, live object
inventory 일치, row-count/aggregate reconciliation, remote/batch smoke test가 모두 필요하다.

## Branch and Live Drift Register

2026-08-11 운영 메타데이터 검사에서 현재 checkout보다 운영 DB가 앞선 역방향 드리프트가 발견됐다.
출처는 `codex/portfolio-pipeline-reliability` branch의 commit
`9dea94c Fix portfolio snapshot integrity and operations`다. 이 branch는 현재 checkout의 ancestor나
descendant가 아니라 공통 base 이후 분기돼 있으므로, 코드상 자동으로 managed 상태가 되지 않는다.

| Object | Intended contract in `9dea94c` | Live state | Current governance status |
| --- | --- | --- | --- |
| `cash_flow` | Silver; 외부입출금·환전·배당·세금 event grain, PK `idempotency_key`, signed `amount_krw`, upsert, Parquet/confidential | base table, 0 rows | branch-defined pending integration |
| `trade_journal` | Silver; 투자결정/거래 journal entry grain, PK `id`, unique `idempotency_key`, upsert, Parquet/confidential | base table, 0 rows | branch-defined pending integration |
| `asset_overview_snapshots` quality extension | Silver canonical snapshot에 `quality_status`, `quality_flags`, `is_complete` 추가 | 세 컬럼 존재 | WI-033에서 DDL/writer/view/test와 함께 managed로 통합; legacy row는 fail-closed |
| `asset_return_daily` | Gold; 일별 총자산 변화에서 외부 현금흐름을 제외한 근사 수익률 view | view는 존재하지만 현재 `asset_overview_daily_snapshots`가 품질 컬럼을 투영하지 않아 조회 실패 | broken branch-defined view |

이 객체들은 정체불명의 수동 DDL은 아니지만, 현재 branch의 registry/DDL/repository/test에는 없다. 따라서
자동으로 삭제하거나 현재 서비스의 공식 consumer로 채택하지 않는다. reliability branch를 현재 mainline과
통합할 때 schema, repository, analytics, backup, tests와 catalog registry를 한 변경으로 편입하고 broken
view를 재생성한다.

### Managed V2 production register

2026-08-28 WI-022-S06 managed release가 checksum-verified migration을 `0010`까지 적용했다. canonical
reconstruction hash와 57-partition aggregate가 일치한 뒤 corporate-action coverage 미평가를 나타내는
`control.reconstruction_exceptions` identity 57건과 first revision 57건만 append했다. current open exception은
57건이며 `silver.position_episodes`, `silver.purchase_lot_identities`, `silver.sell_allocation_sets`는 모두 0건이다.
pre/post complete V2 backup은 private GCS에 업로드·다운로드·fresh DuckDB restore되었고 live/restored aggregate가
일치했다. 이것은 위 `main` branch drift 객체를 채택하거나 수정한 작업이 아니다.

2026-08-28 WI-024의 read-only inventory에서는 open `silver.trade_threads` 19건, owner journal revision 0건,
sell-allocation set 0건과 open reconstruction exception 57건을 확인했다. Migration `0011`과 typed risk-plan 및
owner-review 5개 객체는 production에 적용되지 않았고 새 ledger row도 0건이다. 이는 승인되지 않은 owner
intent를 backfill하지 않는 의도된 release gap이며, 운영 migration은 별도 release gate 전까지 실행하지 않는다.
상세 aggregate evidence는 `docs/operations/wi024-thread-review-readiness-2026-08.md`에 둔다.

## Change Contract

DB 객체 변경 PR 또는 작업은 다음을 모두 만족해야 한다.

1. 관련 source/dataset/metric/pipeline manifest를 확인하고 새 의미면 proposed contract를 먼저 등록한다.
2. `catalog.py`에 물리 객체와 계약을 등록한다.
3. 이 문서의 해당 layer catalog와 필요하면 column convention을 갱신한다.
4. versioned migration 또는 현재 단계의 `schema.py` DDL을 추가한다.
5. repository write mode와 natural key를 테스트한다.
6. Parquet 포함/제외를 명시하고 `docs/backup.md`를 맞춘다.
7. Security/PII 영향이 있으면 `docs/security-and-secrets.md`를 갱신한다.
8. DGH·warehouse contract 검사와 live inventory를 실행한다.

```bash
uv run python .agent/skills/kis-warehouse-contract/scripts/check_warehouse_contracts.py
python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py
uv run python .agent/skills/kis-warehouse-contract/scripts/inspect_portfolio_db.py --inventory
```

알려진 branch/live drift를 통합한 뒤에는 release 검사에서 `--fail-on-drift`를 추가한다.
