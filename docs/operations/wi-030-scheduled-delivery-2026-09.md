# WI-030-S02 first scheduled Telegram delivery evidence — 2026-09-01

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
