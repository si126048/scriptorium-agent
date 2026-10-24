# Derived from MISAKA-Agent (https://github.com/Luciole-Studio/Misaka-Agent)
# Copyright 2026 Luciole Studio. Licensed under Apache License 2.0.
# See NOTICE and LICENSE-MISAKA in the project root.

"""Quote normalization and verification against source documents.

Ported from MISAKA-Agent's index.py quote-matching functions.
Provides Unicode-aware normalization for matching quotations across
different editions, OCR outputs, and formatting variants.
"""
from __future__ import annotations

import re
import unicodedata


def normalize_for_quote_match(text: str) -> str:
    text = re.sub(r'-\n', '', text)
    text = text.replace('\u00ad', '')
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'\s+', '', text)
    return text


def verify_quote(pages: list[str], quote: str, page_hint: int | None = None) -> dict | None:
    norm_quote = normalize_for_quote_match(quote)
    if not norm_quote:
        return None

    search_pages = [page_hint - 1] if page_hint and 0 < page_hint <= len(pages) else range(len(pages))
    for pi in search_pages:
        if pi < 0 or pi >= len(pages):
            continue
        norm_page = normalize_for_quote_match(pages[pi])
        offset = norm_page.find(norm_quote)
        if offset >= 0:
            return {
                'status': 'on_page',
                'page': pi + 1,
                'offset': offset,
                'page_count': len(pages),
            }

    for pi in range(len(pages)):
        if page_hint and pi == page_hint - 1:
            continue
        norm_page = normalize_for_quote_match(pages[pi])
        offset = norm_page.find(norm_quote)
        if offset >= 0:
            return {
                'status': 'elsewhere',
                'page': pi + 1,
                'offset': offset,
                'page_count': len(pages),
            }

    return None


def locate_quote(pages: list[str], quote: str, page_hint: int | None = None) -> str:
    result = verify_quote(pages, quote, page_hint)
    if result is None:
        return 'not_found'
    return result['status']
