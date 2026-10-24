"""Settings are read from the process environment only; no hidden defaults for operations."""
from __future__ import annotations

from dataclasses import replace
import pytest

from hermeneut.research.config import ResearchSettings, redacted_service_url


def test_defaults_keep_worker_leases_and_ocr_engine_explicit(tmp_path, monkeypatch):
    for name in ('HERMENEUT_LEASE_SECONDS', 'HERMENEUT_MAX_ATTEMPTS', 'HERMENEUT_OCR_ENGINE',
                 'HERMENEUT_OBJECT_BACKEND', 'HERMENEUT_S3_BUCKET', 'HERMENEUT_RESEARCH_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    settings = ResearchSettings.from_env()
    assert settings.lease_seconds == 300 and settings.max_attempts == 3
    assert settings.ocr_engine == 'auto'
    assert settings.object_backend == 'filesystem' and settings.s3_bucket == ''
    assert settings.api_key == ''


def test_operational_settings_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMENEUT_LEASE_SECONDS', '20')
    monkeypatch.setenv('HERMENEUT_MAX_ATTEMPTS', '2')
    monkeypatch.setenv('HERMENEUT_OCR_ENGINE', 'rapidocr')
    monkeypatch.setenv('HERMENEUT_OBJECT_BACKEND', 's3')
    monkeypatch.setenv('HERMENEUT_S3_BUCKET', 'bucket-x')
    monkeypatch.setenv('HERMENEUT_DATABASE_URL', 'postgresql+psycopg://user@127.0.0.1/db')
    monkeypatch.setenv('HERMENEUT_OBJECT_ROOT', str(tmp_path / 'objects'))
    settings = ResearchSettings.from_env()
    assert (settings.lease_seconds, settings.max_attempts) == (20, 2)
    assert settings.ocr_engine == 'rapidocr'
    assert (settings.object_backend, settings.s3_bucket) == ('s3', 'bucket-x')
    assert settings.object_root == tmp_path / 'objects'
    # A shorter lease is a deployment choice, not a schema change.
    assert replace(settings, lease_seconds=5).lease_seconds == 5


@pytest.mark.parametrize('name', ['HERMENEUT_LEASE_SECONDS', 'HERMENEUT_MAX_ATTEMPTS'])
@pytest.mark.parametrize('value', ['0', '-1'])
def test_nonpositive_worker_settings_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match='must be positive'):
        ResearchSettings.from_env()


def test_acceptance_endpoint_does_not_record_credentials_or_query_tokens():
    assert redacted_service_url('postgresql+psycopg://user:p%40ss@localhost:5432/test?token=secret') == (
        'postgresql+psycopg://localhost:5432/test')
    assert redacted_service_url('https://user:password@[::1]:9200/?key=secret#fragment') == 'https://[::1]:9200/'
    assert redacted_service_url('') == 'NOT CONFIGURED'
