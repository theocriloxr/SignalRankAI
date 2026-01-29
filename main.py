import os
import sys
import threading
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
        def _run_thread(name: str, fn) -> None:
            try:
                print(f"[boot] RUN_MODE=all starting {name}", flush=True)
                fn()
                print(f"[boot] RUN_MODE=all {name} exited", flush=True)
            except Exception as exc:
                print(f"[boot] RUN_MODE=all {name} crashed: {exc}", file=sys.stderr, flush=True)
                traceback.print_exc()
        def _run_web_impl() -> None:
            import uvicorn
            port = int(os.getenv("PORT", "8000"))
            uvicorn.run("web.app:app", host="0.0.0.0", port=port, log_level="info")
        def _run_worker_impl() -> None:
            from worker.worker import main as worker_main
            worker_main()
        def _run_engine_impl() -> None:
            from engine.core import main_loop
            main_loop(dry_run)
        threads = [
            threading.Thread(target=lambda: _run_thread("web", _run_web_impl), name="web", daemon=True),
            threading.Thread(target=lambda: _run_thread("worker", _run_worker_impl), name="worker", daemon=True),
            threading.Thread(target=lambda: _run_thread("engine", _run_engine_impl), name="engine", daemon=True),
        ]
        for t in threads:
            t.start()
        from signalrank_telegram.bot import run_bot as bot_main
        print("[boot] RUN_MODE=all starting telegram bot", flush=True)
        bot_main()
        print("[boot] RUN_MODE=all telegram bot exited", flush=True)
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
