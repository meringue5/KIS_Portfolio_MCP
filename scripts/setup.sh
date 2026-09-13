#!/usr/bin/env bash
# KIS Portfolio repository setup after the V2 Remote MCP cutover.
# This script never registers or starts the retired local V1 MCP server.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"
CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

echo "──────────────────────────────────────────"
echo " KIS Portfolio V2 repository setup"
echo " Repository: $REPO_DIR"
echo "──────────────────────────────────────────"

if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "❌ .env 파일이 없습니다. .env.example을 복사하고 운영 값을 복원해주세요."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [ -z "${KIS_RESOURCE_SERVER_URL:-}" ]; then
  echo ""
  echo "❌ KIS_RESOURCE_SERVER_URL이 비어 있습니다."
  echo "   V2 OAuth Remote MCP의 canonical HTTPS /mcp URL을 설정해주세요."
  exit 1
fi

python3 - "$KIS_RESOURCE_SERVER_URL" <<'PY'
import sys
from urllib.parse import urlsplit

url = sys.argv[1].strip()
parts = urlsplit(url)
if parts.scheme != "https" or not parts.netloc or parts.path.rstrip("/") != "/mcp":
    raise SystemExit("KIS_RESOURCE_SERVER_URL must be a public HTTPS URL ending in /mcp")
PY
echo "✅ V2 Remote MCP URL 확인"

echo ""
echo "📦 의존성 설치 중..."
cd "$REPO_DIR"
uv sync 2>&1 | tail -3
mkdir -p "$REPO_DIR/var/tokens" "$REPO_DIR/var/local" "$REPO_DIR/var/backup"
echo "✅ 저장소 의존성 설치 완료"

# Remove only the exact retired local registration. Preserve every other
# Claude Desktop preference/server and retain a timestamped recovery copy.
if [ -f "$CLAUDE_CONFIG" ]; then
  python3 "$REPO_DIR/scripts/retire_local_claude_config.py" "$CLAUDE_CONFIG"
fi

echo ""
echo "──────────────────────────────────────────"
echo " ✅ 로컬 V1 표면 정리 완료"
echo ""
echo " Claude의 설정 > 커넥터에서 다음 OAuth Remote MCP를 등록하세요:"
echo "   이름: KIS Portfolio"
echo "   URL:  $KIS_RESOURCE_SERVER_URL"
echo ""
echo " 등록/권한 변경 후 새 대화를 열고 get-portfolio-overview를 호출하세요."
echo " 상세 절차: docs/remote-mcp-v2-migration.md"
echo "──────────────────────────────────────────"
