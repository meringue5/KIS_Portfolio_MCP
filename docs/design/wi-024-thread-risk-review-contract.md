# WI-024 — Thread risk plan and owner review contract

## Authority boundary

A thread risk plan is an owner-authored, append-only revision. Its typed fields are the authoritative inputs for later
planned-loss and Turtle-inspired 2% portfolio-risk calculations. Journal prose and model output are not parsed into a
stop or reference price. Model/ATR suggestions may be retained only in `advice_metadata`; they never change the
`authority_source=owner` rule.

The V1 contract supports long held positions. `stop_price` must be below `reference_price`, both use the declared
currency, and the selected risk budget ratio is positive and no greater than `0.02`. Each changed revision advances
`knowledge_at`, cites the expected prior revision, and keeps its effective time separate from knowledge time.

## Review queue

The review queue stores stable identities plus append-only state revisions for:

- an open trade thread with no authoritative risk plan;
- a trade thread with no owner journal revision;
- an inferred FIFO sell allocation that requires owner confirmation;
- a sell allocation with an unresolved reconciliation exception.

Discovery may open a review item as `system`, but only actor `owner` may answer or dismiss it. An unanswered item stays
`open`; no default answer, stop, journal or allocation intent is synthesized. A resolution stores a reference to the
separate authoritative revision rather than copying intent into Control state.

## Persistence and compatibility

Migration `0011` adds `silver.trade_thread_risk_plan_revisions`,
`silver.trade_thread_risk_plans_current`, `control.owner_review_items`,
`control.owner_review_item_revisions` and `control.owner_review_items_current`. Tables are included in complete V2
Parquet recovery; views are rebuilt from migrations. Existing trade, thread, journal and reconstruction rows are not
rewritten.

This Work Item adds no production migration, backfill, public MCP write tool, schedule, external message or order
capability. Later WI-025 may consume only point-in-time owner-authoritative plans. Later WI-043 owns the scoped Remote
MCP journal/write adapter.
