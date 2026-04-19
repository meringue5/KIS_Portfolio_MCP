# TODO

자주 바뀌는 작업 큐다. 결정된 설계 원칙은 `SPEC.md`, 에이전트 운영 지침은 `AGENTS.md`에 둔다.

## High Priority

- [x] 오케스트레이터 MCP 병행 전환을 구현한다.
  - 기존 5개 계좌 MCP는 유지하고 `kis-portfolio` 서버를 추가한다.
  - `AccountRegistry`로 5개 계좌 설정을 읽고 계좌번호는 마스킹해 노출한다.
  - `get-configured-accounts`, `get-all-token-statuses`, `get-account-balance`, `refresh-all-account-snapshots`를 제공한다.
  - 전체 계좌 refresh는 순차 실행하고 주문 tool은 오케스트레이터에 노출하지 않는다.
- [ ] Claude Desktop 실사용 리허설 결과를 반영한다.
- [ ] 토큰 발급 감사 이벤트 저장을 추가한다.
  - access token 원문은 `var/tokens/`의 런타임 secret cache에만 보관한다.
  - MotherDuck에는 `account_label`, masked account id, `issued_at`, `expires_at`, refresh reason, token fingerprint 같은 메타데이터만 저장한다.
  - 목적은 KIS의 1일 1회 발급/잦은 발급 차단 정책 감시다.

## Remote MCP

- [ ] 개인용 bearer token 인증을 OAuth/OIDC로 승격할 필요가 있는지 검토한다.
- [ ] remote read-only mode를 명시적으로 분리한다.
- [ ] Docker build를 정상 Docker daemon 환경에서 검증한다.
- [ ] 배포 후보(Fly.io, Render, Cloud Run)를 비교하고 1차 타겟을 정한다.

## Refactor

- [ ] 포트폴리오 aggregate tool을 서비스 계층으로 추가 분리한다.
- [ ] KIS client 모듈을 국내/해외/연금/환율 단위로 분리한다.
- [ ] token refresh와 audit logging 경계를 정리한다.
