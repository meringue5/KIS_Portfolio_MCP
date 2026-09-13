from __future__ import annotations

import subprocess
import sys
import tomllib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_console_script_is_a_fail_closed_diagnostic():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)

    assert (
        project["project"]["scripts"]["kis-portfolio-mcp"]
        == "kis_portfolio.legacy_entrypoint:main"
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "server.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(ROOT / "src")},
    )

    assert result.returncode == 2
    assert '"reason_code": "v1_public_surface_retired"' in result.stderr
    assert "OAuth Remote MCP" in result.stderr


def test_fresh_setup_removes_only_legacy_local_registration_and_guides_remote():
    setup = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")

    assert "KIS_RESOURCE_SERVER_URL" in setup
    assert "OAuth Remote MCP" in setup
    assert "retire_local_claude_config.py" in setup
    assert "orchestrator_srv" not in setup
    assert '"args": ["run"' not in setup
    assert not (ROOT / "docs" / "examples" / "claude_desktop_config.example.json").exists()


def test_local_config_retirement_preserves_other_servers_and_preferences(tmp_path):
    script_path = ROOT / "scripts" / "retire_local_claude_config.py"
    spec = importlib.util.spec_from_file_location("retire_local_claude_config", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    config = tmp_path / "claude_desktop_config.json"
    original = {
        "mcpServers": {
            "kis-portfolio": {"command": "uv", "args": ["run", "kis-portfolio-mcp"]},
            "other": {"command": "other"},
        },
        "preferences": {"theme": "dark"},
    }
    config.write_text(json.dumps(original), encoding="utf-8")

    backup = module.remove_legacy_registration(config)

    assert backup is not None and backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8")) == original
    assert json.loads(config.read_text(encoding="utf-8")) == {
        "mcpServers": {"other": {"command": "other"}},
        "preferences": {"theme": "dark"},
    }


def test_v2_is_the_only_remote_deployment_default():
    workflow = (ROOT / ".github" / "workflows" / "deploy-cloud-run.yml").read_text(
        encoding="utf-8"
    )
    remote = (ROOT / "src" / "kis_portfolio" / "remote.py").read_text(encoding="utf-8")

    assert "KIS_REMOTE_SURFACE_VERSION || 'v2'" in workflow
    assert 'KIS_REMOTE_SURFACE_VERSION", "v2"' in remote
    assert "The V1 Remote MCP public surface is retired" in remote
