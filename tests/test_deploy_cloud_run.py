import argparse
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy_cloud_run.py"
WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy-cloud-run.yml"
SPEC = importlib.util.spec_from_file_location("deploy_cloud_run", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
deploy_cloud_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy_cloud_run)


def test_workflow_dispatches_wi055_s01_to_exact_deploy_target():
    workflow = WORKFLOW_PATH.read_text()
    assert "github.event.inputs.target == 'wi055-s01'" in workflow
    assert "scripts/deploy_cloud_run.py wi055-s01" in workflow


def test_workflow_dispatches_wi055_s03_to_exact_deploy_target():
    workflow = WORKFLOW_PATH.read_text()
    assert "github.event.inputs.target == 'wi055-s03'" in workflow
    assert "scripts/deploy_cloud_run.py wi055-s03" in workflow


def test_workflow_dispatches_wi055_s04_to_exact_deploy_target():
    workflow = WORKFLOW_PATH.read_text()
    assert "github.event.inputs.target == 'wi055-s04'" in workflow
    assert "scripts/deploy_cloud_run.py wi055-s04" in workflow


def test_workflow_dispatches_wi046_zero_traffic_stage_target():
    workflow = WORKFLOW_PATH.read_text()
    assert "github.event.inputs.target == 'wi046-stage'" in workflow
    assert "scripts/deploy_cloud_run.py wi046-stage" in workflow


def test_deploy_workflow_does_not_activate_firestore_during_pre_auth_tests():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    test_step = workflow.split("- name: Run test suite", 1)[1].split(
        "- name: Authenticate to Google Cloud", 1
    )[0]

    assert "KIS_STATE_BACKEND: motherduck" in test_step
    assert "KIS_REMOTE_SURFACE_VERSION: v1" in test_step


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
    assert (
        deploy_cloud_run._secret_id_for_env_key("KIS_TELEGRAM_BOT_TOKEN")
        == "kis-portfolio-telegram-bot-token"
    )
    assert deploy_cloud_run._is_secret_env_key("KIS_TELEGRAM_CHAT_ID") is True


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


def test_remote_v2_deploy_requires_and_forwards_managed_runtime_boundary():
    env = {
        "KIS_DB_MODE": "local",
        "KIS_TOKEN_ENCRYPTION_KEY": "enc-key",
        "KIS_REMOTE_AUTH_MODE": "oauth",
        "KIS_AUTH_ISSUER_URL": "https://auth.example.com",
        "KIS_RESOURCE_SERVER_URL": "https://resource.example.com/mcp",
        "KIS_AUTH_REQUIRED_SCOPES": "mcp:read",
        "KIS_AUTH_TOKEN_PEPPER": "pepper",
        "KIS_REMOTE_SURFACE_VERSION": "v2",
        "KIS_STATE_BACKEND": "firestore",
        "KIS_GCP_PROJECT": "project-1",
        "KIS_CLOUD_RUN_REGION": "asia-northeast3",
        "KIS_FIRESTORE_DATABASE": "kis-portfolio-state",
    }

    required = deploy_cloud_run._required_keys_for_remote(env)
    payload = deploy_cloud_run._build_remote_env(env)

    assert {
        "KIS_REMOTE_SURFACE_VERSION", "KIS_STATE_BACKEND", "KIS_GCP_PROJECT",
        "KIS_CLOUD_RUN_REGION", "KIS_FIRESTORE_DATABASE",
    } <= set(required)
    assert payload["KIS_REMOTE_SURFACE_VERSION"] == "v2"
    assert payload["KIS_STATE_BACKEND"] == "firestore"
    assert "KIS_TOKEN_ENCRYPTION_KEY" not in required
    assert "KIS_TOKEN_ENCRYPTION_KEY" not in payload
    assert not any(key.startswith("KIS_APP_KEY_") for key in payload)
    assert not any(key.startswith("KIS_CANO_") for key in payload)


def test_auth_firestore_deploy_excludes_motherduck_state_access():
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "MOTHERDUCK_TOKEN": "md-token",
        "KIS_STATE_BACKEND": "firestore",
        "KIS_GCP_PROJECT": "project-1",
        "KIS_FIRESTORE_DATABASE": "kis-portfolio-state",
    }

    payload = deploy_cloud_run._build_auth_env(env)

    assert payload["KIS_STATE_BACKEND"] == "firestore"
    assert "KIS_DB_MODE" not in payload
    assert "MOTHERDUCK_DATABASE" not in payload
    assert "MOTHERDUCK_TOKEN" not in payload


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


