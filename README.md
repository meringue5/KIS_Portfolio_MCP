# KIS Portfolio Service

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

한국투자증권(KIS) Open API를 기반으로 개인 포트폴리오 조회, 이력 저장, 분석, MCP/remote 접근을
제공하는 서비스입니다.

이 저장소는 `migusdn/KIS_MCP_Server` fork에서 출발했지만, 현재 신규 설계의 기준은 한국투자 공식
Open API 문서와 개인 포트폴리오 서비스 요구사항입니다. MCP는 핵심 서비스 위의 adapter 중 하나로
다룹니다.

## ✨ 주요 기능

- 🇰🇷 **국내 주식 거래**
  - 실시간 현재가 조회
  - 주문 조회
  - 잔고 조회
  - 호가 정보 조회
  - 주문 내역 조회

- 🌏 **해외 주식 거래**
  - 미국, 일본, 중국, 홍콩, 베트남 등 주요 시장 지원
  - 실시간 현재가 조회
  - 해외 잔고/예수금 조회

- ⚡ **특징**
  - 비동기 처리로 빠른 응답
  - 실시간 시세 및 체결 정보
  - 안정적인 에러 처리
  - 확장 가능한 설계

- 🧭 **포트폴리오 오케스트레이션**
  - 5개 계좌 통합 조회
  - MotherDuck/DuckDB 스냅샷 저장
  - DB 기반 포트폴리오 요약/변화 분석
  - local MCP와 remote MCP adapter 병행

## ⚠️ 주의사항

이 프로젝트는 아직 개발 중인 미완성 프로젝트입니다. 실제 투자에 사용하기 전에 충분한 테스트를 거치시기 바랍니다.

* 본 프로젝트를 사용하여 발생하는 모든 손실과 책임은 전적으로 사용자에게 있습니다.
* API 사용 시 한국투자증권의 이용약관을 준수해야 합니다.
* 실제 계좌 사용 시 주의가 필요하며, 모의투자 계좌로 충분한 테스트를 권장합니다.
* API 호출 제한과 관련된 제약사항을 반드시 확인하시기 바랍니다.

## Requirements

* Python >= 3.13
* uv (Python packaging tool)

## Installation

```bash
uv sync
bash scripts/setup.sh
```

### MCP Server Configuration

`scripts/setup.sh`는 Claude Desktop 설정에 `kis-portfolio` 단일 MCP 서버를 등록합니다.
계좌별 KIS key/secret/account는 `.env`의 suffixed 환경변수에서 읽습니다.

```json
{
  "mcpServers": {
    "kis-portfolio": {
      "command": "/Users/YOUR_USERNAME/.local/bin/uv",
      "args": ["run", "--directory", "/path/to/KIS_MCP_Server", "kis-portfolio-mcp"],
      "env": {
        "KIS_APP_KEY_BROKERAGE": "...",
        "KIS_APP_SECRET_BROKERAGE": "...",
        "KIS_CANO_BROKERAGE": "...",
        "KIS_ACNT_PRDT_CD_BROKERAGE": "01",
        "MOTHERDUCK_TOKEN": "..."
      }
    }
  }
}
```

자세한 예시는 `docs/examples/claude_desktop_config.example.json`을 참고하세요.

## MCP Tools

`kis-portfolio`는 clean `get-*` tool 이름만 노출합니다. 기존 fork의 `inquery-*` tool alias는
기본 MCP 표면에 등록하지 않습니다.

### Portfolio / Account

* **get-configured-accounts** - 등록 계좌 목록 조회
* **get-all-token-statuses** - 전체 계좌 토큰 캐시 상태 조회
* **get-account-balance** - 특정 계좌 라벨 잔고 조회 및 스냅샷 저장
* **refresh-all-account-snapshots** - 전체 계좌 잔고 순차 조회 및 스냅샷 저장

### Market / History

* **get-stock-price**, **get-stock-ask**, **get-stock-info**, **get-stock-history**
* **get-overseas-stock-price**, **get-overseas-stock-history**
* **get-exchange-rate-history**

### Overseas / Profit / Orders

* **get-overseas-balance**, **get-overseas-deposit**
* **get-period-trade-profit**, **get-overseas-period-profit**
* **get-order-list**, **get-order-detail**
* **submit-stock-order**, **submit-overseas-stock-order** - disabled stub, 실제 주문 API 호출 없음

## Resources

### Configuration

환경 변수를 통해 API 키와 계좌 정보를 설정합니다:

