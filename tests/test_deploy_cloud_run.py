import argparse
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy_cloud_run.py"
SPEC = importlib.util.spec_from_file_location("deploy_cloud_run", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
deploy_cloud_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy_cloud_run)


def test_remote_deploy_defaults_to_chatgpt_friendly_oauth():
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "MOTHERDUCK_TOKEN": "md-token",
        "KIS_TOKEN_ENCRYPTION_KEY": "enc-key",
        "KIS_AUTH_ISSUER_URL": "https://auth.example.com",
        "KIS_RESOURCE_SERVER_URL": "https://resource.example.com/mcp",
        "KIS_AUTH_REQUIRED_SCOPES": "mcp:read",
        "KIS_AUTH_TOKEN_PEPPER": "pepper",
        "KIS_REAL_API_MIN_INTERVAL_SECONDS": "0.15",
        "KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS": "1.0",
        "KIS_TOKEN_MIN_INTERVAL_SECONDS": "1.0",
        "KIS_RATE_LIMIT_RETRY_DELAY_SECONDS": "1.0",
        "KIS_REAL_API_MAX_IN_FLIGHT": "3",
        "KIS_CIRCUIT_FAILURE_THRESHOLD": "5",
    }

    required = deploy_cloud_run._required_keys_for_remote(env)
    payload = deploy_cloud_run._build_remote_env(env)

    assert deploy_cloud_run._effective_remote_auth_mode(env) == "oauth"
    assert "KIS_REMOTE_AUTH_TOKEN" not in required
    assert payload["KIS_REMOTE_AUTH_MODE"] == "oauth"
    assert payload["KIS_REAL_API_MIN_INTERVAL_SECONDS"] == "0.15"
    assert payload["KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS"] == "1.0"
    assert payload["KIS_TOKEN_MIN_INTERVAL_SECONDS"] == "1.0"
    assert payload["KIS_RATE_LIMIT_RETRY_DELAY_SECONDS"] == "1.0"
    assert payload["KIS_REAL_API_MAX_IN_FLIGHT"] == "3"
    assert payload["KIS_CIRCUIT_FAILURE_THRESHOLD"] == "5"


def test_secret_manager_uses_deterministic_secret_ids():
    assert (
        deploy_cloud_run._secret_id_for_env_key("KIS_APP_SECRET_RIA")
        == "kis-portfolio-kis-app-secret-ria"
    )


def test_secret_manager_validation_allows_secret_values_to_live_in_gcp():
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "KIS_AUTH_ISSUER_URL": "https://auth.example.com",
        "KIS_RESOURCE_SERVER_URL": "https://resource.example.com/mcp",
        "KIS_AUTH_REQUIRED_SCOPES": "mcp:read",
    }

    required = deploy_cloud_run._required_keys_for_remote(env)
    missing = deploy_cloud_run._validate_required(
        env,
        required,
        secret_mode="secret-manager",
    )

    assert missing == []


def test_secret_manager_split_removes_secret_values_and_adds_account_refs():
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "MOTHERDUCK_TOKEN": "md-token",
        "KIS_TOKEN_ENCRYPTION_KEY": "enc-key",
        "KIS_AUTH_ISSUER_URL": "https://auth.example.com",
        "KIS_RESOURCE_SERVER_URL": "https://resource.example.com/mcp",
        "KIS_AUTH_REQUIRED_SCOPES": "mcp:read",
        "KIS_AUTH_TOKEN_PEPPER": "pepper",
        "KIS_APP_KEY_RIA": "app-key",
        "KIS_APP_SECRET_RIA": "app-secret",
        "KIS_CANO_RIA": "12345678",
    }

    required = deploy_cloud_run._required_keys_for_remote(env)
    plain_env, secret_refs = deploy_cloud_run._split_runtime_env(
        env=env,
        payload=deploy_cloud_run._build_remote_env(env),
        required=required,
        secret_mode="secret-manager",
        include_account_secrets=True,
    )

    assert "MOTHERDUCK_TOKEN" not in plain_env
    assert "KIS_TOKEN_ENCRYPTION_KEY" not in plain_env
    assert "KIS_APP_SECRET_RIA" not in plain_env
    assert plain_env["KIS_ACNT_PRDT_CD_IRP"] == "29"
    assert secret_refs["MOTHERDUCK_TOKEN"] == "kis-portfolio-motherduck-token"
    assert secret_refs["KIS_TOKEN_ENCRYPTION_KEY"] == "kis-portfolio-kis-token-encryption-key"
    assert secret_refs["KIS_APP_KEY_RIA"] == "kis-portfolio-kis-app-key-ria"
    assert secret_refs["KIS_APP_SECRET_PENSION"] == "kis-portfolio-kis-app-secret-pension"


