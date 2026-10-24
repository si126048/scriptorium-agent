from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    dashscope_api_key: str = ''
    api_key: str = ''
    db_path: str = './data/lacan.db'
    storage_path: str = '.api/uploads'
    model: str = 'qwen-plus'
    temperature: float = 0.3
    log_level: str = 'INFO'
    mock: bool = False
    enable_wal: bool = True
    max_upload_bytes: int = 10 * 1024 * 1024
    llm_timeout: float = 60.0
    llm_retries: int = 2
    port: int = 8000
    interview_config_dir: str = 'data/interview-configs'
    topostyle_ollama_url: str = 'http://127.0.0.1:11434'
    topostyle_model: str = 'qwen2.5:3b'
    topostyle_embed_model: str = 'nomic-embed-text'
    topostyle_temperature: float = 0.3

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            dashscope_api_key=os.environ.get('DASHSCOPE_API_KEY', ''),
            api_key=os.environ.get('LACAN_API_KEY', ''),
            db_path=os.environ.get('LACAN_DB_PATH', './data/lacan.db'),
            storage_path=os.environ.get('LACAN_STORAGE_PATH', '.api/uploads'),
            model=os.environ.get('LACAN_MODEL', 'qwen-plus'),
            temperature=float(os.environ.get('LACAN_TEMPERATURE', '0.3')),
            log_level=os.environ.get('LACAN_LOG_LEVEL', 'INFO'),
            mock=os.environ.get('LACAN_MOCK', '') != '',
            enable_wal=os.environ.get('LACAN_ENABLE_WAL', '1') == '1',
            max_upload_bytes=int(os.environ.get('LACAN_MAX_UPLOAD_BYTES', str(10 * 1024 * 1024))),
            llm_timeout=float(os.environ.get('LACAN_LLM_TIMEOUT', '60')),
            llm_retries=int(os.environ.get('LACAN_LLM_RETRIES', '2')),
            port=int(os.environ.get('SCRIPTORIUM_PORT', '8000')),
            interview_config_dir=os.environ.get('LACAN_INTERVIEW_CONFIG_DIR', 'data/interview-configs'),
            topostyle_ollama_url=os.environ.get('TOPOSTYLE_OLLAMA_URL', 'http://127.0.0.1:11434'),
            topostyle_model=os.environ.get('TOPOSTYLE_QWEN_MODEL', 'qwen2.5:3b'),
            topostyle_embed_model=os.environ.get('TOPOSTYLE_EMBED_MODEL', 'nomic-embed-text'),
            topostyle_temperature=float(os.environ.get('TOPOSTYLE_TEMPERATURE', '0.3')),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None


def frozen_source() -> str | None:
    """Path of the legacy source database that must never be opened for writing.

    Acceptance runs and tests set this to the frozen migration snapshot. Writing to it would
    silently change the input of every later migration, so the legacy store refuses to open it.
    """
    raw = os.environ.get('SCRIPTORIUM_FROZEN_SOURCE', '').strip()
    if not raw:
        return None
    return str(Path(raw).expanduser().resolve())
