"""Current-user native service installation and bounded, owned-process supervision.

No Docker, global Python/Java, trust-authentication database, or port-based process killing.
The packaged backend also dispatches these commands, so installed users need no interpreter.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

from . import windows_credentials as vault

PACKAGES = {
    'postgres': {'version': '17.6', 'url': 'https://get.enterprisedb.com/postgresql/postgresql-17.6-1-windows-x64-binaries.zip',
        'sha256': 'd378882abd001a186735acd6f6ba716bca6ccd192e800412d4fd15ed25376b3e'},
    'elasticsearch': {'version': '8.19.3', 'url': 'https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.19.3-windows-x86_64.zip',
        'sha256': '5e447aa3b3616524a2d3fa4aed5347e9bcaa91823e41dd0e6df5f23ff824f127'},
}


def default_root():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Scriptorium' / 'research'


def target(root):
    return 'Scriptorium/local/' + hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:24]


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(pending, path)


def phase(root, state, **extra):
    """Publish coarse progress for the desktop window; the supervisor overwrites it later."""
    atomic(root / 'runtime.json', {'state': state, 'updated_at': time.time(), **extra})


def free_port(preferred):
    with socket.socket() as listener:
        try:
            listener.bind(('127.0.0.1', preferred))
        except OSError:
            listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def executable(*args):
    return ([sys.executable] if getattr(sys, 'frozen', False) else
            [sys.executable, '-m', 'scriptorium.desktop_entry']) + list(args)


def _sanitize(text):
    """Keep one short, actionable line; never echo arguments or environment values."""
    line = next((item.strip() for item in reversed((text or '').splitlines()) if item.strip()), '')
    return line[:300]


def decode_output(data):
    """PostgreSQL's Windows tools can emit system-code-page messages, not UTF-8."""
    if isinstance(data, str):
        return data
    import locale
    for encoding in dict.fromkeys(['utf-8', locale.getpreferredencoding(False), 'gb18030']):
        try:
            return (data or b'').decode(encoding)
        except (UnicodeDecodeError, LookupError):
            pass
    return (data or b'').decode('utf-8', 'replace')


