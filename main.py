import os
import sys
import asyncio
import traceback




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



def main() -> None:
    # Configure logging early so modules can log during init
    try:
        from utils.logging_config import setup_logging
        from core.settings import validate_required_settings, get_settings
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
    """Unified entrypoint with strict RUN_MODE separation and robust lifecycle.
    - Only one instance of each service (web, worker, bot, engine) per process.
    - RUN_MODE=all: runs each in a dedicated thread, with clear logs and error handling.
    - Prevents duplicate schedulers/jobs and ensures explicit lifecycle.
    """
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
        from config import config
        dry_run = config.DRY_RUN

        async def _run_all() -> None:
            """Run web, worker, engine, and bot concurrently with auto-restart.

            Each service runs in its own supervised task. If any service crashes it
            is automatically restarted with exponential backoff (capped at 5 minutes)
            so the entire process never stays dead after a transient failure.

            - Web:    uvicorn.Server (native async)
            - Engine: ThreadPoolExecutor (blocking main_loop)
            - Worker: ThreadPoolExecutor (blocking worker_main)
            - Bot:    ThreadPoolExecutor (PTB run_polling owns its own event loop)
            """
            loop = asyncio.get_running_loop()
            _RESTART_BASE_DELAY = 5     # seconds before first restart
            _RESTART_MAX_DELAY  = 300   # cap at 5 minutes

            async def _supervised(name: str, target) -> None:
                """Run *target* coroutine-factory, restarting it on any exception."""
                delay = _RESTART_BASE_DELAY
                while True:
                    print(f"[boot] {name} starting", flush=True)
                    try:
                        await target()
                        # Clean exit (e.g. KeyboardInterrupt forwarded): don't restart.
                        print(f"[boot] {name} exited cleanly", flush=True)
                        return
                    except asyncio.CancelledError:
                        print(f"[boot] {name} cancelled", flush=True)
                        return
                    except Exception as exc:
                        print(
                            f"[boot] {name} crashed ({type(exc).__name__}: {exc}) — "
                            f"restarting in {delay}s",
                            file=sys.stderr, flush=True,
                        )
                        traceback.print_exc()
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, _RESTART_MAX_DELAY)

            async def _web_once() -> None:
                import uvicorn
                port = int(os.getenv("PORT", "8000"))
                cfg = uvicorn.Config(
                    "web.app:app", host="0.0.0.0", port=port, log_level="info"
                )
                server = uvicorn.Server(cfg)
                await server.serve()

            async def _engine_once() -> None:
                from engine.core import main_loop
                await loop.run_in_executor(None, lambda: main_loop(dry_run))

            async def _worker_once() -> None:
                from worker.worker import main as worker_main
                await loop.run_in_executor(None, worker_main)

            async def _bot_once() -> None:
                from signalrank_telegram.bot import run_bot as bot_main
                # PTB run_polling() manages its own event loop; run in executor
                # to avoid conflicting with the outer asyncio loop.
                await loop.run_in_executor(None, bot_main)

            await asyncio.gather(
                _supervised("web",    _web_once),
                _supervised("engine", _engine_once),
                _supervised("worker", _worker_once),
                _supervised("bot",    _bot_once),
            )

        asyncio.run(_run_all())
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
