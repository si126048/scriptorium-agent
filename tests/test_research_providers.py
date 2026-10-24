"""Model access is provider-agnostic; secrets stay out of the browser and out of records."""
from __future__ import annotations

import json

import pytest

from test_research_integration import research, client  # noqa: F401
from scriptorium.research import providers
from scriptorium.research.service import ResearchError

SECRET_ENVS = ('DASHSCOPE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'MOONSHOT_API_KEY',
               'ZHIPU_API_KEY', 'SCRIPTORIUM_MODEL_API_KEY', 'SCRIPTORIUM_PROVIDER',
               'SCRIPTORIUM_MODEL', 'SCRIPTORIUM_LOCAL_RUNTIME_ROOT')


@pytest.fixture(autouse=True)
def isolated_provider_home(tmp_path, monkeypatch):
    monkeypatch.setenv('SCRIPTORIUM_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('SCRIPTORIUM_KEY_STORAGE', 'file')
    for name in SECRET_ENVS:
        monkeypatch.delenv(name, raising=False)
    from scriptorium.config import reset_settings
    reset_settings()
    yield
    reset_settings()


def test_catalog_defaults_and_no_secret_in_status():
    public = providers.public()
    ids = {item['id'] for item in public['providers']}
    assert {'qwen', 'deepseek', 'openai', 'moonshot', 'zhipu', 'ollama', 'custom'} <= ids
    assert public['active'] == 'qwen' and public['editable'] is True
    assert public['storage'] == 'file' and public['secret_returned'] is False
    assert all(item['configured'] is False for item in public['providers'])
    ollama = next(item for item in public['providers'] if item['id'] == 'ollama')
    assert ollama['ready'] is True and ollama['configured'] is False


def test_key_is_saved_privately_and_never_echoed():
    result = providers.save_key('deepseek', 'sk-test-deepseek')
    assert 'sk-test' not in json.dumps(result)
    stored = json.loads(providers.keys_path().read_text(encoding='utf-8'))
    assert stored['deepseek']['key'] == 'sk-test-deepseek'
    assert providers.public()['providers'][1]['configured'] is True or any(
        item['configured'] for item in providers.public()['providers'] if item['id'] == 'deepseek')
    assert providers.key_source('deepseek') == 'private-file'


def test_switch_provider_and_override_endpoint(monkeypatch):
    providers.save_key('deepseek', 'sk-a')
    public = providers.update(provider='deepseek', base_url='https://example.test/v1',
                              model='deepseek-reasoner')
    assert public['active'] == 'deepseek'
    config = providers.provider_config()
    assert (config['base_url'], config['model']) == ('https://example.test/v1', 'deepseek-reasoner')

    captured = {}

    class Capture:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model = kwargs.get('model')
            self.temperature = 0
            self.client = None

    monkeypatch.setattr('scriptorium.llm.QwenProvider', Capture)
    engine = providers.provider('live')
    assert captured['base_url'] == 'https://example.test/v1'
    assert captured['api_key'] == 'sk-a' and captured['model'] == 'deepseek-reasoner'
    assert engine.model == 'deepseek-reasoner'


def test_environment_fallback_keeps_legacy_qwen_working(monkeypatch):
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'legacy-dashscope-key')
    assert providers.key_for('qwen') == 'legacy-dashscope-key'
    assert providers.key_source('qwen') == 'environment'
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'env-deepseek')
    providers.update(provider='deepseek')
    assert providers.key_for('deepseek') == 'env-deepseek'
    # A saved key wins over the environment.
    providers.save_key('deepseek', 'saved-deepseek')
    assert providers.key_for('deepseek') == 'saved-deepseek'


def test_missing_key_fails_loudly_and_delete_clears():
    with pytest.raises(ResearchError, match='MODEL_NOT_CONFIGURED'):
        providers.provider('live')
    providers.save_key('openai', 'sk-openai')
    providers.update(provider='openai')
    providers.delete_key('openai')
    with pytest.raises(ResearchError, match='MODEL_NOT_CONFIGURED'):
        providers.provider('live')


def test_custom_endpoint_requires_a_base_url():
    providers.save_key('custom', 'sk-custom')
    providers.update(provider='custom', base_url='https://llm.example.com/v1', model='h1')
    captured = {}

    class Capture:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.model = kwargs.get('model')
            self.temperature = 0
            self.client = None

    from scriptorium import llm
    original = llm.QwenProvider
    llm.QwenProvider = Capture
    try:
        providers.provider('live')
        assert captured['base_url'] == 'https://llm.example.com/v1'
        providers.update(provider='custom', base_url='')
        with pytest.raises(ResearchError, match='PROVIDER_BASE_URL_REQUIRED'):
            providers.provider('live')
    finally:
        llm.QwenProvider = original


def test_invalid_keys_are_rejected():
    with pytest.raises(ResearchError, match='PROVIDER_KEY_REQUIRED'):
        providers.save_key('openai', '   ')
    with pytest.raises(ResearchError, match='INVALID_PROVIDER_KEY'):
        providers.save_key('openai', 'has a space')
    with pytest.raises(ResearchError, match='UNKNOWN_PROVIDER'):
        providers.save_key('not-a-provider', 'sk')


def test_model_endpoints_save_switch_and_hide_secret(research, client):  # noqa: F811
    status = client.get('/api/v2/system/model').json()
    assert status['editable'] is True and status['providers']
    saved = client.put('/api/v2/system/model', json={
        'provider': 'moonshot', 'key': 'sk-moonshot-only', 'model': 'moonshot-v1-8k'}).json()
    assert saved['active'] == 'moonshot'
    assert 'sk-moonshot-only' not in json.dumps(saved)
    moonshot = next(item for item in saved['providers'] if item['id'] == 'moonshot')
    assert moonshot['configured'] is True and moonshot['model'] == 'moonshot-v1-8k'
    cleared = client.delete('/api/v2/system/model?provider=moonshot').json()
    assert next(item for item in cleared['providers'] if item['id'] == 'moonshot')['configured'] is False
    # Probing without a key reports the code instead of raising or echoing anything secret.
    probe = client.post('/api/v2/system/model/test?provider=moonshot').json()
    assert probe['ok'] is False and probe['error'] == 'MODEL_NOT_CONFIGURED'


def test_legacy_runtime_follows_the_active_provider(monkeypatch):
    """CLI/ACP/MCP construct QwenProvider() with no arguments; it must honour the registry."""
    from scriptorium.llm import QwenProvider
    providers.save_key('deepseek', 'sk-legacy-deepseek')
    providers.update(provider='deepseek', base_url='https://example.test/v1', model='deepseek-reasoner')
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import openai
    monkeypatch.setattr(openai, 'OpenAI', FakeOpenAI)
    provider = QwenProvider()
    assert provider.api_key == 'sk-legacy-deepseek'
    assert provider.model == 'deepseek-reasoner'
    assert captured['base_url'] == 'https://example.test/v1'


def test_legacy_qwen_environment_keeps_dashscope_defaults(monkeypatch):
    from scriptorium.llm import QwenProvider
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'legacy-dashscope')
    monkeypatch.setenv('LACAN_MODEL', 'qwen-max')
    from scriptorium.config import reset_settings
    reset_settings()
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import openai
    monkeypatch.setattr(openai, 'OpenAI', FakeOpenAI)
    provider = QwenProvider()
    assert provider.api_key == 'legacy-dashscope' and provider.model == 'qwen-max'
    assert captured['base_url'].startswith('https://dashscope.aliyuncs.com')
