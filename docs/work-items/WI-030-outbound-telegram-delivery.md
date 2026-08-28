---
id: WI-030
title: Enable approved outbound Telegram delivery
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-007, V2-ADR-012
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

The approved proactive channel is Telegram, but external sending must wait for replay, shadow, destination ownership,
redaction and owner-approved test-message gates.

## Classification and contract

- `change` implementing V2-W0508. This is the shifted, still-unfinished Telegram milestone item; WI-017 remains ETF routing.
- Outbound-only `sendMessage`; no inbound command, journal or order surface.

## Scope

- Include destination verification, redacted rendering, one finance-free test message, retry/unknown outcome and flag activation.
- Exclude inbound bot commands and any order capability.

## Acceptance criteria

- [ ] owner approves rule version, private destination and finance-free test message.
- [ ] account numbers, absolute total assets, credentials, raw source and chat ID never enter payload/log analytics.
- [ ] 10:00, 14:30 and 16:00 KST slots send only `주의` or higher and preserve de-duplication.
- [ ] uncertain post-send timeout is `UNKNOWN` and is not automatically resent.

## Change impact

- External-send gate and secret/IAM review are mandatory; delivery flag rollback is immediate.

## Plan

1. Verify Secret Manager metadata and destination ownership without logging values.
2. Run separately approved finance-free test message.
3. Enable delivery only after WI-029 acceptance and record operational evidence.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed; external send is not authorized by this planning record.
- Remaining risk: destination and transport failure handling must be live-tested.
- Follow-up Work Item: next milestone baseline after owner review.
