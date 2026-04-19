"""Compatibility entrypoint for the primary KIS Portfolio MCP adapter."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kis_portfolio.adapters.mcp import main, mcp  # noqa: E402,F401


if __name__ == "__main__":
    main()
