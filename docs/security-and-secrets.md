# Security and Secrets

이 문서는 KIS Portfolio Service의 인증, 시크릿, 토큰 관리 원칙과 현재 source of truth를 한곳에 모은다.
배포 절차는 `docs/deployment.md`, DB/백업 절차는 `docs/backup.md`, 장기 아키텍처 결정은 `SPEC.md`와
`ARCHITECTURE.md`를 참고한다.
DB 객체의 전체 목록, logical layer, grain과 sensitivity 등급은 `docs/data-catalog.md`가 관리한다.
이 문서는 그중 Security schema 대상 객체의 암호화·회전·접근 경계를 소유한다.

## 기본 원칙

- Provider가 발급한 장기 credential은 DB에 저장하지 않는다. KIS app secret, MotherDuck token,
  OAuth provider secret, Cloud/GitHub credential은 runtime env 또는 플랫폼 secret store로만 주입한다.
- 서비스가 런타임에 발급받는 단기 토큰만 DB에 저장할 수 있다. KIS API access token은 암호화 ciphertext로,
  MCP OAuth access/refresh token과 authorization code는 digest로만 저장한다.
- raw token과 app secret은 로그, analytics table, MCP 응답, issue/PR 본문에 넣지 않는다.
- 전체 계좌번호는 운영 DB row와 백업에 포함될 수 있으므로 민감 데이터로 취급한다. 로그와 MCP 계좌
  메타데이터에서는 마스킹한다.
- 운영 DB는 MotherDuck이다. `KIS_DB_MODE=motherduck`에서 `MOTHERDUCK_TOKEN`이 없으면 실패해야 하며,
  조용히 local DuckDB로 fallback하지 않는다.
- 로컬 개발의 source of truth는 `.env`이고, `.env`는 커밋하지 않는다.
- 현재 CI/CD의 운영 secret source of truth는 GCP Secret Manager다. GitHub Actions에는 Workload Identity
  Federation credential과 비시크릿 vars만 둔다.
- GitHub Environment secret `KIS_DEPLOY_ENV`는 deprecated migration artifact다. 새 workflow에서는 사용하지 않는다.

## 현재 V1과 승인된 V2 목표

현재 runtime은 아래 inventory와 같이 MotherDuck에 encrypted KIS token cache와 OAuth digest state를 저장하고,
Secret Manager의 개별 secret resource를 `latest` version으로 주입한다. 이는 migration 전까지 유효한 V1
운영 계약이다.

2026-08-28 승인된 V2 security plane은 다음과 같다. 이 결정은 목표 architecture이며 아직 secret 재구성,
Firestore 활성화 또는 token migration을 수행하지 않았다.

- 장기 credential과 cryptographic key의 SSOT는 GCP Secret Manager다.
- Secret Manager는 `KIS provider`, `OAuth providers`, `OAuth server keyring`, `Warehouse access`,
  `Token encryption keyring`, `Notification`의 신뢰경계별 최대 6개 bundle을 목표로 한다. 하나의
  mega-secret으로 합치지 않는다.
- release manifest는 `latest` 대신 숫자 secret version을 pin하고, runtime은 필요한 bundle만 시작 시 읽어
  process memory에 cache한다.
- rotation의 previous version은 7일 rollback window 동안 disable하고 검증 뒤 destroy한다.
- OAuth digest, encrypted KIS token cache, lease와 run request는 Seoul의 Firestore Standard database 하나에
  저장한다. database IAM 위에 identity별 application collection allowlist와 negative test를 둔다.
- auth와 pipeline에는 서로의 복호화 key를 주지 않는다. MotherDuck은 V2에서 분석 사실과
  `bronze/silver/gold/control`만 소유한다.

실제 secret payload를 bundle로 옮기는 작업은 별도 security/provisioning Work Item과 rollback rehearsal 뒤에
수행한다. 그 전에는 아래 V1 inventory와 rotation runbook이 현재 운영 절차다.

### 2026-08-28 V2 state foundation inventory

- project `grand-forge-279904`에는 기존 `(default)` `DATASTORE_MODE` database가
  `asia-northeast3`에 있고 free tier를 사용한다. 이 database는 변경·삭제하지 않는다.
