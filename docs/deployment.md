# Deployment Notes

이 문서는 원격 MCP/Web 배포를 준비하기 위한 운영 원칙을 정리한다.

## 현재 상태

현재 기본 엔트리포인트는 local stdio MCP 서버다.

```bash
uv run kis-portfolio-mcp
```

Dockerfile은 이 local MCP 서버를 컨테이너에서 실행할 수 있게 하는 최소 베이스라인이다.
원격 클라이언트용 entrypoint는 `kis-portfolio-remote`이며, `/mcp` endpoint를 Streamable HTTP로 노출한다.

## Remote MCP 인증

초기 remote 배포는 공유 bearer token 방식으로 보호한다.

- 필수 환경변수: `KIS_REMOTE_AUTH_TOKEN`
- 클라이언트 요청 헤더: `Authorization: Bearer <token>`
- health check: `GET /healthz`는 인증 없이 응답
- MCP endpoint: `/mcp`는 인증 필수

`KIS_REMOTE_AUTH_DISABLED=true`는 로컬 터널 실험에만 사용한다. 운영 배포에서는 사용하지 않는다.

다중 사용자나 조직 배포로 확장할 때는 OAuth/OIDC provider 기반 인증으로 승격한다. 그 전까지
remote MCP는 개인용/비공개 endpoint로만 운영한다.

## Secret 원칙

KIS API key, app secret, 계좌번호, MotherDuck token은 이미지에 포함하지 않는다.
배포 플랫폼의 runtime secret/env store에 넣고 컨테이너 실행 시 환경변수로 주입한다.

GitHub Secrets는 다음 용도로만 사용한다.

- 배포 플랫폼 API token
- CI/CD에서 필요한 최소 권한 credential
- 플랫폼 secret을 갱신하는 자동화가 필요한 경우의 입력값

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

원격 MCP 실행 예시:

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  -e KIS_REMOTE_AUTH_TOKEN=... \
  -e KIS_DB_MODE=motherduck \
  -e MOTHERDUCK_DATABASE=kis_portfolio \
  kis-portfolio \
  uv run kis-portfolio-remote
```

remote endpoint는 `http://localhost:8000/mcp` 또는 배포 플랫폼의 HTTPS URL에서 `/mcp`이다.

## Remote MCP 후속 작업

- 인증 방식을 OAuth/OIDC로 승격
- read-only mode 기본값 추가
- 주문 tool은 disabled stub으로 유지
- MCP inspector로 remote endpoint 검증
