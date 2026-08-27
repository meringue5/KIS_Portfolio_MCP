# Deployment Notes

이 문서는 원격 MCP/Web 배포를 준비하기 위한 운영 원칙을 정리한다.

## 현재 상태

현재 기본 엔트리포인트는 local stdio MCP 서버다.

```bash
uv run kis-portfolio-mcp
```

Dockerfile은 이 local MCP 서버를 컨테이너에서 실행할 수 있게 하는 최소 베이스라인이다.
원격 클라이언트용 entrypoint는 `kis-portfolio-remote`이며, `/mcp` endpoint를 Streamable HTTP로 노출한다.

### 승인된 V2 배포 목표

2026-08-28 승인된 V2 기준선은 auth와 Remote MCP를 별도 service로 유지하되, commit당 한 번 만든 동일한
immutable image digest를 두 service와 managed Job에 배포한다. Remote MCP는
`stateless_http=true`·`json_response=true`를 목표로 하지만 Claude·ChatGPT·iPhone 실제 호환성 검증 뒤에만
전환한다. Secret Manager는 신뢰경계별 최대 6개 bundle과 숫자 version pin을 사용한다.

이 목표는 아직 현재 배포 절차를 바꾸지 않는다. build-once workflow, secret migration, Firestore
provisioning과 connector cutover는 각각 별도 Work Item과 rollback evidence를 필요로 한다.

## Remote MCP 인증

remote resource server는 두 가지 모드를 지원한다.

### 1. OAuth v1

ChatGPT 호환과 운영 배포의 기본 경로다. 구조는 **별도 auth server + 기존 remote MCP resource server 분리**다.

- auth server local command: `uv run kis-portfolio-auth`
- resource server local command: `uv run kis-portfolio-remote`
- `KIS_REMOTE_AUTH_MODE=oauth`
- `GET /health`는 공개
- `/mcp`는 OAuth bearer token 필수
- required scope: `mcp:read`
- resource server는 MCP OAuth discovery를 위해 다음 공개 endpoint를 제공한다.
  - `/.well-known/oauth-protected-resource`
- `/.well-known/oauth-protected-resource/mcp`
- `/.well-known/oauth-authorization-server`
- `/authorize`는 auth server `/authorize`로 redirect
- `/register`, `/token`, `/revoke`는 auth server로 proxy
- auth server는 `/.well-known/oauth-authorization-server`와 함께
  `/.well-known/openid-configuration` alias도 제공한다. 일부 클라이언트가 OIDC discovery를 먼저 probe한 뒤 OAuth metadata로 fallback하기 때문이다.
- Cloud Run auth는 기본적으로 `min-instances=0`, `max-instances=1`로 배포한다.
- Cloud Run remote는 기본적으로 `min-instances=0`, `max-instances=1`, `concurrency=20`으로 배포한다.
  Streamable HTTP 세션은 프로세스 메모리에 있고, 같은 세션에서 long-running GET과 POST가 동시에 들어오기 때문이다.
  유휴 상태에서는 scale-to-zero로 비용을 줄이고, 첫 로그인/재연결 cold start에는 `--cpu-boost`를 사용한다.
  Cloud Run 배포는 이미지에 설치된 console script를 직접 실행하며, startup path에서 `uv run`을 사용하지 않는다.

`scripts/deploy_cloud_run.py remote`는 `KIS_REMOTE_AUTH_MODE`가 비어 있으면 ChatGPT 친화 기본값으로 `oauth`를 사용한다.

리소스 서버 필수 환경변수:

- `KIS_REMOTE_AUTH_MODE=oauth`
- `KIS_TOKEN_ENCRYPTION_KEY=...`
- `KIS_AUTH_ISSUER_URL=https://...`
- `KIS_RESOURCE_SERVER_URL=https://...`
- `KIS_AUTH_REQUIRED_SCOPES=mcp:read`
- `KIS_AUTH_ALLOWED_SCOPES=mcp:read offline_access` (선택, 기본값 동일)
- `KIS_AUTH_TOKEN_PEPPER=...`

