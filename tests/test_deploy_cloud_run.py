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
    }

    required = deploy_cloud_run._required_keys_for_remote(env)
    payload = deploy_cloud_run._build_remote_env(env)

    assert deploy_cloud_run._effective_remote_auth_mode(env) == "oauth"
    assert "KIS_REMOTE_AUTH_TOKEN" not in required
    assert payload["KIS_REMOTE_AUTH_MODE"] == "oauth"


def test_auth_deploy_defaults_to_single_instance():
    env = {}

    runtime_flags = deploy_cloud_run._build_auth_runtime_flags(env)

    assert runtime_flags == ["--max-instances", "1"]


def test_auth_deploy_keeps_explicit_max_instance_override():
    env = {
        "KIS_CLOUD_RUN_AUTH_MAX_INSTANCES": "2",
    }

    runtime_flags = deploy_cloud_run._build_auth_runtime_flags(env)

    assert runtime_flags == ["--max-instances", "2"]


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
    }

    required = deploy_cloud_run._required_keys_for_batch(env)
    payload = deploy_cloud_run._build_batch_env(env)

    assert required == ["KIS_DB_MODE", "KIS_TOKEN_ENCRYPTION_KEY"]
    assert payload["KIS_TOKEN_ENCRYPTION_KEY"] == "enc-key"
    assert payload["KIS_APP_KEY_RIA"] == "app-key"
    assert payload["KIS_ACNT_PRDT_CD_RIA"] == "01"
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
        "run,kis-portfolio-batch,collect-overseas-transaction-history,"
        "--date,today,--account-label,brokerage,--exchange,NAS"
    )


def test_overseas_batch_command_allows_account_and_exchange_override():
    command_args = deploy_cloud_run._build_overseas_batch_command_args({
        "KIS_OVERSEAS_TRANSACTION_HISTORY_ACCOUNT_LABEL": "ria",
        "KIS_OVERSEAS_TRANSACTION_HISTORY_EXCHANGE": "NYSE",
    })

    assert "--account-label,ria" in command_args
    assert "--exchange,NYSE" in command_args


def test_token_warmup_batch_command_is_dry_run_only():
    command_args = deploy_cloud_run._build_token_warmup_command_args({})

    assert command_args == (
        "run,kis-portfolio-batch,warm-token-cache,"
        "--account-label,all,--valid-through,16:30,--dry-run"
    )


def test_remote_runtime_flags_keep_existing_safe_defaults():
    env = {}

    runtime_flags = deploy_cloud_run._build_remote_runtime_flags(env)

    assert runtime_flags == [
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
