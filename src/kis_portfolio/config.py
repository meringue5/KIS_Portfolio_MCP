"""Runtime configuration helpers.

Environment paths may be absolute, ``~``-relative, or project-root relative.
This keeps MCP desktop configs portable while avoiding cwd-dependent behavior.
"""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "var"
DEFAULT_MOTHERDUCK_DATABASE = "kis_portfolio"


def resolve_project_path(value: str | os.PathLike | None, default: Path) -> Path:
    """Resolve paths relative to PROJECT_ROOT unless they are absolute."""
    if value in (None, ""):
        return default

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def get_data_dir() -> Path:
    return resolve_project_path(os.environ.get("KIS_DATA_DIR"), DEFAULT_DATA_DIR)


def get_token_dir() -> Path:
    return resolve_project_path(os.environ.get("KIS_TOKEN_DIR"), get_data_dir() / "tokens")


def get_local_db_path() -> Path:
    return resolve_project_path(
        os.environ.get("KIS_LOCAL_DB_PATH"),
        get_data_dir() / "local" / "kis_portfolio.duckdb",
    )


def get_db_mode() -> str:
    return os.environ.get("KIS_DB_MODE", "motherduck").strip().lower()


def get_motherduck_database() -> str:
    return os.environ.get("MOTHERDUCK_DATABASE", DEFAULT_MOTHERDUCK_DATABASE).strip()


def get_motherduck_token() -> str:
    return os.environ.get("MOTHERDUCK_TOKEN", "").strip()