auth 서버 필수 환경변수:

- `KIS_AUTH_BASE_URL=https://...`
- `KIS_AUTH_OWNER_EMAILS=owner@example.com`
- `KIS_AUTH_SESSION_SECRET=...`
- `KIS_AUTH_TOKEN_PEPPER=...`
- `KIS_AUTH_ALLOWED_SCOPES=mcp:read offline_access` (선택, 기본값 동일)
- `KIS_AUTH_CLAUDE_CLIENT_ID=...`
- `KIS_AUTH_CLAUDE_CLIENT_SECRET=...`
- `KIS_OAUTH_GOOGLE_CLIENT_ID/SECRET`
- `KIS_OAUTH_GITHUB_CLIENT_ID/SECRET`

ChatGPT connector 호환 추가사항:

- auth server discovery에 `registration_endpoint` 포함
- auth discovery에 `offline_access`를 광고해 refresh token 유지 경로를 연다
- `POST /register` dynamic client registration 지원
- authorize/token에서 `resource` parameter를 저장하고 access token에 bind
- 기본 dynamic redirect 허용 prefix:
  - `https://chatgpt.com/connector/oauth/`
  - `https://chatgpt.com/connector_platform_oauth_redirect`
- 필요하면 `KIS_AUTH_DYNAMIC_CLIENT_REDIRECT_PREFIXES`로 override 가능

ChatGPT connector 등록 시 app-level metadata 권장값:

- Connector name: `KIS Portfolio`
- Description: `Use this app when you need Korean Investment & Securities (KIS) portfolio balances, total asset allocation, cached price history, exchange-rate history, or saved portfolio analytics for configured accounts. Prefer refresh-all-account-snapshots for the latest cross-account portfolio refresh and get-total-asset-overview for the combined domestic and overseas asset view. Do not use this app for internet news, general market research, or live order placement; order tools are disabled stubs.`
- MCP tool metadata를 바꾼 뒤에는 ChatGPT Settings에서 connector `Refresh`를 눌러 frozen snapshot을 갱신한다.

### 2. Bearer fallback

빠른 실험용 호환 모드다. ChatGPT 배포 기본값으로는 권장하지 않는다.

- `KIS_REMOTE_AUTH_MODE=bearer`
- 필수 환경변수: `KIS_REMOTE_AUTH_TOKEN`
- 클라이언트 요청 헤더: `Authorization: Bearer <token>`
- `GET /health`는 공개
- `POST /mcp`는 인증 필수

`KIS_AUTH_TOKEN_PEPPER`는 auth server와 resource server 양쪽에 같은 값이 들어가야 한다.
opaque token을 DB에 digest로 저장하고 resource server가 같은 방식으로 검증하기 때문이다.

token/revoke endpoint는 `client_secret_basic`과 `client_secret_post`를 모두 받는다.
Claude static client는 basic을, ChatGPT dynamic client는 post를 사용해도 되도록 메타데이터를 맞춘다.

`KIS_TOKEN_ENCRYPTION_KEY`는 remote/local KIS 조회 런타임에서 공통으로 필요하다. KIS API access token을
MotherDuck/local DuckDB의 `kis_api_access_tokens` 테이블에 암호화해 저장하기 때문이다. 일반적인 코드
재배포만으로는 Claude/ChatGPT connector를 다시 연결할 필요가 없지만, 이미 열려 있던 MCP transport/session은
끊기고 다음 호출에서 새 세션을 잡는다.

`/healthz`는 Cloud Run에서 예약 경로와 충돌할 수 있으므로 운영 경로로 사용하지 않는다.

`KIS_REMOTE_AUTH_DISABLED=true`는 로컬 터널 실험에만 사용한다. 운영 배포에서는 사용하지 않는다.

