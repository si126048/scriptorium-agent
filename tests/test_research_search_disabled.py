import pytest

from pathlib import Path

from scriptorium.research import search
from scriptorium.research.config import ResearchSettings
from scriptorium.research.service import ResearchError


class _Service:
    def __init__(self, url: str):
        self.settings = ResearchSettings(
            database_url='', object_root=Path('.'), elasticsearch_url=url,
            api_key='', principal='local-user', allowed_origins=())


def test_empty_url_disables_search_without_touching_elasticsearch():
    service = _Service('')
    assert search.enabled(service) is False
    # The worker must not burn outbox retries when search is intentionally disabled.
    assert search.sync_one(service) is False
    with pytest.raises(ResearchError) as info:
        search.client(service)
    assert info.value.code == 'SEARCH_DISABLED'
    assert info.value.status == 503


def test_configured_url_enables_search():
    assert search.enabled(_Service('http://127.0.0.1:9200')) is True
    assert search.enabled(_Service('   ')) is False
