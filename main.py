import os


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    """Unified entrypoint.

    Select behavior via `RUN_MODE`:
    - `web`: serve FastAPI (`web.app:app`) via uvicorn
    - `worker`: run async worker loop
    - `bot`: run Telegram polling bot
    - `engine` (default): run synchronous engine loop
    """

    mode = (os.getenv("RUN_MODE") or "engine").strip().lower()

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
