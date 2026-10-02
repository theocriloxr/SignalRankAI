from __future__ import annotations

import logging
import sys
from typing import Optional


def setup_logging(level: int = logging.INFO, json: bool = True) -> None:
    """Basic logging setup used by scripts and main entrypoints.

    - Work Package G: Enforces structured JSON logging and injects correlation_id.
    """
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(stream=sys.stdout)
    
    try:
        import json as _json
        from utils.context import get_correlation_id

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                payload = {
                    "ts": int(record.created),
                    "level": record.levelname,
                    "name": record.name,
                    "msg": record.getMessage(),
                }
                
                # Inject correlation ID if present in context
                corr_id = get_correlation_id()
                if corr_id:
                    payload["correlation_id"] = corr_id
                    
                try:
                    if record.exc_info:
                        payload["exc"] = self.formatException(record.exc_info)
                except Exception:
                    pass
                return _json.dumps(payload)

        handler.setFormatter(JsonFormatter())
    except Exception:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    # Remove other handlers to avoid duplicate logs in certain environments
    for h in list(root.handlers):
        root.removeHandler(h)

    root.addHandler(handler)

    # httpx logs complete request URLs at INFO. Telegram Bot API URLs contain
    # the bot token in the path, so these libraries must never emit INFO-level
    # request lines in any environment. Application-level Telegram events are
    # logged separately without credentials.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Optionally initialize Sentry if available via env SENTRY_DSN
    try:
        import os
        dsn = os.getenv("SENTRY_DSN") or os.getenv("SENTRY_URL")
        if dsn:
            try:
                import sentry_sdk
                sentry_kwargs = {}
                try:
                    traces = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
                    sentry_kwargs["traces_sample_rate"] = traces
                except Exception:
                    pass
                try:
                    environment = os.getenv("SENTRY_ENVIRONMENT")
                    if environment:
                        sentry_kwargs["environment"] = environment
                except Exception:
                    pass
                sentry_sdk.init(dsn, **sentry_kwargs)
                root.info("Sentry initialized")
            except Exception:
                root.warning("Sentry SDK not available or failed to initialize")
    except Exception:
        pass

