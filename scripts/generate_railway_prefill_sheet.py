from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / ".env.production.template"
OUTPUT_PATH = ROOT / "docs" / "RAILWAY_VARIABLE_STATUS_PREFILLED.md"


@dataclass(frozen=True)
class VarSpec:
    key: str
    required: bool
    note: str


SPECS: list[VarSpec] = [
    VarSpec("TELEGRAM_BOT_TOKEN", True, "Telegram bot auth token"),
    VarSpec("OWNER_IDS", True, "Owner/admin routing and privileged commands"),
    VarSpec("GEMINI_API_KEY", True, "AI runtime readiness gate"),
    VarSpec("META_API_TOKEN", True, "Execution integration readiness gate"),
    VarSpec("ENCRYPTION_KEY", True, "Encrypted secret/state protection"),
    VarSpec("DATABASE_PUBLIC_URL", True, "Primary DB connection URL on Railway"),
    VarSpec("DATABASE_URL", False, "Fallback DB connection URL"),
    VarSpec("REDIS_URL", True, "Queue/cache backend"),
    VarSpec("APP_BASE_URL", False, "Webhook base URL fallback"),
    VarSpec("WEBHOOK_URL", False, "Webhook base URL source"),
    VarSpec("RAILWAY_PUBLIC_DOMAIN", False, "Railway domain webhook source"),
    VarSpec("BYPASS_KEY", True, "Admin bypass and unlock guardrail key"),
    VarSpec("RUN_MODE", False, "Service mode (recommended: all/web/bot/engine/worker)"),
    VarSpec("TELEGRAM_USE_WEBHOOK", False, "Webhook mode toggle"),
    VarSpec("WEBHOOK_QUEUE_USE_REDIS", False, "Redis queue backend toggle"),
    VarSpec("DB_POOL_SIZE", False, "DB pooled connections"),
    VarSpec("DB_MAX_OVERFLOW", False, "DB overflow connections"),
    VarSpec("REDIS_MAX_CONNECTIONS", False, "Redis connection pool cap"),
    VarSpec("REDIS_WEBHOOK_QUEUE_MAX_DEPTH", False, "Webhook queue max depth"),
    VarSpec("REDIS_SIGNAL_QUEUE_MAX_DEPTH", False, "Signal queue max depth"),
    VarSpec("PAYMENTS_ENABLED", False, "Payment flow switch"),
    VarSpec("PAYSTACK_SECRET_KEY", False, "Paystack integration key"),
    VarSpec("PAYSTACK_WEBHOOK_SECRET", False, "Paystack webhook verification"),
    VarSpec("ML_MODEL_RUNTIME_STATE_KEY", False, "DB key for model payload durability"),
    VarSpec("X_BEARER_TOKEN", False, "X sentiment provider token"),
]


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def _mask_value(key: str, value: str) -> str:
    if not value:
        return "-"
    low = key.lower()
    if any(tok in low for tok in ("key", "token", "secret", "password", "dsn", "url")):
        if len(value) <= 6:
            return "***"
        return f"{value[:3]}...{value[-2:]}"
    if len(value) > 18:
        return f"{value[:8]}..."
    return value


def _present(value: str | None) -> bool:
    return bool((value or "").strip())


def _resolve_value(env_file_values: dict[str, str], key: str) -> tuple[str, str]:
    file_v = env_file_values.get(key, "")
    if _present(file_v):
        return file_v, "template"
    env_v = os.getenv(key, "")
    if _present(env_v):
        return env_v, "process_env"
    return "", "missing"


def main() -> int:
    file_values = _parse_env_file(TEMPLATE_PATH)

    lines: list[str] = []
    lines.append("# Railway Variable Status (Prefilled)")
    lines.append("")
    lines.append("Generated from the current .env.production.template and local process environment.")
    lines.append("")
    lines.append(f"- Generated at: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Template source: {TEMPLATE_PATH.name}")
    lines.append("")

    lines.append("## Core Matrix")
    lines.append("")
    lines.append("| Variable | Required | Status | Source | Value Preview | Note |")
    lines.append("|---|---|---|---|---|---|")

    missing_required = 0
    for spec in SPECS:
        value, src = _resolve_value(file_values, spec.key)
        status = "SET" if _present(value) else "MISSING"
        if spec.required and status == "MISSING":
            missing_required += 1
        required = "yes" if spec.required else "no"
        preview = _mask_value(spec.key, value)
        lines.append(
            f"| {spec.key} | {required} | {status} | {src} | {preview} | {spec.note} |"
        )

    lines.append("")
    lines.append("## Group Checks")
    lines.append("")

    owner_ok = _present(file_values.get("OWNER_IDS", "")) or _present(os.getenv("OWNER_IDS", ""))
    domain_ok = any(
        _present(file_values.get(k, "")) or _present(os.getenv(k, ""))
        for k in ("APP_BASE_URL", "WEBHOOK_URL", "RAILWAY_PUBLIC_DOMAIN")
    )
    db_ok = _present(file_values.get("DATABASE_PUBLIC_URL", "")) or _present(file_values.get("DATABASE_URL", "")) or _present(os.getenv("DATABASE_PUBLIC_URL", "")) or _present(os.getenv("DATABASE_URL", ""))

    lines.append(f"- Owner identity set: {'yes' if owner_ok else 'no'}")
    lines.append(f"- Public webhook domain source set: {'yes' if domain_ok else 'no'}")
    lines.append(f"- Database URL source set: {'yes' if db_ok else 'no'}")
    lines.append(f"- Missing required keys: {missing_required}")
    lines.append("")
    lines.append("## Next Step")
    lines.append("")
    lines.append("1. Fill any MISSING required keys in Railway variables.")
    lines.append("2. Re-run: python scripts/generate_railway_prefill_sheet.py")
    lines.append("3. Run smoke checks: python scripts/post_deploy_smoke.py")

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
