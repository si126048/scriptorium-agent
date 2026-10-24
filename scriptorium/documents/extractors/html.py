# Derived from MISAKA-Agent (https://github.com/Luciole-Studio/Misaka-Agent)
# Copyright 2026 Luciole Studio. Licensed under Apache License 2.0.
# See NOTICE and LICENSE-MISAKA in the project root.

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


class _TextExtractor(HTMLParser):
    _SKIP_TAGS = frozenset({'script', 'style', 'head', 'nav', 'footer', 'header'})

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr'):
            self._parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        text = ''.join(self._parts)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def extract_html_pages(path: Path) -> tuple[list[str], dict]:
    raw = path.read_text(encoding='utf-8', errors='replace')
    extractor = _TextExtractor()
    extractor.feed(raw)
    text = extractor.get_text()
    return [text], {'format': path.suffix.lower(), 'page_count': 1}
