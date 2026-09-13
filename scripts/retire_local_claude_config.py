#!/usr/bin/env python3
"""Remove only the retired local KIS Portfolio Claude Desktop registration."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def remove_legacy_registration(path: Path) -> Path | None:
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict) or "kis-portfolio" not in servers:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = path.with_name(f"{path.name}.bak.{timestamp}")
    shutil.copy2(path, backup)
    del servers["kis-portfolio"]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return backup


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: retire_local_claude_config.py PATH", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    backup = remove_legacy_registration(path)
    if backup is None:
        print("✅ retired local kis-portfolio registration not present")
    else:
        print(f"✅ retired local kis-portfolio registration removed (backup: {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
