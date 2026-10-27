"""Plugin-only SQLite store. Keeps existing plugin corpora; never upgrades a legacy app DB."""

import hashlib
import sqlite3
import threading
from pathlib import Path

from .models import EvidenceSpan, Project, SourceDocument


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: str):
        self.path = Path(path).resolve()
        if self.path.is_file() and self.path.stat().st_size:
            # Inspect first through a read-only connection, before setting WAL or creating tables.
            with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as probe:
                tables = {
                    r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                marked = "scriptorium_plugin" in tables
                if marked and probe.execute(
                    "SELECT version FROM scriptorium_plugin LIMIT 1"
                ).fetchone() != (1,):
                    raise ValueError("PLUGIN_SCHEMA_NOT_SUPPORTED")
                transitional = (
                    "projects" in tables
                    and probe.execute(
                        "SELECT 1 FROM projects WHERE id LIKE 'plugin-%' LIMIT 1"
                    ).fetchone()
                )
                if not marked and not transitional:
                    raise ValueError(
                        "NOT_A_PLUGIN_DATABASE: export legacy materials before importing"
                    )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=15000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS scriptorium_plugin(version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, participant_id TEXT, kind TEXT, data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS plugin_documents_project ON documents(project_id);
            CREATE TABLE IF NOT EXISTS spans(id TEXT PRIMARY KEY, document_id TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS manuscripts(
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
                question TEXT NOT NULL, revision INTEGER NOT NULL, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS manuscript_sections(
                manuscript_id TEXT NOT NULL, section_id TEXT NOT NULL, position INTEGER NOT NULL,
                title TEXT NOT NULL, content TEXT NOT NULL, citations TEXT NOT NULL,
                revision INTEGER NOT NULL, PRIMARY KEY(manuscript_id,section_id)
            );
            CREATE TABLE IF NOT EXISTS manuscript_history(
                manuscript_id TEXT NOT NULL, section_id TEXT NOT NULL, revision INTEGER NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(manuscript_id,section_id,revision)
            );
        """)
        if not self.conn.execute("SELECT 1 FROM scriptorium_plugin").fetchone():
            self.conn.execute("INSERT INTO scriptorium_plugin VALUES(1)")
        self.conn.commit()

    def get_project(self, identifier: str):
        row = self.conn.execute("SELECT data FROM projects WHERE id=?", (identifier,)).fetchone()
        return Project.model_validate_json(row["data"]) if row else None

    def create_project(self, project: Project):
        self.conn.execute(
            "INSERT OR IGNORE INTO projects VALUES(?,?)", (project.id, project.model_dump_json())
        )
        self.conn.commit()
        return project

    def get_document(self, identifier: str):
        row = self.conn.execute("SELECT data FROM documents WHERE id=?", (identifier,)).fetchone()
        return SourceDocument.model_validate_json(row["data"]) if row else None

    def list_documents(self, project_id: str):
        return [
            SourceDocument.model_validate_json(r["data"])
            for r in self.conn.execute(
                "SELECT data FROM documents WHERE project_id=? ORDER BY rowid", (project_id,)
            )
        ]

    def put_document(self, doc: SourceDocument):
        self.conn.execute(
            "INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)",
            (doc.id, doc.project_id, doc.participant_id, doc.type, doc.model_dump_json()),
        )
        self.conn.commit()
        return doc

    def put_spans(self, spans: list[EvidenceSpan]):
        self.conn.executemany(
            "INSERT OR REPLACE INTO spans VALUES(?,?,?)",
            [(s.id, s.document_id, s.model_dump_json()) for s in spans],
        )
        self.conn.commit()
        return spans

    def import_document(self, doc: SourceDocument, spans: list[EvidenceSpan]):
        with self.conn:
            self.conn.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?)",
                (doc.id, doc.project_id, doc.participant_id, doc.type, doc.model_dump_json()),
            )
            self.conn.executemany(
                "INSERT INTO spans VALUES(?,?,?)",
                [(s.id, s.document_id, s.model_dump_json()) for s in spans],
            )