## Secret 원칙

시크릿과 토큰 관리의 canonical policy는 [Security and Secrets](./security-and-secrets.md)를 따른다.
이 문서는 배포에 필요한 환경변수와 절차만 다룬다.

배포 시 특히 지켜야 할 원칙:

- KIS API key, app secret, 계좌번호, MotherDuck token은 이미지에 포함하지 않는다.
- 장기 credential은 runtime env 또는 플랫폼 secret store로만 주입한다.
- 서비스가 발급받은 KIS access token은 DB에 암호화 저장할 수 있고, MCP OAuth token은 DB에 digest로만 저장한다.
- raw token과 app secret은 로그, analytics table, MCP 응답에 포함하지 않는다.
- 전체 계좌번호는 운영 DB row와 백업에 포함될 수 있으므로 민감 데이터로 취급하고, 로그와 MCP 계좌 메타데이터에서는 마스킹한다.
- 운영 Cloud Run secret source of truth는 GCP Secret Manager다. GitHub `KIS_DEPLOY_ENV`는 deprecated이며 새 workflow에서 사용하지 않는다.

## 추천 배포 경로

1. Claude Desktop local MCP로 실사용 기준선을 검증한다.
2. 조회-only remote MCP를 만든다.
3. Fly.io, Render, Cloud Run 중 하나에 Docker 이미지로 배포한다.
4. 주문 tool은 remote 배포 기본값에서 비활성화한다.
5. audit log, confirmation, 권한 분리 이후에만 주문 기능 노출을 검토한다.

## 컨테이너 실행 예시

```bash
docker build -t kis-portfolio .
docker run --rm -i \
  --env-file .env \
  -e KIS_DB_MODE=motherduck \
  -e MOTHERDUCK_DATABASE=kis_portfolio \
  kis-portfolio
```

stdio MCP는 표준 입출력을 사용하므로 컨테이너 테스트도 `-i`가 필요하다.

원격 MCP 실행 예시 (ChatGPT/운영 권장 OAuth):

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  -e KIS_REMOTE_AUTH_MODE=oauth \
  -e KIS_AUTH_ISSUER_URL=https://auth.example.com \
  -e KIS_RESOURCE_SERVER_URL=https://resource.example.com/mcp \
  -e KIS_AUTH_REQUIRED_SCOPES=mcp:read \
  -e KIS_AUTH_TOKEN_PEPPER=... \
  -e KIS_TOKEN_ENCRYPTION_KEY=... \
  -e KIS_DB_MODE=motherduck \
  -e MOTHERDUCK_DATABASE=kis_portfolio \
  kis-portfolio \
  uv run kis-portfolio-remote
```

원격 MCP 실행 예시 (bearer fallback):

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  -e KIS_REMOTE_AUTH_TOKEN=... \
  -e KIS_REMOTE_AUTH_MODE=bearer \
  -e KIS_TOKEN_ENCRYPTION_KEY=... \
  -e KIS_DB_MODE=motherduck \
  -e MOTHERDUCK_DATABASE=kis_portfolio \
  kis-portfolio \
  uv run kis-portfolio-remote
```

remote endpoint는 `http://localhost:8000/mcp` 또는 배포 플랫폼의 HTTPS URL에서 `/mcp`이다.

OAuth auth server 실행 예시:

```bash
docker run --rm -p 8001:8001 \
  --env-file .env \
  -e KIS_AUTH_BASE_URL=http://localhost:8001 \
  -e KIS_AUTH_OWNER_EMAILS=owner@example.com \
  -e KIS_AUTH_SESSION_SECRET=... \
  -e KIS_AUTH_TOKEN_PEPPER=... \
  -e KIS_AUTH_CLAUDE_CLIENT_ID=... \
  -e KIS_AUTH_CLAUDE_CLIENT_SECRET=... \
  -e KIS_OAUTH_GOOGLE_CLIENT_ID=... \
  -e KIS_OAUTH_GOOGLE_CLIENT_SECRET=... \
  -e KIS_OAUTH_GITHUB_CLIENT_ID=... \
  -e KIS_OAUTH_GITHUB_CLIENT_SECRET=... \
  kis-portfolio \
  uv run kis-portfolio-auth
```

