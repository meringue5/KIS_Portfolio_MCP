# WI-071 observed cash history

Approved 2026-10-30: prioritize the amount observed and record dated changes with unknown causes, retaining
available confirmed trade context. Owner-described funding/RP activity is a possible explanation, not evidence
for a particular ledger row. No complete cash-flow or performance claim.

## Behavior

Exact dataset: `dataset.cash-observation-history` through existing get-data-quality. Runtime flag:
`KIS_CASH_OBSERVATION_HISTORY_ENABLED` (default false). Existing tool/scope list and deferred-only reconciliation
are preserved. Owner explicitly authorized protected release and self-verification through actual MCP on 2026-10-30.

`latest` always includes six reviewed scopes: five KRW and brokerage USD. Every last-known balance has its actual
observation time, age and source-basis warning. Missing is null/unavailable, never zero. Source legacy normalization
uses provisional KRW valuation residuals and an unresolved foreign deposit/withdrawable fallback; these are
observations, not certified settled cash. This extension does not silently change canonical balances.

`results` reconstructs existing immutable normalized Bronze payloads visible at both observation and recording
cutoff. Same-basis previous observation yields an exact decimal-string change; baseline/ambiguous input yields
null. Discovery date is in Asia/Seoul, not actual posting date. Every cause remains unknown, even if the pattern
looks like owner funding, RP purchase/redemption, or a trade. At most ten confirmed execution-period trade rows
are shown as context, never subtracted to claim settled effects. Pre-interval trades that later settle can remain
unlinked. Source gaps, old zero suppression and incomplete trade coverage are explicitly not repaired by absence.

31-day source cap, 100 observations per page, snapshot-bound query cursor, 10,000-source-record safety cap and
256-KiB envelope. No new physical table/migration, provider/schedule, warehouse write or Telegram replay. Existing
Bronze backups retain inputs so history is rebuildable. Do not delete or rewrite prior evidence.

## Verification

12 focused tests cover zero/missing distinction, RP-like 100→0→100 observations, absent scopes, old recording
cutoff, late arrival/snapshot pagination, ambiguity, malformed numbers/floats, negative fractional cash, bounded
trade context without cash inference, disabled route, read scope, positive/partial/error. Full shared gates:
971 passed, one existing Authlib deprecation warning.

Protected activation uses target wi071: enable the new history flag on Remote, retain the existing deferred
reconciliation flag, reuse immutable image/backup/preservation checks and promote both Remote routes together.
No new schema is required; the current 0023 prefix is retained. Runtime failure rollback restores prior traffic
and exact Job definitions. Disabling the history flag alone disables the new read. Actual MCP scenarios cover
positive latest/change reads, absent producer partial, old/baseline history, invalid bounds/cursor, stable paging,
unaffected existing diagnostics and quality. No synthetic cash rows are inserted into production.

Actual-client results remain private until separately authorized for publication; release/test success cannot
establish completeness of cash or RP history or owner acceptance.

## RP evidence boundary

KIS public website provides RP/foreign-RP transaction inquiry. This establishes a broker UI capability, not the
availability/completeness of an API for the owner's auto-trading subscription/redemption events:
https://securities.koreainvestment.com/main/mall/openptrade/FundTrade07.jsp?cmd=mainPage
No instruction to install/check HTS or supply a statement is required for this observed-history implementation.