def test_v2_pipeline_env_forces_named_state_and_private_bucket():
    payload = deploy_cloud_run._build_v2_pipeline_env(
        {"KIS_DB_MODE": "motherduck", "MOTHERDUCK_DATABASE": "kis_portfolio"},
        "grand-forge-279904",
    )
    assert payload["KIS_STATE_BACKEND"] == "firestore"
    assert payload["KIS_FIRESTORE_DATABASE"] == "kis-portfolio-state"
    assert payload["KIS_GCS_BUCKET"] == "grand-forge-279904-kis-portfolio-private"


def test_v2_pipeline_env_includes_public_sec_fair_access_identity():
    payload = deploy_cloud_run._build_v2_pipeline_env(
        {
            "KIS_DB_MODE": "motherduck",
            "MOTHERDUCK_DATABASE": "kis_portfolio",
            "SEC_EDGAR_USER_AGENT": "KIS Portfolio mustafa@example.com",
        },
        "grand-forge-279904",
    )
    assert payload["SEC_EDGAR_USER_AGENT"] == "KIS Portfolio mustafa@example.com"


def test_v2_pipeline_env_includes_explicit_telegram_canary_flags():
    payload = deploy_cloud_run._build_v2_pipeline_env(
        {
            "KIS_DB_MODE": "motherduck",
            "MOTHERDUCK_DATABASE": "kis_portfolio",
            "KIS_TELEGRAM_DELIVERY_ENABLED": "true",
            "KIS_TELEGRAM_CANARY_ENABLED": "true",
            "KIS_TELEGRAM_REAL_USE_ENABLED": "false",
            "KIS_TELEGRAM_TOTAL_ASSET_REPORT_ENABLED": "true",
            "KIS_TELEGRAM_DESTINATION_REF": "dest.owner.primary",
        },
        "grand-forge-279904",
    )
    assert payload["KIS_TELEGRAM_DELIVERY_ENABLED"] == "true"
    assert payload["KIS_TELEGRAM_CANARY_ENABLED"] == "true"
    assert payload["KIS_TELEGRAM_REAL_USE_ENABLED"] == "false"
    assert payload["KIS_TELEGRAM_TOTAL_ASSET_REPORT_ENABLED"] == "true"
    assert payload["KIS_TELEGRAM_DESTINATION_REF"] == "dest.owner.primary"


def test_wi055_deploy_enables_digest_on_existing_jobs(monkeypatch):
    captured = {}
    args = argparse.Namespace(
        region="asia-northeast3", target="wi055", dry_run=True,
        secret_mode="secret-manager",
    )
    monkeypatch.setattr(
        deploy_cloud_run, "_deploy_v2_core_jobs",
        lambda args, **kwargs: captured.update(kwargs) or 0,
    )

    result = deploy_cloud_run._deploy_wi055(
        args, env={"KIS_DB_MODE": "motherduck"}, project="grand-forge-279904",
    )

    assert result == 0
    assert captured["env"]["KIS_TELEGRAM_TOTAL_ASSET_REPORT_ENABLED"] == "true"
    assert captured["env"]["KIS_TELEGRAM_DELIVERY_ENABLED"] == "true"
    assert captured["env"]["KIS_TELEGRAM_REAL_USE_ENABLED"] == "true"
    assert captured["deploy_label"] == "wi055-total-asset-digest"