def test_secret_flags_do_not_include_secret_values():
    flags = deploy_cloud_run._build_secret_flags({
        "KIS_APP_SECRET_RIA": "kis-portfolio-kis-app-secret-ria",
    })

    assert flags == ["--set-secrets", "KIS_APP_SECRET_RIA=kis-portfolio-kis-app-secret-ria:latest"]
    assert "super-secret-value" not in " ".join(flags)


def test_auth_deploy_defaults_to_scale_to_zero_with_startup_cpu_boost():
    env = {}

    runtime_flags = deploy_cloud_run._build_auth_runtime_flags(env)

    assert runtime_flags == [
        "--cpu-boost",
        "--min-instances",
        "0",
        "--max-instances",
        "1",
    ]


def test_auth_deploy_keeps_explicit_max_instance_override():
    env = {
        "KIS_CLOUD_RUN_AUTH_MIN_INSTANCES": "0",
        "KIS_CLOUD_RUN_AUTH_MAX_INSTANCES": "2",
    }

    runtime_flags = deploy_cloud_run._build_auth_runtime_flags(env)

    assert runtime_flags == [
        "--cpu-boost",
        "--min-instances",
        "0",
        "--max-instances",
        "2",
    ]


def test_remote_deploy_keeps_explicit_bearer_override():
    env = {
        "KIS_DB_MODE": "local",
        "KIS_TOKEN_ENCRYPTION_KEY": "enc-key",
        "KIS_REMOTE_AUTH_MODE": "bearer",
        "KIS_REMOTE_AUTH_TOKEN": "shared-token",
    }

    required = deploy_cloud_run._required_keys_for_remote(env)
    payload = deploy_cloud_run._build_remote_env(env)

    assert deploy_cloud_run._effective_remote_auth_mode(env) == "bearer"
    assert "KIS_REMOTE_AUTH_TOKEN" in required
    assert payload["KIS_REMOTE_AUTH_MODE"] == "bearer"


def test_batch_deploy_builds_batch_runtime_env_without_remote_auth_fields():
    env = {
        "KIS_DB_MODE": "local",
        "KIS_TOKEN_ENCRYPTION_KEY": "enc-key",
        "KIS_ACCOUNT_TYPE": "REAL",
        "KIS_DATA_DIR": "var",
        "KIS_APP_KEY_RIA": "app-key",
        "KIS_APP_SECRET_RIA": "app-secret",
        "KIS_CANO_RIA": "12345678",
        "KIS_ACNT_PRDT_CD_RIA": "01",
        "KIS_REMOTE_AUTH_MODE": "oauth",
        "KIS_RESOURCE_SERVER_URL": "https://remote.example.com/mcp",
        "KIS_REAL_API_MIN_INTERVAL_SECONDS": "0.15",
        "KIS_RATE_LIMIT_RETRY_DELAY_SECONDS": "1.0",
        "KIS_API_MAX_QUEUE_SIZE": "50",
        "KIS_CIRCUIT_OPEN_SECONDS": "20.0",
    }

    required = deploy_cloud_run._required_keys_for_batch(env)
    payload = deploy_cloud_run._build_batch_env(env)

    assert required == ["KIS_DB_MODE", "KIS_TOKEN_ENCRYPTION_KEY"]
    assert payload["KIS_TOKEN_ENCRYPTION_KEY"] == "enc-key"
    assert payload["KIS_APP_KEY_RIA"] == "app-key"
    assert payload["KIS_ACNT_PRDT_CD_RIA"] == "01"
    assert payload["KIS_RESOURCE_SERVER_URL"] == "https://remote.example.com/mcp"
    assert payload["KIS_REAL_API_MIN_INTERVAL_SECONDS"] == "0.15"
    assert payload["KIS_RATE_LIMIT_RETRY_DELAY_SECONDS"] == "1.0"
    assert payload["KIS_API_MAX_QUEUE_SIZE"] == "50"
    assert payload["KIS_CIRCUIT_OPEN_SECONDS"] == "20.0"
    assert "KIS_REMOTE_AUTH_MODE" not in payload


