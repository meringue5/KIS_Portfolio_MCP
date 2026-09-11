# WI-045 production readiness evidence

> Date: 2026-09-11
> Scope: read-only production inventory/reconciliation/cost capture and bounded private backup/restore
> Production traffic, connector, Scheduler and source activation changes: none

## Decision

The reviewed readiness evidence passes the repository gate and is sufficient to begin WI-046. It does not itself
switch traffic: the evaluator deliberately continues to emit `production_cutover_allowed=false`, so the protected
release and owner-approved cutover record remain separate actions.

## Ten-trading-day observation

The exact 14:30 KST production runs from 2026-08-31 through 2026-09-11 provide ten unique KRX trading dates. The
same KIS calls wrote the V1 feeder snapshots before the V2 normalization/publish stages, allowing row-level comparison
without another provider call.

- configured-account coverage was 5/5 for every run;
- 220 account/instrument holding rows matched exactly on identity and quantity, with zero mismatches;
- 170 KRX adjusted OHLCV rows matched exactly, with zero mismatches;
- both V1 and V2 order surfaces contained zero orders in the observed dates;
- V1 snapshot latency was 3–5 seconds and V2 publish latency was 134–192 seconds, inside the five-minute tolerance;
- all 30 required 10:00/14:30/16:00 runs succeeded and no dispatch had more than one terminal `sent` attempt.

Two gaps remain explicit rather than being converted to false matches. V1 did not schedule a matching-slot global
total-asset materialization; its domestic API evaluation and V2 governed price revaluation differ by basis. The
legacy signal evaluator also did not run beside the V2 alert evaluator. Each session therefore records those two
dimensions as `partial` with stable reasons and missing coverage. Owner acceptance of the production V2 total-asset
report and Telegram behavior closes the observation decision, but the gaps remain residual stabilization evidence.

## Recovery

The first backup attempt correctly failed because production is at migration 0013 while the old manifest assumed the
latest 0017 catalog. WI-045-S01 replaced that assumption with manifest v3: it verifies the immutable migration ledger,
derives the exact managed table/view surface for that prefix in a scratch DB, and rejects a missing or unexpected live
table. Legacy full-surface manifest v2 remains readable.

The corrected capture exported all 58 tables belonging to migration prefix 0001–0013. It uploaded 59 content-addressed
objects (manifest plus Parquet files), 12,990,917 bytes, to the existing private recovery bucket. Exact index hash
download and a fresh in-memory restore both passed; all 58 tables restored and all version-appropriate views compiled.
Conservative evidence records RPO 30 minutes and RTO one minute, below the 24-hour and four-hour limits. Restricted raw
object bytes remain governed by their separate private object-store recovery contract and were not embedded in the
Parquet backup.

## Cost and inventory

The Google Cloud Billing report was read with the current-month, all-project scope. For September 1–9 it displayed
KRW 434 net actual and KRW 119 month-end forecast after savings. The guardrail conservatively evaluates the larger
KRW 434 value, which is below the KRW 7,500 normal-month target and KRW 50,000 hard ceiling.

The fresh inventory found two Cloud Run services, fourteen Cloud Run Jobs, six enabled Scheduler jobs and two Docker
repositories in `asia-northeast3`. Every active compute target resolved to an immutable digest. The release manifest
names all sixteen active compute targets and a target-specific rollback digest. Unchanged recovery/ingestion targets
use a no-op rollback to the same immutable digest; auth, remote and the three owner-core jobs use their prior retained
stable digest.

MotherDuck is checksum-consistent through migration 0013. The missing 0014–0017 objects are expected isolated-work
drift and must be applied by the WI-046 protected migration/release path; three pre-existing unmanaged `main` objects
and the known V1 daily-view quality-column drift are preserved, not adopted or deleted.

## Verification commands

```bash
uv run python scripts/assess_dual_run_readiness.py \
  governance/project/evidence/wi045/dual-run-observation-2026-09-11.json \
  governance/project/evidence/wi045/release-manifest-2026-09-11.json \
  governance/project/evidence/wi045/cost-snapshot-2026-09-11.json \
  --as-of 2026-09-11T09:54:11Z
```

The expected readiness status is `pass`, with ten trading days, zero unexplained differences and twenty explained
partial rows. The next Work Item is WI-046; no cleanup or V1 retirement is authorized.