* `KIS_APP_KEY_{ACCOUNT}`: 한국투자증권 앱키
* `KIS_APP_SECRET_{ACCOUNT}`: 한국투자증권 시크릿키
* `KIS_ACCOUNT_TYPE`: 계좌 타입 ("REAL" 또는 "VIRTUAL")
* `KIS_CANO_{ACCOUNT}`: 계좌번호
* `KIS_ACNT_PRDT_CD_{ACCOUNT}`: 계좌상품코드 (예: 일반/ISA 01, IRP 29, 연금저축 22)

계좌별 환경변수 템플릿은 `.env.example`, MCP 설정 예시는 `docs/examples/claude_desktop_config.example.json`을 참고하세요.

### Portfolio DB Tools

MotherDuck/DuckDB에 저장된 스냅샷은 API 재호출 없이 조회할 수 있습니다:

* **get-latest-portfolio-summary** - 최신 스냅샷 기준 전체/단일 계좌 합산 요약
* **get-portfolio-daily-change** - 일별 대표 스냅샷 기준 평가금액 변화
* **get-portfolio-history** - 계좌 잔고 스냅샷 이력
* **get-portfolio-trend** - 일별 평가금액 이동평균과 추세
* **get-portfolio-anomalies** - 일별 평가금액 변동 이상치 탐지

주문 tool은 disabled stub입니다. 실제 주문 API를 호출하지 않습니다.

### Portfolio Orchestrator MCP

`scripts/setup.sh`는 단일 오케스트레이터 `kis-portfolio`만 생성합니다.
Claude가 계좌별 서버를 직접 조합하지 않아도 전체 계좌 조회와 요약 분석을 실행할 수 있게 합니다.

* **get-configured-accounts** - 등록 계좌 목록 조회 (계좌번호 마스킹, secret 비노출)
* **get-all-token-statuses** - 전체 계좌 토큰 캐시 상태 조회 (토큰 값 비노출)
* **get-account-balance** - 특정 계좌 라벨 잔고 조회 및 스냅샷 저장
* **refresh-all-account-snapshots** - 전체 계좌 잔고를 순차 조회하고 스냅샷 저장
* **get-latest-portfolio-summary** - 최신 스냅샷 기준 전체/단일 계좌 합산 요약
* **get-portfolio-daily-change** - 일별 대표 스냅샷 기준 평가금액 변화

### Architecture Direction

신규 기능은 fork 원본 MCP 구현보다 한국투자 공식 API 문서와 공식 예제 저장소를 우선 기준으로 삼습니다.
기능 분류와 리팩토링 기준은 `docs/api-capability-map.md`를 참고하세요.

장기 구조는 core service와 adapter 분리입니다.

```text
KIS API clients/services
        ↓
repositories / analytics / warehouse
        ↓
adapters: local MCP, remote MCP, batch jobs, future web API
```

### Deployment

컨테이너 베이스라인은 `Dockerfile`에 있습니다. 현재 엔트리포인트는 local stdio MCP 서버이며,
ChatGPT custom MCP용 원격 배포는 `kis-portfolio-remote`가 `/mcp` Streamable HTTP endpoint를 제공합니다.
원격 endpoint는 `KIS_REMOTE_AUTH_TOKEN` 기반 bearer 인증을 요구합니다.
자세한 내용은 `docs/deployment.md`를 참고하세요.

### Local MCP Process Control

Claude Desktop 재시작 후에도 KIS MCP 프로세스가 남아 있거나, Codex에서 리팩토링하기 전에 서버를 내리고 싶다면:

```bash
bash scripts/stop_mcp.sh
```

먼저 대상 프로세스만 확인하려면:

```bash
bash scripts/stop_mcp.sh --dry-run
```

### Trading Hours

국내 주식:
* 정규장: 09:00 ~ 15:30
* 시간외 단일가: 15:40 ~ 16:00

해외 주식:
* 미국(나스닥/뉴욕): 22:30 ~ 05:00 (한국시간)
* 일본: 09:00 ~ 15:10
* 중국: 10:30 ~ 16:00
* 홍콩: 10:30 ~ 16:00
* 베트남: 11:15 ~ 16:15

## Error Handling

API 호출 시 발생할 수 있는 주요 에러:

* 인증 오류: API 키 또는 시크릿키가 잘못된 경우
* 잔고 부족: 주문 금액이 계좌 잔고보다 큰 경우
* 시간 제한: 거래 시간이 아닌 경우
* 주문 제한: 주문 수량이나 금액이 제한을 초과한 경우

## About

* 확장 가능한 설계
* 비동기 처리로 빠른 응답
* 실시간 시세 및 체결 정보
* 안정적인 에러 처리

## License

MIT License

This project started as a fork of `migusdn/KIS_MCP_Server`, which is also distributed under the MIT License.
See `LICENSE`.