def test_wi055_s01_deploy_atomically_replaces_legacy_report(monkeypatch):
    args = argparse.Namespace(
        region="asia-northeast3", target="wi055-s01", dry_run=True,
        secret_mode="secret-manager", allow_local_source=False,
    )
    captured = {}
    commands = []

    def fake_deploy(_args, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(deploy_cloud_run, "_deploy_v2_core_jobs", fake_deploy)
    monkeypatch.setattr(deploy_cloud_run, "_build_release_image", lambda *args, **kwargs: "image@sha256:test")
    monkeypatch.setattr(
        deploy_cloud_run, "_run", lambda command, **kwargs: commands.append(command) or 0,
    )
    result = deploy_cloud_run._deploy_wi055_s01(
        args,
        env={
            "KIS_TELEGRAM_BOT_TOKEN_VERSION": "1",
            "KIS_TELEGRAM_CHAT_ID_VERSION": "1",
        },
        project="project",
    )

    assert result == 0
    assert captured["env"]["KIS_TELEGRAM_TOTAL_ASSET_REPORT_ENABLED"] == "false"
    assert captured["env"]["KIS_TELEGRAM_TOTAL_ASSET_REPORT_V2_ENABLED"] == "true"
    assert captured["env"]["KIS_TELEGRAM_OWNER_DESTINATION_APPROVED"] == "true"
    assert captured["env"]["KIS_TELEGRAM_DESTINATION_REF"] == "dest.owner.primary"
    assert captured["deploy_label"] == "wi055-s01-owner-report"
    assert captured["image"] == "image@sha256:test"
    assert len(commands) == 2
    assert "send-telegram-photo-transport-smoke" in commands[0]
    assert commands[1][0:4] == ["gcloud", "run", "jobs", "execute"]


def test_wi055_s03_reuses_atomic_owner_report_release_with_new_labels(monkeypatch):
    captured = {}
    args = argparse.Namespace(target="wi055-s03")

    def fake_release(_args, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(deploy_cloud_run, "_deploy_wi055_s01", fake_release)

    result = deploy_cloud_run._deploy_wi055_s03(args, env={"safe": "value"}, project="project")

    assert result == 0
    assert captured == {
        "env": {"safe": "value"},
        "project": "project",
        "deploy_label": "wi055-s03-top5-impact",
        "smoke_label": "wi055-s03-photo-transport-smoke",
    }


def test_wi055_s04_reuses_atomic_owner_report_release_with_new_labels(monkeypatch):
    captured = {}
    args = argparse.Namespace(target="wi055-s04")

    def fake_release(_args, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(deploy_cloud_run, "_deploy_wi055_s01", fake_release)

    result = deploy_cloud_run._deploy_wi055_s04(args, env={"safe": "value"}, project="project")

    assert result == 0
    assert captured == {
        "env": {"safe": "value"},
        "project": "project",
        "deploy_label": "wi055-s04-caption-layout",
        "smoke_label": "wi055-s04-photo-transport-smoke",
    }


def test_v2_jobs_reuse_one_digest_and_have_fixed_slot_args(monkeypatch):
    commands = []
    args = argparse.Namespace(
        region="asia-northeast3", target="v2-core-batch", dry_run=True,
        secret_mode="secret-manager",
    )
    env = {
        "KIS_DB_MODE": "motherduck", "MOTHERDUCK_DATABASE": "kis_portfolio",
        "KIS_CLOUD_RUN_BATCH_TASK_TIMEOUT": "1800s",
    }
    monkeypatch.setattr(
        deploy_cloud_run, "_build_release_image",
        lambda args, project: "image@sha256:one-build",
    )
    monkeypatch.setattr(
        deploy_cloud_run, "_run",
        lambda command, dry_run: commands.append(command) or 0,
    )
    result = deploy_cloud_run._deploy_v2_core_jobs(
        args, env=env, project="grand-forge-279904",
    )
    assert result == 0 and len(commands) == 3
    assert {command[command.index("--image") + 1] for command in commands} == {"image@sha256:one-build"}
    fixed_args = {command[command.index("--args") + 1] for command in commands}
    assert fixed_args == {
        "collect-owned-portfolio-v2,--date,today,--slot,kr-1000,--partition-key,all-accounts",
        "collect-owned-portfolio-v2,--date,today,--slot,kr-1430,--partition-key,all-accounts",
        "collect-owned-portfolio-v2,--date,today,--slot,kr-1600,--partition-key,all-accounts",
    }


def test_wi046_stage_applies_0018_then_deploys_zero_traffic_candidates(monkeypatch):
    commands = []
    deployments = []
    identities = []
    smokes = []
    args = argparse.Namespace(
        region="asia-northeast3", target="wi046-stage", dry_run=False,
        secret_mode="secret-manager",
    )
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "KIS_TOKEN_ENCRYPTION_KEY": "secret-ref",
        "KIS_AUTH_BASE_URL": "https://auth.example.com",
        "KIS_AUTH_OWNER_EMAILS": "owner@example.com",
        "KIS_AUTH_SESSION_SECRET": "secret-ref",
        "KIS_AUTH_TOKEN_PEPPER": "secret-ref",
        "KIS_AUTH_CLAUDE_CLIENT_ID": "claude-client",
        "KIS_AUTH_CLAUDE_CLIENT_SECRET": "secret-ref",
        "KIS_OAUTH_GOOGLE_CLIENT_ID": "google-client",
        "KIS_OAUTH_GOOGLE_CLIENT_SECRET": "secret-ref",
        "KIS_OAUTH_GITHUB_CLIENT_ID": "github-client",
        "KIS_OAUTH_GITHUB_CLIENT_SECRET": "secret-ref",
        "KIS_REMOTE_AUTH_MODE": "oauth",
        "KIS_AUTH_ISSUER_URL": "https://auth.example.com",
        "KIS_RESOURCE_SERVER_URL": "https://remote.example.com/mcp",
        "KIS_AUTH_REQUIRED_SCOPES": "mcp:read",
    }
    monkeypatch.setattr(
        deploy_cloud_run, "_build_release_image",
        lambda *_args, **_kwargs: "image@sha256:" + "a" * 64,
    )
    def ensure_identity(account_id, **kwargs):
        identities.append({"account_id": account_id, **kwargs})
        return f"{account_id}@project-1.iam.gserviceaccount.com"

    monkeypatch.setattr(deploy_cloud_run, "_ensure_runtime_identity", ensure_identity)
    monkeypatch.setattr(
        deploy_cloud_run, "_run", lambda command, **_kwargs: commands.append(command) or 0,
    )

    def deploy(**kwargs):
        deployments.append(kwargs)
        return 0

    monkeypatch.setattr(deploy_cloud_run, "_deploy_tagged_service", deploy)
    monkeypatch.setattr(
        deploy_cloud_run, "_tagged_service_url",
        lambda tag, **_kwargs: f"https://{tag}.example.test",
    )
    monkeypatch.setattr(
        deploy_cloud_run, "_smoke_wi046_tagged_urls",
        lambda **kwargs: smokes.append(kwargs) or True,
    )

    result = deploy_cloud_run._deploy_wi046_stage(
        args, env=env, project="project-1"
    )

    assert result == 0
    assert any("--args=--motherduck,--through,0018" in command for command in commands)
    assert any(
        "--args=scripts/migrate_operational_state.py" in command for command in commands
    )
    assert any(command[:4] == ["gcloud", "run", "jobs", "execute"] for command in commands)
    assert [item["tag"] for item in deployments] == ["wi046-auth", "wi046-v2", "wi046-v2"]
    assert deployments[0]["command_name"] == "kis-portfolio-auth"
    assert deployments[1]["command_name"] == "kis-portfolio-remote"
    assert deployments[0]["payload"]["KIS_STATE_BACKEND"] == "firestore"
    assert "MOTHERDUCK_TOKEN" not in deployments[0]["secret_refs"]
    assert set(deployments[1]["secret_refs"]) == {
        "KIS_AUTH_TOKEN_PEPPER", "MOTHERDUCK_TOKEN"
    }
    assert identities[0]["secret_ids"] == {
        "kis-portfolio-kis-auth-claude-client-secret",
        "kis-portfolio-kis-auth-owner-emails",
        "kis-portfolio-kis-auth-session-secret",
        "kis-portfolio-kis-auth-token-pepper",
        "kis-portfolio-kis-oauth-github-client-secret",
        "kis-portfolio-kis-oauth-google-client-secret",
    }
    assert deployments[2]["payload"]["KIS_REMOTE_ADDITIONAL_ALLOWED_HOSTS"] == "wi046-v2.example.test"
    assert "--no-traffic" in Path(deploy_cloud_run.__file__).read_text()
    assert smokes == [{
        "auth_url": "https://wi046-auth.example.test",
        "remote_url": "https://wi046-v2.example.test",
        "expected_resource": "https://remote.example.com/mcp",
    }]


def test_existing_runtime_identity_is_not_rebound_by_protected_stage(monkeypatch):
    monkeypatch.setattr(
        deploy_cloud_run,
        "_run_capture",
        lambda *_args, **_kwargs: argparse.Namespace(returncode=0),
    )
    monkeypatch.setattr(
        deploy_cloud_run,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("existing identity must not mutate IAM"),
    )

    result = deploy_cloud_run._ensure_runtime_identity(
        project="project-1",
        region="asia-northeast3",
        account_id="kis-portfolio-remote",
        secret_ids={"secret-a"},
        job_names=("job-a",),
        dry_run=False,
    )

    assert result == "kis-portfolio-remote@project-1.iam.gserviceaccount.com"


def test_wi021_s06_job_is_single_task_fixed_hash_and_immutable(monkeypatch):
    commands = []
    args = argparse.Namespace(
        region="asia-northeast3", target="wi021-s06", dry_run=True,
        secret_mode="secret-manager", job="kis-portfolio-wi021-s06",
    )
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "KIS_GCS_BUCKET": "private-bucket",
    }
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setattr(
        deploy_cloud_run, "_build_release_image",
        lambda args, project: "image@sha256:" + "b" * 64,
    )
    monkeypatch.setattr(
        deploy_cloud_run, "_run",
        lambda command, dry_run: commands.append(command) or 0,
    )

    result = deploy_cloud_run._deploy_wi021_s06_job(
        args, env=env, project="grand-forge-279904",
    )

    assert result == 0 and len(commands) == 2
    migration, command = commands
    assert migration[4] == "kis-portfolio-wi021-s06-migration"
    assert migration[migration.index("--command") + 1] == "kis-portfolio-migrate"
    assert "--args=--motherduck,--through,0008" in migration
    assert migration[migration.index("--tasks") + 1] == "1"
    assert migration[migration.index("--parallelism") + 1] == "1"
    assert migration[migration.index("--max-retries") + 1] == "0"
    assert migration[migration.index("--image") + 1] == command[command.index("--image") + 1]
    migration_secrets = migration[migration.index("--set-secrets") + 1]
    assert migration_secrets.startswith("MOTHERDUCK_TOKEN=")
    assert "KIS_APP_" not in migration_secrets and "KIS_CANO_" not in migration_secrets
    assert command[command.index("--image") + 1].startswith("image@sha256:")
    assert command[command.index("--tasks") + 1] == "1"
    assert command[command.index("--parallelism") + 1] == "1"
    assert command[command.index("--max-retries") + 1] == "0"
    fixed = command[command.index("--args") + 1]
    assert "--expected-plan-hash,0755656ed8151a91" in fixed
    assert "--expected-budget-hash,0a4abf9b795f9d73" in fixed
    assert "--start-date,20230828,--end-date,20260828" in fixed
    assert "--as-of-date" not in fixed


def test_wi022_s06_job_is_minimal_single_task_fixed_hash_and_immutable(monkeypatch):
    commands = []
    args = argparse.Namespace(
        region="asia-northeast3", target="wi022-s06", dry_run=True,
        secret_mode="secret-manager", job="kis-portfolio-wi022-s06",
    )
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "KIS_GCS_BUCKET": "private-bucket",
    }
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setattr(
        deploy_cloud_run, "_build_release_image",
        lambda args, project: "image@sha256:" + "b" * 64,
    )
    monkeypatch.setattr(
        deploy_cloud_run, "_run",
        lambda command, dry_run: commands.append(command) or 0,
    )

    result = deploy_cloud_run._deploy_wi022_s06_job(
        args, env=env, project="grand-forge-279904",
    )

    assert result == 0 and len(commands) == 2
    migration, command = commands
    assert migration[4] == "kis-portfolio-wi022-s06-migration"
    assert "--args=--motherduck,--through,0010" in migration
    assert migration[migration.index("--image") + 1] == command[command.index("--image") + 1]
    assert migration[migration.index("--tasks") + 1] == "1"
    assert command[command.index("--tasks") + 1] == "1"
    assert command[command.index("--parallelism") + 1] == "1"
    assert command[command.index("--max-retries") + 1] == "0"
    fixed = command[command.index("--args") + 1]
    assert "--start-at,2023-08-28T00:00:00+09:00" in fixed
    assert "--cutoff-at,2026-08-28T18:00:00+09:00" in fixed
    assert "096a01a53fdac9b5c35df13e25a1300c2df8af0c61fca4cbe29d8aa005afd50b" in fixed
    secrets = command[command.index("--set-secrets") + 1]
    assert secrets.startswith("MOTHERDUCK_TOKEN=")
    assert "KIS_APP_" not in secrets and "KIS_CANO_" not in secrets


