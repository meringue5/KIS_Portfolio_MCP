---
name: kis-data-governance
description: Use when proposing or changing a data source, collection basket, dataset, metric, pipeline, quality rule, lineage, retention, sensitivity, or governed data lifecycle in KIS Portfolio.
---

# KIS Data Governance

Use this Skill before data-contract design or any implementation that changes what is collected, published, measured,
retained, exposed, or retired.

## Canonical policy

Read `docs/governance/data-governance-harness.md` completely. It owns authority, lifecycle, gates and exception policy.
Read `governance/contract-schema.toml` for the machine contract and the relevant file under
`governance/catalog/`. For physical warehouse work, also use the Warehouse Contract Skill and read
`docs/data-catalog.md`.

## Workflow

1. Identify the affected source, collection, dataset, metric and pipeline IDs and compare their current contracts.
2. Register a proposed contract before adapter, DDL, schedule, backfill, metric or MCP implementation.
3. Route canonical source, SSOT, grain, key, retention, lineage, provider, security or cost changes through the
   Project OS ADR gate.
4. Update every affected manifest, physical catalog, migration/repository/backup contract and traceability link in one
   coherent change set.
5. Run the deterministic governance check:

   ```bash
   python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py
   ```

6. Use `bash scripts/check.sh quick` during work and `bash scripts/check.sh full` before closeout.

## Constraints

- Only approved or active contracts may authorize production collection, publish or official consumption.
- Do not invent source rights, freshness, quality, lineage or retention values to satisfy the checker.
- Do not put credentials, raw tokens, account identifiers or licensed payloads in manifests or evidence.
- Do not auto-adopt or delete live drift. Establish provenance, consumers, backup and owner approval first.
- A manifest or Skill never grants permission to deploy, migrate, backfill, delete data, add a paid provider or send an
  external notification.
