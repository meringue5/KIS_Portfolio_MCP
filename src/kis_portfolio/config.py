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


def get_state_backend() -> str:
    """Return the explicit operational-state backend.

    ``motherduck`` remains the compatibility/rollback default until the managed
    runtime is deployed with ``KIS_STATE_BACKEND=firestore``.
    """
    return os.environ.get("KIS_STATE_BACKEND", "motherduck").strip().lower()


def get_gcp_project() -> str:
    return (
        os.environ.get("KIS_GCP_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or ""
    ).strip()


def get_firestore_database() -> str:
    return os.environ.get("KIS_FIRESTORE_DATABASE", "kis-portfolio-state").strip()


def get_remote_auth_mode() -> str:
    return os.environ.get("KIS_REMOTE_AUTH_MODE", "bearer").strip().lower()


def get_auth_issuer_url() -> str:
    return os.environ.get("KIS_AUTH_ISSUER_URL", "").strip()


def get_resource_server_url() -> str:
    return os.environ.get("KIS_RESOURCE_SERVER_URL", "").strip()


def get_auth_required_scopes() -> list[str]:
    value = os.environ.get("KIS_AUTH_REQUIRED_SCOPES", "mcp:read").strip()
    return [scope for scope in value.split() if scope]


def get_auth_allowed_scopes() -> list[str]:
    value = os.environ.get("KIS_AUTH_ALLOWED_SCOPES", "mcp:read offline_access").strip()
    return [scope for scope in value.replace(",", " ").split() if scope]


def get_auth_token_pepper() -> str:
    return os.environ.get("KIS_AUTH_TOKEN_PEPPER", "").strip()
