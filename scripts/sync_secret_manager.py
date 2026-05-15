"""Sync deployment secrets from local .env to GCP Secret Manager.

The script never prints secret values. By default it runs in dry-run mode and
only shows the env key to Secret Manager secret-id mapping.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import deploy_cloud_run


def _collect_secret_values(env: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in sorted(env.items())
        if value != "" and deploy_cloud_run._is_secret_env_key(key)
    }


def _build_secret_plan(env: dict[str, str]) -> dict[str, str]:
    return {
        key: deploy_cloud_run._secret_id_for_env_key(key)
        for key in _collect_secret_values(env)
    }


def _run_capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=deploy_cloud_run.PROJECT_ROOT,
        text=True,
        capture_output=True,
    )


def _run_with_input(command: list[str], *, value: str) -> int:
    completed = subprocess.run(
        command,
        cwd=deploy_cloud_run.PROJECT_ROOT,
        input=value,
        text=True,
    )
    return completed.returncode


def _secret_exists(*, project: str, secret_id: str) -> bool:
    completed = _run_capture([
        "gcloud",
        "secrets",
        "describe",
        secret_id,
        "--project",
        project,
    ])
    if completed.returncode == 0:
        return True
    stderr = completed.stderr.lower()
    if "not found" in stderr or "not_found" in stderr:
        return False
    if completed.stdout.strip():
        print(completed.stdout, file=sys.stderr, end="")
    if completed.stderr.strip():
        print(completed.stderr, file=sys.stderr, end="")
    raise RuntimeError(f"Failed to check Secret Manager secret {secret_id}.")


def _create_secret(*, project: str, secret_id: str) -> int:
    print("$", " ".join([
        "gcloud",
        "secrets",
        "create",
        secret_id,
        "--replication-policy",
        "automatic",
        "--project",
        project,
    ]))
    completed = subprocess.run(
        [
            "gcloud",
            "secrets",
            "create",
            secret_id,
            "--replication-policy",
            "automatic",
            "--project",
            project,
        ],
        cwd=deploy_cloud_run.PROJECT_ROOT,
    )
    return completed.returncode


def _add_secret_version(*, project: str, secret_id: str, value: str) -> int:
    command = [
        "gcloud",
        "secrets",
        "versions",
        "add",
        secret_id,
        "--data-file=-",
        "--project",
        project,
    ]
    print("$", " ".join(command))
    return _run_with_input(command, value=value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    env = deploy_cloud_run._load_env()
    project = args.project or env.get("GOOGLE_CLOUD_PROJECT") or env.get("GCLOUD_PROJECT")
    secret_values = _collect_secret_values(env)
    secret_plan = _build_secret_plan(env)

    if not secret_plan:
        print("No deployment secrets found in .env or current environment.")
        return 0

    if args.apply and not project:
        print("Missing required environment variables:")
        print("- GOOGLE_CLOUD_PROJECT")
        return 1

    mode = "apply" if args.apply else "dry-run"
    print(f"Secret Manager sync plan ({mode}):")
    for env_key, secret_id in secret_plan.items():
        print(f"- {env_key} -> {secret_id}")

    if not args.apply:
        print("Dry run only. Pass --apply to create missing secrets and add new versions.")
        return 0

    assert project is not None
    for env_key, secret_id in secret_plan.items():
        if not _secret_exists(project=project, secret_id=secret_id):
            create_code = _create_secret(project=project, secret_id=secret_id)
            if create_code != 0:
                return create_code
        add_code = _add_secret_version(
            project=project,
            secret_id=secret_id,
            value=secret_values[env_key],
        )
        if add_code != 0:
            return add_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
