# Deployment Notes

이 문서는 원격 MCP/Web 배포를 준비하기 위한 운영 원칙을 정리한다.

## 현재 상태

현재 기본 엔트리포인트는 local stdio MCP 서버다.

```bash
uv run python server.py
```

Dockerfile은 이 local MCP 서버를 컨테이너에서 실행할 수 있게 하는 최소 베이스라인이다.
ChatGPT custom MCP나 원격 Claude connector에 붙이려면 별도의 Streamable HTTP MCP 어댑터가
필요하다.

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
docker build -t kis-mcp-server .
docker run --rm -i \
  -e KIS_APP_KEY=... \
  -e KIS_APP_SECRET=... \
  -e KIS_CANO=... \
  -e KIS_ACNT_PRDT_CD=01 \
  -e KIS_ACCOUNT_LABEL=brokerage \
  -e KIS_ACCOUNT_TYPE=REAL \
  -e KIS_DB_MODE=motherduck \
  -e MOTHERDUCK_DATABASE=kis_portfolio \
  -e MOTHERDUCK_TOKEN=... \
  kis-mcp-server
```

stdio MCP는 표준 입출력을 사용하므로 컨테이너 테스트도 `-i`가 필요하다.

## Remote MCP 후속 작업

- `src/kis_mcp_server/adapters/mcp_http.py` 추가
- Streamable HTTP endpoint: `/mcp`
- 인증 middleware 추가
- read-only mode 기본값 추가
- 주문 tool은 `KIS_ENABLE_ORDER_TOOLS=false`를 기본값으로 유지
- MCP inspector로 remote endpoint 검증
