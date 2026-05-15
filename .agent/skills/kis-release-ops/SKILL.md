---
name: kis-release-ops
description: Use when deploying, preparing releases, changing CI/CD, rotating deployment secrets, or investigating GitHub Actions and Cloud Run production state for KIS Portfolio Service.
---

# KIS Release Ops

Use this skill before any production deployment, CI/CD change, Secret Manager migration, or release-state cleanup.

## Rules

- Treat GitHub Actions as the normal production deployment path.
- Do not run local Cloud Run deploys from dirty, unpushed, or non-`master` source.
- Use local deploy only as an emergency path with `--allow-local-source --reason "<why>"`.
- Keep long-lived runtime secrets in GCP Secret Manager, not GitHub `KIS_DEPLOY_ENV`.
- Never print KIS app secrets, account numbers, MotherDuck token, OAuth secrets, token pepper, or encryption keys.
- Confirm deployed source via Git SHA, GitHub Actions run ID, and Cloud Run/Job deployment labels.

## Workflow

1. Check source state:

   ```bash
   git status --short
   git rev-parse HEAD
   git rev-parse origin/master
   ```

2. Run release verification:

   ```bash
   uv run pytest
   uv run python .agent/skills/kis-architecture-audit/scripts/check_architecture_contracts.py
   uv run python .agent/skills/kis-mcp-surface-audit/scripts/inspect_mcp_surface.py
   bash -n scripts/setup.sh
   python3 -m json.tool docs/examples/claude_desktop_config.example.json >/dev/null
   git diff --check
   ```

3. For secret migration or rotation, dry-run first:

   ```bash
   uv run python scripts/sync_secret_manager.py --project grand-forge-279904
   ```

4. Apply secret versions only after reviewing the dry-run mapping:

   ```bash
   uv run python scripts/sync_secret_manager.py --project grand-forge-279904 --apply
   ```

5. Deploy production through `.github/workflows/deploy-cloud-run.yml` with the `production` environment approval.
6. Verify the GitHub Actions run succeeded and that the target Cloud Run service/job labels include the expected `git-sha`, `github-run-id`, `deploy-target`, and `deploy-source`.

## Notes

- `scripts/deploy_cloud_run.py` defaults to `--secret-mode secret-manager`.
- A local dry-run is safe and useful:

  ```bash
  uv run python scripts/deploy_cloud_run.py remote --dry-run
  ```

- `KIS_DEPLOY_ENV` is deprecated as a deployment source and should not be added back to workflows.