def test_batch_runtime_flags_apply_to_domestic_and_overseas_jobs():
    env = {
        "KIS_CLOUD_RUN_BATCH_TASK_TIMEOUT": "2400s",
        "KIS_CLOUD_RUN_BATCH_MAX_RETRIES": "1",
        "KIS_CLOUD_RUN_BATCH_SERVICE_ACCOUNT": "batch@example.iam.gserviceaccount.com",
    }

    runtime_flags = deploy_cloud_run._build_batch_runtime_flags(env)

    assert runtime_flags == [
        "--task-timeout",
        "2400s",
        "--max-retries",
        "1",
        "--service-account",
        "batch@example.iam.gserviceaccount.com",
    ]


def test_overseas_batch_command_uses_default_account_and_exchange():
    command_args = deploy_cloud_run._build_overseas_batch_command_args({})

    assert command_args == (
        "collect-overseas-transaction-history,"
        "--date,today,--account-label,brokerage,--exchange,NAS"
    )


def test_overseas_batch_command_allows_account_and_exchange_override():
    command_args = deploy_cloud_run._build_overseas_batch_command_args({
        "KIS_OVERSEAS_TRANSACTION_HISTORY_ACCOUNT_LABEL": "ria",
        "KIS_OVERSEAS_TRANSACTION_HISTORY_EXCHANGE": "NYSE",
    })

    assert "--account-label,ria" in command_args
    assert "--exchange,NYSE" in command_args


def test_token_warmup_batch_command_refreshes_tokens():
    command_args = deploy_cloud_run._build_token_warmup_command_args({})

    assert command_args == (
        "warm-token-cache,"
        "--account-label,all,--valid-through,16:30,--warm-service-health"
    )


def test_remote_runtime_flags_default_to_scale_to_zero_with_startup_cpu_boost():
    env = {}

    runtime_flags = deploy_cloud_run._build_remote_runtime_flags(env)

    assert runtime_flags == [
        "--cpu-boost",
        "--concurrency",
        "20",
        "--min-instances",
        "0",
        "--max-instances",
        "1",
    ]


def test_remote_runtime_flags_support_min_instance_override():
    env = {
        "KIS_CLOUD_RUN_REMOTE_MIN_INSTANCES": "1",
    }

    runtime_flags = deploy_cloud_run._build_remote_runtime_flags(env)

    assert "--min-instances" in runtime_flags
    assert runtime_flags[runtime_flags.index("--min-instances") + 1] == "1"


def test_cloud_run_deploy_uses_installed_console_script(monkeypatch):
    args = argparse.Namespace(region="asia-northeast3", target="remote", dry_run=True)
    captured = {}

    def fake_run(command, dry_run=False):
        captured["command"] = command
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(deploy_cloud_run, "_run", fake_run)

    result = deploy_cloud_run._deploy_service_or_job(
        args=args,
        project="kis-portfolio-prod",
        payload={"KIS_DB_MODE": "motherduck"},
        secret_refs={},
        runtime_flags=["--min-instances", "1"],
        target_name="kis-portfolio-remote",
        command="kis-portfolio-remote",
        command_args="",
        is_job=False,
    )

    command = captured["command"]
    assert result == 0
    assert captured["dry_run"] is True
    assert "--command" in command
    assert command[command.index("--command") + 1] == "kis-portfolio-remote"
    assert "uv" not in command
    assert command[command.index("--args") + 1] == ""


def test_cloud_run_job_deploy_uses_batch_console_script(monkeypatch):
    args = argparse.Namespace(region="asia-northeast3", target="batch", dry_run=True)
    captured = {}

    def fake_run(command, dry_run=False):
        captured["command"] = command
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(deploy_cloud_run, "_run", fake_run)

    result = deploy_cloud_run._deploy_service_or_job(
        args=args,
        project="kis-portfolio-prod",
        payload={"KIS_DB_MODE": "motherduck"},
        secret_refs={},
        runtime_flags=["--task-timeout", "1800s"],
        target_name="kis-portfolio-domestic-order-history",
        command="kis-portfolio-batch",
        command_args="collect-domestic-order-history,--date,today",
        is_job=True,
    )

    command = captured["command"]
    assert result == 0
    assert command[command.index("--command") + 1] == "kis-portfolio-batch"
    assert command[command.index("--args") + 1] == "collect-domestic-order-history,--date,today"
    assert "uv" not in command


def test_scheduler_service_account_defaults_to_project_compute_account():
    env = {
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789012",
    }

    service_account = deploy_cloud_run._resolve_scheduler_service_account(
        env,
        project="kis-portfolio-prod",
        dry_run=True,
    )

    assert service_account == "123456789012-compute@developer.gserviceaccount.com"


