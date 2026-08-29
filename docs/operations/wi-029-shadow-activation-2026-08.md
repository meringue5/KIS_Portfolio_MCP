# WI-029 DB-only shadow activation evidence — 2026-08-28

## Decision boundary

- ETF constituent collection and look-through are deferred from initial V2 under DEC-049 / ADR-024. ETF holdings
  remain opaque listed instruments during replay and shadow evaluation.
- This activation cannot send Telegram messages. The deployed rule version is `shadow`, the runtime has no Telegram
  adapter or secret, and the verification Job receives only the MotherDuck token plus private GCS access.
- The three existing scale-to-zero portfolio Jobs are reused. No always-on service or additional scheduler was added.

## Release and execution

| Evidence | Result |
| --- | --- |
| merge | PR #26, merge commit `e9909220af9b8c43c27c06486c4396acf5a3d0ae` |
| deployment | GitHub Actions run `33180964201`, success in 5m28s |
| immutable image | `sha256:a766382c886614d628271ed9a9f995652d8658df0618f14d2e6f35c93ee23aba` |
| initial morning execution | `kis-portfolio-owned-core-v2-1000-46dfx`, completed |
| verification execution | `kis-portfolio-wi029-s04-verify-nqnl4`, completed |
| schedules | 10:00, 14:30 and 16:00 KST weekdays, all enabled |

The repeatable evidence closeout merged as PR #27 at
`2bf17859521308b946a70c616bb948c9000f8c84` and deployment run `33182018996` succeeded in 4m49s. It deployed
immutable image `sha256:c1bee7d983deec8586a361265f2b1935088aad5750a0be407e9b49870b922a43`; final verification execution
`kis-portfolio-wi029-s04-verify-jlvt6` completed.

The initial morning run reused the already completed governed core partition and performed only the newly needed
classification and shadow composition. It made 36 core source calls and 8 bounded classification calls.

## Aggregate live result

| Check | Result |
| --- | ---: |
| held overseas instruments examined | 4 |
| official-reference classifications resolved | 4 |
| unresolved classifications | 0 |
| evaluated slots | `kr-1000`, prior `us-close` |
| candidates | 18 |
| quality-suppressed candidates | 18 |
| state transitions | 0 |
| shadow dispatch claims | 0 |
| external sends | 0 |

No account number, holding symbol, absolute asset value or confidential source payload is copied into this evidence.

## Recovery and transport proof

- Migration `0013` was required before the three runtime Jobs were updated.
- The post-migration backup exported 58 governed tables and one index object, uploaded and downloaded all 59 objects,
  and restored all 58 tables into a fresh DuckDB database.
- Initial backup index SHA-256:
  `2d3f7ba00b4fbccf65f33cb3b2901395634c7cb746d8a46ad5241eb0b038b418`.
- The final backup, after persisting calibration and shadow controls, also round-tripped 59 objects and restored 58
  tables. Its index SHA-256 is `b4f9b9ccd99d0a0b1292288276e13ebebb4d73aca87e2a5cd3d00440ba4d0a0f`.
- Verification found zero `external` alert rule versions and zero Telegram dispatch claims.

## Observation window

The immutable replay report hash remains
`a9048d06d758d5923899f15f2a6a034e9bb5f2b7e9efc2844706df6ebf13dc8d` for the bounded
2023-08-28 through 2026-08-27 reconstructed window. MotherDuck contains exactly one `draft` calibration row with
that hash and exactly one `collecting` shadow window for 2026-08-28 through 2026-09-10 inclusive. Its initial state is
2 observed session keys, 18 candidates, 18 quality suppressions and zero external sends. S05 may not verify the window
before 14 elapsed calendar days, governed-session reconciliation, zero-send proof and explicit owner
false-positive/miss review.

## S05 coverage-collector rollout

On 2026-08-30, PR #29 was merged at `20c9f437dac174323a86a3a86ee5558d4c86abad` after its PR and `master` CI
completed. Deployment run `33261574130` then rebuilt one immutable image
`sha256:77b3694ce009ba157914c021c3f55243176a182a5b8ed291f15deb12739ba940` and deployed it to the three existing
fixed-argument V2 core Jobs (`1000`, `1430`, `1600`). The Jobs carry `deploy-source=github-actions`,
`deploy-target=v2-core-batch`, the merge SHA and that GitHub run ID as deployment labels.

This rollout does not change schedules, credentials, provider calls or the shadow-only transport boundary. It adds a
MotherDuck-only evidence refresh after each successful shadow evaluation and a manual
`kis-portfolio-batch review-wi029-s05` read/recompute operation. Its expectation is derived from complete KRX
calendar rows and due Korean evaluation slots, then reconciled independently against candidates. No Job was executed
for this rollout because the deployment occurred on a KRX-closed weekend day; the next governed scheduled execution
will produce the first updated S05 evidence. Any already missed slot remains visible as missing and cannot be
backfilled as a production observation.