def wait_postgres(root, pg, port, child, stop_file, *, timeout=120):
    """A listening socket may still reject SQL during startup or crash recovery."""
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if stop_file.exists():
            raise RuntimeError('LOCAL_START_CANCELLED')
        if child.poll() is not None:
            raise RuntimeError('LOCAL_POSTGRES_EXITED:' + _log_tail(root, 'postgres'))
        probe = subprocess.run([str(pg / 'pg_isready.exe'), '-h', '127.0.0.1',
            '-p', str(port), '-U', 'scriptorium', '-d', 'postgres', '-t', '1'],
            capture_output=True, check=False, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if probe.returncode == 0:
            if child.poll() is not None:
                raise RuntimeError('LOCAL_POSTGRES_EXITED:' + _log_tail(root, 'postgres'))
            return
        if probe.returncode not in (1, 2):
            raise RuntimeError('LOCAL_POSTGRES_PROBE_FAILED:' + _sanitize(decode_output(probe.stderr)))
        time.sleep(.5)
    raise RuntimeError('LOCAL_POSTGRES_READY_TIMEOUT:数据库仍在启动或恢复，请查看数据库日志后重试')


def run(command, *, env=None, input=None):
    result = subprocess.run(command, check=False, env=env, input=input, capture_output=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=180)
    if result.returncode:
        detail = _sanitize(decode_output(result.stderr))
        # Command arguments and remote exception bodies can contain secrets: report only the tool.
        suffix = (':' + detail) if detail else ''
        raise RuntimeError('LOCAL_DEPENDENCY_COMMAND_FAILED:' + Path(command[0]).name + suffix)
    return result


def _log_tail(root, name):
    path = root / 'logs' / (name + '.log')
    try:
        text = decode_output(path.read_bytes())
    except OSError:
        return ''
    return _sanitize(text[-2000:])


def package(root, name, cache=None):
    manifest = PACKAGES[name]
    destination = root / 'runtime' / name
    marker = destination / 'installed.json'
    if marker.exists() and json.loads(marker.read_text()) == manifest:
        return destination
    archive = root / 'downloads' / (name + '.zip')
    archive.parent.mkdir(parents=True, exist_ok=True)
    cached = Path(cache) / ('elastic.zip' if name == 'elasticsearch' else 'postgres.zip') if cache else None
    if cached and cached.is_file():
        source = cached
    else:
        # A partial download is never executed or accepted as an installed dependency.
        pending = archive.with_suffix('.part')
        urllib.request.urlretrieve(manifest['url'], pending)
        os.replace(pending, archive)
        source = archive
    with source.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['sha256']:
            raise RuntimeError('DEPENDENCY_CHECKSUM_MISMATCH:' + name)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as bundle:
        for member in bundle.infolist():
            resolved = (destination / member.filename).resolve()
            if not resolved.is_relative_to(destination.resolve()):
                raise RuntimeError('UNSAFE_DEPENDENCY_ARCHIVE')
        bundle.extractall(destination)
    atomic(marker, manifest)
    return destination


def install(root, cache=None, autostart=True, search=True):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    phase(root, 'installing', progress='pandoc')
    from .exporting import ensure_pandoc
    ensure_pandoc(root / 'runtime' / 'pandoc')
    state_file = root / 'installation.json'
    if state_file.exists():
        if not vault.read(target(root)):
            raise RuntimeError('LOCAL_CREDENTIALS_MISSING_REPAIR_REQUIRED')
        return json.loads(state_file.read_text(encoding='utf-8'))
    state = {'version': 1, 'root': str(root), 'api_port': free_port(8010),
             'pg_port': free_port(55433), 'es_port': free_port(59201) if search else None,
             'search': bool(search)}
    credentials = vault.read(target(root)) or {'database': secrets.token_hex(24),
        'elastic': secrets.token_hex(24), 'api_key': secrets.token_hex(32)}
    vault.write(target(root), credentials)
    phase(root, 'installing', progress='postgres')
    pg = package(root, 'postgres', cache) / 'pgsql' / 'bin'
    es = package(root, 'elasticsearch', cache) / 'elasticsearch-8.19.3' if search else None
    for folder in ('database', 'objects', 'logs', 'backups'):
        (root / folder).mkdir(exist_ok=True)
    phase(root, 'installing', progress='database')
    if not (root / 'database' / 'cluster' / 'PG_VERSION').exists():
        # initdb requires a password file; it exists only during initialization and is removed.
        password_file = root / 'database' / '.init-password'
        password_file.write_text(credentials['database'], encoding='utf-8')
        try:
            run([str(pg / 'initdb.exe'), '-D', str(root / 'database' / 'cluster'), '-U', 'scriptorium',
                 '--pwfile=' + str(password_file), '--auth=scram-sha-256', '--encoding=UTF8', '--no-locale'])
        finally:
            password_file.unlink(missing_ok=True)
    (root / 'database' / 'cluster' / 'postgresql.auto.conf').write_text(
        f"listen_addresses = '127.0.0.1'\nport = {state['pg_port']}\n", encoding='utf-8')
    if es is not None:
        phase(root, 'installing', progress='elasticsearch')
        config = '\n'.join(['cluster.name: scriptorium-local', 'node.name: research', 'network.host: 127.0.0.1',
            f"http.port: {state['es_port']}", 'discovery.type: single-node', 'xpack.security.enabled: true',
            'xpack.security.autoconfiguration.enabled: false', 'xpack.security.http.ssl.enabled: false',
            'xpack.security.transport.ssl.enabled: false', 'xpack.ml.enabled: false'])
        (es / 'config' / 'elasticsearch.yml').write_text(config, encoding='utf-8')
        (es / 'config' / 'jvm.options.d' / 'scriptorium.options').write_text('-Xms512m\n-Xmx512m\n', encoding='ascii')
        keystore = str(es / 'bin' / 'elasticsearch-keystore.bat')
        run([keystore, 'add', '-f', '--stdin', 'bootstrap.password'], input=credentials['elastic'].encode())
    atomic(state_file, state)
    phase(root, 'installing', progress='done')
    if autostart:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            winreg.SetValueEx(key, 'ScriptoriumResearch', 0, winreg.REG_SZ,
                subprocess.list2cmdline(executable('local-runtime', 'start', '--root', str(root))))
    return state


def environment(root, state):
    credentials = vault.read(target(root))
    if not credentials:
        raise RuntimeError('LOCAL_CREDENTIALS_MISSING')
    return {**os.environ,
        'SCRIPTORIUM_DATABASE_URL': f"postgresql+psycopg://scriptorium:{credentials['database']}@127.0.0.1:{state['pg_port']}/scriptorium",
        'SCRIPTORIUM_OBJECT_ROOT': str(root / 'objects'), 'SCRIPTORIUM_RESEARCH_OWNER': 'local-user',
        'SCRIPTORIUM_RESEARCH_API_KEY': credentials['api_key'], 'SCRIPTORIUM_PORT': str(state['api_port']),
        'SCRIPTORIUM_ELASTICSEARCH_URL': (f"http://127.0.0.1:{state['es_port']}" if state.get('search', True) else ''),
        'SCRIPTORIUM_ELASTICSEARCH_USERNAME': 'elastic' if state.get('search', True) else '',
        'SCRIPTORIUM_ELASTICSEARCH_PASSWORD': credentials['elastic'] if state.get('search', True) else '',
        'PGPASSWORD': credentials['database'], 'SCRIPTORIUM_LOCAL_RUNTIME_ROOT': str(root), 'SCRIPTORIUM_PANDOC_CACHE': str(root / 'runtime' / 'pandoc')}


def supervise(root):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    mutex = kernel.CreateMutexW(None, False, 'Local\\' + target(root).replace('/', '_'))
    if not mutex:
        raise ctypes.WinError()
    if ctypes.windll.kernel32.GetLastError() == 183:
        kernel.CloseHandle(mutex)
        return
    state = json.loads((root / 'installation.json').read_text(encoding='utf-8'))
    env = environment(root, state)
    pg = root / 'runtime' / 'postgres' / 'pgsql' / 'bin'
    es = root / 'runtime' / 'elasticsearch' / 'elasticsearch-8.19.3'
    children, handles = {}, []
    stop_file = root / 'stop.request'
    stop_file.unlink(missing_ok=True)
    def launch(name, command):
        log = (root / 'logs' / (name + '.log')).open('ab')
        handles.append(log)
        child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        children[name] = child
        return child
    def wait_ready(port, seconds=120):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if stop_file.exists():
                raise RuntimeError('LOCAL_START_CANCELLED')
            with socket.socket() as connection:
                if connection.connect_ex(('127.0.0.1', port)) == 0:
                    return
            time.sleep(.5)
        raise RuntimeError('LOCAL_DEPENDENCY_START_TIMEOUT')
    search = state.get('search', True)
    try:
        phase(root, 'starting', progress='postgres', pid=os.getpid())
        launch('postgres', [str(pg / 'postgres.exe'), '-D', str(root / 'database' / 'cluster')])
        if search:
            launch('elasticsearch', [str(es / 'bin' / 'elasticsearch.bat')])
        phase(root, 'starting', progress='postgres_wait', pid=os.getpid())
        wait_postgres(root, pg, state['pg_port'], children['postgres'], stop_file)
        exists = run([str(pg / 'psql.exe'), '-h', '127.0.0.1', '-p', str(state['pg_port']), '-U', 'scriptorium',
                      '-d', 'postgres', '-tAc', "select 1 from pg_database where datname='scriptorium'"], env=env)
        if not exists.stdout.strip():
            run([str(pg / 'createdb.exe'), '-h', '127.0.0.1', '-p', str(state['pg_port']), '-U', 'scriptorium', 'scriptorium'], env=env)
        if search:
            phase(root, 'starting', progress='search_wait', pid=os.getpid())
            wait_ready(state['es_port'], 300)
        import httpx
        if search:
            with httpx.Client(trust_env=False, timeout=5) as client:
                until = time.monotonic() + 120
                while True:
                    try:
                        response = client.get(f"http://127.0.0.1:{state['es_port']}/_cluster/health",
                            auth=('elastic', vault.read(target(root))['elastic']))
                        response.raise_for_status()
                        if response.json().get('status') in {'yellow', 'green'}:
                            break
                    except (httpx.HTTPError, ValueError):
                        pass
                    if time.monotonic() >= until or stop_file.exists():
                        raise RuntimeError('LOCAL_SEARCH_HEALTH_FAILED')
                    time.sleep(1)
        phase(root, 'starting', progress='schema', pid=os.getpid())
        run(executable('research-command', 'init-db'), env=env)
        phase(root, 'starting', progress='api', pid=os.getpid())
        commands = {'api': executable('research-command', 'serve', '--port', str(state['api_port'])),
                    'worker': executable('research-command', 'worker')}
        for name, command in commands.items():
            launch(name, command)
        wait_ready(state['api_port'], 60)
        with httpx.Client(trust_env=False, timeout=10) as client:
            response = client.get(f"http://127.0.0.1:{state['api_port']}/api/v2/projects",
                headers={'Authorization': 'Bearer ' + vault.read(target(root))['api_key']})
            response.raise_for_status()
        failures = {name: 0 for name in commands}
        phase(root, 'running', progress='done', url=f"http://127.0.0.1:{state['api_port']}",
              search=search, api_port=state['api_port'], pid=os.getpid())
        while not stop_file.exists():
            for name, child in list(children.items()):
                if child.poll() is None:
                    continue
                if name not in commands or failures[name] >= 3:
                    raise RuntimeError('LOCAL_COMPONENT_STOPPED:' + name)
                failures[name] += 1
                time.sleep(2 ** failures[name])
                launch(name, commands[name])
            time.sleep(1)
    except Exception as exc:
        phase(root, 'failed', error=type(exc).__name__ + ':' + str(exc)[:500])
        raise
    finally:
        pg_child = children.get('postgres')
        if pg_child and pg_child.poll() is None:
            try:
                run([str(pg / 'pg_ctl.exe'), '-D', str(root / 'database' / 'cluster'), '-m', 'fast', '-w', 'stop'], env=env)
            except RuntimeError:
                pass
        for child in children.values():
            if child.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                        capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                else:
                    child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
        for handle in handles:
            handle.close()
        ctypes.windll.kernel32.CloseHandle(mutex)
        current = json.loads((root / 'runtime.json').read_text(encoding='utf-8')) if (root / 'runtime.json').exists() else {}
        if current.get('state') != 'failed':
            atomic(root / 'runtime.json', {'state': 'stopped'})


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'start', 'ensure', 'stop', 'status', 'connection', 'uninstall', 'prepare-upgrade'])
    parser.add_argument('--root', type=Path, default=default_root())
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--no-autostart', action='store_true')
    parser.add_argument('--without-search', action='store_true', help='skip Elasticsearch (smaller, faster first run)')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.action == 'install':
        print(json.dumps(install(root, args.cache, not args.no_autostart, search=not args.without_search)))
    elif args.action == 'start':
        supervise(root)
    elif args.action == 'ensure':
        install(root, args.cache, not args.no_autostart, search=not args.without_search)
        phase(root, 'starting', progress='launching')
        subprocess.Popen(executable('local-runtime', 'start', '--root', str(root)),
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
        print(json.dumps({'state': 'starting'}))
    elif args.action == 'prepare-upgrade':
        if (root / 'installation.json').exists():
            import shutil
            # A stopped cluster snapshot also works when the installed application predates
            # the new table definitions. Never run new metadata against an old live schema.
            main(['stop', '--root', str(root)])
            destination = root / 'backups' / ('upgrade-' + str(time.time_ns()))
            destination.mkdir(parents=True)
            for name in ('database', 'objects'):
                shutil.copytree(root / name, destination / name)
            shutil.copy2(root / 'installation.json', destination / 'installation.json')
            if getattr(sys, 'frozen', False):
                shutil.copy2(sys.executable, destination / 'scriptorium-backend.exe')
            atomic(destination / 'manifest.json', {'format': 'scriptorium-stopped-native.v1',
                'created_at': time.time(), 'state': 'stopped', 'dependencies': PACKAGES,
                'restore': 'Restore database and objects together with the matching saved program; never open newer tables with an older program.'})
        print(json.dumps({'state': 'upgrade_prepared', 'data_preserved': True}))
    elif args.action in {'stop', 'uninstall'}:
        root.mkdir(parents=True, exist_ok=True)
        (root / 'stop.request').touch()
        for _ in range(60):
            status = root / 'runtime.json'
            if not status.exists() or json.loads(status.read_text(encoding='utf-8')).get('state') not in {'running', 'starting'}:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('LOCAL_STOP_TIMEOUT_DATA_PRESERVED')
        if args.action == 'uninstall':
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, 'ScriptoriumResearch')
            except FileNotFoundError:
                pass
        print(json.dumps({'state': 'stopping', 'data_preserved': True}))
    elif args.action == 'connection':
        state = json.loads((root / 'installation.json').read_text(encoding='utf-8'))
        secret = vault.read(target(root))
        print(json.dumps({'url': f"http://127.0.0.1:{state['api_port']}", 'api_key': secret['api_key'],
                          'search': state.get('search', True)}))
    else:
        state = root / 'runtime.json'
        print(state.read_text(encoding='utf-8') if state.exists() else '{"state":"not_installed"}')
