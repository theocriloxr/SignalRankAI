import os

# Load local environment overrides if present.
try:
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    load_dotenv(".env.local", override=True)
except Exception:
    pass


def _infer_run_mode() -> str:
    """Derive a sensible default RUN_MODE from Railway service naming.

    If RUN_MODE is explicitly set, it wins. Otherwise we look at
    RAILWAY_SERVICE_NAME/RAILWAY_SERVICE and pick a mode so you can deploy
    four Railway services without manual env tweaks.
    """

    explicit = os.getenv("RUN_MODE")
    if explicit:
        return explicit.strip().lower()

    service = (os.getenv("RAILWAY_SERVICE_NAME") or os.getenv("RAILWAY_SERVICE") or "").lower()
    for needle, mode in (
        ("all", "all"),
        ("web", "web"),
        ("bot", "bot"),
        ("telegram", "bot"),
        ("worker", "worker"),
        ("engine", "engine"),
        ("core", "engine"),
    ):
        if needle in service:
            return mode

    return "engine"


def _check_database_configured() -> bool:
    """Check if database is properly configured at startup."""
    try:
        from db.session import is_db_configured
        from config import resolve_database_url
        
        # First try resolve_database_url which checks multiple env vars
        url = resolve_database_url(async_driver=False)
        if url:
            return True
            
        # Fallback to session check
        return is_db_configured()
    except Exception as e:
        print(f"[startup] DB config check failed: {e}", flush=True)
        return False


def main() -> None:
    # Configure logging early so modules can log during init
    try:
        from utils.logging_config import setup_logging
        from core.settings import validate_required_settings
        import os
        json_logs = str(os.getenv("LOG_JSON") or "0").strip().lower() in {"1", "true", "yes"}
        setup_logging(json=json_logs)
        # Validate required settings early
        try:
            validate_required_settings()
        except Exception as e:
            print(f"Missing required settings: {e}", flush=True)
            raise
    except Exception:
        pass
    
    # Early database configuration check
    db_configured = _check_database_configured()
    if not db_configured:
        print("[startup] WARNING: Database not configured - some features may not work", flush=True)
    else:
        print("[startup] Database configured successfully", flush=True)

    # Unified entrypoint with strict RUN_MODE separation and robust lifecycle.
    # Only one instance of each service (web, worker, bot, engine) per process.
    # RUN_MODE=all: runs each in a dedicated thread, with clear logs and error handling.
    # Prevents duplicate schedulers/jobs and ensures explicit lifecycle.
    mode = _infer_run_mode()
    print(
        "[boot] starting | "
        f"run_mode={mode} "
        f"railway_service={os.getenv('RAILWAY_SERVICE_NAME')} "
        f"railway_env={os.getenv('RAILWAY_ENVIRONMENT')} "
        f"railway_deployment={os.getenv('RAILWAY_DEPLOYMENT_ID')} "
        f"git_sha={os.getenv('RAILWAY_GIT_COMMIT_SHA')} ",
        flush=True,
    )
    # Run DB migrations and startup ops once per process
    try:
        from db.auto_ops import run_startup_ops
        run_startup_ops("web" if mode == "all" else mode)
    except Exception:
        raise
    try:
        from data.startup_selfcheck import run_startup_data_selfcheck
        run_startup_data_selfcheck()
    except Exception:
        pass
    if mode == "all":
        # Delegate to railway_main which owns the /telegram/webhook FastAPI route.
        # Running separate per-mode processes (old approach) caused the bot process
        # to register a Telegram webhook URL that the web process (web.app:app,
        # which has no /telegram/webhook route) couldn't serve, producing 404s for
        # every inbound Telegram update.  railway_main bundles web + engine + worker
        # + bot in a single asyncio event loop with correct route registration.
        import uvicorn
        port = int(os.getenv("PORT", "8000"))
        print("[boot] all mode → delegating to railway_main:app (webhook route included)", flush=True)
        uvicorn.run("railway_main:app", host="0.0.0.0", port=port, log_level="info")
        return
    elif mode == "web":
        import uvicorn
        port = int(os.getenv("PORT", "8000"))
        uvicorn.run("web.app:app", host="0.0.0.0", port=port, log_level="info")
        return
    elif mode == "worker":
        from worker.worker import main as worker_main
        worker_main()
        return
    elif mode == "bot":
        from signalrank_telegram.bot import run_bot as bot_main
        bot_main()
        return
    # engine (default)
    from engine.core import main_loop
    from config import config
    dry_run = config.DRY_RUN
    main_loop(dry_run)


if __name__ == "__main__":
    main()
