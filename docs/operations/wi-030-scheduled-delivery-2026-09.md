# WI-030 scheduled Telegram delivery and real-use activation evidence — 2026-09

> Scope: production execution, outbound delivery and owner receipt evidence
> Classification: client-network incident; no application, destination or Telegram API defect found

## Result

The first scheduled bounded-canary delivery succeeded. The owner's initial report of no visible messages was caused by
the current Wi-Fi network blocking Telegram: the Telegram client remained in `연결중` state. Switching the same device
to LTE revealed the already-delivered portfolio alerts. No destination rebind or Secret rotation was required.

## Timeline and aggregate evidence

| Time (KST) | Evidence |
| --- | --- |
| 10:00:03 | Scheduler invoked `kis-portfolio-owned-core-v2-1000`. |
| 10:18:54 | Execution emitted its terminal aggregate result. |
| 10:18:57 | Execution `kis-portfolio-owned-core-v2-1000-6tnkp` completed successfully. |
| after completion | Owner initially observed no messages while Telegram itself showed `연결중` on Wi-Fi. |
| incident check | Delivery and canary were temporarily set to `false` on all three core Jobs; collection and DB-only shadow remained enabled. |
| destination probe | Same pinned bot/chat Secret v1 resolved to `wyott_bot`, one private chat, and the same chat seen in recent `/start` updates. Raw identifiers were not printed or recorded. |
| LTE check | Owner switched to LTE and confirmed the portfolio alerts were present in the intended `wyott_bot` conversation. |
| recovery | All three core Jobs were restored to `KIS_TELEGRAM_DELIVERY_ENABLED=true` and `KIS_TELEGRAM_CANARY_ENABLED=true`; the ephemeral diagnostic Job was deleted. |

The 10:00 execution reported:

- pipeline status `succeeded`, 57 source calls;
- shadow: 21 candidates, 4 transitions, 4 DB-only shadow claims and zero external sends;
- canary: 21 candidates and 21 transitions across `kr-1000` and `us-close`;
- Telegram: 8 eligible, 8 attempts, 8 provider-confirmed sends;
- zero unknown, retryable failure or permanent failure outcomes.

The Telegram client treats a response as `sent` only when the provider response is successful and contains an integer
message ID. Existing sent claims are terminal, so the rollback/re-enable sequence cannot resend those eight candidates.

## Acceptance impact

- First scheduled `kr-1000` plus `us-close` delivery: passed.
- Owner destination receipt: passed over LTE.
- Destination mismatch hypothesis: rejected by the GCP-side hashed probe.
- Application/Telegram transport defect hypothesis: rejected for this incident.
- Subsequent bounded-canary runs completed all four evaluation slots. The immutable canary ended with 18/18 unique,
  provider-confirmed deliveries, zero retryable/unknown/permanent outcomes, owner receipt and append-only revocation.
- `WI-030-S02` is closed as transport evidence. It does not promote the canary to a permanent rule or accept the Rich
  Message product experience; those gates remain S03/S04.

## WI-029 interim evidence incident — 2026-09-03 14:30 KST

Execution `kis-portfolio-owned-core-v2-1430-l6ss6` failed while recording a DB-only shadow attempt. MotherDuck raised
internal commit error ID `a152c99c`; the error handler then issued an unconditional rollback after the transaction had
already ended, replacing the original exception with `cannot rollback - no transaction is active`. The partial slot
has one `claimed` shadow dispatch with zero attempts.

WI-029-S06 preserves this as `MOTHERDUCK_COMMIT_FAILED_A152C99C`; it is not backfilled or called live success. Slot
coverage now requires terminal candidate outcomes and required shadow claims, and from 2026-09-08 requires a
deterministic completion marker written only after shadow evaluation finishes. The original 2026-08-28 through
2026-09-10 evidence row remains immutable; the corrected window excludes pre-activation 2026-08-28 and runs from
2026-09-01 through 2026-09-14. September 10 is an interim review gate, not automatic milestone closure.

