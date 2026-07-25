import os

# Load local environment overrides if present.
try:
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    load_dotenv(".env.local", override=True)
except Exception:
    pass


def _infer_run_mode() -> str:
    """Resolve the canonical role from RUN_MODE or Railway service naming."""
    from runtime.roles import infer_run_mode
    return infer_run_mode().value


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
        from runtime.all_dev import run as run_all_dev
        run_all_dev()
        return
        # Legacy monolith launch code below is retained for source-level
        # rollback reference but is unreachable after the adapter return.
        print("[boot] all mode → delegating to railway_main:app (webhook route included)", flush=True)
        
    elif mode == "web":
        from runtime.web import run as run_web
        run_web()
        return
    elif mode == "worker":
        from worker.worker import main as worker_main
        worker_main()
        return
    elif mode == "bot":
        from runtime.bot import run as run_bot
        run_bot()
        return
    # Kept below for compatibility with the historical branch layout. The
    # canonical dispatcher is used for every role in the new entrypoint.
    from runtime.dispatcher import dispatch
    requested_mode = str(os.getenv("RUN_MODE") or mode).strip().lower()
    dispatch(requested_mode, legacy_worker=(requested_mode == "worker"))


if __name__ == "__main__":
    main()
