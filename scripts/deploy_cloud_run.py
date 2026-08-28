"""Deploy KIS Cloud Run services, jobs, and scheduler triggers from release source."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGION = "asia-northeast3"
DEFAULT_REMOTE_SERVICE = "kis-portfolio-remote"
DEFAULT_AUTH_SERVICE = "kis-portfolio-auth"
DEFAULT_BATCH_JOB = "kis-portfolio-domestic-order-history"
DEFAULT_BATCH_SCHEDULER = "kis-portfolio-domestic-order-history-1535"
DEFAULT_OVERSEAS_BATCH_JOB = "kis-portfolio-overseas-transaction-history"
DEFAULT_OVERSEAS_BATCH_SCHEDULER = "kis-portfolio-overseas-transaction-history-0735"
DEFAULT_TOKEN_WARMUP_JOB = "kis-portfolio-token-warmup-dry-run"
DEFAULT_TOKEN_WARMUP_SCHEDULER = "kis-portfolio-token-warmup-0830"
DEFAULT_WI021_S06_JOB = "kis-portfolio-wi021-s06"
DEFAULT_V2_CORE_JOBS = {
    "kr-1000": "kis-portfolio-owned-core-v2-1000",
    "kr-1430": "kis-portfolio-owned-core-v2-1430",
    "kr-1600": "kis-portfolio-owned-core-v2-1600",
}
DEFAULT_V2_CORE_SCHEDULES = {
    "kr-1000": "0 10 * * 1-5",
    "kr-1430": "30 14 * * 1-5",
    "kr-1600": "0 16 * * 1-5",
}
DEFAULT_AUTH_MIN_INSTANCES = "0"
DEFAULT_AUTH_MAX_INSTANCES = "1"
DEFAULT_REMOTE_CONCURRENCY = "20"
DEFAULT_REMOTE_MIN_INSTANCES = "0"
DEFAULT_REMOTE_MAX_INSTANCES = "1"
DEFAULT_CHATGPT_REMOTE_AUTH_MODE = "oauth"
DEFAULT_BATCH_TASK_TIMEOUT = "1800s"
DEFAULT_BATCH_MAX_RETRIES = "0"
DEFAULT_WI021_S06_TASK_TIMEOUT = "14400s"
DEFAULT_BATCH_SCHEDULE = "35 15 * * 1-5"
DEFAULT_BATCH_TIME_ZONE = "Asia/Seoul"
DEFAULT_OVERSEAS_BATCH_SCHEDULE = "35 7 * * 1-5"
DEFAULT_OVERSEAS_BATCH_TIME_ZONE = "Asia/Seoul"
DEFAULT_OVERSEAS_ACCOUNT_LABEL = "brokerage"
DEFAULT_OVERSEAS_EXCHANGE = "NAS"
DEFAULT_TOKEN_WARMUP_SCHEDULE = "30 8 * * 1-5"
DEFAULT_TOKEN_WARMUP_TIME_ZONE = "Asia/Seoul"
DEFAULT_TOKEN_WARMUP_ACCOUNT_LABEL = "all"
DEFAULT_TOKEN_WARMUP_VALID_THROUGH = "16:30"
DEFAULT_DEPLOY_SECRET_MODE = "secret-manager"
PRODUCTION_BRANCH = "master"
DEFAULT_ACCOUNT_PRODUCT_CODES = {
    "RIA": "01",
    "ISA": "01",
    "BROKERAGE": "01",
    "IRP": "29",
    "PENSION": "22",
}
SECRET_ENV_EXACT_KEYS = {
    "MOTHERDUCK_TOKEN",
    "KIS_TOKEN_ENCRYPTION_KEY",
    "KIS_REMOTE_AUTH_TOKEN",
    "KIS_AUTH_OWNER_EMAILS",
    "KIS_AUTH_SESSION_SECRET",
    "KIS_AUTH_TOKEN_PEPPER",
    "KIS_AUTH_CLAUDE_CLIENT_SECRET",
    "KIS_OAUTH_GOOGLE_CLIENT_SECRET",
    "KIS_OAUTH_GITHUB_CLIENT_SECRET",
}
SECRET_ENV_PREFIXES = (
    "KIS_APP_KEY_",
    "KIS_APP_SECRET_",
    "KIS_CANO_",
)


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    dotenv_path = PROJECT_ROOT / ".env"
    if dotenv_path.exists():
        for key, value in dotenv_values(dotenv_path).items():
            if key and value is not None:
                env[key] = value
    for key, value in os.environ.items():
        env[key] = value
    return env


def _collect_prefixed(env: dict[str, str], prefixes: tuple[str, ...]) -> dict[str, str]:
    return {
        key: value
        for key, value in env.items()
        if any(key.startswith(prefix) for prefix in prefixes) and value != ""
    }


def _required_keys_for_auth(env: dict[str, str]) -> list[str]:
    keys = [
        "KIS_DB_MODE",
        "KIS_AUTH_BASE_URL",
        "KIS_AUTH_OWNER_EMAILS",
        "KIS_AUTH_SESSION_SECRET",
        "KIS_AUTH_TOKEN_PEPPER",
        "KIS_AUTH_CLAUDE_CLIENT_ID",
        "KIS_AUTH_CLAUDE_CLIENT_SECRET",
        "KIS_OAUTH_GOOGLE_CLIENT_ID",
        "KIS_OAUTH_GOOGLE_CLIENT_SECRET",
        "KIS_OAUTH_GITHUB_CLIENT_ID",
        "KIS_OAUTH_GITHUB_CLIENT_SECRET",
    ]
    if env.get("KIS_DB_MODE", "").lower() == "motherduck":
        keys.extend(["MOTHERDUCK_DATABASE", "MOTHERDUCK_TOKEN"])
    return keys


def _required_keys_for_remote(env: dict[str, str]) -> list[str]:
    keys = [
        "KIS_DB_MODE",
        "KIS_TOKEN_ENCRYPTION_KEY",
    ]
    if env.get("KIS_DB_MODE", "").lower() == "motherduck":
        keys.extend(["MOTHERDUCK_DATABASE", "MOTHERDUCK_TOKEN"])

    auth_mode = _effective_remote_auth_mode(env)
    if auth_mode == "oauth":
        keys.extend([
            "KIS_AUTH_ISSUER_URL",
            "KIS_RESOURCE_SERVER_URL",
            "KIS_AUTH_REQUIRED_SCOPES",
            "KIS_AUTH_TOKEN_PEPPER",
        ])
    elif auth_mode == "bearer":
        keys.append("KIS_REMOTE_AUTH_MODE")
        keys.append("KIS_REMOTE_AUTH_TOKEN")

    return keys


def _required_keys_for_batch(env: dict[str, str]) -> list[str]:
    keys = [
        "KIS_DB_MODE",
        "KIS_TOKEN_ENCRYPTION_KEY",
    ]
    if env.get("KIS_DB_MODE", "").lower() == "motherduck":
        keys.extend(["MOTHERDUCK_DATABASE", "MOTHERDUCK_TOKEN"])
    return keys


def _effective_remote_auth_mode(env: dict[str, str]) -> str:
    return env.get("KIS_REMOTE_AUTH_MODE", DEFAULT_CHATGPT_REMOTE_AUTH_MODE).strip().lower()


def _deploy_account_labels(env: dict[str, str]) -> tuple[str, ...]:
    raw = env.get("KIS_DEPLOY_ACCOUNT_LABELS", "").strip()
    if not raw:
        raw = env.get("KIS_ACCOUNT_LABELS", "").strip()
    if not raw:
        return tuple(DEFAULT_ACCOUNT_PRODUCT_CODES)
    labels = tuple(label.strip().upper() for label in raw.split(",") if label.strip())
    return labels or tuple(DEFAULT_ACCOUNT_PRODUCT_CODES)


def _build_account_env(env: dict[str, str]) -> dict[str, str]:
    payload = _collect_prefixed(
        env,
        ("KIS_APP_KEY_", "KIS_APP_SECRET_", "KIS_CANO_", "KIS_ACNT_PRDT_CD_"),
    )
    for label in _deploy_account_labels(env):
        product_key = f"KIS_ACNT_PRDT_CD_{label}"
        default_product_code = DEFAULT_ACCOUNT_PRODUCT_CODES.get(label)
        if env.get(product_key, "") != "":
            payload[product_key] = env[product_key]
        elif default_product_code:
            payload[product_key] = default_product_code
    return payload


def _build_auth_env(env: dict[str, str]) -> dict[str, str]:
    keys = {
        "KIS_DB_MODE",
        "MOTHERDUCK_DATABASE",
        "MOTHERDUCK_TOKEN",
        "KIS_AUTH_BASE_URL",
        "KIS_AUTH_OWNER_EMAILS",
        "KIS_AUTH_SESSION_SECRET",
        "KIS_AUTH_TOKEN_PEPPER",
        "KIS_AUTH_ALLOWED_SCOPES",
        "KIS_AUTH_CLAUDE_CLIENT_ID",
        "KIS_AUTH_CLAUDE_CLIENT_SECRET",
        "KIS_AUTH_CLAUDE_REDIRECT_URIS",
        "KIS_OAUTH_GOOGLE_CLIENT_ID",
        "KIS_OAUTH_GOOGLE_CLIENT_SECRET",
        "KIS_OAUTH_GITHUB_CLIENT_ID",
        "KIS_OAUTH_GITHUB_CLIENT_SECRET",
        "KIS_DATA_DIR",
    }
    return {key: env[key] for key in keys if env.get(key, "") != ""}


def _build_remote_env(env: dict[str, str]) -> dict[str, str]:
    keys = {
        "KIS_DB_MODE",
        "MOTHERDUCK_DATABASE",
        "MOTHERDUCK_TOKEN",
        "KIS_ACCOUNT_TYPE",
        "KIS_ENABLE_ORDER_TOOLS",
        "KIS_DATA_DIR",
        "KIS_TOKEN_ENCRYPTION_KEY",
        "KIS_REMOTE_AUTH_MODE",
        "KIS_REMOTE_AUTH_TOKEN",
        "KIS_AUTH_ISSUER_URL",
        "KIS_RESOURCE_SERVER_URL",
        "KIS_AUTH_REQUIRED_SCOPES",
        "KIS_AUTH_ALLOWED_SCOPES",
        "KIS_AUTH_TOKEN_PEPPER",
        "KIS_REAL_API_MIN_INTERVAL_SECONDS",
        "KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS",
        "KIS_TOKEN_MIN_INTERVAL_SECONDS",
        "KIS_RATE_LIMIT_RETRY_DELAY_SECONDS",
        "KIS_RATE_LIMIT_MAX_COOLDOWN_SECONDS",
        "KIS_REAL_API_MAX_IN_FLIGHT",
        "KIS_VIRTUAL_API_MAX_IN_FLIGHT",
        "KIS_API_MAX_QUEUE_SIZE",
        "KIS_CIRCUIT_FAILURE_THRESHOLD",
        "KIS_CIRCUIT_WINDOW_SECONDS",
        "KIS_CIRCUIT_OPEN_SECONDS",
    }
    payload = {key: env[key] for key in keys if env.get(key, "") != ""}
    payload["KIS_REMOTE_AUTH_MODE"] = _effective_remote_auth_mode(env)
    payload.update(_build_account_env(env))
    return payload


def _build_batch_env(env: dict[str, str]) -> dict[str, str]:
    keys = {
        "KIS_DB_MODE",
        "MOTHERDUCK_DATABASE",
        "MOTHERDUCK_TOKEN",
        "KIS_ACCOUNT_TYPE",
        "KIS_DATA_DIR",
        "KIS_TOKEN_ENCRYPTION_KEY",
        "KIS_AUTH_BASE_URL",
        "KIS_AUTH_ISSUER_URL",
        "KIS_RESOURCE_SERVER_URL",
        "KIS_SERVICE_WARMUP_HEALTH_URLS",
        "KIS_REAL_API_MIN_INTERVAL_SECONDS",
        "KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS",
        "KIS_TOKEN_MIN_INTERVAL_SECONDS",
        "KIS_RATE_LIMIT_RETRY_DELAY_SECONDS",
        "KIS_RATE_LIMIT_MAX_COOLDOWN_SECONDS",
        "KIS_REAL_API_MAX_IN_FLIGHT",
        "KIS_VIRTUAL_API_MAX_IN_FLIGHT",
        "KIS_API_MAX_QUEUE_SIZE",
        "KIS_CIRCUIT_FAILURE_THRESHOLD",
        "KIS_CIRCUIT_WINDOW_SECONDS",
        "KIS_CIRCUIT_OPEN_SECONDS",
        "KIS_STATE_BACKEND",
        "KIS_GCP_PROJECT",
        "KIS_FIRESTORE_DATABASE",
        "KIS_GCS_BUCKET",
    }
    payload = {key: env[key] for key in keys if env.get(key, "") != ""}
    payload.update(_build_account_env(env))
    return payload


def _build_v2_pipeline_env(env: dict[str, str], project: str) -> dict[str, str]:
    payload = _build_batch_env(env)
    payload.update({
        "KIS_STATE_BACKEND": "firestore",
        "KIS_GCP_PROJECT": project,
        "KIS_FIRESTORE_DATABASE": env.get("KIS_FIRESTORE_DATABASE", "kis-portfolio-state"),
        "KIS_GCS_BUCKET": env.get("KIS_GCS_BUCKET", f"{project}-kis-portfolio-private"),
    })
    return payload


def _build_auth_runtime_flags(env: dict[str, str]) -> list[str]:
    return [
        "--cpu-boost",
        "--min-instances",
        env.get("KIS_CLOUD_RUN_AUTH_MIN_INSTANCES", DEFAULT_AUTH_MIN_INSTANCES),
        "--max-instances",
        env.get("KIS_CLOUD_RUN_AUTH_MAX_INSTANCES", DEFAULT_AUTH_MAX_INSTANCES),
    ]


def _build_remote_runtime_flags(env: dict[str, str]) -> list[str]:
    return [
        "--cpu-boost",
        "--concurrency",
        env.get("KIS_CLOUD_RUN_REMOTE_CONCURRENCY", DEFAULT_REMOTE_CONCURRENCY),
        "--min-instances",
        env.get("KIS_CLOUD_RUN_REMOTE_MIN_INSTANCES", DEFAULT_REMOTE_MIN_INSTANCES),
        "--max-instances",
        env.get("KIS_CLOUD_RUN_REMOTE_MAX_INSTANCES", DEFAULT_REMOTE_MAX_INSTANCES),
    ]


def _build_batch_runtime_flags(env: dict[str, str]) -> list[str]:
    runtime_flags = [
        "--task-timeout",
        env.get("KIS_CLOUD_RUN_BATCH_TASK_TIMEOUT", DEFAULT_BATCH_TASK_TIMEOUT),
        "--max-retries",
        env.get("KIS_CLOUD_RUN_BATCH_MAX_RETRIES", DEFAULT_BATCH_MAX_RETRIES),
    ]
    batch_service_account = env.get("KIS_CLOUD_RUN_BATCH_SERVICE_ACCOUNT", "").strip()
    if batch_service_account:
        runtime_flags.extend(["--service-account", batch_service_account])
    return runtime_flags


def _build_overseas_batch_command_args(env: dict[str, str]) -> str:
    account_label = env.get(
        "KIS_OVERSEAS_TRANSACTION_HISTORY_ACCOUNT_LABEL",
        DEFAULT_OVERSEAS_ACCOUNT_LABEL,
    )
    exchange = env.get(
        "KIS_OVERSEAS_TRANSACTION_HISTORY_EXCHANGE",
        DEFAULT_OVERSEAS_EXCHANGE,
    )
    return (
        "collect-overseas-transaction-history,"
        f"--date,today,--account-label,{account_label},--exchange,{exchange}"
    )


def _build_token_warmup_command_args(env: dict[str, str]) -> str:
    account_label = env.get(
        "KIS_TOKEN_WARMUP_ACCOUNT_LABEL",
        DEFAULT_TOKEN_WARMUP_ACCOUNT_LABEL,
    )
    valid_through = env.get(
        "KIS_TOKEN_WARMUP_VALID_THROUGH",
        DEFAULT_TOKEN_WARMUP_VALID_THROUGH,
    )
    return (
        "warm-token-cache,"
        f"--account-label,{account_label},--valid-through,{valid_through},"
        "--warm-service-health"
    )


def _is_secret_env_key(key: str) -> bool:
    return key in SECRET_ENV_EXACT_KEYS or any(key.startswith(prefix) for prefix in SECRET_ENV_PREFIXES)


def _secret_id_for_env_key(key: str) -> str:
    return f"kis-portfolio-{key.lower().replace('_', '-')}"


def _account_secret_keys(env: dict[str, str]) -> set[str]:
    return {
        f"{prefix}{label}"
        for label in _deploy_account_labels(env)
        for prefix in SECRET_ENV_PREFIXES
    }


def _validate_required(
    env: dict[str, str],
    required: list[str],
    *,
    secret_mode: str = "env-file",
) -> list[str]:
    if secret_mode == "secret-manager":
        return [key for key in required if env.get(key, "") == "" and not _is_secret_env_key(key)]
    return [key for key in required if env.get(key, "") == ""]


def _target_secret_keys(
    *,
    env: dict[str, str],
    payload: dict[str, str],
    required: list[str],
    include_account_secrets: bool,
) -> set[str]:
    secret_keys = {key for key in payload if _is_secret_env_key(key)}
    secret_keys.update(key for key in required if _is_secret_env_key(key))
    if include_account_secrets:
        secret_keys.update(_account_secret_keys(env))
    return secret_keys


def _split_runtime_env(
    *,
    env: dict[str, str],
    payload: dict[str, str],
    required: list[str],
    secret_mode: str,
    include_account_secrets: bool,
) -> tuple[dict[str, str], dict[str, str]]:
    if secret_mode != "secret-manager":
        return payload, {}

    plain_env = {key: value for key, value in payload.items() if not _is_secret_env_key(key)}
    secret_refs = {
        key: _secret_id_for_env_key(key)
        for key in sorted(
            _target_secret_keys(
                env=env,
                payload=payload,
                required=required,
                include_account_secrets=include_account_secrets,
            )
        )
    }
    return plain_env, secret_refs


def _build_secret_flags(secret_refs: dict[str, str]) -> list[str]:
    if not secret_refs:
        return []
    assignments = ",".join(
        f"{key}={secret_id}:latest"
        for key, secret_id in sorted(secret_refs.items())
    )
    return ["--set-secrets", assignments]


def _run_git(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )


def _git_stdout(command: list[str]) -> str | None:
    completed = _run_git(command)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _is_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS", "").lower() == "true"


def _deploy_source_errors(args: argparse.Namespace) -> list[str]:
    if args.dry_run:
        return []

    if _is_github_actions():
        github_ref = os.environ.get("GITHUB_REF", "")
        if github_ref != f"refs/heads/{PRODUCTION_BRANCH}":
            return [
                f"GitHub Actions deploys must run from refs/heads/{PRODUCTION_BRANCH}, "
                f"got {github_ref or '<unset>'}."
            ]
        return []

    if args.allow_local_source:
        if not args.reason or not args.reason.strip():
            return ["--allow-local-source requires --reason with a non-empty emergency reason."]
        return []

    errors: list[str] = []
    branch = _git_stdout(["branch", "--show-current"])
    status = _git_stdout(["status", "--porcelain=v1"])
    head = _git_stdout(["rev-parse", "HEAD"])
    origin = _git_stdout(["rev-parse", f"origin/{PRODUCTION_BRANCH}"])

    if branch != PRODUCTION_BRANCH:
        errors.append(f"local deploy requires branch {PRODUCTION_BRANCH}, got {branch or '<unknown>'}.")
    if status:
        errors.append("local deploy requires a clean worktree.")
    if not origin:
        errors.append(f"local deploy requires origin/{PRODUCTION_BRANCH}; run git fetch first.")
    elif head != origin:
        errors.append(f"local deploy requires HEAD to match origin/{PRODUCTION_BRANCH}.")
    return errors


def _enforce_deploy_source(args: argparse.Namespace) -> int:
    errors = _deploy_source_errors(args)
    if not errors:
        return 0
    print("Refusing Cloud Run deploy from an unapproved source:")
    for error in errors:
        print(f"- {error}")
    print("Use GitHub Actions production deployment, or pass --allow-local-source --reason for an emergency local deploy.")
    return 1


def _sanitize_label_value(value: str) -> str:
    sanitized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    sanitized = sanitized.strip("-")
    return sanitized[:63] or "unknown"


def _build_deploy_labels(target: str) -> dict[str, str]:
    source = "github-actions" if _is_github_actions() else "local"
    git_sha = os.environ.get("GITHUB_SHA", "").strip() or (_git_stdout(["rev-parse", "HEAD"]) or "")
    labels = {
        "deploy-source": source,
        "deploy-target": target,
    }
    if git_sha:
        labels["git-sha"] = git_sha[:40]
    github_run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if github_run_id:
        labels["github-run-id"] = github_run_id
    return {key: _sanitize_label_value(value) for key, value in labels.items()}


def _build_label_flags(target: str) -> list[str]:
    labels = _build_deploy_labels(target)
    if not labels:
        return []
    return ["--labels", ",".join(f"{key}={value}" for key, value in sorted(labels.items()))]


def _write_env_yaml(payload: dict[str, str]) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    with handle:
        for key in sorted(payload):
            handle.write(f"{key}: {json.dumps(payload[key], ensure_ascii=False)}\n")
    return handle.name


def _run(command: list[str], *, dry_run: bool) -> int:
    print("$", " ".join(command))
    if dry_run:
        return 0
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return completed.returncode


def _run_capture(command: list[str], *, dry_run: bool) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(command))
    if dry_run:
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )


def _build_run_job_uri(*, project: str, region: str, job: str) -> str:
    return f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run"


def _default_scheduler_service_account(project_number: str) -> str:
    return f"{project_number}-compute@developer.gserviceaccount.com"


def _resolve_project_number(env: dict[str, str], *, project: str | None, dry_run: bool) -> str | None:
    for key in ("GOOGLE_CLOUD_PROJECT_NUMBER", "GCLOUD_PROJECT_NUMBER"):
        value = env.get(key, "").strip()
        if value:
            return value

    if dry_run or not project:
        return None

    completed = _run_capture(
        [
            "gcloud",
            "projects",
            "describe",
            project,
            "--format=value(projectNumber)",
        ],
        dry_run=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _resolve_scheduler_service_account(
    env: dict[str, str],
    *,
    project: str | None,
    dry_run: bool,
) -> str | None:
    explicit = env.get("KIS_CLOUD_SCHEDULER_INVOKER_SERVICE_ACCOUNT", "").strip()
    if explicit:
        return explicit

    project_number = _resolve_project_number(env, project=project, dry_run=dry_run)
    if project_number:
        return _default_scheduler_service_account(project_number)
    return None


def _build_scheduler_http_command(
    *,
    action: str,
    scheduler: str,
    scheduler_region: str,
    schedule: str,
    time_zone: str,
    uri: str,
    service_account: str,
    project: str | None,
) -> list[str]:
    header_flag = "--headers" if action == "create" else "--update-headers"
    command = [
        "gcloud",
        "scheduler",
        "jobs",
        action,
        "http",
        scheduler,
        "--location",
        scheduler_region,
        "--schedule",
        schedule,
        "--time-zone",
        time_zone,
        "--uri",
        uri,
        "--http-method",
        "POST",
        header_flag,
        "Content-Type=application/json",
        "--message-body",
        "{}",
        "--oauth-service-account-email",
        service_account,
    ]
    if project:
        command.extend(["--project", project])
    return command


def _build_job_invoker_binding_command(
    *,
    job: str,
    region: str,
    service_account: str,
    project: str | None,
) -> list[str]:
    command = [
        "gcloud",
        "run",
        "jobs",
        "add-iam-policy-binding",
        job,
        "--region",
        region,
        "--member",
        f"serviceAccount:{service_account}",
        "--role",
        "roles/run.invoker",
    ]
    if project:
        command.extend(["--project", project])
    return command


def _scheduler_exists(
    *,
    scheduler: str,
    scheduler_region: str,
    project: str | None,
    dry_run: bool,
) -> bool:
    command = [
        "gcloud",
        "scheduler",
        "jobs",
        "describe",
        scheduler,
        "--location",
        scheduler_region,
    ]
    if project:
        command.extend(["--project", project])

    completed = _run_capture(command, dry_run=dry_run)
    if completed.returncode == 0:
        return True
    if dry_run:
        return False

    stderr = completed.stderr.lower()
    if "not found" in stderr or "not_found" in stderr:
        return False

    if completed.stdout.strip():
        print(completed.stdout, file=sys.stderr, end="")
    if completed.stderr.strip():
        print(completed.stderr, file=sys.stderr, end="")
    raise RuntimeError("Failed to check existing Cloud Scheduler job state.")


def _deploy_service_or_job(
    *,
    args: argparse.Namespace,
    project: str | None,
    payload: dict[str, str],
    secret_refs: dict[str, str],
    runtime_flags: list[str],
    target_name: str,
    command: str,
    command_args: str,
    is_job: bool,
) -> int:
    env_yaml_path = _write_env_yaml(payload)
    try:
        if is_job:
            command = [
                "gcloud",
                "run",
                "jobs",
                "deploy",
                target_name,
                "--source",
                ".",
                "--region",
                args.region,
                "--env-vars-file",
                env_yaml_path,
                "--command",
                command,
            ]
            command.extend(["--args", command_args])
        else:
            command = [
                "gcloud",
                "run",
                "deploy",
                target_name,
                "--source",
                ".",
                "--region",
                args.region,
                "--allow-unauthenticated",
                "--env-vars-file",
                env_yaml_path,
                "--command",
                command,
            ]
            command.extend(["--args", command_args])
        command.extend(runtime_flags)
        command.extend(_build_secret_flags(secret_refs))
        command.extend(_build_label_flags(args.target))
        if project:
            command.extend(["--project", project])
        return _run(command, dry_run=args.dry_run)
    finally:
        try:
            os.unlink(env_yaml_path)
        except FileNotFoundError:
            pass


def _build_release_image(args: argparse.Namespace, *, project: str) -> str | None:
    sha = os.environ.get("GITHUB_SHA", "").strip() or (_git_stdout(["rev-parse", "HEAD"]) or "unknown")
    tag = f"{args.region}-docker.pkg.dev/{project}/kis-portfolio/kis-portfolio:{sha[:40]}"
    code = _run(["gcloud", "builds", "submit", "--tag", tag, "--project", project, "."], dry_run=args.dry_run)
    if code != 0:
        return None
    if args.dry_run:
        return f"{tag}@sha256:dry-run"
    completed = _run_capture(
        ["gcloud", "artifacts", "docker", "images", "describe", tag,
         "--project", project, "--format=value(image_summary.digest)"],
        dry_run=False,
    )
    digest = completed.stdout.strip() if completed.returncode == 0 else ""
    return f"{tag.split(':', 1)[0]}@{digest}" if digest.startswith("sha256:") else None


def _deploy_v2_core_jobs(
    args: argparse.Namespace,
    *,
    env: dict[str, str],
    project: str,
) -> int:
    required = _required_keys_for_batch(env)
    payload, secret_refs = _split_runtime_env(
        env=env,
        payload=_build_v2_pipeline_env(env, project),
        required=required,
        secret_mode=args.secret_mode,
        include_account_secrets=True,
    )
    missing = _validate_required(env, required, secret_mode=args.secret_mode)
    if missing:
        print("Missing required environment variables:")
        for key in missing:
            print(f"- {key}")
        return 1
    image = _build_release_image(args, project=project)
    if not image:
        print("Failed to resolve the build-once image digest.")
        return 1
    service_account = env.get(
        "KIS_CLOUD_RUN_V2_PIPELINE_SERVICE_ACCOUNT",
        f"kis-portfolio-pipeline@{project}.iam.gserviceaccount.com",
    )
    env_yaml_path = _write_env_yaml(payload)
    try:
        for slot, default_job in DEFAULT_V2_CORE_JOBS.items():
            key = f"KIS_V2_CORE_JOB_{slot.split('-', 1)[1]}"
            job = env.get(key, default_job)
            command = [
                "gcloud", "run", "jobs", "deploy", job,
                "--image", image, "--region", args.region,
                "--env-vars-file", env_yaml_path,
                "--command", "kis-portfolio-batch",
                "--args", f"collect-owned-portfolio-v2,--date,today,--slot,{slot},--partition-key,all-accounts",
                "--task-timeout", env.get("KIS_CLOUD_RUN_BATCH_TASK_TIMEOUT", DEFAULT_BATCH_TASK_TIMEOUT),
                "--max-retries", "0", "--service-account", service_account,
                *_build_secret_flags(secret_refs), *_build_label_flags("v2-core-batch"),
                "--project", project,
            ]
            if _run(command, dry_run=args.dry_run) != 0:
                return 1
    finally:
        try:
            os.unlink(env_yaml_path)
        except FileNotFoundError:
            pass
    print(f"build-once image digest deployed to {len(DEFAULT_V2_CORE_JOBS)} fixed-argument jobs: {image}")
    return 0


def _deploy_v2_core_schedulers(
    args: argparse.Namespace,
    *,
    env: dict[str, str],
    project: str,
) -> int:
    scheduler_sa = env.get(
        "KIS_V2_SCHEDULER_INVOKER_SERVICE_ACCOUNT",
        f"kis-portfolio-scheduler@{project}.iam.gserviceaccount.com",
    )
    for slot, job in DEFAULT_V2_CORE_JOBS.items():
        suffix = slot.split("-", 1)[1]
        job = env.get(f"KIS_V2_CORE_JOB_{suffix}", job)
        scheduler = env.get(f"KIS_V2_CORE_SCHEDULER_{suffix}", f"{job}-schedule")
        code = _deploy_scheduler_target(
            args=args, env={**env, "KIS_CLOUD_SCHEDULER_INVOKER_SERVICE_ACCOUNT": scheduler_sa},
            project=project, job=job, scheduler=scheduler,
            scheduler_region=args.scheduler_region or args.region,
            schedule=env.get(f"KIS_V2_CORE_SCHEDULE_{suffix}", DEFAULT_V2_CORE_SCHEDULES[slot]),
            time_zone="Asia/Seoul",
        )
        if code != 0:
            return code
    return 0


def _deploy_wi021_s06_job(
    args: argparse.Namespace,
    *,
    env: dict[str, str],
    project: str,
) -> int:
    required = _required_keys_for_batch(env)
    payload, secret_refs = _split_runtime_env(
        env=env,
        payload=_build_batch_env(env),
        required=required,
        secret_mode=args.secret_mode,
        include_account_secrets=True,
    )
    missing = _validate_required(env, required, secret_mode=args.secret_mode)
    if missing:
        print("Missing required environment variables:")
        for key in missing:
            print(f"- {key}")
        return 1
    image = _build_release_image(args, project=project)
    if not image or "@sha256:" not in image:
        print("Failed to resolve the immutable build-once image digest.")
        return 1
    git_sha = os.environ.get("GITHUB_SHA", "").strip() or (_git_stdout(["rev-parse", "HEAD"]) or "")
    if len(git_sha) < 7:
        print("Failed to resolve release Git SHA.")
        return 1
    payload.update({
        "KIS_GCP_PROJECT": project,
        "KIS_GCS_BUCKET": env.get("KIS_GCS_BUCKET", f"{project}-kis-portfolio-private"),
        "KIS_RELEASE_IMAGE_DIGEST": image.split("@", 1)[1],
        "KIS_RELEASE_GIT_SHA": git_sha,
    })
    service_account = env.get(
        "KIS_CLOUD_RUN_V2_PIPELINE_SERVICE_ACCOUNT",
        f"kis-portfolio-pipeline@{project}.iam.gserviceaccount.com",
    )
    job = args.job or env.get("KIS_WI021_S06_JOB_NAME") or DEFAULT_WI021_S06_JOB
    command_args = (
        "run-wi021-s06,--start-date,20230828,--end-date,20260828,"
        "--expected-plan-hash,0755656ed8151a91,--expected-budget-hash,0a4abf9b795f9d73,"
        f"--project,{project},--bucket,{payload['KIS_GCS_BUCKET']}"
    )
    env_yaml_path = _write_env_yaml(payload)
    try:
        command = [
            "gcloud", "run", "jobs", "deploy", job,
            "--image", image,
            "--region", args.region,
            "--env-vars-file", env_yaml_path,
            "--command", "kis-portfolio-batch",
            "--args", command_args,
            "--tasks", "1",
            "--parallelism", "1",
            "--task-timeout", env.get("KIS_CLOUD_RUN_WI021_S06_TASK_TIMEOUT", DEFAULT_WI021_S06_TASK_TIMEOUT),
            "--max-retries", "0",
            "--service-account", service_account,
            *_build_secret_flags(secret_refs),
            *_build_label_flags("wi021-s06"),
            "--project", project,
        ]
        return _run(command, dry_run=args.dry_run)
    finally:
        try:
            os.unlink(env_yaml_path)
        except FileNotFoundError:
            pass


def _deploy_scheduler_target(
    *,
    args: argparse.Namespace,
    env: dict[str, str],
    project: str,
    job: str,
    scheduler: str,
    scheduler_region: str,
    schedule: str,
    time_zone: str,
) -> int:
    scheduler_service_account = _resolve_scheduler_service_account(
        env,
        project=project,
        dry_run=args.dry_run,
    )
    if not scheduler_service_account:
        print("Missing required environment variables:")
        print("- KIS_CLOUD_SCHEDULER_INVOKER_SERVICE_ACCOUNT or GOOGLE_CLOUD_PROJECT_NUMBER")
        return 1

    binding_code = _run(
        _build_job_invoker_binding_command(
            job=job,
            region=args.region,
            service_account=scheduler_service_account,
            project=project,
        ),
        dry_run=args.dry_run,
    )
    if binding_code != 0:
        return binding_code

    action = "create"
    if not args.dry_run and _scheduler_exists(
        scheduler=scheduler,
        scheduler_region=scheduler_region,
        project=project,
        dry_run=False,
    ):
        action = "update"

    return _run(
        _build_scheduler_http_command(
            action=action,
            scheduler=scheduler,
            scheduler_region=scheduler_region,
            schedule=schedule,
            time_zone=time_zone,
            uri=_build_run_job_uri(project=project, region=args.region, job=job),
            service_account=scheduler_service_account,
            project=project,
        ),
        dry_run=args.dry_run,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        choices=(
            "auth",
            "remote",
            "batch",
            "scheduler",
            "overseas-batch",
            "overseas-scheduler",
            "token-warmup-batch",
            "token-warmup-scheduler",
            "v2-core-batch",
            "v2-core-schedulers",
            "wi021-s06",
        ),
    )
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--project")
    parser.add_argument("--service")
    parser.add_argument("--job")
    parser.add_argument("--scheduler")
    parser.add_argument("--scheduler-region")
    parser.add_argument("--schedule")
    parser.add_argument("--time-zone")
    parser.add_argument(
        "--secret-mode",
        choices=("secret-manager", "env-file"),
        default=os.environ.get("KIS_DEPLOY_SECRET_MODE", DEFAULT_DEPLOY_SECRET_MODE),
    )
    parser.add_argument("--allow-local-source", action="store_true")
    parser.add_argument("--reason")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env = _load_env()
    project = args.project or env.get("GOOGLE_CLOUD_PROJECT") or env.get("GCLOUD_PROJECT")

    source_status = _enforce_deploy_source(args)
    if source_status != 0:
        return source_status

    if args.target == "auth":
        required = _required_keys_for_auth(env)
        missing = _validate_required(env, required, secret_mode=args.secret_mode)
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        payload, secret_refs = _split_runtime_env(
            env=env,
            payload=_build_auth_env(env),
            required=required,
            secret_mode=args.secret_mode,
            include_account_secrets=False,
        )
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=payload,
            secret_refs=secret_refs,
            runtime_flags=_build_auth_runtime_flags(env),
            target_name=args.service or DEFAULT_AUTH_SERVICE,
            command="kis-portfolio-auth",
            command_args="",
            is_job=False,
        )

    if args.target == "remote":
        required = _required_keys_for_remote(env)
        missing = _validate_required(env, required, secret_mode=args.secret_mode)
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        payload, secret_refs = _split_runtime_env(
            env=env,
            payload=_build_remote_env(env),
            required=required,
            secret_mode=args.secret_mode,
            include_account_secrets=True,
        )
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=payload,
            secret_refs=secret_refs,
            runtime_flags=_build_remote_runtime_flags(env),
            target_name=args.service or DEFAULT_REMOTE_SERVICE,
            command="kis-portfolio-remote",
            command_args="",
            is_job=False,
        )

    if args.target == "batch":
        required = _required_keys_for_batch(env)
        missing = _validate_required(env, required, secret_mode=args.secret_mode)
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        payload, secret_refs = _split_runtime_env(
            env=env,
            payload=_build_batch_env(env),
            required=required,
            secret_mode=args.secret_mode,
            include_account_secrets=True,
        )
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=payload,
            secret_refs=secret_refs,
            runtime_flags=_build_batch_runtime_flags(env),
            target_name=args.job or env.get("KIS_BATCH_JOB_NAME") or DEFAULT_BATCH_JOB,
            command="kis-portfolio-batch",
            command_args="collect-domestic-order-history,--date,today",
            is_job=True,
        )

    if args.target == "overseas-batch":
        required = _required_keys_for_batch(env)
        missing = _validate_required(env, required, secret_mode=args.secret_mode)
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        payload, secret_refs = _split_runtime_env(
            env=env,
            payload=_build_batch_env(env),
            required=required,
            secret_mode=args.secret_mode,
            include_account_secrets=True,
        )
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=payload,
            secret_refs=secret_refs,
            runtime_flags=_build_batch_runtime_flags(env),
            target_name=args.job or env.get("KIS_OVERSEAS_BATCH_JOB_NAME") or DEFAULT_OVERSEAS_BATCH_JOB,
            command="kis-portfolio-batch",
            command_args=_build_overseas_batch_command_args(env),
            is_job=True,
        )

    if args.target == "token-warmup-batch":
        required = _required_keys_for_batch(env)
        missing = _validate_required(env, required, secret_mode=args.secret_mode)
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        payload, secret_refs = _split_runtime_env(
            env=env,
            payload=_build_batch_env(env),
            required=required,
            secret_mode=args.secret_mode,
            include_account_secrets=True,
        )
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=payload,
            secret_refs=secret_refs,
            runtime_flags=_build_batch_runtime_flags(env),
            target_name=args.job or env.get("KIS_TOKEN_WARMUP_JOB_NAME") or DEFAULT_TOKEN_WARMUP_JOB,
            command="kis-portfolio-batch",
            command_args=_build_token_warmup_command_args(env),
            is_job=True,
        )

    if args.target == "v2-core-batch":
        if not project:
            print("Missing required environment variables:\n- GOOGLE_CLOUD_PROJECT")
            return 1
        return _deploy_v2_core_jobs(args, env=env, project=project)

    if args.target == "wi021-s06":
        if not project:
            print("Missing required environment variables:\n- GOOGLE_CLOUD_PROJECT")
            return 1
        return _deploy_wi021_s06_job(args, env=env, project=project)

    if not project:
        print("Missing required environment variables:")
        print("- GOOGLE_CLOUD_PROJECT")
        return 1

    if args.target == "scheduler":
        return _deploy_scheduler_target(
            args=args,
            env=env,
            project=project,
            job=args.job or env.get("KIS_BATCH_JOB_NAME") or DEFAULT_BATCH_JOB,
            scheduler=args.scheduler or env.get("KIS_BATCH_SCHEDULER_NAME") or DEFAULT_BATCH_SCHEDULER,
            scheduler_region=args.scheduler_region or env.get("KIS_CLOUD_SCHEDULER_REGION") or args.region,
            schedule=args.schedule or env.get("KIS_BATCH_ORDER_HISTORY_SCHEDULE") or DEFAULT_BATCH_SCHEDULE,
            time_zone=args.time_zone or env.get("KIS_BATCH_ORDER_HISTORY_TIME_ZONE") or DEFAULT_BATCH_TIME_ZONE,
        )

    if args.target == "token-warmup-scheduler":
        return _deploy_scheduler_target(
            args=args,
            env=env,
            project=project,
            job=args.job or env.get("KIS_TOKEN_WARMUP_JOB_NAME") or DEFAULT_TOKEN_WARMUP_JOB,
            scheduler=args.scheduler or env.get("KIS_TOKEN_WARMUP_SCHEDULER_NAME") or DEFAULT_TOKEN_WARMUP_SCHEDULER,
            scheduler_region=args.scheduler_region or env.get("KIS_CLOUD_SCHEDULER_REGION") or args.region,
            schedule=args.schedule or env.get("KIS_TOKEN_WARMUP_SCHEDULE") or DEFAULT_TOKEN_WARMUP_SCHEDULE,
            time_zone=args.time_zone or env.get("KIS_TOKEN_WARMUP_TIME_ZONE") or DEFAULT_TOKEN_WARMUP_TIME_ZONE,
        )

    if args.target == "v2-core-schedulers":
        return _deploy_v2_core_schedulers(args, env=env, project=project)

    return _deploy_scheduler_target(
        args=args,
        env=env,
        project=project,
        job=args.job or env.get("KIS_OVERSEAS_BATCH_JOB_NAME") or DEFAULT_OVERSEAS_BATCH_JOB,
        scheduler=args.scheduler or env.get("KIS_OVERSEAS_BATCH_SCHEDULER_NAME") or DEFAULT_OVERSEAS_BATCH_SCHEDULER,
        scheduler_region=args.scheduler_region or env.get("KIS_CLOUD_SCHEDULER_REGION") or args.region,
        schedule=args.schedule or env.get("KIS_OVERSEAS_TRANSACTION_HISTORY_SCHEDULE") or DEFAULT_OVERSEAS_BATCH_SCHEDULE,
        time_zone=args.time_zone or env.get("KIS_OVERSEAS_TRANSACTION_HISTORY_TIME_ZONE") or DEFAULT_OVERSEAS_BATCH_TIME_ZONE,
    )


if __name__ == "__main__":
    sys.exit(main())
