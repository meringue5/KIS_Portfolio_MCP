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
- Remaining S02 evidence: `kr-1430` and `kr-1600`, cross-slot de-duplication, and expiry/revocation fail-closed behavior.
- `WI-030-S02` therefore remains `in_progress`; this evidence does not promote the canary to a permanent rule.

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
