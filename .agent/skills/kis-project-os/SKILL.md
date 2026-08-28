---
name: kis-project-os
description: Use for non-trivial KIS Portfolio repository changes, bug triage, requirement or ADR changes, work-item delivery, incident follow-up, and governance updates so decisions, implementation, evidence, and acceptance remain traceable.
---

# KIS Project Operating System

Use this Skill before mutating the repository or classifying a non-trivial product/operations issue.

## Canonical Policy

Read `docs/governance/project-operating-system.md`. It owns the workflow, document authority, change taxonomy,
ADR gate, WIP limit and evidence rules. Do not copy those policies into this Skill or infer a new policy from code.

Also read:

- `docs/traceability.md` for current work and decision links.
- The active `docs/work-items/WI-*.md`, if one exists.
- The specialized Skill selected by the change: architecture, warehouse, MCP surface, API capability or release ops.

## Workflow

1. Capture evidence and compare the reported behavior with approved requirements, ADRs and owned contracts.
2. Classify the work. Do not call a requested behavior change a defect merely because the user dislikes current behavior.
3. For repository mutation, create or activate one Work Item and add its traceability row before substantive edits.
4. Decide whether product decisions require explicit user approval. Read-only investigation may continue while approval is pending.
5. Make the smallest coherent change set that updates every affected owner document and executable contract together.
6. Run `bash scripts/check.sh quick` during work and `bash scripts/check.sh full` before closeout.
7. Record actual evidence, remaining risk and follow-up work. Mark the item closed only when its acceptance criteria are met.

## Constraints

- A ticket tracks the journey; approved DEC/ADR/catalog documents own decisions.
- Never weaken a contract merely to make a failing check pass.
- Skills and hooks call the shared harness; they do not reimplement its checks.
- Preserve secrets, account identifiers and raw tokens outside Issues, Work Items, logs and responses.
- Deployment, infrastructure, destructive data work and external messages still require their normal authorization.
- If another Work Item is already `in_progress`, finish, block or explicitly supersede it before starting implementation.
