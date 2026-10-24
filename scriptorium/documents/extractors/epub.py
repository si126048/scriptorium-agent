# Derived from MISAKA-Agent (https://github.com/Luciole-Studio/Misaka-Agent)
# Copyright 2026 Luciole Studio. Licensed under Apache License 2.0.
# See NOTICE and LICENSE-MISAKA in the project root.

from __future__ import annotations

import zipfile
from pathlib import Path

from .html import _TextExtractor


def extract_epub_pages(path: Path) -> tuple[list[str], dict]:
    pages: list[str] = []
    with zipfile.ZipFile(str(path), 'r') as zf:
        html_names = sorted(
            n for n in zf.namelist()
            if n.lower().endswith(('.html', '.xhtml', '.htm'))
            and 'META-INF' not in n
        )
        for name in html_names:
            raw = zf.read(name).decode('utf-8', errors='replace')
            extractor = _TextExtractor()
            extractor.feed(raw)
            text = extractor.get_text()
            if text:
                pages.append(text)
    if not pages:
        return [''], {'format': 'epub', 'page_count': 0}
    return pages, {'format': 'epub', 'page_count': len(pages)}
