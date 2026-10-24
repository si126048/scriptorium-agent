# Derived from MISAKA-Agent (https://github.com/Luciole-Studio/Misaka-Agent)
# Copyright 2026 Luciole Studio. Licensed under Apache License 2.0.
# See NOTICE and LICENSE-MISAKA in the project root.

"""Format-specific text extractors. Returns (pages, metadata) for any supported file."""
from __future__ import annotations

from pathlib import Path

_TEXT_SUFFIXES = {'.txt', '.md', '.markdown', '.rst', '.tex', '.text'}
_PDF_SUFFIXES = {'.pdf'}
_HTML_SUFFIXES = {'.html', '.htm', '.xhtml'}
_EPUB_SUFFIXES = {'.epub'}
_OFFICE_SUFFIXES = {'.docx', '.xlsx', '.pptx'}

SUPPORTED_SUFFIXES = _TEXT_SUFFIXES | _PDF_SUFFIXES | _HTML_SUFFIXES | _EPUB_SUFFIXES | _OFFICE_SUFFIXES


def extract_pages(path: str | Path) -> tuple[list[str], dict]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        from .text import extract_text_pages
        return extract_text_pages(path)
    if suffix in _PDF_SUFFIXES:
        from .pdf import extract_pdf_pages
        return extract_pdf_pages(path)
    if suffix in _HTML_SUFFIXES:
        from .html import extract_html_pages
        return extract_html_pages(path)
    if suffix in _EPUB_SUFFIXES:
        from .epub import extract_epub_pages
        return extract_epub_pages(path)
    if suffix in _OFFICE_SUFFIXES:
        from .office import extract_office_pages
        return extract_office_pages(path)
    raise ValueError(f'unsupported format: {suffix}')
