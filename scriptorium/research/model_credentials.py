"""Compatibility facade over the provider registry.

Older call sites import configured_key/save_key; credentials now live in the provider registry,
which supports several OpenAI-compatible providers and both the OS credential store and a
private development file.
"""
from __future__ import annotations



def configured_key(provider_id: str | None = None):
    from .providers import key_for
    return key_for(provider_id)


def save_key(value, provider_id: str | None = None):
    from .providers import active_id, save_key as store
    if not provider_id:
        provider_id = active_id()
    store(provider_id, value)
    return {'configured': True, 'provider': provider_id, 'secret_returned': False}


def delete_key(provider_id: str | None = None):
    from .providers import active_id, delete_key as remove
    return remove(provider_id or active_id())
