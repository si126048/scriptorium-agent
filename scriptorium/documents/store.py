# Derived from MISAKA-Agent (https://github.com/Luciole-Studio/Misaka-Agent)
# Copyright 2026 Luciole Studio. Licensed under Apache License 2.0.
# See NOTICE and LICENSE-MISAKA in the project root.

"""SQLite-backed content-addressed document store."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .extractors import SUPPORTED_SUFFIXES, extract_pages
from .outline import build_text_tree


class DocumentStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS doc_store(
                doc_id TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                title TEXT,
                origin_path TEXT,
                format TEXT,
                page_count INTEGER DEFAULT 0,
                outline_json TEXT,
                meta_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS doc_pages(
                doc_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                text TEXT NOT NULL,
                PRIMARY KEY (doc_id, page_number),
                FOREIGN KEY (doc_id) REFERENCES doc_store(doc_id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS doc_page_fts USING fts5(
                doc_id UNINDEXED, page_number UNINDEXED, text
            );
        ''')

    def ingest(self, path: str | Path, title: str | None = None) -> tuple[str, int]:
        path = Path(path)
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f'unsupported format: {path.suffix} (supported: {", ".join(sorted(SUPPORTED_SUFFIXES))})')

        raw_bytes = path.read_bytes()
        sha = hashlib.sha256(raw_bytes).hexdigest()
        doc_id = sha[:12]

        existing = self.get_document(doc_id)
        if existing:
            return doc_id, existing['page_count']

        pages, meta = extract_pages(path)
        is_markdown = path.suffix.lower() in ('.md', '.markdown')
        outline = build_text_tree(pages, markdown=is_markdown)

        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            'INSERT INTO doc_store(doc_id, sha256, title, origin_path, format, page_count, outline_json, meta_json, created_at) '
            'VALUES(?,?,?,?,?,?,?,?,?)',
            (doc_id, sha, title or path.stem, str(path.resolve()), path.suffix.lower(),
             len(pages), json.dumps(outline) if outline else None, json.dumps(meta, default=str), now),
        )
        for i, page_text in enumerate(pages, 1):
            self.conn.execute(
                'INSERT INTO doc_pages(doc_id, page_number, text) VALUES(?,?,?)',
                (doc_id, i, page_text),
            )
            self.conn.execute(
                'INSERT INTO doc_page_fts(doc_id, page_number, text) VALUES(?,?,?)',
                (doc_id, str(i), page_text),
            )
        self.conn.commit()
        return doc_id, len(pages)

    def get_document(self, doc_id: str) -> dict | None:
        row = self.conn.execute(
            'SELECT doc_id, sha256, title, origin_path, format, page_count, outline_json, meta_json, created_at '
            'FROM doc_store WHERE doc_id=?', (doc_id,)
        ).fetchone()
        if not row:
            return None
        return {
            'doc_id': row[0], 'sha256': row[1], 'title': row[2], 'origin_path': row[3],
            'format': row[4], 'page_count': row[5],
            'outline': json.loads(row[6]) if row[6] else None,
            'meta': json.loads(row[7]) if row[7] else {},
            'created_at': row[8],
        }

    def get_page(self, doc_id: str, page_number: int) -> str | None:
        row = self.conn.execute(
            'SELECT text FROM doc_pages WHERE doc_id=? AND page_number=?', (doc_id, page_number)
        ).fetchone()
        return row[0] if row else None

    def get_all_pages(self, doc_id: str) -> list[str]:
        rows = self.conn.execute(
            'SELECT text FROM doc_pages WHERE doc_id=? ORDER BY page_number', (doc_id,)
        ).fetchall()
        return [r[0] for r in rows]

    def list_documents(self) -> list[dict]:
        rows = self.conn.execute(
            'SELECT doc_id, title, format, page_count, created_at FROM doc_store ORDER BY created_at DESC'
        ).fetchall()
        return [
            {'doc_id': r[0], 'title': r[1], 'format': r[2], 'page_count': r[3], 'created_at': r[4]}
            for r in rows
        ]

    def search(self, query: str, doc_id: str | None = None, limit: int = 10) -> list[dict]:
        if doc_id:
            rows = self.conn.execute(
                'SELECT doc_id, page_number, text FROM doc_page_fts '
                'WHERE doc_page_fts MATCH ? AND doc_id = ? LIMIT ?',
                (query, doc_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                'SELECT doc_id, page_number, text FROM doc_page_fts '
                'WHERE doc_page_fts MATCH ? LIMIT ?',
                (query, limit),
            ).fetchall()
        return [
            {'doc_id': r[0], 'page_number': r[1], 'snippet': r[2][:200]}
            for r in rows
        ]
