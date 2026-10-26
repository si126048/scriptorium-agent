"""Provider-agnostic model access: OpenAI-compatible endpoints, keys kept out of the browser.

The workspace never stores model secrets in page storage. A key is written either to the Windows
Credential Manager (default on Windows) or to a private file under the Scriptorium home for
development and non-Windows hosts; environment variables are always accepted as a fallback so
server deployments can keep using their own secret injection.

Provider ids follow the same idea as Misaka-Agent's provider registry (one active provider, its
base URL and model, keys per provider), without reusing its code or credential format.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .service import ResearchError

CATALOG: tuple[dict, ...] = (
    {'id': 'qwen', 'label': '通义千问（DashScope）',
     'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
     'default_model': 'qwen-plus', 'env': ('DASHSCOPE_API_KEY',), 'key_optional': False},
    {'id': 'deepseek', 'label': 'DeepSeek',
     'base_url': 'https://api.deepseek.com/v1',
     'default_model': 'deepseek-chat', 'env': ('DEEPSEEK_API_KEY',), 'key_optional': False},
    {'id': 'openai', 'label': 'OpenAI',
     'base_url': 'https://api.openai.com/v1',
     'default_model': 'gpt-4o-mini', 'env': ('OPENAI_API_KEY',), 'key_optional': False},
    {'id': 'moonshot', 'label': 'Moonshot（Kimi）',
     'base_url': 'https://api.moonshot.cn/v1',
     'default_model': 'moonshot-v1-8k', 'env': ('MOONSHOT_API_KEY',), 'key_optional': False},
    {'id': 'zhipu', 'label': '智谱 GLM',
     'base_url': 'https://open.bigmodel.cn/api/paas/v4',
     'default_model': 'glm-4-flash', 'env': ('ZHIPU_API_KEY',), 'key_optional': False},
    {'id': 'ollama', 'label': 'Ollama（本机）',
     'base_url': 'http://127.0.0.1:11434/v1',
     'default_model': 'qwen2.5:7b', 'env': (), 'key_optional': True},
    {'id': 'custom', 'label': '自定义 OpenAI 兼容端点',
     'base_url': '', 'default_model': '', 'env': ('SCRIPTORIUM_MODEL_API_KEY',), 'key_optional': False},
)
BY_ID = {item['id']: item for item in CATALOG}


def home() -> Path:
    root = os.getenv('SCRIPTORIUM_LOCAL_RUNTIME_ROOT')
    if root:
        return Path(root) / 'state'
    if os.getenv('SCRIPTORIUM_HOME'):
        return Path(os.environ['SCRIPTORIUM_HOME'])
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA') or Path.home()) / 'Scriptorium'
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'scriptorium'


def config_path() -> Path:
    return home() / 'providers.json'


def keys_path() -> Path:
    return home() / 'provider-keys.json'


def storage_kind() -> str:
    forced = os.getenv('SCRIPTORIUM_KEY_STORAGE', '').strip().lower()
    if forced in {'vault', 'file'}:
        return forced
    return 'vault' if os.name == 'nt' else 'file'


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, staging = tempfile.mkstemp(prefix='.providers-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != 'nt':
            os.chmod(staging, 0o600)
        os.replace(staging, path)
    finally:
        Path(staging).unlink(missing_ok=True)


def _config() -> dict:
    return _read_json(config_path())


def _keys() -> dict:
    return _read_json(keys_path())


def _save_keys(value: dict):
    _write_json(keys_path(), value)


def _vault_read(provider_id: str) -> str | None:
    from . import windows_credentials
    try:
        stored = windows_credentials.read(f'scriptorium-model-{provider_id}') or {}
    except (OSError, RuntimeError):
        return None
    return stored.get('key') or None


def _vault_write(provider_id: str, key: str) -> bool:
    from . import windows_credentials
    try:
        windows_credentials.write(f'scriptorium-model-{provider_id}', {'key': key})
        return True
    except (OSError, RuntimeError):
        return False


def _vault_delete(provider_id: str) -> bool:
    from . import windows_credentials
    try:
        windows_credentials.write(f'scriptorium-model-{provider_id}', {'key': ''})
        return True
    except (OSError, RuntimeError):
        return False


def key_for(provider_id: str | None = None) -> str | None:
    """Resolution order: OS vault (or private file), provider env var, generic override."""
    provider_id = provider_id or active_id()
    entry = BY_ID.get(provider_id)
    if entry is None:
        raise ResearchError('UNKNOWN_PROVIDER', 422)
    if storage_kind() == 'vault':
        value = _vault_read(provider_id)
        if value:
            return value
    else:
        value = (_keys().get(provider_id) or {}).get('key')
        if value:
            return value
    for name in entry['env']:
        value = os.getenv(name, '').strip()
        if value:
            return value
    return os.getenv('SCRIPTORIUM_MODEL_API_KEY', '').strip() or None


def key_source(provider_id: str | None = None) -> str:
    provider_id = provider_id or active_id()
    if storage_kind() == 'vault' and _vault_read(provider_id):
        return 'credential-store'
    if storage_kind() == 'file' and (_keys().get(provider_id) or {}).get('key'):
        return 'private-file'
    entry = BY_ID.get(provider_id) or {}
    if any(os.getenv(name, '').strip() for name in entry.get('env', ())):
        return 'environment'
    if os.getenv('SCRIPTORIUM_MODEL_API_KEY', '').strip():
        return 'environment'
    return 'unset'


def active_id() -> str:
    stored = _config().get('active')
    env = os.getenv('SCRIPTORIUM_PROVIDER', '').strip()
    for candidate in (stored, env):
        if candidate in BY_ID:
            return candidate
    return 'qwen'


def stored(provider_id: str) -> dict:
    """Per-provider overrides written by the workspace (base URL and model only)."""
    return dict((_config().get('providers') or {}).get(provider_id) or {})


def provider_config(provider_id: str | None = None) -> dict:
    provider_id = provider_id or active_id()
    entry = BY_ID.get(provider_id)
    if entry is None:
        raise ResearchError('UNKNOWN_PROVIDER', 422)
    stored = (_config().get('providers') or {}).get(provider_id) or {}
    has_key = bool(key_for(provider_id))
    return {'id': provider_id, 'label': entry['label'],
            'base_url': stored.get('base_url') or entry['base_url'],
            'model': stored.get('model') or os.getenv('SCRIPTORIUM_MODEL', '').strip() or entry['default_model'],
            'key_optional': entry['key_optional'], 'configured': has_key,
            'ready': has_key or entry['key_optional'], 'source': key_source(provider_id)}


def public(provider_id: str | None = None) -> dict:
    active = provider_id or active_id()
    items = []
    from .native_search import capabilities
    for entry in CATALOG:
        current = provider_config(entry['id'])
        items.append({'id': entry['id'], 'label': entry['label'], 'base_url': current['base_url'],
                      'model': current['model'], 'key_optional': entry['key_optional'],
                      'configured': current['configured'], 'ready': current['ready'],
                      'source': current['source'], 'web_search': capabilities(current)['web_search']})
    return {'active': active, 'editable': True, 'storage': storage_kind(),
            'secret_returned': False, 'providers': items}


def update(*, provider: str | None = None, base_url: str | None = None,
           model: str | None = None, activate: bool = True) -> dict:
    provider_id = provider or active_id()
    if provider_id not in BY_ID:
        raise ResearchError('UNKNOWN_PROVIDER', 422)
    config = _config()
    providers = dict(config.get('providers') or {})
    entry = dict(providers.get(provider_id) or {})
    if base_url is not None:
        if base_url and not base_url.startswith(('http://', 'https://')):
            raise ResearchError('INVALID_PROVIDER_BASE_URL', 422)
        entry['base_url'] = base_url.rstrip('/')
    if model is not None:
        entry['model'] = model.strip()[:200]
    providers[provider_id] = entry
    config['providers'] = providers
    if activate:
        config['active'] = provider_id
    _write_json(config_path(), config)
    return public(provider_id)


def save_key(provider_id: str, key: str) -> dict:
    key = (key or '').strip()
    if provider_id not in BY_ID:
        raise ResearchError('UNKNOWN_PROVIDER', 422)
    if not key:
        raise ResearchError('PROVIDER_KEY_REQUIRED', 422)
    if len(key) > 512 or any(ch.isspace() for ch in key):
        raise ResearchError('INVALID_PROVIDER_KEY', 422)
    if storage_kind() == 'vault' and _vault_write(provider_id, key):
        return {'stored': 'credential-store', **public(provider_id)}
    values = _keys()
    values[provider_id] = {'key': key}
    _save_keys(values)
    return {'stored': 'private-file', **public(provider_id)}


def delete_key(provider_id: str) -> dict:
    if provider_id not in BY_ID:
        raise ResearchError('UNKNOWN_PROVIDER', 422)
    if storage_kind() == 'vault':
        _vault_delete(provider_id)
    values = _keys()
    if provider_id in values:
        values.pop(provider_id)
        _save_keys(values)
    return public(provider_id)


def provider(mode: str = 'live', service=None, job=None):
    """Build the active provider; demo stays deterministic, missing keys fail loudly."""
    if mode == 'demo':
        from scriptorium.llm import FakeProvider
        return FakeProvider()
    config = provider_config()
    key = key_for(config['id'])
    if not key and not config['key_optional']:
        raise ResearchError('MODEL_NOT_CONFIGURED')
    if not config['base_url']:
        raise ResearchError('PROVIDER_BASE_URL_REQUIRED', 422)
    from scriptorium.llm import QwenProvider
    # QwenProvider is a generic OpenAI-compatible client; the name is historical.
    return QwenProvider(api_key=key or 'local-model', model=config['model'] or None,
                        base_url=config['base_url'])


def probe(provider_id: str | None = None) -> dict:
    """Cheap connectivity check: list models without sending material. Never echoes the key."""
    config = provider_config(provider_id)
    if not config['base_url']:
        return {'ok': False, 'provider': config['id'], 'error': 'PROVIDER_BASE_URL_REQUIRED'}
    key = key_for(config['id'])
    if not key and not config['key_optional']:
        return {'ok': False, 'provider': config['id'], 'error': 'MODEL_NOT_CONFIGURED'}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key or 'local-model', base_url=config['base_url'], timeout=8, max_retries=0)
        client.models.list()
        return {'ok': True, 'provider': config['id'], 'model': config['model']}
    except Exception as exc:
        name = type(exc).__name__
        status = getattr(exc, 'status_code', None)
        return {'ok': False, 'provider': config['id'], 'model': config['model'],
                'error': f'PROVIDER_PROBE_FAILED:{name}' + (f':{status}' if status else '')}
