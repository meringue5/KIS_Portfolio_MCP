# Milestone 2 data-readiness review

Status: reviewed from 2026-08-28 read-only evidence. This document does not authorize production collection, migration,
historical backfill or external notification.

## Review rule

A formula with golden fixtures is `fixture-ready`. It is `production-ready` only when its approved source, canonical
dataset, point-in-time semantics, minimum history, quality and reconciliation inputs are all available. Missing inputs
produce an explicit unavailable or partial state; they are never replaced with zero, a neutral indicator or an
inferred transaction.

## Production readiness by metric family

| Family | Current non-sensitive evidence | Verdict | Required predecessor |
| --- | --- | --- | --- |
| W0502 return, contribution, drawdown | one production Gold date has 31 pass rows; migrated history is 27 non-contiguous dates with 48 degraded rows; 237 cash balance snapshots exist but canonical external cash-flow events are empty | fixture-ready, production no-go | external cash-flow classification, continuous daily state and trade/price/FX reconciliation |
| W0503 trend and volatility | 875 price rows cover 24 instruments; currently held coverage is labelled only `raw`, adjusted coverage is zero; seven instruments have at least 50 rows, two have at least 120 and none has approximately three years | fixture-ready, production no-go | corrected dual-basis provenance, point-in-time revisions and bounded three-year price backfill |
| W0504 lot/thread risk | 19 migrated trade, lot and thread rows cover five instruments and three accounts; all migrated trades are labelled buys, current account-position coverage is five of 26 and all are partial/inferred; sell allocation and journal revisions are empty | fixture-ready, production no-go | trade-side migration correction, trade reconstruction, lot/position reconciliation, sell allocation, adjusted price and typed thread risk-plan revisions |
| W0505 ETF look-through | the canonical V1 overview identifies 14 held domestic ETFs; current V2 held instruments are all `unknown`, issuer routing and constituent snapshots are empty, and no live ETF pipeline definition is registered | parser/metric fixture-ready only, production no-go | held-instrument classification, issuer allowlist and official daily composition collection |

The unmanaged V1 `main.asset_return_daily` object is not adopted as a shortcut: its contract is not governed and a
live query produced a schema binding error. A cash balance is not interpreted as an external cash flow. Missing ETF
history is not reconstructed from today's weights.

## Contract defects found before metric implementation

1. The KIS domestic history request uses the vendor's adjusted-price option, while the current bridge writes V2 rows
   as `raw`. Until corrected, those rows are semantically unfit for official return, trend or high-watermark metrics.
2. `silver.price_bars_daily` overwrites a repeated instrument/date/basis row and cannot select the revision known at a
   historical evaluation cutoff.
3. Cash-flow rows do not yet carry the complete source-observation and knowledge-time classification needed by a
   replay-safe Modified Dietz denominator.
4. A typed, versioned thread risk plan does not yet own stop and reference prices; journal prose is not parsed into a
   trading control.
5. WI-013 initially required a numeric metric value. The parallel review caught this before deployment; the contract
   now permits a null value with an explicit state such as `insufficient_history` instead of inventing zero.
6. `scripts/migrate_v1_v2_trade_lots.py` does not read the V1 domestic order side code and maps every positive filled
   quantity to `buy`, then creates a purchase lot. The 19 all-buy rows are therefore a migration artifact candidate,
   not evidence of owner behaviour. Production correction requires source-side mapping, a reconciliation dry-run,
   append/correction semantics and a bounded verified repair; existing rows must not be silently overwritten.
7. ETF availability is not equivalent to collection permission. KRX Data Marketplace terms prohibit unapproved
   automated collection, and issuer downloads reviewed so far do not provide an open licence for automated cloud
   processing and three-year raw retention. A connector can be implemented against fixtures, but production activation
   remains blocked until its provider profile has explicit rights fields and an approved usage basis.
8. The overseas transaction normalizer omits source fields for executed price, fees, settlement amount and applied
   FX. The trade event natural key is also too narrow for multi-year broker order-number reuse. These are source
   contract defects, not tolerances that a performance formula may absorb.

## ETF source and rights readiness

KRX describes Portfolio Deposit Files as daily disclosures, but the Marketplace website is not an automation API.
Its web endpoints must not be scraped. An approved KRX API or separately granted product is the only acceptable KRX
automation path.

The reviewed issuer sites are routed independently rather than hidden behind one generic scraper:

| Profile | Public capability found | Historical indication | Activation state |
| --- | --- | --- | --- |
| TIME ETF | official current XLSX download | current-only path observed | fixture/manual intake only until rights review |
| KoAct | official dated JSON and legacy XLS download | exact-date request works | historical inventory and rights review required |
| RISE | official dated spreadsheet endpoint | exact-date request works | internal product routing, TLS and rights review required |
| PLUS | official paged JSON and XLSX | exact-date request works | pagination fixtures and explicit rights review required |

Each held ETF is manually allowlisted with its KRX code/ISIN, canonical instrument, issuer legal entity and provider
product key. A provider contract records `automation_allowed`, `cloud_processing_allowed`, `raw_retention_allowed`,
`derived_use_allowed` and `redistribution_allowed`; unknown is fail-closed. `unsupported_source` and `stale` are valid
quality outcomes. KIS 30-row composition is a cross-check and never a completeness fallback.

## Recommended v1 formula baselines and fixture boundary

