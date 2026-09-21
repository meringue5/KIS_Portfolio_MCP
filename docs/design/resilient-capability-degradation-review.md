# Resilient capability degradation review (WI-060)

> 2026-09-17 evidence-led review, approved as DEC-057/ADR-029. WI-060 remains isolated and no new FX source is
> production-active.

## Finding

The V2 layers have useful physical separation, but several consumer contracts collapse independent facts into one
quality decision. The all-or-nothing owner report is contract-compliant under DEC-055 and fails the owner's actual
usability expectation. Separate defects make MCP quality misleading in both directions.

| Failure | Current propagation | Evidence | Required boundary |
| --- | --- | --- | --- |
| Prior same-slot state absent | owner report hides current total, allocations and all holdings | `_build_owner_report` returns early on `missing_prior_state`; 9/17 10:00 preflight | comparison/Top 5 unavailable; current verified capabilities remain visible |
| USD/KRW stale | complete KRW total unsafe; old Gold could still say pass | 9/16 16:00 preflight `fx_input_stale`; WI-059-S01 | foreign KRW conversion unavailable; native units and verified KRW holdings remain visible |
| Any Gold row degraded | overview still sums a numeric `total_value_krw` | `remote_v2_warehouse.py::_get_portfolio_overview` | no complete total claim; only explicitly scoped verified subtotal |
| Any rows exist | generic MCP envelope quality `pass` | `remote_v2_warehouse.py::_envelope` ignores row quality and `missing_coverage` | aggregate relevant row statuses, coverage and freshness per capability |
| Performance history uses `passed` | actual persisted `pass` rows appear degraded | `_get_performance_history`; existing test fixture also uses `passed` | use one canonical status vocabulary and test real persisted values |
| Optional macro/ETF look-through absent | direct exposure still exists, but a client can conflate it with full exposure | `_get_exposure_analysis` returns direct plus missing coverage | preserve direct result; label absent look-through and do not infer economic total |
| Single FX source | one adapter/collection issue blocks all converted outputs | `dataset.fx-rate-daily` lists only `source.kis-open-api` | versioned secondary source with rate-basis, date, rights and discrepancy policy |

## Proposed capability cells

Evaluate quality for each field group, then compose a response; never infer complete coverage from a nonempty rowset.

1. `holdings_native`: quantity, native-currency price/value, source time and per-instrument quality. No FX or prior
   slot dependency. Account/holding coverage still required for any completeness claim.
2. `krw_listed_positions`: KRX/KRW positions with their own price and position quality. Label this as a verified
   subset, **not** domestic economic exposure or total assets; KRX-listed overseas-themed ETFs remain opaque.
3. `converted_foreign`: eligible native holding plus a rate matching currency pair, source date, valuation basis,
   provider revision and freshness policy. Failure does not poison cells 1 or 2.
4. `complete_total`: all required account, cash, domestic and converted foreign components pass and reconcile.
   Otherwise `null`; a confirmed subtotal may be shown only with named excluded coverage.
5. `same_slot_change`: two complete, comparable states with identical slot and reconciliation; absent prior state
   disables only this cell and dependent Top 5 impact.
6. `optional_context`: macro, ETF look-through, filings and signal enrichments carry independent status and never
   gate basic holdings. Unsupported is distinct from missing or stale.

Status must distinguish `pass`, `partial`, `stale`, `unavailable` and `unsupported` per capability. A partial response
must say what is excluded and must never relabel a subset as the complete total. Preserve source/effective/observed
times and lineage so Claude cannot mistake a morning stored view for live market data.

## User scenarios to freeze before activation

| Scenario | MCP answer | Telegram answer | No false claim |
| --- | --- | --- | --- |
| Complete current + comparable prior | complete total and comparison | exact owner report | full coverage/reconciliation |
| Current complete, prior same-slot missing | current total, no daily change | current-only report with comparison omitted | no invented change/Top 5 |
| FX stale, KRX/KRW valid | native foreign data and verified KRW subset | bounded partial report only after presentation approval | subset is not total |
| One account missing | observed holdings only, explicit account gap | no complete total; optional bounded partial | no complete-portfolio label |
| Optional macro/ETF absent | direct/core result unaffected, gap typed | omit optional block | no look-through inference |
| MCP empty rowset | unavailable with precise reason | not applicable | no `pass` from run success |

## Design and rollout sequence

1. Correct false-green/false-degraded MCP quality semantics against persisted `pass`/`degraded` fixtures. Keep
   existing 18 tools and OAuth scopes; add a compatibility check for any response-field change.
2. Introduce a shared read-only capability evaluator in the application layer, not inside MCP/Telegram adapters.
   Use it for current-only, complete-total and same-slot-comparison decisions without rescanning independent
   datasets through unrelated feature gates.
3. Version the owner report decision and layout to allow accurate partial/current-only presentation. Keep one
   owner-only provider operation, terminal idempotency, no auto-replay and no raw content logs.
4. Evaluate official secondary FX data. `source.bok-ecos` is approved for macro observations, **not** automatically
   approved as a valuation FX fallback. Establish whether its rate meaning and publication lag fit each slot;
   otherwise compare another provider. Cross-source disagreement must quarantine conversion, not choose a convenient
   rate. Version source/dataset/pipeline contracts and bound calls/cost before any production activation.
5. Use synthetic fault-injection fixtures for every matrix row, then isolated Claude-equivalent MCP and Telegram
   renderer tests. Production release requires owner-reviewed presentation and approved contracts, but **not**
   MS-006 closure; that would recreate the failure coupling under review.

The immediate 9/17 10:16 KRX/KRW subset is independently readable; the missing 9/16 10:00 state and stale FX
do not make that observation disappear. It remains a stored, time-labeled subset, not a real-time complete total.

## Isolated first slice and open edges

The first read-model correction has deterministic tests for a degraded component, an old pass-marked stale FX
component, a missing account and the `pass`/`passed` history mismatch. It leaves the 18-tool surface intact and
does not send a message. It adds an explicitly scoped `verified_krw_listed_positions_krw` subtotal while nulling
`total_value_krw` when complete coverage is not established.

The release candidate now uses the shared application quality composer for MCP and Telegram. Owner presentation
`2.3.0` has four outcomes: complete photo, complete current total without comparison, scoped KRX/KRW listed-position
Rich Message, and value-free unavailable. `get-data-quality` aggregates actual rule statuses, and the owned-portfolio
`get-pipeline-run` is partial when a succeeded run lacks linked quality evidence. The generic envelope remains a
transport helper; callers with governed row quality must supply their composed status.

`uv run python scripts/check_resilient_portfolio_cases.py` immediately reproduces missing prior, stale FX, missing
account, degraded row and missing-current cases without network, database, Telegram or scheduler time. The protected
`wi060` target builds once and supplies the same immutable digest to Remote MCP and the report Jobs; it does not send
a Telegram test payload. Korea Eximbank's official Open API is registered only as a proposed fallback-validation
source. No adapter, credential, provider call or valuation use is authorized until its exact rate field and
10:00/16:00 publication behavior are measured and approved.