Google callback URL:

- `https://<auth-service>/auth/google/callback`

GitHub callback URL:

- `https://<auth-service>/auth/github/callback`

Claude static client 기본 redirect URI:

- `https://claude.ai/api/mcp/auth_callback`
- `https://claude.com/api/mcp/auth_callback`

Cloud Run 배포 스크립트는 기본적으로 Secret Manager reference를 사용한다. 실제 운영 배포는 GitHub Actions의
`production` environment approval을 통해 실행한다. 로컬에서는 먼저 dry-run으로 command shape만 확인한다.

```bash
uv run python scripts/deploy_cloud_run.py remote --dry-run
```

스크립트는 `.env`와 현재 셸 환경을 함께 읽고, 필요한 비시크릿 값이 비어 있으면 누락된 키를 바로 출력한다.
`--secret-mode secret-manager`가 기본값이며, secret env는 `--set-secrets ENV=secret-id:latest`로 배포한다.
로컬 실제 배포는 기본 차단된다. `master` branch, clean worktree, `HEAD == origin/master` 조건을 만족해야 하며,
비상시에는 `--allow-local-source --reason "<사유>"`를 명시해야 한다.

Secret Manager secret id 규칙:

- `KIS_APP_SECRET_RIA` → `kis-portfolio-kis-app-secret-ria`
- `MOTHERDUCK_TOKEN` → `kis-portfolio-motherduck-token`

Secret Manager 동기화는 dry-run을 먼저 확인한 뒤 적용한다.

```bash
uv run python scripts/sync_secret_manager.py --project grand-forge-279904
uv run python scripts/sync_secret_manager.py --project grand-forge-279904 --apply
```

현재 `batch` target은 `collect-domestic-order-history --date today` 전용 Cloud Run Job을 배포한다.
`overseas-batch` target은 `collect-overseas-transaction-history --date today --account-label brokerage --exchange NAS`
전용 Cloud Run Job을 배포한다. 기본값은 다음과 같다.
`token-warmup-batch` target은
`warm-token-cache --account-label all --valid-through 16:30 --warm-service-health`
전용 Cloud Run Job을 배포한다. 각 계좌 토큰이 당일 16:30 KST까지 안전하게 유효하지 않으면 KIS 토큰을
재발급하고 암호화된 최신 값을 MotherDuck 공유 캐시에 저장한다.
`--warm-service-health`는 auth/remote 서비스의 공개 `/health` endpoint를 호출해 scale-to-zero 상태의 Cloud Run
서비스를 미리 깨운다. 이 health probe는 best-effort이며, 콜드 스타트 타임아웃만으로 토큰 워밍업 Job을
실패 처리하지 않는다.

- Job name: `kis-portfolio-domestic-order-history`
- Scheduler name: `kis-portfolio-domestic-order-history-1535`
- Schedule: 평일 `15:35` KST (`35 15 * * 1-5`)
- Overseas Job name: `kis-portfolio-overseas-transaction-history`
- Overseas Scheduler name: `kis-portfolio-overseas-transaction-history-0735`
- Overseas Schedule: 평일 `07:35` KST (`35 7 * * 1-5`)
- Token warm-up Job name: `kis-portfolio-token-warmup-dry-run`
- Token warm-up Scheduler name: `kis-portfolio-token-warmup-0830`
- Token warm-up Schedule: 평일 `08:30` KST (`30 8 * * 1-5`)
- Time zone: `Asia/Seoul`
- Cloud Run Job task timeout: `1800s`
- Cloud Run Job max retries: `0`

