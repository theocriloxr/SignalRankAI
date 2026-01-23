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
    """Unified entrypoint.

    Select behavior via `RUN_MODE`:
    - `web`: serve FastAPI (`web.app:app`) via uvicorn
    - `worker`: run async worker loop
    - `bot`: run Telegram polling bot
    - `engine` (default): run synchronous engine loop
    - `all`: run web + bot + engine + worker in one process (single Railway service)
    """

    mode = _infer_run_mode()

    print(
        "[boot] starting | "
        f"run_mode={mode} "
        f"railway_service={os.getenv('RAILWAY_SERVICE_NAME')} "
        f"railway_env={os.getenv('RAILWAY_ENVIRONMENT')} "
        f"railway_deployment={os.getenv('RAILWAY_DEPLOYMENT_ID')} "
        f"git_sha={os.getenv('RAILWAY_GIT_COMMIT_SHA')}",
        flush=True,
    )

    # Railway-friendly: auto-run migrations against Postgres (idempotent)
    # and optionally wipe data for a clean "fresh start".
    try:
        from db.auto_ops import run_startup_ops

        # In single-service mode, treat startup ops as "web" so it can run
        # migrations and (optionally) perform a one-time fresh start.
        run_startup_ops("web" if mode == "all" else mode)
    except Exception:
        # If startup ops fail, crash loudly so Railway logs show the issue.
        raise

    # Market data connectivity self-check (non-fatal): prints warnings if
    # Binance/AlphaVantage are unreachable so you can see "can it see charts"
    # immediately in Railway logs.
    try:
        from data.startup_selfcheck import run_startup_data_selfcheck

        run_startup_data_selfcheck()
    except Exception:
        # Never block startup due to self-check issues.
        pass

    if mode == "all":
        dry_run = _env_bool("DRY_RUN", False)

        def _run_thread(name: str, fn) -> None:
            try:
                print(f"[boot] RUN_MODE=all starting {name}", flush=True)
                fn()
                print(f"[boot] RUN_MODE=all {name} exited", flush=True)
            except Exception as exc:
                print(
                    f"[boot] RUN_MODE=all {name} crashed: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
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

        # Run web/worker/engine in background threads.
        # Keep the Telegram bot in the main thread (most predictable).
        threads = [
            threading.Thread(target=lambda: _run_thread("web", _run_web_impl), name="web", daemon=True),
            threading.Thread(
                target=lambda: _run_thread("worker", _run_worker_impl),
                name="worker",
                daemon=True,
            ),
            threading.Thread(
                target=lambda: _run_thread("engine", _run_engine_impl),
                name="engine",
                daemon=True,
            ),
        ]
        for t in threads:
            t.start()

        from signalrank_telegram.bot import run_bot as bot_main

        print("[boot] RUN_MODE=all starting telegram bot", flush=True)
        bot_main()
        print("[boot] RUN_MODE=all telegram bot exited", flush=True)
        return

    if mode == "web":
        import uvicorn

        port = int(os.getenv("PORT", "8000"))
        uvicorn.run("web.app:app", host="0.0.0.0", port=port, log_level="info")
        return

    if mode == "worker":
        from worker.worker import main as worker_main

        worker_main()
        return

    if mode == "bot":
        from signalrank_telegram.bot import run_bot as bot_main

        bot_main()
        return

    # engine (default)
    from engine.core import main_loop

    dry_run = _env_bool("DRY_RUN", False)
    main_loop(dry_run)


if __name__ == "__main__":
    main()
