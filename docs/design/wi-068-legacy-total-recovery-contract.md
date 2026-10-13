# WI-068 — bounded legacy total reference recovery (approved)

Status: owner approved 2026-10-13; DEC-062 / ADR-033. Implementation and protected activation authorized.
Owner request: 2026-10-13 "채워봅시다", following acceptance of missing overseas cash = 0 and the bounded 27 dates.
Owner subsequently approved the exact storage/read boundary below and authorized protected production activation.

## Concrete candidate

A private local calculation has 27 dated rows: 14 recorded references, 11 estimated references, 2 unavailable totals.
25 dates are usable as labelled reference total levels; none is promoted to canonical portfolio performance.
Amounts are retained in owner-only ignored `var/recovery/wi068` JSON/review artifacts with 0700 directory/0600 files.
The tracked [sanitized calculation evidence](../../governance/project/evidence/wi068/total-recovery-candidate-2026-10-13.json)
contains dates, classifications, counts and fingerprints, not monetary values, account ids or raw source payloads.

| classification | dates (2026) |
| --- | --- |
| recorded_reference | 04-19/20/21/22/23/25/27; 05-03/14/29; 06-05/14/16/20 |
| estimated_reference | 05-04/06/11/12/16/22; 06-08; 07-24; 08-10/26/27 |
| unavailable_total | 08-06/25 |

The earlier list of 27 "recoverable dates" was a list of retained overview dates; it was not a verification that all
27 global totals could be repaired. The two unavailable dates have no overseas position observations. Missing cash
= 0 does not authorize missing positions = 0. Their recorded partial amounts are preserved and not published as totals.

## Calculation and source

- Select the latest preserved overview per its original stored date and only its linked holding rows; do not mix
  account snapshots from unrelated fetches. All 27 selected overview groups have five account labels in holdings.
- Assert recorded overview total equals the sum of non-null linked holding/cash KRW amounts. This is a consistency
  check, not a completeness/pass certificate. Preserve original aggregate, original timestamp and input SHA-256.
- Keep every existing observed KRW amount. For only foreign position rows with NULL KRW and present USD value,
  add `value_foreign × external USD/KRW`. No unobserved quantity, price, cash flow or corporate action is invented.
- Do not overwrite observed foreign cash. Only absent overseas cash may be assumed zero per owner statement.
  May 22 has no missing position valuation but is estimated because its absent cash is assumed zero.
- No overseas positions observed → candidate total NULL/unavailable. No silent zero for all overseas assets.
- External source: Federal Reserve Board H.10 via [FRED DEXKOUS](https://fred.stlouisfed.org/series/DEXKOUS), New York
  noon buying rate, KRW per USD. A dated CSV for Apr 1–Aug 27 was obtained; hash, retrieval time and used observation
  dates are retained privately. Use the latest nonmissing observation <= legacy date, maximum four calendar days.
  Original valid KRW valuations keep their original basis. This is retrospective valuation, not historic PIT knowledge.
- Every repair identifies provider, series, native rate type, requested/used dates, lag, fetched time and content hash.
  It does not masquerade as the original KIS applied FX, a Korean market close, or an official performance return.
- Source reads were SELECT-only and in one transaction, rolled back without DML/DDL. Retained `v1-latest` count/hash
  checked unchanged. WI-066 quality quarantine and native V2 values remain intact.

## Approved production boundary

Choose **owner-only noncanonical reference storage and explicit read projection**, scoped to total levels for these
25 dates. Existing V1 input and canonical V2 ledgers remain immutable. This is the reference portion of the earlier
hybrid recommendation; no broader source-fact promotion is needed for this first total-history outcome.

1. New dataset `dataset.portfolio-legacy-total-reference`, recovery version + date + input hash, append-only
   corrections/supersession. Physical target `silver.portfolio_legacy_total_reference`; DDL is migration 0021.
2. Row fields: date, original amount, reference amount, `recorded_reference|estimated_reference`, assumptions,
   input hash, knowledge/recorded time, recovery version and FX provenance. No account id or raw source locator.
   Unavailable rows may retain safe coverage reasons; reference amount stays NULL.
3. Native V2 passing state takes precedence on overlapping dates. Reference rows never overwrite or satisfy canonical
   quality, return, drawdown, alert or contribution inputs. Dataset/read-model approval does not amend WI-066.
4. Explicit opt-in on existing `get-performance-history`: `include_legacy_reference=true`, returning a
   **separate `reference_history` array** with classification/assumptions/lineage. Default canonical history remains
   unchanged. No automatic fallback to estimates and no new public tool or command.
5. Total-only grain. Account-filter requests combined with legacy references return a bounded unsupported-combination
   error, so a global total cannot be misrepresented as a filtered account total. Daily ranges/pages keep current bounds.
6. No source API calls during MCP reads. Reference data is materialized only by separately approved recovery work.
   No new always-on service, provider credential, recurring collection or notification.
7. Private Parquet backup/versioned manifest and fresh local restore must include the new physical dataset before
   production release. Rollback disables the opt-in projection/reference version and retains immutable source evidence.
8. Owner approval is recorded in DEC-062/ADR-033 and the logical/physical contracts.
   Then test idempotency, source hash, reconciliation, native precedence, NULL handling and actual Codex/Claude
   positive (25 dated references), partial (Aug 6/25 unavailable), error (account-filter combination) behavior.

## Owner decision

Owner approved the 25 dated records as **noncanonical total-level reference data**, with disclosed external FX/zero-cash
assumptions, separate append-only storage and explicit opt-in MCP projection. This is not approval to mark legacy
rows pass, overwrite native totals, interpolate absent dates, deploy unrelated Work Items or publish raw payloads.

The approved reference dataset/read model is registered separately from the existing three governance read models.
The earlier [read-model draft](wi-068-proposed-reference-read-model.toml) remains retained as investigation evidence.

Owner approved this exact boundary and requested implementation. Production applies only after protected verification gates.
