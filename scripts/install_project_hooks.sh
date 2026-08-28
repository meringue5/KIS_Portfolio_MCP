#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

git config --local core.hooksPath .githooks
echo "Project OS Git hooks enabled: core.hooksPath=.githooks"
