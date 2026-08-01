import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "sync_secret_manager.py"
SPEC = importlib.util.spec_from_file_location("sync_secret_manager", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
sync_secret_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_secret_manager)


def test_secret_manager_sync_plan_only_includes_allowlisted_secrets():
    env = {
        "KIS_APP_KEY_RIA": "app-key",
        "KIS_APP_SECRET_RIA": "app-secret",
        "KIS_CANO_RIA": "12345678",
        "KIS_ACNT_PRDT_CD_RIA": "01",
        "MOTHERDUCK_DATABASE": "kis_portfolio",
        "MOTHERDUCK_TOKEN": "md-token",
        "KIS_DEPLOY_ENV": "bundled-env",
        "KIS_BATCH_ALERT_WEBHOOK_URL": "https://alerts.example.invalid/hook",
    }

    plan = sync_secret_manager._build_secret_plan(env)

    assert plan == {
        "KIS_APP_KEY_RIA": "kis-portfolio-kis-app-key-ria",
        "KIS_APP_SECRET_RIA": "kis-portfolio-kis-app-secret-ria",
        "KIS_CANO_RIA": "kis-portfolio-kis-cano-ria",
        "MOTHERDUCK_TOKEN": "kis-portfolio-motherduck-token",
        "KIS_BATCH_ALERT_WEBHOOK_URL": "kis-portfolio-kis-batch-alert-webhook-url",
    }
