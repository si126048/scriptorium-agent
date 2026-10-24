"""Participant manifest loading and validation."""

from __future__ import annotations

import json
from pathlib import Path


def load_participant_manifest(path: str | Path) -> dict[str, str]:
    source = Path(path)
    data = json.loads(source.read_text(encoding='utf-8'))
    entries = data.get('participants', data) if isinstance(data, dict) else data
    if not isinstance(entries, (dict, list)):
        raise ValueError('INVALID_PARTICIPANT_MANIFEST')
    result: dict[str, str] = {}
    if isinstance(entries, dict):
        entries = [{'id': key, 'file': value} for key, value in entries.items()]
    for item in entries:
        if not isinstance(item, dict) or not item.get('id') or not item.get('file'):
            raise ValueError('INVALID_PARTICIPANT_ENTRY')
        participant_id = str(item['id'])
        if participant_id in result:
            raise ValueError(f'DUPLICATE_PARTICIPANT:{participant_id}')
        result[participant_id] = str(item['file'])
    return result
