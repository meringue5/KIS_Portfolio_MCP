"""Retired local V1 entrypoint with explicit Remote MCP migration guidance."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kis_portfolio.legacy_entrypoint import main, retirement_notice  # noqa: E402,F401


if __name__ == "__main__":
    main()
