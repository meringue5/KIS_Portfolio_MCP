# Alert temporal acceptance plan

> Status: approved plan; live evidence accumulates over time
> Owner: WI-030-S04
> Decision: DEC-052

## Purpose

An alert that behaves correctly for several daily slots has not thereby proved month-end, earnings-season, quarter-end
or year-boundary behavior. KIS Portfolio therefore records acceptance by explicit time window and never promotes an
unobserved long window to `passed` merely because shorter windows passed.

Long-window defects are discovered with three complementary evidence paths:

1. **Historical replay:** run the immutable rule over the governed three-year price and portfolio history without
   claiming that reconstructed observations were live.
2. **Deterministic calendar fixtures:** test month/quarter/year boundaries, KRX/U.S. holidays, leap dates, U.S. daylight
   saving changes and missing-session recovery without waiting for wall-clock time.
3. **Live longitudinal observation:** retain the real Scheduler, candidate, transition, quality and delivery ledger
   evidence and owner feedback for the actual elapsed window.

Replay finds regime and threshold problems early, fixtures prove clock/calendar mechanics, and live evidence proves
source behavior and user value. None substitutes for the other two.

## Window matrix

| Window | Primary questions | Required evidence | Claim boundary |
| --- | --- | --- | --- |
| Slot / daily | Did each due slot run, use fresh inputs, suppress duplicates and deliver safely? | pipeline run, candidate/state transition, redacted delivery outcome, owner-visible sample | operational correctness for the observed slots only |
| Weekly | Is message volume tolerable; are repeated signals, false positives and misses explainable across different market days? | due-slot reconciliation, p50/p95 message count, reason distribution, owner labels, unavailable-rate trend | one observed trading-week pattern, not month-end behavior |
| Monthly | Do holdings turnover, dividend/cash events, month-end calendars, cost and warehouse drift change results? | replay plus live month boundary, cost/capacity report, contract drift and stale/unavailable review | the observed/replayed month classes only |
| Quarterly | Do earnings, consensus revisions, dividends and corporate actions produce coherent signals and recover correctly? | quarter-boundary fixture, reporting-season replay, source/license review, private backup restore rehearsal | tested quarter scenarios and elapsed quarters, not annual closure |
| Annual | Do tax/year-end cash flows, holiday/DST/year rollover, 52-week/ATH measures, retention and backfill stay correct? | three-year replay, year-boundary/DST fixtures, annual cost/retention review and at least one live rollover when available | explicitly distinguishes simulated/replayed evidence from live-year evidence |

## Evidence states

Each window is one of `not_observed`, `fixture_pass`, `replay_pass`, `live_collecting`, `live_review_ready`, `accepted`
or `failed`. A parent capability may remain useful in production while a longer window is still `not_observed`, but its
documentation and MCP/Telegram claims must state that limitation.

A failure or ambiguous owner observation creates a WI-030 sub-item when it remains within alert delivery outcome;
independent analytics, source or architecture changes receive the next unused Work Item. Existing rule versions,
candidates, claims and attempts remain immutable. Corrections use a new rule/contract version and repeat the relevant
short-window gates before returning to longitudinal observation.

## Low-cost operation

No always-on service or governance SaaS is introduced. Existing scale-to-zero Jobs and MotherDuck ledgers provide the
facts. Repository tests run fixtures/replay in bounded batches; live reviews are scheduled only at the cheapest useful
cadence. Monthly, quarterly or annual notifications are not created until the owner separately approves their exact
schedule and notification policy.
