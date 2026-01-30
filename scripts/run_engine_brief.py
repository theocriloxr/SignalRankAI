"""Run the engine `main_loop` briefly (dry-run) and exit after a timeout.

This script is intended for local verification: it starts the engine in
DRY_RUN mode and exits the process after `RUN_SECONDS` to avoid a long-
running loop during automated checks.
"""
import os
import threading
import time
import sys

os.environ.setdefault('DRY_RUN', '1')

RUN_SECONDS = int(os.getenv('ENGINE_BRIEF_SECONDS', '25'))


def _run():
    try:
        import engine.core as core
        core.main_loop(DRY_RUN=True)
    except Exception as e:
        print(f"Engine run raised: {e}", flush=True)


if __name__ == '__main__':
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print(f"Started engine.preview for {RUN_SECONDS}s (DRY_RUN=1)")
    try:
        time.sleep(RUN_SECONDS)
    except KeyboardInterrupt:
        pass
    print("Timeout reached; exiting.")
    sys.exit(0)
