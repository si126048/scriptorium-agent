# Derived from MISAKA-Agent (https://github.com/Luciole-Studio/Misaka-Agent)
# Copyright 2026 Luciole Studio. Licensed under Apache License 2.0.
# See NOTICE and LICENSE-MISAKA in the project root.

"""Page-based navigation helpers for indexed documents."""
from __future__ import annotations

from .store import DocumentStore


def get_page_range(store: DocumentStore, doc_id: str) -> tuple[int, int] | None:
    doc = store.get_document(doc_id)
    if not doc:
        return None
    return (1, doc['page_count'])


def search_within_page(store: DocumentStore, doc_id: str, page_number: int, query: str) -> list[dict]:
    text = store.get_page(doc_id, page_number)
    if text is None:
        return []
    q = query.lower()
    hits = []
    pos = 0
    while True:
        idx = text.lower().find(q, pos)
        if idx < 0:
            break
        start = max(0, idx - 40)
        end = min(len(text), idx + len(query) + 40)
        hits.append({'offset': idx, 'context': text[start:end]})
        pos = idx + 1
    return hits


def find_outline_node(outline: list[dict] | None, page_number: int) -> list[str]:
    if not outline:
        return []
    path: list[str] = []
    for node in outline:
        if node.get('start_index', 0) <= page_number <= node.get('end_index', 0):
            path.append(node['title'])
            children = node.get('nodes', [])
            if children:
                path.extend(find_outline_node(children, page_number))
            break
    return path
