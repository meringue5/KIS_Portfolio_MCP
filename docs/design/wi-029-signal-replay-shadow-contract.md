# WI-029 — Signal replay, calibration and shadow contract

## Severity and bootstrap rule set

The canonical four levels are `normal` (정상), `watch` (주의), `warning` (경고) and `critical` (긴급).
Delivery eligibility starts at rank 1, `watch`. Migration `0013` adds the numeric floor because the earlier
transport ledger's coarse `minimum_delivery_severity` column cannot express `watch`; the earlier migration checksum
is not edited.

Bootstrap boundaries are the owner-approved Package D values, not production claims:

| Signal | watch | warning | critical |
| --- | ---: | ---: | ---: |
| absolute daily return | `max(3%, 2*vol20)` | `max(5%, 3*vol20)` | `max(8%, 4*vol20)` |
| absolute KRW portfolio contribution | 0.25 percentage points | 0.75 pp | 1.50 pp |
| position-episode drawdown | -8% | -12% | -20% |
| planned loss / portfolio value | 1.5% | 2.0% | 2.5% or stop breach |

Price at or below SMA20, RSI14 30/70 and Bollinger 20/2 are context only. Price shock plus volume/SMA20 at least
1.5 strengthens one level; 2.5 is high-volume context. A close below SMA50 with SMA20 below SMA50 and a drawdown
condition is at least warning. If fewer than 20 valid bars exist, volatility and volume rules are unavailable while
absolute return and contribution remain evaluable.

ETF, REIT, leveraged and inverse products are evaluated as their own listed instruments. Look-through is unavailable.
Asset-class calibration changes only a versioned absolute-boundary multiplier chosen from an explicit candidate grid;
it never silently changes the approved formula or overwrites a used rule version.

해외 보유상품의 `stock`/`reit` 분류는 이름 heuristic을 쓰지 않는다. KIS `CTPF1702R`의 exact symbol과
상품분류, SEC submissions의 exact ticker/CIK/SIC가 모두 일치할 때만 official-reference evidence로 채택한다.
SEC SIC 6798은 REIT로, 그 외 KIS 해외주식 상품은 equity로 분류하며, identity 또는 상품분류가 모호하면
`unknown`으로 남긴다. 실제 보유 symbol은 공개 저장소 문서에 기록하지 않는다.

## Replay semantics

- Input is sorted by evaluation time, slot and opaque subject before evaluation.
- Every observation declares `historical_live` or `retrospective_reconstructed`; reconstructed data may calibrate a
  boundary but is never labelled as an old live alert.
- Non-pass quality is counted and produces no alert state.
- The daily budget target is median at most 2 and nearest-rank p95 at most 5 stateful delivery candidates per
  evaluation slot. Raw active observations are reported separately; only entry, escalation, changed signal set,
  recovery and re-entry count toward the budget, using the same de-duplication semantics as WI-028.
- Asset-class candidates are first checked independently, then the selected profile combination must pass the same
  budget again after all held asset classes are combined. A per-class pass cannot hide a noisy total slot.
- "False positive" and "miss" are owner-review labels. Until labels exist, the report exposes only transparent
  proxies: top candidate episodes and the maximum adverse observation below watch. It must not claim precision.
- A three-year report states actual date span and coverage by asset class. Review readiness requires at least 1,096
  calendar days from first to last eligible session and at least 600 distinct eligible session dates per observed
  asset class. A short or class-missing window remains `insufficient_history`; fixture success does not satisfy
  production acceptance.

## Shadow and approval

Shadow is DB-only. `control.alert_shadow_windows` requires external send count zero and records expected/observed
sessions, candidates, de-duplication, quality suppression and sensitive-value violations. A window cannot be verified
until at least 14 elapsed days, expected governed slots are reconciled, sensitive violations are zero and owner review
is complete.

`control.alert_rule_approval_revisions` is owner-only and references both a review-ready calibration run and a verified
shadow window. Approval does not itself enable Telegram; WI-030 owns destination verification, test message and the
external delivery feature flag.

## Cost and safety

Replay reads governed MotherDuck rows and makes zero provider calls. It is a bounded, terminating analytical job.
Shadow reuses the three scale-to-zero monitoring slots; it creates no always-on worker and has no Telegram secret or
network adapter. Reports use opaque subject hashes and aggregate counts, never account numbers or absolute total
asset values.