- 합의한 Firestore Native state plane은 named database `kis-portfolio-state`로 같은 서울 region에 생성했다.
  Standard edition, delete protection enabled, PITR/managed backup/TTL deletes disabled다.
- named database는 free quota 대상이 아니지만 생성 고정비는 없고 read/write/storage 실제 사용량만
  과금된다. 1인 앱의 token·lease·run request만 저장하고 월 50,000원 비용 gate를 적용한다.
- `scripts/bootstrap_firestore_state.py`가 non-secret `system_config/state-schema-v1` marker와 transactional
  lease fencing을 검증했다. collection allowlist는 `auth_users`, `auth_identities`, `oauth_clients`,
  `oauth_grants`, `oauth_codes`, `oauth_tokens`, `kis_token_cache`, `leases`, `run_requests`, `system_config`다.
- Secret Manager API와 기존 KIS Portfolio secret entity는 이미 존재하므로 중복 생성하거나 secret 값을
  읽지 않았다.

근거: [Firestore database 관리](https://cloud.google.com/firestore/docs/manage-databases),
[Firestore 가격과 named database](https://cloud.google.com/firestore/pricing).

## Trust Boundaries

- Local developer machine: `.env`, local DuckDB, legacy `var/tokens/token_{CANO}.json` migration input을 가진다.
- GitHub Actions: WIF로 Google Cloud에 인증하고, 비시크릿 vars와 Secret Manager reference로 Cloud Run 배포 스크립트를 실행한다.
- Cloud Run auth service: MCP OAuth authorization server다. owner login, consent, token issuance를 담당한다.
- Cloud Run remote service: MCP resource server다. OAuth bearer token을 검증하고 KIS 조회 tool을 실행한다.
- Cloud Run batch job: 예약 수집 job이다. KIS/MotherDuck runtime env를 사용하지만 MCP OAuth client token은 쓰지 않는다.
- MotherDuck: 현재 V1 운영 데이터베이스다. portfolio data, encrypted KIS token cache, OAuth digest state를
  저장한다. 승인된 V2에서는 분석 plane만 맡는다.
- KIS Open API: app key/secret으로 KIS API access token을 발급한다.
- Claude/ChatGPT clients: MCP OAuth access token을 bearer로 보내고 refresh token을 클라이언트 쪽에 보관한다.

## Secret Inventory

| Name or pattern | Source of truth | Runtime consumer | DB storage | Stored form | Rotation notes |
| --- | --- | --- | --- | --- | --- |
| `KIS_APP_KEY_{ACCOUNT}` | KIS developer console, local `.env`, GCP Secret Manager | local MCP, remote, batch | No | env/secret manager only | Update `.env`, sync Secret Manager, redeploy. Cache key includes app key, so new keys create new KIS token cache rows. |
| `KIS_APP_SECRET_{ACCOUNT}` | KIS developer console, local `.env`, GCP Secret Manager | local MCP, remote, batch | No | env/secret manager only | Update `.env`, sync Secret Manager, redeploy. Clear stale KIS token cache if the old secret is revoked before token expiry. |
| `KIS_CANO_{ACCOUNT}` | User account records, local `.env`, GCP Secret Manager | local MCP, remote, batch | Yes, in portfolio/order rows | Account id in operational data | Treat as sensitive. MCP account metadata must mask it, but DB snapshots and backups may contain full account ids. |
| `KIS_ACNT_PRDT_CD_{ACCOUNT}` | User account records, local `.env`, GitHub vars/Cloud Run env | local MCP, remote, batch | Yes, in order/canonical rows where needed | Product code | Needed for IRP/pension API routing and order identity. |
| `MOTHERDUCK_TOKEN` | MotherDuck console, local `.env`, GCP Secret Manager | local MCP, auth, remote, batch, backup | No | env/secret manager only | Rotate in MotherDuck, sync Secret Manager, redeploy all services/jobs. |
| `MOTHERDUCK_DATABASE` | Config | local MCP, auth, remote, batch, backup | No | env only | Not secret, but must match across auth and remote. |
| `KIS_TOKEN_ENCRYPTION_KEY` | Generated Fernet key, local `.env`, GCP Secret Manager | local MCP, remote, batch | No | env/secret manager only | Protect carefully. Rotation requires re-encrypting or deleting `kis_api_access_tokens`; otherwise cached KIS tokens become unreadable. |
| KIS API access token | KIS token endpoint response | local MCP, remote, batch | Yes | encrypted `token_ciphertext` in `kis_api_access_tokens` | Automatically refreshed when expired or near expiry. Never log or return raw token. |
| `KIS_AUTH_TOKEN_PEPPER` | Generated secret, local `.env`, GCP Secret Manager | auth and remote | No | env/secret manager only | Must be identical on auth and remote. Rotation invalidates existing OAuth token digests unless users reconnect. |
| MCP OAuth access token | auth server generated value | Claude/ChatGPT bearer requests | Yes | digest only in `oauth_tokens` | Short-lived. Raw value is not recoverable from DB. |
| MCP OAuth refresh token | auth server generated value | Claude/ChatGPT token refresh | Yes | digest only in `oauth_tokens` | Rotated on refresh. Pepper rotation or expiry requires connector reauthorization. |
| OAuth authorization code | auth server generated value | OAuth code exchange | Yes | digest only in `oauth_authorization_codes` | One-time use and short-lived. |
| OAuth dynamic client secret | auth server generated value | ChatGPT dynamic client token endpoint | Yes | hash in `oauth_clients` | Raw value is returned once to client and not recoverable from DB. |
| `KIS_AUTH_CLAUDE_CLIENT_ID` | Local `.env`, GitHub vars/Cloud Run env | auth server, Claude static client | Yes | `client_id` in `oauth_clients` | Not secret by itself. Keep stable unless recreating the Claude app/client. |
| `KIS_AUTH_CLAUDE_CLIENT_SECRET` | Local `.env`, GCP Secret Manager | auth server, Claude static client | Yes | hash in `oauth_clients` | Sync Secret Manager and redeploy auth. Existing client configuration must use the new secret. |
| `KIS_AUTH_SESSION_SECRET` | Generated secret, local `.env`, GCP Secret Manager | auth server browser session | No | env/secret manager only | Rotation invalidates pending browser login sessions, not already issued OAuth tokens. |
| `KIS_AUTH_OWNER_EMAILS` | Local `.env`, GCP Secret Manager | auth server allowlist | Yes | auth user rows may store email/profile | Treat as personal data. Controls who may authorize MCP access. |
| `KIS_OAUTH_GOOGLE_CLIENT_ID/SECRET` | Google Cloud OAuth app | auth server | No | ID in env, secret in Secret Manager | Rotate in Google Cloud, sync Secret Manager for the secret, redeploy auth. |
| `KIS_OAUTH_GITHUB_CLIENT_ID/SECRET` | GitHub OAuth app | auth server | No | ID in env, secret in Secret Manager | Rotate in GitHub, sync Secret Manager for the secret, redeploy auth. |
| `KIS_REMOTE_AUTH_TOKEN` | Generated secret, GCP Secret Manager | remote bearer fallback only | No | env/secret manager only | Bearer mode is for experiments. Rotate token and update clients together. |
| `KIS_DEPLOY_ENV` | Deprecated GitHub Environment secret | None in current workflow | No | Deprecated GitHub secret | Do not add back to workflow. Remove after Secret Manager deployment is verified. |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | GitHub Environment secret | GitHub Actions auth | No | GitHub secret | Deployment control plane credential/config. Keep scoped to this repository/environment. |
| `GCP_SERVICE_ACCOUNT` | GitHub Environment secret or var | GitHub Actions auth | No | GitHub secret/var | Not a password, but grants deployment authority through WIF. Keep least-privilege IAM. |

## Runtime Env vs DB State

Runtime env is the source of truth for long-lived provider credentials and encryption/digest secrets. DB state is the
source of truth for service-issued state: portfolio snapshots, KIS token cache rows, OAuth grants, OAuth token digests,
dynamic OAuth client metadata, and identity allowlist results.

Do not move provider secrets into MotherDuck. MotherDuck can hold encrypted or hashed service-issued tokens, but it
must not become the store for KIS app secrets, MotherDuck token, OAuth provider secrets, or encryption/pepper keys.

## Token Storage Model

KIS API token cache:

- Table: `kis_api_access_tokens`
- Key: `sha256("{KIS_ACCOUNT_TYPE}:{KIS_CANO}:{KIS_APP_KEY}")`
- Sensitive value: KIS access token
- Stored value: Fernet-encrypted `token_ciphertext`
- Required env: `KIS_TOKEN_ENCRYPTION_KEY`
- Shared consumers: local MCP, Cloud Run remote, and batch use the same cache key and common token manager
- Expiry policy: compare KIS wall-clock timestamps in `Asia/Seoul` and refresh from `expires_at - 10 minutes`
- Refresh ownership: whichever consumer refreshes first upserts the shared row; later cold starts reuse that ciphertext
- Legacy migration input: `var/tokens/token_{CANO}.json`, then delete the file after migration

MCP OAuth state:

- Tables: `auth_users`, `auth_identities`, `oauth_clients`, `oauth_grants`, `oauth_authorization_codes`, `oauth_tokens`
- Access/refresh tokens: digest only, using `KIS_AUTH_TOKEN_PEPPER`
- Authorization codes: digest only, one-time use
- Client secrets: hash only
- Required env shared by auth and remote: `KIS_AUTH_TOKEN_PEPPER`
- Required OAuth scope for MCP: `mcp:read`
- `offline_access` should be advertised so clients can keep refresh-token based sessions

## Backups

Default Parquet backups exclude OAuth state tables and `kis_api_access_tokens`. Backups can still contain account ids,
holdings, order history, and portfolio values, so treat backup folders as sensitive data.

Do not commit `var/backup`, local DuckDB files, legacy token files, or exported Parquet snapshots. Store off-machine
backups only in private locations with access controls.

## Logging and MCP Responses

- MCP account metadata should return masked account numbers only.
- Token status tools may return storage, expiry, and health metadata, but must not return token values.
- Exceptions and logs should avoid raw request headers, `authorization`, app secret, KIS access token, OAuth token,
  MotherDuck token, and full account numbers.
- Order tools remain disabled stubs until separate audit/confirmation and permission boundaries are designed.

## Rotation Runbook

1. Rotate the upstream secret in its provider console when applicable.
2. Update local `.env` for manual/local usage.
3. Run `uv run python scripts/sync_secret_manager.py --project grand-forge-279904` and review the dry-run mapping.
4. Run `uv run python scripts/sync_secret_manager.py --project grand-forge-279904 --apply`.
5. Redeploy affected targets through the GitHub Actions production deployment workflow.
6. Verify `/health`, OAuth discovery, token exchange or refresh, and a read-only MCP tool call.

Special cases:

- Rotating `KIS_TOKEN_ENCRYPTION_KEY` requires re-encrypting or clearing `kis_api_access_tokens`.
- Rotating `KIS_AUTH_TOKEN_PEPPER` forces MCP clients to reconnect because existing OAuth token digests cannot be
  recomputed.
- Rotating `KIS_AUTH_SESSION_SECRET` only invalidates browser login sessions and pending auth flows.
- Rotating KIS app keys/secrets may require deleting affected KIS token cache rows if old tokens continue to fail.

## Incident Response

If a long-lived provider secret leaks:

1. Revoke or rotate it at the provider first.
2. Update `.env` and sync GCP Secret Manager.
3. Redeploy every target that consumes it through GitHub Actions.
4. Clear or invalidate derived token rows when needed.
5. Check Secret Manager audit logs, GitHub Actions logs, Cloud Run logs, local shell history, and backups for accidental exposure.

If a DB-stored derived token leaks:

- KIS access token ciphertext alone should not be usable without `KIS_TOKEN_ENCRYPTION_KEY`, but rotate the KIS API
  token cache if key exposure is possible.
- OAuth token digests are not bearer tokens, but rotate `KIS_AUTH_TOKEN_PEPPER` and force reconnect if pepper exposure
  is possible.
