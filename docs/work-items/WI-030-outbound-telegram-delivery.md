---
id: WI-030
title: Enable approved outbound Telegram delivery
status: in_progress
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-007, V2-ADR-012, DEC-050, DEC-051
requirement_refs: DEC-006, DEC-026..030, DEC-038, DEC-041, DEC-044, DEC-051
milestone_ref: MS-002
delivery_refs: V2-W0508
parent_work_item: none
depends_on: WI-029
architecture_impact: adds the approved outbound-only Telegram transport behind the delivery ledger
data_impact: transport outcome only; analytics contracts remain unchanged
security_impact: Secret Manager token and destination reference with strict redaction and resource-level access
cost_impact: negligible Bot API traffic from three scheduled slots; no always-on service
---

# WI-030 — Enable approved outbound Telegram delivery

## Problem and evidence

The approved proactive channel is Telegram. S01 prepared its fail-closed transport. On 2026-08-31 the first complete
Monday schedule passed and the owner approved DEC-050: a bounded experimental canary may run while WI-029-S05 keeps
collecting the separate formal shadow evidence.

## Classification and contract

- `change` implementing V2-W0508. This is the shifted, still-unfinished Telegram milestone item; WI-017 remains ETF routing.
- Outbound-only `sendMessage`; no inbound command, journal or order surface.
- WI-029 remains the permanent-rule gate. DEC-050 authorizes only a seven-day immutable canary with explicit expiry,
  watch-or-higher transitions, at most 20 attempts per run and no automatic promotion.

## Scope

- S01 includes fail-closed configuration, redacted rendering, transport classification, delivery-ledger integration,
  deployment preparation and offline tests with no Telegram request.
- S02 includes destination verification, one finance-free test message, a parallel immutable external canary rule,
  deployment and operational proof while the original shadow rule continues unchanged.
- S03 includes the production-value message contract, upstream readiness correction, a new immutable release candidate,
  live stabilization and owner acceptance. It preserves rather than edits S02's immutable canary evidence.
- Exclude inbound bot commands and any order capability.

## Acceptance criteria

- [x] owner approves rule version, private destination and finance-free test message.
- [x] account numbers, absolute total assets, credentials, raw source and chat ID never enter payload/log analytics.
- [ ] 10:00, 14:30 and 16:00 KST slots send only `주의` or higher and preserve de-duplication.
- [ ] uncertain post-send timeout is `UNKNOWN` and is not automatically resent.
- [ ] canary expiry and owner revocation fail closed without changing the shadow rule or its evidence.
- [x] disabled or incompletely configured delivery fails closed before a claim or network request.
- [ ] Production delivery identifies the instrument safely and explains market/type, change, held-episode drawdown,
  KRW valuation-change contribution, trend, quality/freshness and reasons in owner-readable Korean.
- [ ] A production-equivalent release candidate is received and stabilized before permanent activation; transport-only
  receipt is not product acceptance.

### S01 preparation acceptance

- [x] Disabled configuration exits before candidate query, claim or network request.
- [x] Active external rule, latest owner approval, pass quality and delivery-required transition are rechecked before
  a Telegram claim.
- [x] Plain-text rendering rejects sensitive fields, identifiers, currency/absolute values and unsafe lengths.
- [x] 429/5xx retryable, 4xx permanent and timeout/ambiguity terminal-unknown outcomes are ledgered without bodies.
- [x] An expired Telegram lease is sealed as terminal unknown instead of being resent.
- [x] Secret Manager names, environment template, DGH pipeline and S02 activation/rollback checklist are documented.

## Change impact

- External-send gate and secret/IAM review are mandatory; delivery flag rollback is immediate.

## Plan

1. Implement and offline-verify disabled-by-default outbound rendering, transport and ledger integration.
2. Prepare Secret Manager/deployment references without reading values or deploying them.
3. Verify destination ownership and run the separately approved finance-free test message.
4. Register the DEC-050 bounded canary independently of the permanent-rule approval path.
5. Enable delivery, preserve the parallel shadow and record operational evidence.

## Sub-items