- W0502 uses Modified Dietz for external-cash-flow-adjusted daily return. Drawdown is calculated from the chain-linked
  wealth index, not absolute total assets. Contribution persists an explicit residual and remains `partial` until it
  reconciles.
- W0503 uses adjusted closes for SMA20/50/120, Wilder RSI14, population-standard-deviation Bollinger context and
  Wilder ATR20. Intraday slots use the last completed daily session for trend; a slot quote is a separate shock input.
- W0504 uses adjusted high/low paths for lot MFE/MAE and resets a position episode after quantity returns to zero.
  Additions and partial exits require cash-flow-adjusted thread performance. A missing stop produces no official 2%
  risk result; an ATR-derived stop is advice metadata only.
- SQL and Python reference fixtures must not import one another's production helpers. Ratio results are rounded to the
  warehouse `DECIMAL(38,10)` contract; lineage, quality and input references compare exactly.

Each baseline becomes canonical only when its paired metric contract and Work Item are approved and closed after the
named data predecessor. Synthetic fixtures may be prepared earlier, but their status must remain explicit.

## Price replay boundary

Price-option meanings are endpoint-specific. The domestic history option `FID_ORG_ADJ_PRC=0` means adjusted price,
while the current overseas history path uses `MODP=0` for unadjusted and the official adjusted path uses `MODP=1`.
A global zero/one boolean mapping is prohibited.

The price predecessor adds append-only observation revisions with effective session time, knowledge/fetch time,
endpoint, requested option, page/continuation and content hash. A strict operational replay selects only revisions
known by the evaluation cutoff. A three-year history fetched today is instead
`retrospective_reconstructed`: it may calibrate thresholds and validate formulas, but cannot impersonate an old live
observation or generate Telegram delivery.

For the current held scope, approximately 756 sessions and 21 instruments imply about 168 successful calls per basis,
336 for two bases and a recommended physical-call ceiling of 400. The one-off job remains scale-to-zero,
`max-instances=1`, and separate from normal batch windows. The runner must reserve budget before each call, not only
check after a stage.

## Cash-flow and trade boundary

An immutable cash event and its versioned classification are separate. The event retains `effective_at`,
`settled_at`, `knowledge_at`, `fetched_at` and `recorded_at`; source evidence, reconstruction state, link quality and
publish quality are independent dimensions.

- owner deposit/withdrawal is external and excluded from investment return;
- transfers between managed accounts, FX legs and buy/sell settlement are internal portfolio movements;
- fees and taxes reduce return;
- dividends are investment return rather than external capital;
- unmatched legs, historical manual imports and later broker corrections remain reversible and point-in-time.

Domestic source work must preserve side and correction identity and add the missing pagination/TR split. Overseas
normalization must capture source price, fee, settlement and FX fields before any three-year collection. A sell may
never create a purchase lot. A balance difference is never promoted to a cash event.

## Re-sequenced independent Work Items

1. stop the active price-basis semantic contamination, add revision-aware dual-basis history and perform a bounded
   reconstructed three-year backfill;
2. correct broker history contracts: domestic side/correction/pagination, overseas transaction fields and long-term
   trade identity, followed by a reconciliation dry-run rather than an in-place repair;
3. classify held instruments and establish ETF issuer routing;
4. create provider-specific ETF contracts and offline parser fixtures; activate forward collection per provider only
   after its rights profile is approved, because uncollected current-only files may be lost;
5. implement W0503 trend/volatility metrics against the corrected price ledger;
6. add the canonical cash-event and classification-revision contract;
7. collect bounded three-year trade/cash history into raw landing and canonicalize reversible links;
8. reconstruct and reconcile positions, lots and sell allocations, applying only verified corrections to the bad
   migration output;
9. implement W0502 return, contribution/residual and drawdown;
10. add typed thread risk-plan revisions and sell-allocation review state;
11. implement W0504 lot/thread MFE, MAE, episode high and 2% risk cap;
12. implement W0505 nested ETF look-through, residual and confidence.

Only one item may change the repository at a time. Official-source/terms research, source-call planning and fixture
design may run in parallel without writes.

## Telegram path remains a later gated consumer

The safe delivery shape is `evaluate -> candidate -> dispatch claim -> render/redact -> send -> delivery ledger`.
The product remains outbound-only: private one-to-one destination onboarding is a one-time administrative operation,
not a webhook or permanent inbound command surface. The bot token and future chat identifier are separate Secret
Manager secrets with resource-level accessor grants; analytics rows and logs retain only an opaque destination
reference.

Before delivery, three gates remain mandatory: three-year replay and two-week DB-only shadow, owner approval of the
rule version/destination, and a separately approved finance-free single test message. An uncertain post-send timeout
is recorded as `UNKNOWN` and is not automatically resent. Telegram payloads and logs fail closed on account numbers,
absolute total assets, credentials, raw source content or chat identifiers.

Relevant primary operational references: [Telegram getUpdates](https://core.telegram.org/bots/api#getupdates),
[Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage),
[Telegram rate-limit FAQ](https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this), and
[Secret Manager access control](https://cloud.google.com/secret-manager/docs/manage-access-to-secrets).

## Selected next implementation

The next implementation Work Item is the dual-basis, revision-aware price contract. It is immediately actionable,
stops a currently recurring semantic error, and unlocks trend, performance and lot/thread price-path metrics. ETF
rights and connector fixture work, plus broker/cash source planning, may continue as read-only research while that one
implementation Work Item is active.
