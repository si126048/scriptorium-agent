"""Local model credential access, separate from project records and browser storage."""
import os
from pathlib import Path
from .service import ResearchError


def configured_key():
    root = os.getenv('SCRIPTORIUM_LOCAL_RUNTIME_ROOT')
    if root:
        from .local_runtime import target
        from .windows_credentials import read
        value = read(target(Path(root))) or {}
        return value.get('qwen') or os.getenv('DASHSCOPE_API_KEY', '')
    return os.getenv('DASHSCOPE_API_KEY', '')


def save_key(value):
    root = os.getenv('SCRIPTORIUM_LOCAL_RUNTIME_ROOT')
    if not root or os.name != 'nt':
        raise ResearchError('MODEL_KEY_MANAGED_BY_SERVER_ENVIRONMENT', 409)
    from .local_runtime import target
    from .windows_credentials import read, write
    name = target(Path(root))
    credentials = read(name)
    if not credentials:
        raise ResearchError('LOCAL_CREDENTIALS_MISSING', 409)
    write(name, {**credentials, 'qwen': value})