- `WI-030-S01`: implement and verify the disabled Telegram delivery path without external requests.
- `WI-030-S02`: verify destination, send the approved finance-free test message and activate the bounded canary.
- `WI-030-S03`: activate and stabilize the production-value Telegram alert experience after the MS-002 readiness audit (`in_progress`).

## Evidence

- 2026-09-03 S03 real-use activation passed. PR `#43` merged as master `fe61625`; GitHub Actions run `33652147678`
  activated `rc-2026-09-03.1` with presentation `production-value-v1` after verifying 18 provider-confirmed S02 sends.
  Activation execution `kis-portfolio-wi030-s03-q87wm` succeeded and append-only replaced the S02 canary approval.
  All three core Jobs use digest `sha256:791da9af703524f4e4579219f9aeddeac2c271aa9b17b63d09512f6d03faf9eb`
  with delivery `true`, canary producer `false` and real-use producer `true`; all three weekday Schedulers remain enabled.
  First production-value scheduled receipt and stabilization observations are pending.
- 2026-09-01 first scheduled execution `kis-portfolio-owned-core-v2-1000-6tnkp` ran from 10:00:03 to 10:18:57 KST.
  It evaluated `kr-1000` and `us-close`, produced 21 canary candidates, attempted 8 eligible Telegram deliveries and
  received 8 provider message IDs with zero unknown/retryable/permanent failures. The owner confirmed the portfolio
  alerts in the intended `wyott_bot` private conversation after switching from a Wi-Fi network that left Telegram in
  `연결중` state to LTE.
- Incident mitigation temporarily disabled Telegram delivery/canary on all three core Jobs without stopping collection
  or DB-only shadow. A GCP-side hashed probe confirmed pinned Secret v1 resolves to `wyott_bot`, the configured private
  chat and the recent `/start` chat. The flags were restored to `true` after owner receipt, and the ephemeral probe Job
  was deleted. Detail: `docs/operations/wi-030-scheduled-delivery-2026-09.md`.
- GitHub Actions run `33454254322` deployed master SHA `17a085a` and one image digest to the activation Job and all
  three V2 core Jobs. Activation execution `kis-portfolio-wi030-s02-gt9g4` completed 1/1 successfully at
  2026-09-01 09:21 KST; delivery and canary flags are `true`, destination alias is non-secret, and both Telegram
  secret references are pinned to version `1`.
- 2026-09-01 destination setup confirmed exactly one private chat, created pinned chat-ID secret version `1` and sent
  the approved finance-free test message. Raw token, chat ID and Telegram response body were not recorded.
- GitHub Actions run `33453713586` built master SHA `760e2ad` successfully but stopped before activation because the
  least-privilege deployment identity cannot mutate Secret Manager IAM. Both resource-level accessor bindings were
  pre-provisioned by the owner operator; the deploy target was corrected to consume, not grant, those permissions.
- WI-030-S01 closed: disabled-by-default adapter, renderer, owner-approval query/claim gate, bounded orchestration and
  Secret Manager allowlist are implemented.
- S01 contract and S02 checklist: `docs/design/wi-030-telegram-delivery-contract.md`.
- Focused tests cover disabled/missing configuration, redaction, approval/revocation, success hash, explicit retry,
  terminal timeout and expired-claim ambiguity. No real Telegram client, token, chat ID or external request was used.
- `tests/test_telegram_delivery.py`: 13 passed.
- `bash scripts/check.sh quick`: passed with 54 tracked Work Items, zero active implementation WIP and 114 governed
  contracts.
- S03 release gate: focused 68 passed; `bash scripts/check.sh full`: 449 passed with one third-party Authlib
  deprecation warning.

## Closeout

- Result: S01 is closed; S02 evidence is preserved and its external approval is revoked; S03 is deployed in real-use
  stabilization under DEC-051.
- Remaining risk: live production-value receipt, false-positive/miss review, duplicate suppression and owner acceptance
  are not yet proven. Episode drawdown and KRW valuation-change contribution remain explicit `계산 보류` until their
  upstream governed readiness passes.
- Follow-up Work Item: next milestone baseline after owner review.
