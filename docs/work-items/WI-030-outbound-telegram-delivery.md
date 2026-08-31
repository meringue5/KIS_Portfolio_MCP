---
id: WI-030
title: Enable approved outbound Telegram delivery
status: in_progress
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-007, V2-ADR-012, DEC-050
requirement_refs: DEC-006, DEC-026..030, DEC-038, DEC-041, DEC-044
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
- Exclude inbound bot commands and any order capability.

## Acceptance criteria

- [ ] owner approves rule version, private destination and finance-free test message.
- [ ] account numbers, absolute total assets, credentials, raw source and chat ID never enter payload/log analytics.
- [ ] 10:00, 14:30 and 16:00 KST slots send only `주의` or higher and preserve de-duplication.
- [ ] uncertain post-send timeout is `UNKNOWN` and is not automatically resent.
- [ ] canary expiry and owner revocation fail closed without changing the shadow rule or its evidence.
- [x] disabled or incompletely configured delivery fails closed before a claim or network request.

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

## Evidence

- WI-030-S01 closed: disabled-by-default adapter, renderer, owner-approval query/claim gate, bounded orchestration and
  Secret Manager allowlist are implemented.
- S01 contract and S02 checklist: `docs/design/wi-030-telegram-delivery-contract.md`.
- Focused tests cover disabled/missing configuration, redaction, approval/revocation, success hash, explicit retry,
  terminal timeout and expired-claim ambiguity. No real Telegram client, token, chat ID or external request was used.
- `tests/test_telegram_delivery.py`: 13 passed.
- `bash scripts/check.sh quick`: passed with 54 tracked Work Items, zero active implementation WIP and 114 governed
  contracts.
- `bash scripts/check.sh full`: 431 passed with one third-party Authlib deprecation warning.

## Closeout

- Result: S01 is closed; S02 is in progress under the owner-approved DEC-050 bounded-canary exception.
- Remaining risk: destination and transport failure handling must be live-tested.
- Follow-up Work Item: next milestone baseline after owner review.
