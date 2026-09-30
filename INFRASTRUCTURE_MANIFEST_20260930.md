# SignalRankAI Infrastructure Manifest & Runbook
**Date:** 2026-09-30
**Applies to:** WORK PACKAGE B — BRANCHES, STAGING, STORAGE

This document contains the exact CLI commands, Terraform blocks, or UI instructions required to implement the external SaaS infrastructure requirements for the next hardening cycle.

## 1. Protect Canonical Main and Staging Branches
**GitHub Settings Runbook:**
1. Navigate to **Settings > Branches** in the SignalRankAI repository.
2. Click **Add branch protection rule**.
3. **Branch name pattern:** `main`
4. Check **Require a pull request before merging** (Require approvals: 1).
5. Check **Require status checks to pass before merging**.
   - Search for and require `backend-certification` and `mobile-typecheck`.
6. Check **Do not allow bypassing the above settings**.
7. Repeat steps 2-6 for the `staging` branch pattern.

## 2. Repoint Production Services Away from Fix-Branch Deploy Sources
**Railway UI Runbook:**
1. Navigate to the **SignalRankAI Production** project in Railway.
2. For each service (Engine, Delivery, Web, Gateway, Monolith, Outcome, Worker):
   - Go to **Settings > Deployments**.
   - Under **Deployment Trigger**, ensure the branch is strictly set to `main`.
   - Remove any triggers pointing to `fix/*` or `feature/*` branches.

## 3. Create Real Isolated Staging Environment
**Railway CLI/Terraform:**
```bash
railway environment add staging
railway plugin add postgresql -e staging
railway plugin add redis -e staging
```
Ensure that `configs/env/railway-staging.env.example` is populated in the new environment's variables, substituting realistic test tokens for Telegram and Paystack.

## 4. Mirror Production Role Topology in Staging
In the new Railway `staging` environment, duplicate the production service layout:
1. Create isolated services for `analytics`, `delivery`, `engine`, `gateway`, `monolith_safe`, `outcome`, and `worker`.
2. Apply the `.env` fragments located in `deploy/railway_roles/` to the respective services.
3. Link all staging services to the staging Postgres and Redis plugins created in Step 3.

## 5. Expand Production Postgres Storage & Add Alerts
**Railway UI Runbook:**
1. Navigate to the Production Postgres plugin.
2. Under **Settings > Resources**, upgrade the storage volume to the required new capacity (e.g., 50GB to 100GB).
3. Under **Observability / Alerts**, configure a webhook or email alert:
   - Condition: `Volume Usage > 80%`
   - Condition: `CPU Usage > 90%` for 5 minutes.

## 6. Provision Dedicated R2 Storage Bucket
**Cloudflare CLI (Wrangler):**
```bash
wrangler r2 bucket create signalrank-artifacts
# Apply retention policy via API (example script to keep 30 days of cold backups)
```
Ensure bucket credentials are injected into the Railway environment variables (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`).

## 7. Add Scheduled Restore Certification
To verify backups, configure a GitHub Actions scheduled workflow (`.github/workflows/restore-drill.yml`) that runs weekly:
- Downloads the latest Postgres dump from the R2 bucket.
- Instantiates a temporary `postgres:16` Docker container.
- Loads the dump and runs `scripts/schema_audit.py` to prove database integrity.
