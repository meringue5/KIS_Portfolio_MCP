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
