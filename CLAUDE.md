# KIS MCP Server — Claude 컨텍스트

이 프로젝트는 [migusdn/KIS_MCP_Server](https://github.com/migusdn/KIS_MCP_Server)를 포크하여,
한국투자증권 Open API를 Claude Desktop(Cowork 모드)에서 자연어로 조회하기 위해 확장한 MCP 서버입니다.

---

## 프로젝트 구조

```
KIS_MCP_Server/
├── server.py          # MCP 서버 본체 (모든 tool 정의)
├── .env.example       # 환경변수 템플릿 (실제 값은 .env 또는 claude_desktop_config.json)
├── CLAUDE.md          # 이 파일 — Claude용 프로젝트 컨텍스트
├── SPEC.md            # 요구사항 및 아키텍처 의사결정 기록
└── pyproject.toml     # uv 기반 의존성 관리
```

---

## 서버 실행 방법

Claude Desktop에서 MCP로 자동 실행됨. 수동 테스트 시:

```bash
cd /Users/lvcwoo/workspace/KIS_MCP_Server
uv run python server.py
```

---

## 계좌 구성 (claude_desktop_config.json)

5개 계좌가 독립적인 MCP 서버 인스턴스로 실행됨:

| 서버 이름       | CANO     | ACNT_PRDT_CD | 계좌 종류     |
|--------------|----------|-------------|------------|
| kis-ria      | 44299692 | 01          | 위험자산 일임  |
| kis-isa      | 43786274 | 01          | ISA        |
| kis-brokerage| 43416048 | 01          | 일반 위탁    |
| kis-irp      | 43362670 | 29          | IRP (퇴직연금)|
| kis-pension  | 43286118 | 22          | 연금저축     |

별도로 `kis-api-search` 서버(koreainvestment-mcp)가 API 문서 검색용으로 실행됨.

---

## 핵심 설계 규칙

### 계좌별 토큰 파일 분리
모든 인스턴스가 같은 디렉터리에서 실행되므로, OAuth 토큰을 계좌별로 분리:
```python
TOKEN_FILE = Path(__file__).resolve().parent / f"token_{os.environ.get('KIS_CANO', 'default')}.json"
```

### IRP vs 연금저축 API 분기
- **IRP (ACNT_PRDT_CD=29)**: 전용 pension API 사용
  - endpoint: `/uapi/domestic-stock/v1/trading/pension/inquire-balance`
  - TR_ID: `TTTC2208R`
- **연금저축 (ACNT_PRDT_CD=22)**: 표준 잔고 API 사용 (MTS 화면 구조로 확인)
  - endpoint: `/uapi/domestic-stock/v1/trading/inquire-balance`
  - TR_ID: `TTTC8434R`

```python
is_pension = acnt_prdt_cd == "29"  # IRP만 pension API, 22(연금저축)는 표준 API
```

### 환경변수 주입 방식
API 키와 계좌정보는 `claude_desktop_config.json`의 `env` 블록에서 주입.
`server.py`는 `os.environ`으로만 읽으므로, `.env` + `python-dotenv`로도 대체 가능 (클라우드 배포 시).

---

## 트러블슈팅 기록

### token.json 충돌
- **증상**: RIA 토큰으로 ISA API 호출 → 인증 오류
- **원인**: 5개 인스턴스가 동일 디렉터리에서 `token.json` 하나를 공유
- **해결**: `token_{CANO}.json` 형식으로 계좌별 파일 분리

### koreainvestment-mcp Python 버전 오류
- **증상**: `uv run python server.py` 실행 시 pandas 빌드 실패
- **원인**: Python 3.14에서 pandas 미지원
- **해결**: `uv sync --python 3.13` 후 `--python 3.13` 플래그 명시

### 연금저축 appSecret 파싱 오류
- **증상**: 토큰 발급 실패
- **원인**: KIS 발급 appSecret 끝에 `]` 문자 포함 (잘못된 base64)
- **해결**: `]` 문자 제거

### IRP/연금저축 "계좌 없음"
- **증상**: `inquery-balance` 호출 시 계좌 조회 실패
- **원인**: ACNT_PRDT_CD가 01이 아닌 계좌는 별도 처리 필요
- **해결**: 환경변수 `KIS_ACNT_PRDT_CD` 추가 및 API 분기 로직 구현

---

## 관련 레포지토리

| 레포 | 용도 |
|------|------|
| `~/workspace/KIS_MCP_Server` | **이 서버** (메인) |
| `~/workspace/koreainvestment-mcp` | API 문서 검색용 MCP (kis-api-search) |
| `~/workspace/stock_manager_llm` | KIS Open API 레퍼런스 코드 (참조용) |

---

## 예정 작업

- DuckDB 로컬 캐시/누적 DB 구현 (SPEC.md 참조)
- python-dotenv 도입 (클라우드 배포 대비)
