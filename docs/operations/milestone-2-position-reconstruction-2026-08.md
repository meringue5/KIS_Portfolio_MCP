# Milestone 2 — WI-022 production reconstruction evidence

## Scope and outcome

WI-022 reconstructed the governed position/lot/sell-allocation boundary without rewriting V1 history. The approved
production window was `2023-08-28T00:00:00+09:00` through `2026-08-28T18:00:00+09:00`. It contained 57 partitions,
22 current-held scopes and 282 canonical trade rows, but no passing corporate-action date-range coverage.

The correct fail-closed outcome was therefore 57 open Control review exceptions and zero Silver episode, lot or
sell-allocation projections. No KIS source call occurred.

## Failed-safe diagnosis

Runs `33161931155` and `33162598479` stopped at the exact plan gate before any reconstruction write. All aggregate
counts matched, but DuckDB rendered the same `TIMESTAMPTZ` instants using the local session timezone, so the original
hash differed between macOS/Asia-Seoul and Cloud Run/Linux-UTC. The repository had zero reconstruction rows after both
failures. A Cloud Run read-only planner confirmed the mismatch without changing the Job definition or database.

The fix canonicalized replay and persistence hash timestamps to UTC `Z` and Decimal values to scale-independent
strings. An equivalent-instant/equivalent-scale regression test pins the behavior. The reviewed canonical execution
hash is `096a01a53fdac9b5c35df13e25a1300c2df8af0c61fca4cbe29d8aa005afd50b`.

One later build attempt failed before deployment because GHCR timed out while serving the base image. The same tested
master attempt was rerun without a code or data change.

## Successful managed execution

- workflow: `33163171218`, attempt 2;
- master Git SHA: `38a376ccadb798ab086cb38de6b3753a87c0439f`;
- immutable image: `sha256:ed5ea8b8a4e4b36eaab8f9c358e1ae77c8b7980ecce6d66143be2afd38b42327`;
- Cloud Run execution: `kis-portfolio-wi022-s06-9zmm2`;
- schema: migration `0010` applied;
- first apply: 57 exception identities and 57 revisions, zero Silver rows;
- identical replay: zero inserted revisions and zero resolutions;
- live/restore reconciliation: 57 partitions, 57 open exceptions, zero episode/lot/allocation identities;
- source calls: 0;
- elapsed time: 167.48 seconds.

The private pre-backup contained 47 objects / 8,138,373 bytes with index hash `91ac88cee2d09333168e967a7358bb4a9b7c3e324fb1c413c9c93f3053c0295b`.
The post-backup contained 47 objects / 8,171,053 bytes with index hash `3ae8f818cdd829649b8cd4bbff878cdd5fad5ca3acc661c78c2f867c72172e53`.
Both were downloaded by exact hash and restored to fresh DuckDB files inside the Job. The aggregate evidence object is
private and content-addressed by `636d3846a6a6b33af844d2ed3002f332472519eb3f7e116480e612be685615cd`.

## Remaining governed boundary

These exceptions are not failed trades or asserted corporate actions. They record that absence-of-action coverage is
not yet proven. A later source activation may resolve them only through a new read-only S05 plan, a new exact hash and
a separately reviewed append-only apply. WI-023 and later metrics must not treat the exception scopes as reconstructed
Silver history before that gate passes.
