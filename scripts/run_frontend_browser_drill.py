"""Build and test Next against an owned, migrated PostgreSQL/FastAPI instance.

The browser uses the production build and its real same-origin HTTPS API rewrite.
Only synthetic accounts and the database created here are touched. No broker or
delivery credentials are inherited. This is not production/native acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
from urllib.request import urlopen
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_KEYS = {'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP', 'USERPROFILE',
               'APPDATA', 'LOCALAPPDATA', 'COMSPEC', 'PROGRAMFILES', 'PROGRAMFILES(X86)',
               'PROGRAMDATA', 'HOMEDRIVE', 'HOMEPATH', 'HOME', 'PLAYWRIGHT_BROWSERS_PATH'}


def port() -> int:
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def wait_ready(process, url, *, context=None):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('owned browser server exited; inspect its log')
        try:
            with urlopen(url, timeout=2, context=context) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError('owned browser server did not become ready')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--browser-python', required=True)
    parser.add_argument('--workspace-mode', choices=('next','legacy'), default='next')
    args = parser.parse_args()
    source = make_url(os.environ.get('DATABASE_URL', ''))
    if (os.environ.get('APP_ENV') != 'test' or source.get_backend_name() != 'postgresql'
            or source.host not in {'127.0.0.1', 'localhost'} or 'test' not in (source.database or '')):
        raise RuntimeError('frontend drill requires an explicit loopback test database')
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    database = 'signalrank_research_browser_test_' + uuid4().hex[:12]
    owned = source.set(database=database)
    api_port, web_port = port(), port()
    api = f'https://127.0.0.1:{api_port}'
    web = f'http://127.0.0.1:{web_port}'
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Owned local browser test')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=2))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(key, hashes.SHA256()))
    cert_file, key_file = output/'local-ca.pem', output/'local-key.pem'
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    env = {k:v for k,v in os.environ.items() if k.upper() in SYSTEM_KEYS}
    env.update(APP_ENV='test', ENVIRONMENT='test', SIGNALRANK_ALLOW_DOTENV='0',
        DATABASE_URL=owned.set(drivername='postgresql+asyncpg').render_as_string(hide_password=False),
        DATABASE_MIGRATION_URL=owned.set(drivername='postgresql').render_as_string(hide_password=False),
        APP_COOKIE_SECURE='0', APP_AUTH_SECRET='synthetic-local-browser-test-secret-20261006',
        APP_BASE_URL=web, SIGNALRANK_DISABLE_BACKGROUND_THREADS='1', GLOBAL_EXECUTION_KILL_SWITCH='1',
        REAL_EXECUTION_ENABLED='0', AUTO_EXECUTION_ENABLED='0', AUTO_TRADE_ENABLED='0',
        COPY_TRADE_ENABLED='0', PROP_EXECUTION_ENABLED='0', REAL_PAYOUTS_ENABLED='0',
        PAYMENTS_PUBLIC_ENABLED='0', PYTHONPATH=str(ROOT), FRONTEND_BROWSER_BASE_URL=web,
        RESEARCH_BROWSER_BASE_URL=web, FRONTEND_BROWSER_OUTPUT_DIR=str(output),
        FRONTEND_BROWSER_WORKSPACE_MODE=args.workspace_mode,
        BROWSER_CANDIDATE_SHA=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        BROWSER_CANDIDATE_DIRTY='1' if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip() else '0')
    frontend_env = {k:v for k,v in env.items() if k.upper() in SYSTEM_KEYS}
    frontend_env.update(NODE_ENV='production', SIGNALRANK_PLATFORM_API_ORIGIN=api,
        NODE_EXTRA_CA_CERTS=str(cert_file), NEXT_TELEMETRY_DISABLED='1',
        SIGNALRANK_WORKSPACE_MODE=args.workspace_mode,
        SIGNALRANK_FRONTEND_COMMIT=env['BROWSER_CANDIDATE_SHA'])
    admin = psycopg2.connect(source.set(drivername='postgresql',database='postgres')
                             .render_as_string(hide_password=False),connect_timeout=10)
    admin.autocommit = True
    processes, logs = [], []
    created = dropped = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        created = True
        for name, command in [('migration',[sys.executable,'-m','alembic','upgrade','head']),
                              ('seed',[sys.executable,'tests/research_browser_seed.py'])]:
            with (output/f'{name}.log').open('w',encoding='utf-8') as log:
                subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        with (output/'frontend-build.log').open('w',encoding='utf-8') as log:
            subprocess.run(['node','node_modules/next/dist/bin/next','build'],cwd=ROOT/'frontend',
                env=frontend_env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        for name, command, cwd, child_env in [
            ('api',[sys.executable,'-m','uvicorn','web.app:app','--host','127.0.0.1','--port',str(api_port),
                    '--lifespan','off','--ssl-certfile',str(cert_file),'--ssl-keyfile',str(key_file)],ROOT,env),
            ('frontend',['node','node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',str(web_port)],ROOT/'frontend',frontend_env),
        ]:
            log = (output/f'{name}.log').open('w',encoding='utf-8')
            logs.append(log)
            processes.append(subprocess.Popen(command,cwd=cwd,env=child_env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        wait_ready(processes[0],api+'/health',context=ssl.create_default_context(cafile=str(cert_file)))
        wait_ready(processes[1],web+'/login')
        verifier = 'scripts/verify_frontend_legacy_routing.py' if args.workspace_mode == 'legacy' else 'scripts/verify_frontend_ui.py'
        return subprocess.run([args.browser_python,verifier],cwd=ROOT,env=env,timeout=900).returncode
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        for log in logs:
            log.close()
        try:
            if created:
                with admin.cursor() as cursor:
                    cursor.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',(database,))
                    cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
                dropped = True
        finally:
            admin.close()
            key_file.unlink(missing_ok=True)
            (output/'cleanup.json').write_text(json.dumps({'database':database,'owned_servers_stopped':all(p.poll() is not None for p in processes),
                'owned_database_dropped':dropped,'local_key_removed':not key_file.exists()},indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