def test_scheduler_command_targets_cloud_run_job_run_endpoint():
    uri = deploy_cloud_run._build_run_job_uri(
        project="kis-portfolio-prod",
        region="asia-northeast3",
        job="kis-portfolio-domestic-order-history",
    )

    command = deploy_cloud_run._build_scheduler_http_command(
        action="create",
        scheduler="kis-portfolio-domestic-order-history-1535",
        scheduler_region="asia-northeast3",
        schedule="35 15 * * 1-5",
        time_zone="Asia/Seoul",
        uri=uri,
        service_account="scheduler@kis-portfolio-prod.iam.gserviceaccount.com",
        project="kis-portfolio-prod",
    )

    assert command[:5] == ["gcloud", "scheduler", "jobs", "create", "http"]
    assert "--oauth-service-account-email" in command
    assert "scheduler@kis-portfolio-prod.iam.gserviceaccount.com" in command
    assert uri in command
    assert "--message-body" in command
    assert "{}" in command
    assert "--headers" in command


def test_scheduler_update_command_uses_update_headers_flag():
    uri = deploy_cloud_run._build_run_job_uri(
        project="kis-portfolio-prod",
        region="asia-northeast3",
        job="kis-portfolio-domestic-order-history",
    )

    command = deploy_cloud_run._build_scheduler_http_command(
        action="update",
        scheduler="kis-portfolio-domestic-order-history-1535",
        scheduler_region="asia-northeast3",
        schedule="35 15 * * 1-5",
        time_zone="Asia/Seoul",
        uri=uri,
        service_account="scheduler@kis-portfolio-prod.iam.gserviceaccount.com",
        project="kis-portfolio-prod",
    )

    assert command[:5] == ["gcloud", "scheduler", "jobs", "update", "http"]
    assert "--update-headers" in command
    assert "--headers" not in command


def test_local_deploy_guard_allows_clean_synced_master(monkeypatch):
    args = argparse.Namespace(dry_run=False, allow_local_source=False, reason=None)

    def fake_git_stdout(command):
        responses = {
            ("branch", "--show-current"): "master",
            ("status", "--porcelain=v1"): "",
            ("rev-parse", "HEAD"): "abc123",
            ("rev-parse", "origin/master"): "abc123",
        }
        return responses[tuple(command)]

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(deploy_cloud_run, "_git_stdout", fake_git_stdout)

    assert deploy_cloud_run._deploy_source_errors(args) == []


def test_local_deploy_guard_blocks_dirty_worktree(monkeypatch):
    args = argparse.Namespace(dry_run=False, allow_local_source=False, reason=None)

    def fake_git_stdout(command):
        responses = {
            ("branch", "--show-current"): "master",
            ("status", "--porcelain=v1"): " M scripts/deploy_cloud_run.py",
            ("rev-parse", "HEAD"): "abc123",
            ("rev-parse", "origin/master"): "abc123",
        }
        return responses[tuple(command)]

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(deploy_cloud_run, "_git_stdout", fake_git_stdout)

    errors = deploy_cloud_run._deploy_source_errors(args)

    assert "local deploy requires a clean worktree." in errors


def test_local_deploy_guard_requires_reason_for_emergency_override(monkeypatch):
    args = argparse.Namespace(dry_run=False, allow_local_source=True, reason="")

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    assert deploy_cloud_run._deploy_source_errors(args) == [
        "--allow-local-source requires --reason with a non-empty emergency reason."
    ]


def test_github_actions_deploy_guard_blocks_non_master(monkeypatch):
    args = argparse.Namespace(dry_run=False, allow_local_source=False, reason=None)

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")

    errors = deploy_cloud_run._deploy_source_errors(args)

    assert errors == ["GitHub Actions deploys must run from refs/heads/master, got refs/heads/feature."]


def test_deploy_labels_include_source_target_and_sha(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234567890")
    monkeypatch.setenv("GITHUB_RUN_ID", "123456")

    flags = deploy_cloud_run._build_label_flags("remote")

    assert flags == [
        "--labels",
        "deploy-source=github-actions,deploy-target=remote,git-sha=abcdef1234567890,github-run-id=123456",
    ]


def test_deploy_workflow_uses_secret_manager_not_bundled_env():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "deploy-cloud-run.yml"
    ).read_text()

    assert "KIS_DEPLOY_ENV" not in workflow
    assert "environment: production" in workflow
    assert 'test "${GITHUB_REF}" = "refs/heads/master"' in workflow
    assert "KIS_DEPLOY_SECRET_MODE: secret-manager" in workflow

