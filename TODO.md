# TODO

자주 바뀌는 작업 큐다. 결정된 설계 원칙은 `SPEC.md`, 에이전트 운영 지침은 `AGENTS.md`에 둔다.

## High Priority

- [x] KIS Portfolio Service 구조 전환을 구현한다.
  - Python package를 `kis_portfolio`로 rename하고 CLI를 `kis-portfolio-*`로 정리한다.
  - Claude 기본 MCP 설정은 `kis-portfolio` 단일 서버만 노출한다.
  - `clients/services/adapters/mcp` 구조로 legacy MCP 중심 구현을 흡수한다.
  - 기존 `inquery-*` tool alias는 새 MCP에 노출하지 않고 clean `get-*` tool 표면으로 재정리한다.
  - 주문 기능은 실제 KIS 주문 호출 없이 disabled/stub으로만 제공한다.
- [x] 오케스트레이터 MCP 병행 전환을 구현한다.
  - 기존 5개 계좌 MCP는 유지하고 `kis-portfolio` 서버를 추가한다.
  - `AccountRegistry`로 5개 계좌 설정을 읽고 계좌번호는 마스킹해 노출한다.
  - `get-configured-accounts`, `get-all-token-statuses`, `get-account-balance`, `refresh-all-account-snapshots`를 제공한다.
  - 전체 계좌 refresh는 순차 실행하고 주문 tool은 오케스트레이터에 노출하지 않는다.
- [x] forked MCP에서 KIS API 기반 포트폴리오 서비스로 설계 기준을 전환한다.
  - ADR-011로 프로젝트 정체성 전환을 기록한다.
  - `docs/api-capability-map.md`에 공식 API 기준 capability map을 둔다.
- [ ] Claude Desktop 실사용 리허설 결과를 반영한다.
  - [x] 전체 자산현황용 `get-total-asset-overview`를 추가해 국내/해외/환율 반영 합계와 차트용 비중 데이터를 반환한다.
  - [x] `get-total-asset-overview`를 canonical 총자산 API로 승격하고 글로벌 스냅샷/분석 tool을 추가한다.
  - [x] 국내 상장 해외 ETF/REIT를 `해외우회투자`로 분류하는 master+heuristic+override 계층을 추가한다.
  - [x] DB 검사 클라이언트 `inspect_portfolio_db.py`를 warehouse skill에 추가한다.
  - [ ] `instrument_classification_overrides` 운영 루틴과 override 입력 UX를 정리한다.
  - [ ] 종목마스터 동기화 주기와 실패 시 fallback 정책을 정리한다.
  - [x] `sync_instrument_master.py`의 MotherDuck 대량 upsert 성능을 staging + bulk upsert로 개선한다.
  - [ ] `sync_instrument_master.py`의 재시도/재개 전략을 정리한다.
- [ ] 토큰 발급 감사 이벤트 저장을 추가한다.
  - access token은 `kis_api_access_tokens`에 암호화 저장하며 audit table에는 원문/ciphertext를 중복 저장하지 않는다.
  - audit event에는 `account_label`, masked account id, `issued_at`, `expires_at`, refresh reason, token fingerprint 같은 메타데이터만 저장한다.
  - 목적은 KIS의 1일 1회 발급/잦은 발급 차단 정책 감시다.

## Data Governance

- [x] MotherDuck/DuckDB 관리 책임 문서와 전체 객체 카탈로그를 만든다.
  - `docs/data-catalog.md`를 purpose/grain/key/layer/sensitivity/backup/schema plan의 canonical 문서로 지정한다.
  - `src/kis_portfolio/db/catalog.py`에 25 tables + 2 views의 machine-readable allowlist를 둔다.
  - backup table 목록을 catalog registry에서 파생하고 warehouse contract 검사에서 DDL/catalog/docs 일치를 검증한다.
  - DB 검사 클라이언트에 `--inventory`와 managed/unmanaged drift 보고를 추가한다.
- [ ] `codex/portfolio-pipeline-reliability`의 DB 변경을 현재 mainline과 통합한다.
  - 출처 commit은 `9dea94c Fix portfolio snapshot integrity and operations`이며 현재 branch와 공통 base 이후 분기돼 있다.
  - `cash_flow`, `trade_journal` table과 repository/test를 Silver 계약으로 편입한다. 현재 운영 table은 0 rows다.
  - `asset_overview_snapshots`의 `quality_status`, `quality_flags`, `is_complete`를 DDL/catalog에 편입한다.
  - `asset_overview_daily_snapshots`가 품질 컬럼을 투영하도록 갱신한 뒤 깨진 `asset_return_daily` Gold view를 재생성한다.
  - branch 통합 전에는 해당 객체를 현재 서비스의 공식 조회, 자동 백업, 삭제 대상으로 삼지 않는다.
- [ ] `main` 단일 schema를 계층별 물리 schema로 전환한다.
  - 목표 schema: `bronze`, `silver`, `gold`, `control`, `security`.
  - runtime auto-DDL을 versioned migration runner와 schema version check로 분리한다.
  - single-writer migration lock과 backup/restore rehearsal을 준비한다.
  - 객체별 row count, PK uniqueness, null contract, 총자산 aggregate reconciliation 후 repository SQL을 schema-qualified name으로 전환한다.
  - transition 기간에는 필요한 `main` read-only compatibility view만 유지하고 최종적으로 retire한다.