def test_v2_schedulers_use_dedicated_invoker_instead_of_legacy_default(monkeypatch):
    calls = []
    args = argparse.Namespace(
        region="asia-northeast3", scheduler_region="asia-northeast3",
        dry_run=True, target="v2-core-schedulers",
    )
    env = {
        "KIS_CLOUD_SCHEDULER_INVOKER_SERVICE_ACCOUNT":
            "legacy-compute@example.iam.gserviceaccount.com",
    }
    monkeypatch.setattr(
        deploy_cloud_run,
        "_deploy_scheduler_target",
        lambda **kwargs: calls.append(kwargs) or 0,
    )

    result = deploy_cloud_run._deploy_v2_core_schedulers(
        args, env=env, project="grand-forge-279904",
    )

    assert result == 0 and len(calls) == 3
    assert {
        call["env"]["KIS_CLOUD_SCHEDULER_INVOKER_SERVICE_ACCOUNT"]
        for call in calls
    } == {
        "kis-portfolio-scheduler@grand-forge-279904.iam.gserviceaccount.com",
    }


def test_wi029_s04_migrates_before_same_digest_core_and_verifies_private_restore(monkeypatch):
    commands = []
    scheduler_calls = []
    builds = {"count": 0}
    args = argparse.Namespace(
        region="asia-northeast3", scheduler_region="asia-northeast3",
        target="wi029-s04", dry_run=True, secret_mode="secret-manager",
        job="kis-portfolio-wi029-s04",
    )
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "KIS_GCS_BUCKET": "private-bucket",
        "SEC_EDGAR_USER_AGENT": "KIS Portfolio mustafa@example.com",
    }

    def build(_args, *, project):
        builds["count"] += 1
        assert project == "grand-forge-279904"
        return "image@sha256:" + "b" * 64

    monkeypatch.setattr(deploy_cloud_run, "_build_release_image", build)
    monkeypatch.setattr(
        deploy_cloud_run, "_run", lambda command, dry_run: commands.append(command) or 0,
    )
    monkeypatch.setattr(
        deploy_cloud_run, "_deploy_v2_core_schedulers",
        lambda *args, **kwargs: scheduler_calls.append(kwargs) or 0,
    )

    result = deploy_cloud_run._deploy_wi029_s04(
        args, env=env, project="grand-forge-279904",
    )
    assert result == 0
    assert builds["count"] == 1
    assert commands[0][4] == "kis-portfolio-wi029-s04-migration"
    assert "--args=--motherduck,--through,0013" in commands[0]
    assert commands[1][:5] == ["gcloud", "run", "jobs", "execute", "kis-portfolio-wi029-s04-migration"]
    core_deploys = [command for command in commands if "v2-core-batch" in " ".join(command)]
    assert len(core_deploys) == 3
    assert {command[command.index("--image") + 1] for command in core_deploys} == {
        "image@sha256:" + "b" * 64
    }
    verify = next(command for command in commands if "wi029-s04-verify" in " ".join(command) and "deploy" in command)
    secrets = verify[verify.index("--set-secrets") + 1]
    assert secrets.startswith("MOTHERDUCK_TOKEN=")
    assert "KIS_APP_" not in secrets and "KIS_CANO_" not in secrets
    assert scheduler_calls


