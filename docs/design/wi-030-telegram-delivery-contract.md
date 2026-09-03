# WI-030 Telegram delivery contract

> 상태: S01 closed; DEC-050 transport canary S02 and DEC-051/052 production-value S03 in progress
> Work Item: WI-030-S01 / WI-030-S02 / WI-030-S03
> Data contracts: `pipeline.telegram-delivery-v2:1.3.0`, `dataset.alert-candidate:1.2.0`, `dataset.alert-delivery-ledger:1.2.0`

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

S01 makes this path executable in offline tests. DEC-050 authorizes S02 to add one immutable external canary rule for
at most seven elapsed days while the original shadow rule and formal WI-029 evidence continue unchanged. Permanent
external activation still requires WI-029 closeout.

## Bounded canary exception

- Canary rule version and alert state identity are separate from `bootstrap-1.0.0` shadow state.
- The rule is `active/external`, has an explicit `valid_from` and `valid_to` no more than seven days apart, and cannot
  be edited or automatically promoted.
- `watch` or higher pass-quality transitions are sent, including signals later labelled false positive. `normal`,
  non-pass and repeated `no_change` candidates remain DB evidence and are not individual Telegram messages.
- Eligibility and claim paths both recheck rule validity at dispatch time. Expiry or owner revocation fails closed.
- The normal owner approval method still requires verified replay/shadow evidence. A dedicated canary approval path
  accepts only the exact bounded contract after at least one successful complete scheduled day, zero sensitive
  violations and zero prior external sends.
- Maximum delivery remains 20 attempts per monitoring run. Rollback is the enable flag; history is never deleted.

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

S03 production-value presentation replaces the transport template for its new immutable rule version. It renders a
safe instrument name, market/type, Korean reason, signed daily change, SMA20/50/120 relations, volume ratio, RSI14,
Bollinger context, KST data/evaluation time and quality. Episode drawdown and KRW valuation-change contribution are
rendered as signed percentages when their governed metric quality passes; otherwise the message says `계산 보류` with
a bounded reason. It never substitutes allocation, unrealized PnL or zero for an unavailable metric. Internal rule ID,
version and reason codes remain in the ledger rather than occupying the owner-facing message.

DEC-052 correction uses a successor immutable rule version. `하회` means the current price is below an average;
`하향 이탈` requires prior close at or above prior SMA20 and current close below current SMA20. Price-to-average
position and SMA20-to-SMA50 structure are separate lines. A successor rule's first active observation seeds a silent
baseline and is not presented as a new market event. KRX 10:00/14:30 cumulative volume is explicitly unavailable until
same-slot normalization exists; only KRX close and U.S. close use prior 20 completed sessions as the full-day baseline.

Only these `public_context` keys are accepted:

- `presentation_version`
- `subject_label`
- `market_label`
- `asset_type_label`
- `summary`
- `reason_codes`
- `change_percent`
- `sma20_relation`, `sma50_relation`, `sma120_relation`
- `sma20_sma50_relation`
- `volume_ratio20`, `rsi14`, `bollinger_state`
- `episode_drawdown_percent`, `portfolio_impact_percent`, `unavailable_codes`
- `source_at`
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
- `KIS_TELEGRAM_CANARY_ENABLED` and `KIS_TELEGRAM_REAL_USE_ENABLED`: mutually exclusive producers. S03 sets the
  former to `false` and the latter to `true`; an invalid simultaneous configuration fails before collection.

Generic batch, auth and Remote MCP do not receive Notification secrets. Secret payloads, request URLs and Telegram
response bodies do not enter command output, logs, PR evidence, MotherDuck or backup.

## S02 activation checklist

1. Confirm the owner initiated the private bot conversation and verify destination without recording its raw ID.
2. Owner separately approves this finance-free message before it is sent:
   `KIS Portfolio 알림 채널 연결 테스트입니다. 계좌·자산 데이터는 포함하지 않았습니다.`
3. Confirm enabled Secret Manager versions and resource-level accessor for only the V2 pipeline runtime identity.
4. Record the approved bounded canary as a new immutable version; never mutate the shadow rule in place.
5. Run the finance-free test, inspect only redacted outcome, then deploy the three existing scale-to-zero jobs with the
   enable flag and pinned secret versions.
6. Verify one eligible alert, deduplication, terminal ledger status, zero sensitive violations and no repeated U.S.
   close at 14:30/16:00.
7. Review false positives, misses and message volume after the canary. Expiry cannot create a permanent rule.
8. Close WI-029 before permanent external activation.
9. Roll back immediately by setting the enable flag to `false`; do not delete claims or attempts.

Steps 2 through 7 are external/production actions and remain outside S01 authorization.

## S03 real-use stabilization checklist

1. Preserve S02 candidates, approvals, claims and delivery attempts as immutable transport evidence.
2. Register and owner-approve the separately versioned production-value release candidate, then append a revocation
   of the S02 approval so exactly one external producer remains active.
3. Deploy one tested image digest to all three existing scale-to-zero jobs with real-use delivery enabled.
4. Receive a production-equivalent message in the private owner destination and verify that it identifies the
   instrument and explains the actionable price, trend, volume/momentum, freshness and quality facts.
5. Display governed-but-not-ready drawdown and KRW valuation-change contribution as explicit `계산 보류`; track the
   upstream readiness remediation instead of filling zero or a substitute metric.
6. Stabilize duplicate suppression, missing messages, unsafe-payload failures, false positives and message volume from
   actual use. Record redacted provider/ledger evidence and owner observations.
7. Only after WI-029 evidence, the production-equivalent observation window and owner acceptance pass, issue a new
   permanent immutable rule version and close MS-002. Do not silently promote this bounded release candidate.
8. Maintain separate daily, weekly, monthly, quarterly and annual evidence states in
   `docs/operations/alert-temporal-acceptance-plan.md`; passing a shorter window does not pass a longer one.
