"""Versioned prompt registry for external AI reviews.

Prompts are intentionally kept out of Python business logic so trading-review
behavior can be tuned and audited without touching the signal engine. Every AI
review should carry the prompt version used, either in the signal payload or in
its persisted review metadata.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT_FILE = Path(__file__).resolve().parents[1] / "configs" / "prompts" / "gemini_prompts.json"


@lru_cache(maxsize=8)
def _load_prompt_file(path: str) -> dict[str, Any]:
    try:
        p = Path(path)
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("prompt file must contain a JSON object")
        return data
    except Exception as exc:
        logger.warning("[prompt_registry] failed to load prompt file path=%s err=%s", path, exc)
        return {"version": "missing_prompt_file", "templates": {}}


def prompt_file_path() -> str:
    return (os.getenv("AI_PROMPT_CONFIG_PATH") or str(_DEFAULT_PROMPT_FILE)).strip()


def prompt_version() -> str:
    data = _load_prompt_file(prompt_file_path())
    version = str(data.get("version") or os.getenv("AI_PROMPT_VERSION") or "unknown_prompt_version").strip()
    return version or "unknown_prompt_version"


def render_prompt(name: str, **context: Any) -> tuple[str, str]:
    """Return (prompt, version) for a named template.

    Formatting failures return a defensive fallback containing the context so AI
    calls degrade safely rather than crashing the engine.
    """
    data = _load_prompt_file(prompt_file_path())
    version = prompt_version()
    templates = data.get("templates") if isinstance(data.get("templates"), dict) else {}
    template = str(templates.get(name) or "{context}")
    safe_context = {k: ("" if v is None else v) for k, v in context.items()}
    safe_context.setdefault("context", context)
    try:
        return template.format(**safe_context), version
    except Exception as exc:
        logger.warning("[prompt_registry] prompt render failed name=%s version=%s err=%s", name, version, exc)
        return f"Prompt template render failed for {name}. Context: {context}", version


__all__ = ["render_prompt", "prompt_version", "prompt_file_path"]