Cloud Scheduler는 Cloud Run Job의 `https://run.googleapis.com/v2/projects/PROJECT/locations/REGION/jobs/JOB:run` endpoint를 OAuth로 호출한다. Google 공식 문서 예시도 같은 URI 패턴과 `--oauth-service-account-email` 구성을 사용한다. [Cloud Run jobs on a schedule](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule)

`scheduler` target은 먼저 선택된 service account에 `roles/run.invoker`를 부여한 뒤 Cloud Scheduler job을 create/update 한다.
권장 env:

- `KIS_CLOUD_SCHEDULER_INVOKER_SERVICE_ACCOUNT`
- `KIS_BATCH_JOB_NAME`
- `KIS_BATCH_SCHEDULER_NAME`
- `KIS_OVERSEAS_BATCH_JOB_NAME`
- `KIS_OVERSEAS_BATCH_SCHEDULER_NAME`
- `KIS_CLOUD_SCHEDULER_REGION`
- `KIS_BATCH_ORDER_HISTORY_SCHEDULE`
- `KIS_BATCH_ORDER_HISTORY_TIME_ZONE`
- `KIS_OVERSEAS_TRANSACTION_HISTORY_SCHEDULE`
- `KIS_OVERSEAS_TRANSACTION_HISTORY_TIME_ZONE`
- `KIS_OVERSEAS_TRANSACTION_HISTORY_ACCOUNT_LABEL`
- `KIS_OVERSEAS_TRANSACTION_HISTORY_EXCHANGE`

