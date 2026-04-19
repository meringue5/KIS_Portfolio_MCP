#!/usr/bin/env bash
# Stop KIS MCP server processes started by Claude Desktop or local testing.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FORCE=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE=1 ;;
    --dry-run|-n) DRY_RUN=1 ;;
    --help|-h)
      echo "Usage: bash scripts/stop_mcp.sh [--dry-run] [--force]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

PIDS_TEXT="$(
  python3 - "$REPO_DIR" <<'PY'
import os
import sys

repo = os.path.realpath(sys.argv[1])
current = os.getpid()

if sys.platform == "darwin":
    import subprocess

    out = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_text, _, command = line.partition(" ")
        if not pid_text.isdigit() or int(pid_text) == current:
            continue
        if repo in command and ("server.py" in command or "kis-mcp-server" in command):
            print(pid_text)
else:
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == current:
            continue
        try:
            raw = open(f"/proc/{name}/cmdline", "rb").read()
        except OSError:
            continue
        command = raw.replace(b"\0", b" ").decode(errors="ignore")
        if repo in command and ("server.py" in command or "kis-mcp-server" in command):
            print(name)
PY
)"

PIDS=()
if [ -n "$PIDS_TEXT" ]; then
  while IFS= read -r pid; do
    [ -n "$pid" ] && PIDS+=("$pid")
  done <<EOF
$PIDS_TEXT
EOF
fi

if [ "${#PIDS[@]}" -eq 0 ]; then
  echo "No KIS MCP server processes found for $REPO_DIR"
  exit 0
fi

echo "Found KIS MCP server process(es): ${PIDS[*]}"

if [ "$DRY_RUN" -eq 1 ]; then
  ps -p "$(IFS=,; echo "${PIDS[*]}")" -o pid=,command= 2>/dev/null || true
  exit 0
fi

kill "${PIDS[@]}" 2>/dev/null || true
sleep 1

STILL_RUNNING=()
for pid in "${PIDS[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    STILL_RUNNING+=("$pid")
  fi
done

if [ "${#STILL_RUNNING[@]}" -gt 0 ] && [ "$FORCE" -eq 1 ]; then
  echo "Force killing: ${STILL_RUNNING[*]}"
  kill -9 "${STILL_RUNNING[@]}" 2>/dev/null || true
  STILL_RUNNING=()
fi

if [ "${#STILL_RUNNING[@]}" -gt 0 ]; then
  echo "Some processes are still running: ${STILL_RUNNING[*]}"
  echo "Run with --force to send SIGKILL."
  exit 1
fi

echo "Stopped KIS MCP server process(es)."
