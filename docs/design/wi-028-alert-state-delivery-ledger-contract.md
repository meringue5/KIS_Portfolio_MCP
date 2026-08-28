# WI-028 — Alert state and delivery-ledger contract

## Boundary

This Work Item turns governed point-in-time metrics into replayable alert candidates and transport-neutral dispatch
claims. It performs no Telegram request, reads no Telegram secret and does not activate a production threshold.
`shadow` is the only permitted delivery mode in WI-028; external delivery remains WI-030.

ETF instruments are evaluated as opaque securities from their own price, trend, valuation-change and lot/thread
metrics. Missing constituent coverage is explicit and cannot be replaced by inferred sector, country or currency
exposure.

## Identity and time

- An alert identity is the hash of rule id/version plus opaque subject type/id. It survives scheduler retries and
  spans the three Korean evaluation slots so unchanged active state is not sent again later in the day.
- A candidate identity also includes the logical session key and slot. The allowed slots are `kr-1000`, `kr-1430`,
  `kr-1600` and `us-close`. A U.S. close evaluation uses `us-close:<US session date>` and is not recreated in the
  14:30 or 16:00 Korean runs.
- Rule versions are immutable. Threshold calibration in WI-029 creates or approves a version; it never edits a used
  version in place.
- Candidate rows are immutable by their logical evaluation key. A conflicting replay fails instead of overwriting
  history.

## State machine

`normal` and `active` are evaluated states. `partial`, `stale`, `reconstructed`, `insufficient_history` and any other
non-pass quality create an auditable suppressed candidate but do not mutate prior alert state and never produce a
claim.

| Prior | Current | Transition | New delivery candidate |
| --- | --- | --- | --- |
| none | normal | `initial_normal` | no |
| none/normal | active watch+ | `entered`/`reentered` | yes |
| active | identical fingerprint | none | no |
| active | higher severity | `escalated` | yes |
| active | changed watch+ fingerprint | `updated` | yes |
| active | lower severity but active | `deescalated` | no |
| active watch+ | normal | `recovered` | yes |

A re-entry increments the episode number. Recovery carries the prior delivered severity for routing while the current
candidate remains normal. WI-029 clarifies the approved Korean mapping as `normal/정상`, `watch/주의`,
`warning/경고`, `critical/긴급`; migration `0013` therefore adds the exact rank-1 `watch` delivery floor without
editing migration `0012`.

## Warehouse objects

- `control.alert_rule_versions`: immutable rule definition and hash, validity and delivery mode.
- `gold.alert_candidates`: point-in-time candidate, quality, lineage and allowlisted public context.
- `control.alert_state_revisions` and `control.alert_states_current`: append-only transitions and current projection.
- `control.alert_candidate_outcomes`: exactly-once processing marker for transition, no-change, quality suppression or
  out-of-order suppression;
  this prevents a historical no-change candidate from being applied against a later state during replay.
- `control.alert_dispatch_claims`: one idempotent claim per candidate/channel/opaque destination with a bounded lease.
- `control.alert_delivery_attempts`: redacted attempt outcomes. `unknown` is terminal and is never automatically retried.

All tables are `confidential` Parquet backup members. They may contain opaque subject identities, but never account
numbers, total-asset absolute amounts, chat identifiers, credentials, raw source content or arbitrary exception text.
Candidate public context is an allowlist of label, summary, reason codes, percentage change, metric references and
quality. Delivery errors are bounded codes only.

## Failure and concurrency

State revisions use expected-prior revision checks. Dispatch acquisition is a unique insert or a compare-and-update
of an expired/retryable claim. Completed, unknown and permanent-failure claims are terminal. A retryable failure may
be reacquired with a new lease token; raw lease tokens are never stored, only SHA-256 digests.

No always-on worker is introduced. Evaluation and writes run in the existing bounded, scale-to-zero pipeline slots
and make zero source or network calls.

Candidates for one alert identity must be applied in increasing `evaluation_at` order. A late historical candidate is
recorded as `out_of_order` without changing current state; replay orchestration must sort the partition and start from
an empty or explicitly restored state.
