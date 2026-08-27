#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

run_project_os() {
  python3 .agent/skills/kis-project-os/scripts/check_project_os.py
}

run_architecture() {
  uv run python .agent/skills/kis-architecture-audit/scripts/check_architecture_contracts.py
}

run_warehouse() {
  uv run python .agent/skills/kis-warehouse-contract/scripts/check_warehouse_contracts.py
}

run_mcp_surface() {
  uv run python .agent/skills/kis-mcp-surface-audit/scripts/inspect_mcp_surface.py
}

run_shell_and_json() {
  while IFS= read -r script_path; do
    bash -n "$script_path"
  done < <(find scripts .githooks -type f \( -name '*.sh' -o -path '.githooks/pre-*' \) -print | sort)
  python3 -m json.tool docs/examples/claude_desktop_config.example.json >/dev/null
}

case "$MODE" in
  staged)
    git diff --cached --check
    run_project_os
    run_architecture
    run_warehouse
    ;;
  quick)
    run_project_os
    run_architecture
    run_warehouse
    run_mcp_surface
    run_shell_and_json
    git diff --check
    ;;
  full)
    run_project_os
    run_architecture
    run_warehouse
    run_mcp_surface
    run_shell_and_json
    uv run pytest
    git diff --check
    git diff --cached --check
    ;;
  *)
    echo "usage: bash scripts/check.sh [staged|quick|full]" >&2
    exit 2
    ;;
esac

echo "Project check passed: mode=$MODE"