The correction merged in PR `#49` as master `167d3db`. Deploy run `34127107566` completed successfully, including
activation execution `kis-portfolio-wi030-s03-zdr98`, and deployed one build-once digest
`sha256:dc009b95eaa2bdfd8ff0b37ba155a2a936ec8a1eaf3ac2ee3c0436b5162e8d1b` to the 10:00, 14:30 and 16:00 Jobs.
This proves deployment, not the first post-cutover scheduled marker or Rich Message receipt.

## Repeated U.S. close incident — 2026-09-08 10:00 KST

Execution `kis-portfolio-owned-core-v2-1000-khpbl` ran the core collection successfully, then exited 1 during shadow
evaluation with `AlertWarehouseConflictError: alert candidate changed on replay`. The same governed U.S. close
session was selected on two Korean evaluation dates around a U.S. market closure. Four existing `us-close`
candidates matched the stable candidate identity but differed only in evaluation date and evaluation run ID.

The failed execution wrote 17 shadow candidates but no Telegram attempt and no `shadow-slot-terminal-v1` marker.
WI-030-S05 keeps the original candidate immutable, skips a previously evaluated older market session as an explicit
idempotent reuse, and requires a normal same-day retry plus terminal marker before the slot is recovered. It does not
backfill a Telegram message for the missed run.

PR `#51` merged the correction as master `dca08284`. GitHub Actions run `34180002830` passed and deployed digest
`sha256:8cf0b598d7d7c60835a57442f63f0045fad6b7f81f5e3da36d23548265ac0595` to the three fixed-slot Jobs.
Recovery execution `kis-portfolio-owned-core-v2-1000-l7hr5` completed successfully. Read-only warehouse verification
showed one succeeded `pipeline.owned-portfolio-core-v2` `kr-1000` run, one passing terminal marker with 17 evaluated
candidates, zero transitions and four reused U.S. sessions, and zero Telegram attempts for the date. The successful
core collection was reused; no synthetic missed alert or duplicate dispatch was emitted. WI-030-S05 is closed while
the broader S03/S04 real-use acceptance remains open.

## Operational lesson

When the provider ledger says `sent` but the owner sees nothing, check the Telegram client's own connection state and
compare Wi-Fi versus cellular access before rotating chat IDs or credentials. API success is delivery evidence, while
owner-visible receipt remains a separate acceptance observation.

## WI-030-S03 production-value activation — 2026-09-03

PR `#43` passed CI and merged as master SHA `fe616253a681b9ca1d4a763db7cd9ae4a338d7a5`. GitHub Actions run
`33652147678` completed the manual `wi030-s03` production target successfully. The activation execution
`kis-portfolio-wi030-s03-q87wm` returned:

- status `activated` for immutable rule version `rc-2026-09-03.1`;
- presentation version `production-value-v1`;
- 18 prior provider-confirmed S02 canary sends as the transport prerequisite;
- evidence hash `036c47074ca062d74f1b40f390f2be1dc6c6d04b1920df1e253cec792938dd85`;
- append-only replacement of canary version `canary-2026-09-01.1`; no S02 candidate, claim or attempt was changed.

The build-once digest `sha256:791da9af703524f4e4579219f9aeddeac2c271aa9b17b63d09512f6d03faf9eb`
was deployed to all three existing core Jobs. Read-only post-deploy inspection confirmed each Job has master SHA
`fe61625`, deploy target `wi030-s03-real-use`, delivery enabled, canary producer disabled and production-value producer
enabled. The three existing Scheduler Jobs remain `ENABLED` at 10:00, 14:30 and 16:00 KST on weekdays.

This is the start of real use, not MS-002 closure. The first production-value scheduled message and subsequent
duplicate/failure/volume observations remain pending. A weekday 10:20 thread heartbeat reads only redacted aggregate
runtime and ledger evidence and reports meaningful new success, failure or owner-action conditions; owner receipt and
product acceptance are still manual decisions.

## First S03 owner feedback — 2026-09-03 10:00 KST

