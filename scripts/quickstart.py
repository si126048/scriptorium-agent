#!/usr/bin/env python3
"""One-command bootstrap for Scriptorium.

    python scripts/quickstart.py --check              # diagnose this machine
    python scripts/quickstart.py --docker             # PostgreSQL + API + worker (no search)
    python scripts/quickstart.py --docker --with-search
    python scripts/quickstart.py --native --database-url postgresql+psycopg://...

Docker mode builds the image, generates .env.compose on first use, waits for /health and prints
the workbench URL. Native mode installs the Python extras into .venv, migrates the database,
builds the web client when needed and runs API + worker in the foreground (Ctrl+C stops both).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / '.venv'
IS_WINDOWS = platform.system() == 'Windows'
PYTHON = VENV / ('Scripts/python.exe' if IS_WINDOWS else 'bin/python')
COMPOSE_ENV = ROOT / '.env.compose'
EXAMPLE_ENV = ROOT / '.env.compose.example'


def say(message: str = '') -> None:
    print(message, flush=True)


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    say('$ ' + ' '.join(command))
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def port_open(port: int, host: str = '127.0.0.1') -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def wait_health(url: str, seconds: int, label: str) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + '/health', timeout=2) as response:
                body = json.loads(response.read())
            if body.get('status') == 'ok':
                say(f'{label}: {json.dumps(body, ensure_ascii=False)}')
                return True
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        time.sleep(1)
    return False


def write_compose_env() -> None:
    if COMPOSE_ENV.exists():
        say(f'Using existing {COMPOSE_ENV.name}')
        return
    text = EXAMPLE_ENV.read_text(encoding='utf-8').replace(
        'change-me-url-safe', secrets.token_urlsafe(24))
    COMPOSE_ENV.write_text(text, encoding='utf-8')
    say(f'Created {COMPOSE_ENV.name} with a random database password')


def check() -> int:
    problems = 0
    say('Scriptorium quickstart check')
    say(f'  platform     {platform.system()} {platform.machine()}')
    say(f'  python       {sys.version.split()[0]} at {sys.executable}')
    if sys.version_info < (3, 12):  # noqa: UP036 - this check exists for unsupported interpreters
        say('  [!] Python 3.12+ is required'); problems += 1
    node = shutil.which('node')
    npm = shutil.which('npm')
    say(f'  node/npm     {node or "missing"} / {npm or "missing"}')
    if not npm:
        say('  [i] no npm: Docker mode still works; native mode needs a prebuilt web/dist')
    docker = shutil.which('docker')
    say(f'  docker       {docker or "missing"}')
    if docker:
        try:
            run([docker, 'compose', 'version'], capture_output=True, text=True)
            say('  compose      available')
        except subprocess.CalledProcessError:
            say('  [i] docker compose plugin missing')
    say(f'  web/dist     {"present" if (ROOT / "web/dist/index.html").exists() else "missing"}')
    say(f'  .venv        {"present" if VENV.exists() else "missing"}')
    say(f'  .env.compose {"present" if COMPOSE_ENV.exists() else "missing"}')
    say(f'  port 8010    {"in use" if port_open(8010) else "free"}')
    db = os.getenv('SCRIPTORIUM_DATABASE_URL', '')
    es = os.getenv('SCRIPTORIUM_ELASTICSEARCH_URL')
    search = 'disabled (empty URL)' if es is not None and not es.strip() else (es or 'default http://127.0.0.1:9200')
    say(f'  database     {db.split("@")[-1] if db else "(not set)"}')
    say(f'  search       {search}')
    say()
    say('Next: --docker (recommended) or --native --database-url <postgres url>')
    return 1 if problems else 0


def docker(args: argparse.Namespace) -> int:
    if not shutil.which('docker'):
        say('Docker is not installed. Use --native or install Docker Desktop.')
        return 1
    write_compose_env()
    compose = ROOT / ('compose.research.yml' if args.with_search else 'compose.research.lite.yml')
    base = ['docker', 'compose', '-f', str(compose), '--env-file', str(COMPOSE_ENV)]
    try:
        run(base + ['up', '-d', '--build'])
    except subprocess.CalledProcessError:
        say('Compose failed. Inspect with: docker compose -f '
            f'{compose.name} --env-file .env.compose logs')
        return 1
    say('Waiting for the API (first build can take a few minutes)…')
    if not wait_health(f'http://127.0.0.1:{args.port}', 300, 'health'):
        say('API did not become healthy. Inspect container logs with the command above.')
        return 1
    say()
    say(f'Workbench: http://127.0.0.1:{args.port}')
    say(f'Stop:      docker compose -f {compose.name} --env-file .env.compose down')
    say('Logs:      docker compose -f ' + compose.name + ' --env-file .env.compose logs -f api worker')
    if not args.with_search:
        say('Search:    disabled (material scan fallback). Add --with-search for full-text search.')
    if args.open:
        open_browser(f'http://127.0.0.1:{args.port}')
    return 0


def ensure_venv(args: argparse.Namespace) -> None:
    if not VENV.exists():
        run([sys.executable, '-m', 'venv', str(VENV)])
    pip = PYTHON
    run([str(pip), '-m', 'pip', 'install', '--upgrade', 'pip', '--quiet'])
    run([str(pip), '-m', 'pip', 'install', '-e', '.[research]', '--quiet'])


def ensure_web(args: argparse.Namespace) -> bool:
    if (ROOT / 'web/dist/index.html').exists() and not args.build:
        return True
    npm = shutil.which('npm')
    if not npm:
        say('web/dist is missing and npm is unavailable; install Node.js 20+ or use --docker.')
        return False
    run([npm, '--prefix', 'web', 'ci'])
    run([npm, '--prefix', 'web', 'run', 'build'])
    return True


def native(args: argparse.Namespace) -> int:
    database = args.database_url or os.getenv('SCRIPTORIUM_DATABASE_URL', '')
    if not database:
        say('Set SCRIPTORIUM_DATABASE_URL or pass --database-url '
            'postgresql+psycopg://user:password@127.0.0.1:5432/scriptorium')
        say('(A local PostgreSQL 17 is enough; Elasticsearch is optional.)')
        return 1
    if not args.no_install:
        ensure_venv(args)
    python = PYTHON if PYTHON.exists() else Path(sys.executable)
    if not args.no_build and not ensure_web(args):
        return 1
    env = dict(os.environ)
    env['SCRIPTORIUM_DATABASE_URL'] = database
    env.setdefault('SCRIPTORIUM_OBJECT_ROOT', str(ROOT / 'output' / 'research-objects'))
    env['SCRIPTORIUM_PORT'] = str(args.port)
    if not env.get('SCRIPTORIUM_RESEARCH_ORIGINS'):
        env['SCRIPTORIUM_RESEARCH_ORIGINS'] = (
            f'http://127.0.0.1:{args.port},http://localhost:{args.port}')
    if not args.no_init:
        run([str(python), '-m', 'scriptorium.research.cli', 'init-db'], env=env)
    worker = subprocess.Popen([str(python), '-m', 'scriptorium.research.cli', 'worker'], cwd=ROOT, env=env)
    say(f'Worker pid {worker.pid}; starting API on port {args.port} (Ctrl+C stops both)…')
    api = subprocess.Popen([str(python), '-m', 'scriptorium.research.cli', 'serve',
                            '--port', str(args.port)], cwd=ROOT, env=env)
    try:
        if wait_health(f'http://127.0.0.1:{args.port}', 60, 'health'):
            say()
            say(f'Workbench: http://127.0.0.1:{args.port}')
            configured = os.getenv('SCRIPTORIUM_ELASTICSEARCH_URL')
            say('Search: ' + ('disabled (material scan fallback)' if configured is not None and not configured.strip()
                              else f'{configured or "http://127.0.0.1:9200"} (unreachable URLs fall back automatically)'))
            if args.open:
                open_browser(f'http://127.0.0.1:{args.port}')
        api.wait()
    except KeyboardInterrupt:
        say('\nStopping…')
    finally:
        for process in (api, worker):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
    return api.returncode or 0


def open_browser(url: str) -> None:
    import webbrowser
    webbrowser.open(url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--docker', action='store_true', help='run PostgreSQL + API + worker with Docker')
    mode.add_argument('--native', action='store_true', help='run against an existing PostgreSQL')
    parser.add_argument('--check', action='store_true', help='print an environment report and exit')
    parser.add_argument('--with-search', action='store_true', help='Docker mode: include Elasticsearch')
    parser.add_argument('--database-url', default='', help='native mode: SQLAlchemy PostgreSQL URL')
    parser.add_argument('--port', type=int, default=8010)
    parser.add_argument('--no-install', action='store_true', help='native mode: skip .venv creation/pip install')
    parser.add_argument('--no-build', action='store_true', help='native mode: require an existing web/dist')
    parser.add_argument('--build', action='store_true', help='native mode: rebuild web/dist')
    parser.add_argument('--no-init', action='store_true', help='native mode: skip init-db')
    parser.add_argument('--open', action='store_true', help='open the workbench in a browser')
    args = parser.parse_args(argv)
    if args.check or not (args.docker or args.native):
        return check()
    return docker(args) if args.docker else native(args)


if __name__ == '__main__':
    raise SystemExit(main())
