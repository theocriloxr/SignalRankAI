"""Verify research UX with an owned local PostgreSQL database and HTTP process.

All observations and users are synthetic. This is neither broker certification
nor native-device testing. Only the database and process created here are removed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_ENVIRONMENT = {
    "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA",
    "LOCALAPPDATA", "COMSPEC", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA",
    "HOMEDRIVE", "HOMEPATH", "HOME", "PLAYWRIGHT_BROWSERS_PATH",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--browser-python", default=os.getenv("RESEARCH_BROWSER_PYTHON", sys.executable))
    args = parser.parse_args()
    source = make_url(os.environ.get("DATABASE_URL", ""))
    if (os.environ.get("APP_ENV") != "test" or source.get_backend_name() != "postgresql"
            or source.host not in {"127.0.0.1", "localhost"}
            or "test" not in (source.database or "")):
        raise RuntimeError("browser drill requires an explicit loopback test database")
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    database = "signalrank_research_browser_test_" + uuid4().hex[:12]
    owned = source.set(database=database)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {k: v for k, v in os.environ.items() if k.upper() in SYSTEM_ENVIRONMENT}
    env.update(
        APP_ENV="test", ENVIRONMENT="test", SIGNALRANK_ALLOW_DOTENV="0",
        DATABASE_URL=owned.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False),
        DATABASE_MIGRATION_URL=owned.set(drivername="postgresql").render_as_string(hide_password=False),
        APP_COOKIE_SECURE="0", APP_AUTH_SECRET="synthetic-local-browser-test-secret-20261006",
        SIGNALRANK_DISABLE_BACKGROUND_THREADS="1", GLOBAL_EXECUTION_KILL_SWITCH="1",
        REAL_EXECUTION_ENABLED="0", AUTO_EXECUTION_ENABLED="0", AUTO_TRADE_ENABLED="0",
        COPY_TRADE_ENABLED="0", PROP_EXECUTION_ENABLED="0", REAL_PAYOUTS_ENABLED="0",
        PAYMENTS_PUBLIC_ENABLED="0", PYTHONPATH=str(ROOT),
        RESEARCH_BROWSER_BASE_URL=base, RESEARCH_BROWSER_OUTPUT_DIR=str(output),
        BROWSER_CANDIDATE_SHA=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        BROWSER_CANDIDATE_DIRTY="1" if subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip() else "0",
    )
    admin = psycopg2.connect(source.set(drivername="postgresql", database="postgres")
                             .render_as_string(hide_password=False), connect_timeout=10)
    admin.autocommit = True
    created = dropped = False
    server = log = None
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        created = True
        with (output / "migration.log").open("w", encoding="utf-8") as migration:
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env,
                           stdout=migration, stderr=subprocess.STDOUT, check=True, timeout=120)
        subprocess.run([sys.executable, str(ROOT / "tests/research_browser_seed.py")], cwd=ROOT,
                       env=env, check=True, timeout=60)
        log = (output / "server.log").open("w", encoding="utf-8")
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.app:app", "--host", "127.0.0.1",
                                   "--port", str(port), "--lifespan", "off"], cwd=ROOT, env=env,
                                  stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError("owned browser server exited")
            try:
                with urllib.request.urlopen(base + "/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("owned browser server did not become ready")
        return subprocess.run([args.browser_python, str(ROOT / "scripts/verify_research_ui.py")],
                              cwd=ROOT, env=env, timeout=240).returncode
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
        if log:
            log.close()
        try:
            if created:
                with admin.cursor() as cursor:
                    cursor.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                                   "WHERE datname=%s AND pid<>pg_backend_pid()", (database,))
                    cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
                dropped = True
        finally:
            admin.close()
            (output / "cleanup.json").write_text(json.dumps({
                "database": database, "owned_server_stopped": server is None or server.poll() is not None,
                "owned_database_dropped": dropped,
            }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