def test_wi030_s02_pins_secrets_activates_once_and_reuses_one_core_digest(monkeypatch):
    commands = []
    builds = {"count": 0}
    args = argparse.Namespace(
        region="asia-northeast3", target="wi030-s02", dry_run=True,
        secret_mode="secret-manager", job="kis-portfolio-wi030-s02",
    )
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "KIS_TELEGRAM_BOT_TOKEN_VERSION": "2",
        "KIS_TELEGRAM_CHAT_ID_VERSION": "1",
    }

    def build(_args, *, project):
        builds["count"] += 1
        assert project == "grand-forge-279904"
        return "image@sha256:" + "c" * 64

    monkeypatch.setattr(deploy_cloud_run, "_build_release_image", build)
    monkeypatch.setattr(
        deploy_cloud_run, "_run", lambda command, dry_run: commands.append(command) or 0,
    )

    result = deploy_cloud_run._deploy_wi030_s02(
        args, env=env, project="grand-forge-279904",
    )

    assert result == 0
    assert builds["count"] == 1
    assert not [
        command for command in commands
        if command[:3] == ["gcloud", "secrets", "add-iam-policy-binding"]
    ]
    activation = next(
        command for command in commands
        if command[:4] == ["gcloud", "run", "jobs", "deploy"]
        and command[4] == "kis-portfolio-wi030-s02"
    )
    assert activation[activation.index("--args") + 1] == "activate-wi030-canary"
    assert "MOTHERDUCK_TOKEN=" in activation[activation.index("--set-secrets") + 1]
    core = [
        command for command in commands
        if command[:4] == ["gcloud", "run", "jobs", "deploy"]
        and command[4].startswith("kis-portfolio-owned-core-v2-")
    ]
    assert len(core) == 3
    assert {command[command.index("--image") + 1] for command in core} == {
        "image@sha256:" + "c" * 64
    }
    for command in core:
        secrets = command[command.index("--set-secrets") + 1]
        assert "KIS_TELEGRAM_BOT_TOKEN=kis-portfolio-telegram-bot-token:2" in secrets
        assert "KIS_TELEGRAM_CHAT_ID=kis-portfolio-telegram-chat-id:1" in secrets