`KIS_CLOUD_SCHEDULER_INVOKER_SERVICE_ACCOUNT`를 비워두면 `GOOGLE_CLOUD_PROJECT_NUMBER` 또는 `gcloud projects describe ... --format=value(projectNumber)` 결과를 사용해 기본 compute service account (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`)를 fallback으로 잡는다.

## GitHub Actions CI/CD

이 저장소에는 자동 검증용 [.github/workflows/ci.yml](../.github/workflows/ci.yml) 과 수동 승인 배포용
[.github/workflows/deploy-cloud-run.yml](../.github/workflows/deploy-cloud-run.yml) 이 포함되어 있다.

CI workflow:

- PR 및 `master` push에서 실행한다.
- `uv run pytest`, architecture audit, MCP surface audit, shell/json sanity, `git diff --check`를 실행한다.
- 운영 secret을 읽지 않는다.

Deploy workflow:

- `workflow_dispatch`만 지원하며 target은 `all`, `auth`, `remote`, `batch`, `scheduler`, `overseas-batch`, `overseas-scheduler`, `token-warmup-batch`, `token-warmup-scheduler`다.
- `production` GitHub Environment approval을 거친다.
- `refs/heads/master`에서만 실행된다. `master` push만으로는 배포되지 않는다.
- GitHub Actions가 Workload Identity Federation으로 Google Cloud에 로그인한다.
- workflow는 `KIS_DEPLOY_ENV`를 복원하지 않고, Secret Manager reference와 비시크릿 vars로 `scripts/deploy_cloud_run.py`를 호출한다.
- Cloud Run service/job에는 `git-sha`, `github-run-id`, `deploy-target`, `deploy-source` labels가 붙는다.

권장 GitHub 설정:

- GitHub Environment: `production`
- Environment secrets:
  - `GCP_WORKLOAD_IDENTITY_PROVIDER`
  - `GCP_SERVICE_ACCOUNT`
- Repository or Environment vars:
  - `GOOGLE_CLOUD_PROJECT`
  - `KIS_DEPLOY_REGION` (선택)
  - `KIS_AUTH_SERVICE_NAME` (선택)
  - `KIS_REMOTE_SERVICE_NAME` (선택)
  - `KIS_CLOUD_RUN_AUTH_MAX_INSTANCES` (선택, 기본값 `1`)
  - `KIS_CLOUD_RUN_REMOTE_CONCURRENCY` (선택, 기본값 `20`)
  - `KIS_CLOUD_RUN_REMOTE_MIN_INSTANCES` (선택, 기본값 `0`)
  - `KIS_CLOUD_RUN_REMOTE_MAX_INSTANCES` (선택, 기본값 `1`)
  - `KIS_REAL_API_MIN_INTERVAL_SECONDS` (선택, 기본값 `0.15`)
  - `KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS` (선택, 기본값 `1.0`)
  - `KIS_TOKEN_MIN_INTERVAL_SECONDS` (선택, 기본값 `1.0`)
  - `KIS_RATE_LIMIT_RETRY_DELAY_SECONDS` (선택, 기본값 `1.0`)
  - `KIS_RATE_LIMIT_MAX_COOLDOWN_SECONDS` (선택, 기본값 `10.0`)
  - `KIS_REAL_API_MAX_IN_FLIGHT` (선택, 기본값 `3`)
  - `KIS_VIRTUAL_API_MAX_IN_FLIGHT` (선택, 기본값 `1`)
  - `KIS_API_MAX_QUEUE_SIZE` (선택, 기본값 `50`)
  - `KIS_CIRCUIT_FAILURE_THRESHOLD` (선택, 기본값 `5`)
  - `KIS_CIRCUIT_WINDOW_SECONDS` (선택, 기본값 `30.0`)
  - `KIS_CIRCUIT_OPEN_SECONDS` (선택, 기본값 `20.0`)
  - `KIS_BATCH_JOB_NAME` (선택)
  - `KIS_BATCH_SCHEDULER_NAME` (선택)
  - `KIS_CLOUD_SCHEDULER_REGION` (선택)
  - `KIS_AUTH_BASE_URL`
  - `KIS_AUTH_ISSUER_URL`
  - `KIS_RESOURCE_SERVER_URL`
  - `KIS_AUTH_CLAUDE_CLIENT_ID`
  - `KIS_OAUTH_GOOGLE_CLIENT_ID`
  - `KIS_OAUTH_GITHUB_CLIENT_ID`

운영 secret은 GCP Secret Manager에 둔다. 런타임 서비스 계정에는 필요한 secret에 대한
`roles/secretmanager.secretAccessor`를 부여한다.

Google Cloud 권장 인증 방식:

- GitHub Actions용 service account를 하나 만든다.
- `roles/run.admin`을 부여한다.
- Secret Manager reference를 확인할 수 있도록 필요한 secret metadata 접근 권한을 부여한다.
- Cloud Run runtime service account를 사용할 수 있도록 `Service Account User` 권한을 부여한다.
- Cloud Scheduler가 사용할 invoker service account를 정했다면, GitHub Actions 배포 principal에 그 계정에 대한 `iam.serviceAccounts.actAs` 권한도 준다.
- GitHub OIDC용 Workload Identity Provider를 만들고 repository 단위 attribute condition을 건다.
- GitHub workflow에서는 `google-github-actions/auth` + `setup-gcloud` 조합을 사용한다.

참고한 공식 문서:

- [google-github-actions/auth](https://github.com/google-github-actions/auth)
- [google-github-actions/setup-gcloud](https://github.com/google-github-actions/setup-gcloud)
- [google-github-actions/deploy-cloudrun](https://github.com/google-github-actions/deploy-cloudrun)
- [Execute jobs on a schedule](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule)
- [gcloud run jobs deploy](https://docs.cloud.google.com/sdk/gcloud/reference/run/jobs/deploy)
- [gcloud scheduler jobs create http](https://docs.cloud.google.com/sdk/gcloud/reference/scheduler/jobs/create/http)

## Remote MCP 후속 작업

- auth schema migration command 분리
- consent/audit UI 다듬기
- custom domain 연결
- read-only mode 기본값 추가
- 주문 tool은 disabled stub으로 유지
- MCP inspector로 remote endpoint 검증
