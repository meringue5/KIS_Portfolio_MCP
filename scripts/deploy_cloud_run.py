"""Deploy KIS Cloud Run services, jobs, and scheduler triggers from local source."""

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
DEFAULT_AUTH_MAX_INSTANCES = "1"
DEFAULT_REMOTE_CONCURRENCY = "20"
DEFAULT_REMOTE_MIN_INSTANCES = "0"
DEFAULT_REMOTE_MAX_INSTANCES = "1"
DEFAULT_CHATGPT_REMOTE_AUTH_MODE = "oauth"
DEFAULT_BATCH_TASK_TIMEOUT = "1800s"
DEFAULT_BATCH_MAX_RETRIES = "0"
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
    }
    payload = {key: env[key] for key in keys if env.get(key, "") != ""}
    payload["KIS_REMOTE_AUTH_MODE"] = _effective_remote_auth_mode(env)
    payload.update(_collect_prefixed(env, ("KIS_APP_KEY_", "KIS_APP_SECRET_", "KIS_CANO_", "KIS_ACNT_PRDT_CD_")))
    return payload


def _build_batch_env(env: dict[str, str]) -> dict[str, str]:
    keys = {
        "KIS_DB_MODE",
        "MOTHERDUCK_DATABASE",
        "MOTHERDUCK_TOKEN",
        "KIS_ACCOUNT_TYPE",
        "KIS_DATA_DIR",
        "KIS_TOKEN_ENCRYPTION_KEY",
    }
    payload = {key: env[key] for key in keys if env.get(key, "") != ""}
    payload.update(_collect_prefixed(env, ("KIS_APP_KEY_", "KIS_APP_SECRET_", "KIS_CANO_", "KIS_ACNT_PRDT_CD_")))
    return payload


def _build_auth_runtime_flags(env: dict[str, str]) -> list[str]:
    return [
        "--max-instances",
        env.get("KIS_CLOUD_RUN_AUTH_MAX_INSTANCES", DEFAULT_AUTH_MAX_INSTANCES),
    ]


def _build_remote_runtime_flags(env: dict[str, str]) -> list[str]:
    return [
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
        "run,kis-portfolio-batch,collect-overseas-transaction-history,"
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
        "run,kis-portfolio-batch,warm-token-cache,"
        f"--account-label,{account_label},--valid-through,{valid_through},--dry-run"
    )


def _validate_required(env: dict[str, str], required: list[str]) -> list[str]:
    return [key for key in required if env.get(key, "") == ""]


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
    runtime_flags: list[str],
    target_name: str,
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
                "uv",
                "--args",
                command_args,
            ]
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
                "uv",
                "--args",
                command_args,
            ]
        command.extend(runtime_flags)
        if project:
            command.extend(["--project", project])
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
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env = _load_env()
    project = args.project or env.get("GOOGLE_CLOUD_PROJECT") or env.get("GCLOUD_PROJECT")

    if args.target == "auth":
        missing = _validate_required(env, _required_keys_for_auth(env))
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=_build_auth_env(env),
            runtime_flags=_build_auth_runtime_flags(env),
            target_name=args.service or DEFAULT_AUTH_SERVICE,
            command_args="run,kis-portfolio-auth",
            is_job=False,
        )

    if args.target == "remote":
        missing = _validate_required(env, _required_keys_for_remote(env))
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=_build_remote_env(env),
            runtime_flags=_build_remote_runtime_flags(env),
            target_name=args.service or DEFAULT_REMOTE_SERVICE,
            command_args="run,kis-portfolio-remote",
            is_job=False,
        )

    if args.target == "batch":
        missing = _validate_required(env, _required_keys_for_batch(env))
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=_build_batch_env(env),
            runtime_flags=_build_batch_runtime_flags(env),
            target_name=args.job or env.get("KIS_BATCH_JOB_NAME") or DEFAULT_BATCH_JOB,
            command_args="run,kis-portfolio-batch,collect-domestic-order-history,--date,today",
            is_job=True,
        )

    if args.target == "overseas-batch":
        missing = _validate_required(env, _required_keys_for_batch(env))
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=_build_batch_env(env),
            runtime_flags=_build_batch_runtime_flags(env),
            target_name=args.job or env.get("KIS_OVERSEAS_BATCH_JOB_NAME") or DEFAULT_OVERSEAS_BATCH_JOB,
            command_args=_build_overseas_batch_command_args(env),
            is_job=True,
        )

    if args.target == "token-warmup-batch":
        missing = _validate_required(env, _required_keys_for_batch(env))
        if missing:
            print("Missing required environment variables:")
            for key in missing:
                print(f"- {key}")
            return 1
        return _deploy_service_or_job(
            args=args,
            project=project,
            payload=_build_batch_env(env),
            runtime_flags=_build_batch_runtime_flags(env),
            target_name=args.job or env.get("KIS_TOKEN_WARMUP_JOB_NAME") or DEFAULT_TOKEN_WARMUP_JOB,
            command_args=_build_token_warmup_command_args(env),
            is_job=True,
        )

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
