"""Signal-engine role adapter."""

from __future__ import annotations


def run(*, dry_run: bool | None = None) -> None:
    from config import config
    from engine.core import main_loop

    main_loop(config.DRY_RUN if dry_run is None else bool(dry_run))


start = run

__all__ = ["run", "start"]