def test_wi030_s03_activates_real_use_and_disables_canary_on_one_digest(monkeypatch):
    commands = []
    builds = {"count": 0}
    core_call = {}
    args = argparse.Namespace(
        region="asia-northeast3", target="wi030-s03", dry_run=True,
        secret_mode="secret-manager", job="kis-portfolio-wi030-s03",
    )
    env = {
        "KIS_DB_MODE": "motherduck",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "KIS_TELEGRAM_BOT_TOKEN_VERSION": "2",
        "KIS_TELEGRAM_CHAT_ID_VERSION": "1",
    }

    def build(_args, *, project):
        builds["count"] += 1
        assert project == "grand-forge-279904"
        return "image@sha256:" + "d" * 64

    monkeypatch.setattr(deploy_cloud_run, "_build_release_image", build)
    monkeypatch.setattr(
        deploy_cloud_run, "_run", lambda command, dry_run: commands.append(command) or 0,
    )
    monkeypatch.setattr(
        deploy_cloud_run,
        "_deploy_v2_core_jobs",
        lambda args, **kwargs: core_call.update(kwargs) or 0,
    )

    result = deploy_cloud_run._deploy_wi030_s03(
        args, env=env, project="grand-forge-279904",
    )

    assert result == 0
    assert builds["count"] == 1
    wi030_deploys = [
        command for command in commands
        if command[:4] == ["gcloud", "run", "jobs", "deploy"]
        and command[4] == "kis-portfolio-wi030-s03"
    ]
    assert len(wi030_deploys) == 2
    smoke, activation = wi030_deploys
    assert smoke[smoke.index("--args") + 1] == "send-telegram-rich-transport-smoke"
    smoke_secrets = smoke[smoke.index("--set-secrets") + 1]
    assert "KIS_TELEGRAM_BOT_TOKEN=kis-portfolio-telegram-bot-token:2" in smoke_secrets
    assert "KIS_TELEGRAM_CHAT_ID=kis-portfolio-telegram-chat-id:1" in smoke_secrets
    assert activation[activation.index("--args") + 1] == "activate-wi030-real-use"
    assert core_call["image"] == "image@sha256:" + "d" * 64
    assert core_call["deploy_label"] == "wi030-s03-real-use"
    assert core_call["env"]["KIS_TELEGRAM_DELIVERY_ENABLED"] == "true"
    assert core_call["env"]["KIS_TELEGRAM_CANARY_ENABLED"] == "false"
    assert core_call["env"]["KIS_TELEGRAM_REAL_USE_ENABLED"] == "true"


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
