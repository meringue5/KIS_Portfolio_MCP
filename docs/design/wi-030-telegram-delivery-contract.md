# WI-030 Telegram delivery contract

> 상태: S01 repository preparation; production disabled
> Work Item: WI-030-S01 / WI-030-S02
> Data contracts: `pipeline.telegram-delivery-v2:1.0.0`, `dataset.alert-delivery-ledger:1.1.0`

## Boundary

Telegram is an outbound-only adapter after the alert state and delivery ledger. It cannot collect data, accept bot
commands, write journals or place orders. Signal evaluation remains valid even when delivery fails.

```text
approved point-in-time candidate
  -> delivery-required state transition
  -> active external rule + latest owner approval gate
  -> allowlisted plain-text renderer
  -> leased telegram claim
  -> one sendMessage attempt
  -> redacted terminal/retryable ledger outcome
```

S01 makes this path executable in offline tests but keeps `KIS_TELEGRAM_DELIVERY_ENABLED=false` and gives no Telegram
secret to production jobs. S02 may enable it only after WI-029 closes.

## Candidate and activation gates

All gates are conjunctive:

1. rule contract status is `active` and delivery mode is `external`;
2. the latest owner decision for the exact rule ID/version is `approved`;
3. candidate quality is `pass` and its state revision says delivery is required;
4. severity is `watch`, `warning` or `critical` under the approved rule floor;
5. runtime enable flag is exactly `true`, and both token and private chat destination are present;
6. renderer accepts every field and the dispatch lease is acquired.

The repository rechecks owner approval while claiming, not only while listing candidates. A later `revoked` decision
wins immediately. Disabled or incomplete configuration never creates a claim or request.

## Payload contract

Plain text includes severity, subject label, transition, bounded summary, percentage change when available, reason
codes, evaluation timestamp/slot, rule ID/version and a fixed next-check instruction. It does not use Telegram HTML or
Markdown parsing.

Only these `public_context` keys are accepted:

- `subject_label`
- `summary`
- `reason_codes`
- `change_percent`
- `metric_refs`
- `quality_status`

Account numbers, chat identifiers, credentials, raw provider text, total-asset/evaluation/cash absolute amounts,
currency-marked values, long absolute numbers and overlong fields fail before the network call. The destination in the
ledger is the non-secret alias `dest.owner.primary`, never the Telegram chat ID.

## Outcome and retry contract

| Observation | Ledger outcome | Automatic behavior |
| --- | --- | --- |
| Telegram confirms `message_id` | `sent` | terminal; message ID reference is hashed |
| explicit HTTP 429 | `retryable_failure / RATE_LIMITED` | eligible once in a later scheduled run |
| explicit HTTP 5xx | `retryable_failure / TELEGRAM_5XX` | eligible once in a later scheduled run |
| explicit HTTP 4xx | `permanent_failure / TELEGRAM_4XX` | terminal |
| unsafe payload | `permanent_failure / UNSAFE_PAYLOAD` | terminal; no request |
| timeout after request or transport ambiguity | `unknown` | terminal; never automatically resent |
| malformed success response | `unknown / INVALID_RESPONSE` | terminal |
| dispatch lease expires before a terminal record | `unknown / CLAIM_EXPIRED_UNKNOWN` | terminal; process-crash ambiguity is never resent |

There is no in-process retry. One monitoring run processes at most 20 eligible claims, and Cloud Run Job infrastructure
retry remains zero.

## Secret and release contract

- `KIS_TELEGRAM_BOT_TOKEN`: GCP Secret Manager; V2 pipeline identity only after S02.
- `KIS_TELEGRAM_CHAT_ID`: GCP Secret Manager; V2 pipeline identity only after owner destination verification.
- `KIS_TELEGRAM_DESTINATION_REF`: non-secret opaque alias; must not encode the chat ID.
- `KIS_TELEGRAM_DELIVERY_ENABLED`: defaults to `false`; S02 release manifest changes it to `true`.

Generic batch, auth and Remote MCP do not receive Notification secrets. Secret payloads, request URLs and Telegram
response bodies do not enter command output, logs, PR evidence, MotherDuck or backup.

## S02 activation checklist

1. Close WI-029 after the full elapsed window, scheduled-slot reconciliation, sensitive-value review and owner rule
   approval.
2. Confirm the owner initiated the private bot conversation and verify destination without recording its raw ID.
3. Owner separately approves this finance-free message before it is sent:
   `KIS Portfolio 알림 채널 연결 테스트입니다. 계좌·자산 데이터는 포함하지 않았습니다.`
4. Confirm enabled Secret Manager versions and resource-level accessor for only the V2 pipeline runtime identity.
5. Record the approved external rule as a new immutable version; never mutate the shadow rule in place.
6. Run the finance-free test, inspect only redacted outcome, then deploy the three existing scale-to-zero jobs with the
   enable flag and pinned secret versions.
7. Verify one eligible alert, deduplication, terminal ledger status, zero sensitive violations and no repeated U.S.
   close at 14:30/16:00.
8. Roll back immediately by setting the enable flag to `false`; do not delete claims or attempts.

Steps 2 through 7 are external/production actions and remain outside S01 authorization.
