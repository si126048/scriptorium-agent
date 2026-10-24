from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def redacted_service_url(value):
    """Identify an acceptance service without recording credentials or URL query secrets."""
    if not value:
        return 'NOT CONFIGURED'
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc.rsplit('@', 1)[-1], parsed.path, '', ''))


@dataclass(frozen=True)
class ResearchSettings:
    database_url: str
    object_root: Path
    elasticsearch_url: str
    api_key: str
    principal: str
    allowed_origins: tuple[str, ...]
    max_upload_bytes: int = 30 * 1024 * 1024
    lease_seconds: int = 300
    max_attempts: int = 3
    ocr_engine: str = 'auto'
    object_backend: str = 'filesystem'
    s3_bucket: str = ''
    s3_endpoint: str | None = None
    s3_region: str = 'us-east-1'
    elasticsearch_username: str = ''
    elasticsearch_password: str = field(default='', repr=False)

    def __post_init__(self):
        if self.lease_seconds <= 0 or self.max_attempts <= 0:
            raise ValueError('Worker lease_seconds and max_attempts must be positive')

    @classmethod
    def from_env(cls):
        return cls(
            elasticsearch_username=os.getenv('SCRIPTORIUM_ELASTICSEARCH_USERNAME', ''),
            elasticsearch_password=os.getenv('SCRIPTORIUM_ELASTICSEARCH_PASSWORD', ''),
            lease_seconds=int(os.getenv('SCRIPTORIUM_LEASE_SECONDS', '300')),
            max_attempts=int(os.getenv('SCRIPTORIUM_MAX_ATTEMPTS', '3')),
            ocr_engine=os.getenv('SCRIPTORIUM_OCR_ENGINE', 'auto'),
            object_backend=os.getenv('SCRIPTORIUM_OBJECT_BACKEND', 'filesystem'),
            s3_bucket=os.getenv('SCRIPTORIUM_S3_BUCKET', ''),
            s3_endpoint=os.getenv('SCRIPTORIUM_S3_ENDPOINT') or None,
            s3_region=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
            database_url=os.getenv('SCRIPTORIUM_DATABASE_URL', ''),
            object_root=Path(os.getenv('SCRIPTORIUM_OBJECT_ROOT', './data/research-objects')),
            elasticsearch_url=os.getenv('SCRIPTORIUM_ELASTICSEARCH_URL', 'http://127.0.0.1:9200'),
            api_key=os.getenv('SCRIPTORIUM_RESEARCH_API_KEY', ''),
            principal=os.getenv('SCRIPTORIUM_RESEARCH_OWNER', 'local-user'),
            allowed_origins=tuple(os.getenv('SCRIPTORIUM_RESEARCH_ORIGINS',
                'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,'
                'http://127.0.0.1:8000,http://localhost:8010,http://127.0.0.1:8010,'
                'tauri://localhost,https://tauri.localhost').split(',')),
        )