Execution `kis-portfolio-owned-core-v2-1000-z9h6x` completed successfully. It evaluated 21 production-value candidates
and sent 14/14 eligible messages with zero unknown, retryable or permanent failures. The owner confirmed that the
messages arrived, but did not accept the product wording as intuitive.

Read-only candidate review found all 14 messages were first-evaluation `entered` states under
`rc-2026-09-03.1`; the public reason `confirmed_sma20_break` required only current price below SMA20 plus another
weakness confirmation and did not require a prior-to-current cross. Several instruments rose on the day while still
remaining below SMA20/50/120, so `이탈` could be misread as a reversal. KRX 10:00 volume also compared partial-day
cumulative volume with full-day history. DEC-052 classifies these as meaning-accuracy defects rather than owner
education gaps.

The correction must use a successor immutable RC, preserve all v1 candidates and attempts, seed the first active state
without external delivery, distinguish `하회` from observed `하향 이탈`, suppress non-comparable intraday volume and
scope the quality line to the facts that actually passed. Owner acceptance remains open.

## S03 semantic stabilization deployment — 2026-09-03

PR `#45` passed CI and merged as master SHA `0ef833e039f0e644c503b5bbc804c2a5907ef7b7`. GitHub Actions run
`33716893875` completed the manual `wi030-s03` target successfully. Activation execution
`kis-portfolio-wi030-s03-rrn2x` completed in 24.83 seconds and returned:

- status `activated` for successor rule version `rc-2026-09-03.2` under `DEC-052`;
- presentation version `production-value-v2`;
- 14 provider-confirmed v1 sends as the real-use prerequisite;
- zero shadow sensitive-data violations and zero shadow external sends;
- evidence hash `6fc5d1085709da156e5f54ec74357216c289d0531b0364a503600e44410c11ba`.

The activation append-only revoked `rc-2026-09-03.1` and approved the successor contract; prior candidates, claims and
attempts remain immutable. The build-once digest
`sha256:b86bc87ca8bca9dce0f52f983b9aa8f05b1b951efb86338b44cc8d032f1dc03e` was deployed to all three core Jobs.
Read-only inspection confirmed the Jobs share that digest and master SHA, have delivery and real-use enabled, and have
canary disabled. The weekday 10:00, 14:30 and 16:00 KST Scheduler Jobs remain `ENABLED`.

Deployment success proves activation and configuration, not owner acceptance. The first v2 evaluation seeds existing
active conditions as a no-send baseline; only a later state change may produce a new notification. Calendar-window
claims remain governed by `alert-temporal-acceptance-plan.md` and `WI-030-S04`.

## S03 Rich Message successor — 2026-09-07

Through the 16:00 run, `rc-2026-09-03.2` accumulated 27 provider-confirmed deliveries with zero retryable, unknown or
permanent outcomes and unique dispatch identities. Owner inspection of the 10:00 message found repeated unavailable
labels and timestamps, poor scan order, fixed next-check boilerplate and an unsupported `가격·추세 정상` claim when
the displayed trend metrics were unavailable.

DEC-053 approves a successor immutable RC, `rc-2026-09-07.1`, with presentation `production-value-v3`. It uses
Telegram `sendRichMessage`, severity icons, an available-only compact table, one collapsed unavailable-details block
and one source-time footer. It has no automatic `sendMessage` fallback. Existing v2 candidates and delivery ledger
evidence remain unchanged.

PR `#47` merged as master `fa05adaf1d020253749dc9a87650bb42e76b2f68`. Deploy run `34120564082` passed and
activation execution `kis-portfolio-wi030-s03-6wrvq` returned `activated`, prior version
`rc-2026-09-03.2`, prior successful sends `27`, presentation `production-value-v3`, zero shadow sensitive violations,
zero shadow external sends and evidence hash `bcf6b81ee1136fec2ed497186d12f04d13657d4cd68bace5a98dba3cdd36935b`.
Digest `sha256:1a427f354b70c19fc43739691612f01b3d668b242ab52a81d04bc1b5bfedb7ed` is deployed to the
three core Jobs. Scheduled Rich Message receipt and owner acceptance remain pending.
