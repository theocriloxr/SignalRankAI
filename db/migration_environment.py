"""Keep explicit migration destinations authoritative over local dotenv files."""
from __future__ import annotations

import os
from pathlib import Path


def load_migration_environment(project_root: Path) -> None:
    production = str(os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "").lower() in {"production", "prod"}
    railway = any(os.getenv(name) for name in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID"))
    policy = os.getenv("SIGNALRANK_ALLOW_DOTENV", "0" if production or railway else "1").strip().lower()
    if policy in {"0", "false", "no", "off", ""}:
        return
    if policy not in {"1", "true", "yes", "on"}:
        raise RuntimeError("invalid_migration_dotenv_policy")
    from dotenv import load_dotenv
    # Root-relative paths avoid loading an unrelated shell directory. Existing
    # DATABASE_* variables can never be replaced by either local file.
    load_dotenv(project_root / ".env", override=False)
    load_dotenv(project_root / ".env.local", override=False)
