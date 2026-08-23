from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from services.codex_governance import collect_codex_governance_context

_SENSITIVE_KEYS = {
    "api_key", "authorization", "bot_token", "chat_id", "email", "password",
    "payment_details", "phone", "secret", "telegram_id", "token", "user_id",
}


def anonymize_research_payload(value: Any) -> Any:
    """Remove identifiers and secrets before research data leaves the trust boundary."""
    if isinstance(value, Mapping):
        return {
            str(key): anonymize_research_payload(item)
            for key, item in value.items()
            if str(key).strip().lower() not in _SENSITIVE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [anonymize_research_payload(item) for item in value]
    return value


def dataset_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def collect_weekly_snapshot(days: int = 7) -> dict[str, Any]:
    raw = await collect_codex_governance_context(days=max(1, int(days)), limit=50)
    clean = anonymize_research_payload(raw)
    return {"snapshot": clean, "dataset_hash": dataset_hash(clean)}
