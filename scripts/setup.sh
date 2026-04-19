#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# KIS MCP Server — 신규 환경 셋업 스크립트
#
# 사용법:
#   1. .env 파일 준비 (Google Drive 등에서 복사)
#      cp /path/to/your/.env .env
#   2. 이 스크립트 실행
#      bash scripts/setup.sh
#
# 수행 내용:
#   - .env 유효성 검사
#   - uv + Python 의존성 설치
#   - claude_desktop_config.json 자동 생성
#   - Claude Desktop 설정 경로에 config 복사
# ─────────────────────────────────────────────────────────────────
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

echo "──────────────────────────────────────────"
echo " KIS MCP Server 셋업"
echo " 리포: $REPO_DIR"
echo "──────────────────────────────────────────"

# ── 1. .env 확인 ──────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "❌ .env 파일이 없습니다."
  echo "   Google Drive 등에서 .env를 복사해주세요:"
  echo "   cp /path/to/backup/.env $ENV_FILE"
  exit 1
fi

echo "✅ .env 파일 확인"

# .env 로드
set -a
source "$ENV_FILE"
set +a

# 필수 변수 확인
REQUIRED=(
  KIS_APP_KEY_RIA KIS_APP_SECRET_RIA KIS_CANO_RIA KIS_ACNT_PRDT_CD_RIA
  KIS_APP_KEY_ISA KIS_APP_SECRET_ISA KIS_CANO_ISA KIS_ACNT_PRDT_CD_ISA
  KIS_APP_KEY_IRP KIS_APP_SECRET_IRP KIS_CANO_IRP KIS_ACNT_PRDT_CD_IRP
  KIS_APP_KEY_PENSION KIS_APP_SECRET_PENSION KIS_CANO_PENSION KIS_ACNT_PRDT_CD_PENSION
  KIS_APP_KEY_BROKERAGE KIS_APP_SECRET_BROKERAGE KIS_CANO_BROKERAGE KIS_ACNT_PRDT_CD_BROKERAGE
  MOTHERDUCK_TOKEN
)
MISSING=()
for var in "${REQUIRED[@]}"; do
  if [ -z "${!var}" ]; then
    MISSING+=("$var")
  fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
  echo ""
  echo "❌ .env에 다음 변수가 비어있습니다:"
  for m in "${MISSING[@]}"; do echo "   - $m"; done
  exit 1
fi
echo "✅ 필수 환경변수 확인 완료"

# ── 2. uv + 의존성 설치 ───────────────────────
echo ""
echo "📦 의존성 설치 중..."
cd "$REPO_DIR"
uv sync 2>&1 | tail -3
mkdir -p "$REPO_DIR/var/tokens" "$REPO_DIR/var/local" "$REPO_DIR/var/backup"
echo "✅ 의존성 설치 완료"

# ── 3. claude_desktop_config.json 생성 ────────
echo ""
echo "⚙️  claude_desktop_config.json 생성 중..."

USERNAME=$(whoami)
REPO_PARENT="$(dirname "$REPO_DIR")"

# 기존 config 백업
if [ -f "$CLAUDE_CONFIG" ]; then
  BACKUP="$CLAUDE_CONFIG.bak.$(date +%Y%m%d_%H%M%S)"
  cp "$CLAUDE_CONFIG" "$BACKUP"
  echo "   기존 config 백업: $BACKUP"
fi

mkdir -p "$CLAUDE_CONFIG_DIR"

# preferences 보존: 기존 config에서 preferences 추출, 없으면 빈 객체
if [ -f "$BACKUP" ]; then
  PREFS=$(python3 -c "
import json, sys
try:
  d = json.load(open('$BACKUP'))
  print(json.dumps(d.get('preferences', {}), ensure_ascii=False))
except:
  print('{}')
")
else
  PREFS="{}"
fi

python3 - <<PYEOF
import json, os

env = {k: os.environ[k] for k in os.environ}
username = os.environ.get('USER', os.popen('whoami').read().strip())
repo_dir = "$REPO_DIR"
uv_bin   = os.path.expanduser("~/.local/bin/uv")
prefs    = json.loads(r'''$PREFS''')

def srv(key_suffix, extra_env=None):
    e = {
        "KIS_APP_KEY":    env[f"KIS_APP_KEY_{key_suffix}"],
        "KIS_APP_SECRET": env[f"KIS_APP_SECRET_{key_suffix}"],
        "KIS_CANO":       env[f"KIS_CANO_{key_suffix}"],
        "KIS_ACNT_PRDT_CD": env[f"KIS_ACNT_PRDT_CD_{key_suffix}"],
        "KIS_ACCOUNT_LABEL": key_suffix.lower(),
        "KIS_ACCOUNT_TYPE": "REAL",
        "KIS_ENABLE_ORDER_TOOLS": env.get("KIS_ENABLE_ORDER_TOOLS", "false"),
        "KIS_DB_MODE": env.get("KIS_DB_MODE", "motherduck"),
        "MOTHERDUCK_DATABASE": env.get("MOTHERDUCK_DATABASE", "kis_portfolio"),
        "KIS_DATA_DIR": env.get("KIS_DATA_DIR", "var"),
        "MOTHERDUCK_TOKEN": env["MOTHERDUCK_TOKEN"],
    }
    if extra_env:
        e.update(extra_env)
    return {
        "command": uv_bin,
        "args": ["run", "--directory", repo_dir, "python", "server.py"],
        "env": e,
    }

config = {
    "mcpServers": {
        "kis-api-search": {
            "command": uv_bin,
            "args": ["run", "--directory",
                     os.path.join(os.path.dirname(repo_dir), "koreainvestment-mcp"),
                     "--python", "3.13", "python", "server.py"],
            "env": {}
        },
        "kis-ria":       srv("RIA"),
        "kis-isa":       srv("ISA"),
        "kis-irp":       srv("IRP"),
        "kis-pension":   srv("PENSION"),
        "kis-brokerage": srv("BROKERAGE"),
    },
    "preferences": prefs,
}

out = "$CLAUDE_CONFIG"
with open(out, "w") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
print(f"   저장 완료: {out}")
PYEOF

echo "✅ claude_desktop_config.json 생성 완료"

# ── 4. 완료 ───────────────────────────────────
echo ""
echo "──────────────────────────────────────────"
echo " ✅ 셋업 완료!"
echo ""
echo " 다음 단계:"
echo "   1. Claude Desktop 재시작"
echo "   2. 채팅창에서 '전체 계좌 잔고 보여줘' 테스트"
echo "──────────────────────────────────────────"
