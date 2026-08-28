# WI-022-S03 — Deterministic Position Replay

## Scope and side-effect boundary

This sub-item turns the S01 reconstruction contract into a pure replay plan. It accepts only canonical passing trade
revisions, governed passing corporate-action effects, an explicit reconstruction window and the current broker
quantity. It returns candidate position episodes, lot states and FIFO sell allocations in memory.

The implementation does not read a source, open MotherDuck/DuckDB, persist an S02 object, run a migration, change a
scheduler or send an alert. Append-only persistence and restore proof remain S04 responsibilities.

## Deterministic input boundary

One replay partition is fixed by account, target canonical instrument, reconstruction start/cutoff and governed
instrument lineage. Every input must be timezone-aware, inside that window and inside the account/lineage scope.
Only `quality_status=pass` revisions are admitted. A corporate-action revision may contribute at most one of each
quantity, price and successor effect, and all effects in the revision share the same effective time, knowledge time
and input instrument.

Canonical order is `(effective time, execution sequence, stable identity)`. A trade and action at the same instant,
multiple action revisions at one instant, or opposing trade sides with the same timestamp and sequence are not
silently tie-broken: the plan returns `reconciliation_exception` with no derived facts.

The replay hash serializes sorted canonical inputs, evidence coverage and source gaps. Input iteration order therefore
cannot change an episode, lot, allocation or replay identity.

## Reverse boundary derivation

The current broker quantity is authoritative only at the cutoff. The engine walks events backward to derive the
quantity required at the reconstruction boundary:

- undo a buy by subtracting its quantity;
- undo a sell by adding its quantity;
- undo a quantity effect by dividing by its exact rational factor;
- undo a governed successor by restoring its input instrument.

A negative boundary requirement, broken successor chain, non-decimal quantity result or more than ten fractional
quantity digits is an exception. When the positive boundary requirement survives passing action coverage and no
source gaps, the engine creates an `inferred_opening` lot at the start boundary. It carries no execution reference,
price or fabricated cost; unknown currency is labelled `UNKNOWN` until explicit evidence supplies it.

## Forward replay and episode boundary

The derived opening state is then replayed forward with the same ordered events. An actual buy creates an actual lot.
A sell is allocated by the S01 deterministic FIFO contract only within the active account, instrument and episode.
Insufficient open-lot quantity blocks the whole candidate plan rather than creating a negative lot or synthetic buy.

When all lot balances reach zero, the episode closes at that sell time. A later buy starts a new stable episode. A
governed successor may carry the open episode and its remaining lots to the output instrument; symbol/name similarity
alone cannot. Quantity and price effects update effective quantity and unit cost while preserving original evidence.

Episode reconstruction status is local to its evidence. Thus an inferred historical episode may close, while a later
episode based entirely on actual buys is `reconstructed`. The plan-level status remains `inferred_opening` whenever
the reconstruction window needed an inferred boundary.

## Fail-closed precedence and handoff

Before replay, failed action coverage or ambiguous ordering is `reconciliation_exception`, unassessed action coverage
is `not_assessed`, and a named source gap is `provisional`. These states return no candidate episode, lot or allocation
facts. After replay, quantity or instrument mismatch is also an exception with no partial projection.

S04 may persist a plan only when `eligible_for_reconciled_projection=true`, must bind it to the replay hash and coverage
quality result, and must prove append-only idempotency, allocation reconciliation and backup/restore. S03 itself owns
no warehouse mutation.