## Remote MCP

- [ ] 개인용 bearer token 인증을 OAuth/OIDC로 승격할 필요가 있는지 검토한다.
- [ ] remote read-only mode를 명시적으로 분리한다.
- [ ] Docker build를 정상 Docker daemon 환경에서 검증한다.
- [ ] 배포 후보(Fly.io, Render, Cloud Run)를 비교하고 1차 타겟을 정한다.
  - 현재 운영 가설은 `Cloud Run + Cloudflare Access(+ WAF/IP allowlist)` 조합이다.
  - Claude/remote MCP는 Anthropic cloud에서 public HTTPS endpoint로 붙으므로, private network/VPN-only 구성은 1차안에서 제외한다.
- [ ] 원격 배포용 서비스 가입과 결제수단 준비를 끝낸다.
  - `Google Cloud`
    - 용도: `Cloud Run` 배포, `Artifact Registry` 컨테이너 이미지 저장, `Secret Manager` 운영 secret 저장.
    - 가입 링크: <https://cloud.google.com/free>, 콘솔: <https://console.cloud.google.com>
    - 월 예상 비용(개인 저사용량 기준):
      - `Cloud Run`: 대체로 `$0-5/월` 예상. `min instances=0`이면 무료구간 안에 머물 가능성이 크다.
      - `Secret Manager`: secret 6개까지는 free tier로 커버 가능. 현재처럼 env를 잘게 나누면 대략 `$0-2/월` 정도로 볼 것.
      - `Artifact Registry`: 이미지가 작으면 사실상 무료에 가깝고, 0.5GB 초과분만 `GB당 $0.10/월`.
    - 비고:
      - remote v1은 파일 기반 토큰 캐시를 쓰므로 `max instances=1`로 시작하는 편이 안전하다.
      - 비용은 공식 가격표 기준이며 실제 청구는 리전/트래픽/secret 개수에 따라 달라진다.
  - `Cloudflare`
    - 용도: `Access`로 Claude 앞단 인증, `WAF/custom rules`로 IP allowlist, custom domain 프록시.
    - 가입 링크: <https://dash.cloudflare.com/sign-up>
    - 제품/설정 문서:
      - Access 가격: <https://www.cloudflare.com/plans/zero-trust-services/>
      - Self-hosted app 보호: <https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/>
      - Managed OAuth: <https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/managed-oauth/>
    - 월 예상 비용(개인 사용 기준):
      - `Cloudflare Access Free`: 50명 미만은 `$0/월`로 시작 가능.
      - custom domain만 쓰는 수준에서는 보통 추가 비용 없이 시작 가능.
    - 비고:
      - 운영 전에는 Anthropic published IP 범위를 allowlist에 넣고, 초기 설정 중에는 내 접속 IP도 임시 허용한다.
  - `도메인 등록업체(선택)`
    - 용도: `mcp.example.com` 같은 custom domain 연결.
    - 월 예상 비용: 도메인 종류에 따라 다르지만 보통 `연 $10-20` 수준(`월 $1-2` 감각)으로 본다.
    - 비고: 기존 보유 도메인이 있으면 신규 가입 없이 그대로 써도 된다.
- [ ] 가입 전에 준비해둘 운영 메모를 정리한다.
  - Google Cloud billing account를 먼저 열어야 `Cloud Run`, `Artifact Registry`, `Secret Manager`를 바로 켤 수 있다.
  - Cloudflare는 계정 생성 후 `Zero Trust`와 DNS 관리를 같이 붙일 수 있는지 확인한다.
  - 비용 절감을 위해 1차 목표는 `Cloud Run min instances=0`, `max instances=1`, `concurrency=1`로 둔다.
  - 실제 KIS secret 개수와 주입 방식은 배포 직전에 다시 세서 `Secret Manager` 비용 추정치를 업데이트한다.

## Refactor

- [ ] DB schema initialization을 runtime 자동 실행에서 migration/initialization command로 분리한다.
  - 현재는 `get_connection()` 첫 호출에서 `init_schema()`가 실행된다.
  - MotherDuck에서 여러 프로세스가 동시에 시작되면 `CREATE OR REPLACE VIEW` catalog write-write conflict가 날 수 있어 retry로 1차 방어 중이다.
  - 상세 이행 기준은 `docs/data-catalog.md`의 Physical Schema Migration Plan을 따른다.
- [ ] `app.py` legacy MCP tool을 core service와 MCP adapter로 분리한다.
- [ ] `docs/api-capability-map.md` 기준으로 KIS client/service 패키지 구조를 설계한다.
- [ ] 포트폴리오 aggregate tool을 서비스 계층으로 추가 분리한다.
- [ ] KIS client 모듈을 국내/해외/연금/환율 단위로 분리한다.
- [ ] token refresh와 audit logging 경계를 정리한다.
- [ ] ETF 편입종목/PDF/외부 데이터까지 포함한 해외노출 enrichment pipeline 필요성을 검토한다.
