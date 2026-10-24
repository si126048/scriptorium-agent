from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .models import (
    AnalysisRun,
    ConceptCard,
    EvidenceSpan,
    InterviewSession,
    InterviewState,
    Participant,
    Project,
    SourceDocument,
)

logger = logging.getLogger(__name__)
_JOURNAL_MODE_LOCK = threading.Lock()


class Store:
    SCHEMA_VERSION = 0
    MIGRATIONS: list[tuple[int, str, str]] = []

    def __init__(self, path: str | None = None):
        from .config import frozen_source, get_settings
        cfg = get_settings()
        self.path = Path(path or cfg.db_path)
        frozen = frozen_source()
        if frozen and str(self.path.resolve()) == frozen:
            # Opening the frozen snapshot would create tables and a default project in it,
            # changing the input of every later migration. Use a working copy instead.
            raise RuntimeError('SOURCE_DATABASE_READ_ONLY: refusing to write the frozen migration source '
                               f'{frozen}; set LACAN_DB_PATH to a working copy')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        if cfg.enable_wal:
            try:
                with _JOURNAL_MODE_LOCK:
                    self.conn.execute('PRAGMA journal_mode=WAL')
            except sqlite3.OperationalError:
                logger.debug('WAL unavailable for %s; continuing with default journal', self.path)
        self.conn.execute('PRAGMA busy_timeout=30000')
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS participants(id TEXT, project_id TEXT, data TEXT NOT NULL, PRIMARY KEY(id,project_id));
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, project_id TEXT, participant_id TEXT, kind TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS spans(id TEXT PRIMARY KEY, document_id TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS concepts(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, project_id TEXT, participant_id TEXT, idem TEXT, data TEXT NOT NULL, UNIQUE(project_id,idem));
            CREATE TABLE IF NOT EXISTS interview_sessions(
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                state TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(document_id UNINDEXED, text);
            CREATE TABLE IF NOT EXISTS _migrations(version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL);
        ''')
        self.conn.commit()
        self.migrate()
        self._ensure_topostyle_schema()
        self._ensure_default_project()

    def _ensure_topostyle_schema(self) -> None:
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS personas(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, participant_id TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS persona_artifacts(id TEXT PRIMARY KEY, persona_id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, persona_id TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversation_messages(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS topology_metrics(id TEXT PRIMARY KEY, persona_id TEXT NOT NULL, conversation_id TEXT, data TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_personas_project ON personas(project_id, participant_id);
            CREATE INDEX IF NOT EXISTS idx_artifacts_persona ON persona_artifacts(persona_id, version);
            CREATE INDEX IF NOT EXISTS idx_metrics_persona ON topology_metrics(persona_id, created_at);
        ''')
        self.conn.commit()

    def _ensure_default_project(self) -> None:
        if not self.get_project('default'):
            self.create_project(Project(
                id='default', name='Default Project',
                description='Default workspace',
                created_at=datetime.now(UTC).isoformat(),
            ))

    def migrate(self) -> list[int]:
        applied: list[int] = []
        existing = {r['version'] for r in self.conn.execute('SELECT version FROM _migrations').fetchall()}
        for version, description, sql in sorted(self.MIGRATIONS, key=lambda m: m[0]):
            if version in existing:
                continue
            logger.info("applying migration %d: %s", version, description)
            self.conn.executescript(sql)
            self.conn.execute(
                'INSERT INTO _migrations(version, description, applied_at) VALUES(?,?,?)',
                (version, description, datetime.now(UTC).isoformat()),
            )
            self.conn.commit()
            applied.append(version)
        if applied:
            logger.info("applied %d migration(s): %s", len(applied), applied)
        return applied

    def create_project(self, p: Project) -> Project:
        self.conn.execute('INSERT OR REPLACE INTO projects VALUES(?,?)', (p.id, p.model_dump_json()))
        self.conn.commit()
        return p

    def get_project(self, project_id: str) -> Project | None:
        r = self.conn.execute('SELECT data FROM projects WHERE id=?', (project_id,)).fetchone()
        return Project.model_validate_json(r['data']) if r else None

    def list_projects(self) -> list[Project]:
        rows = self.conn.execute('SELECT data FROM projects ORDER BY id').fetchall()
        return [Project.model_validate_json(r['data']) for r in rows]

    def delete_project(self, project_id: str) -> bool:
        if project_id == 'default':
            return False
        existing = self.get_project(project_id)
        if not existing:
            return False
        with self.lock:
            self.conn.execute('DELETE FROM personas WHERE project_id=?', (project_id,))
            self.conn.execute('DELETE FROM interview_sessions WHERE project_id=?', (project_id,))
            self.conn.execute('DELETE FROM runs WHERE project_id=?', (project_id,))
            self.conn.execute('DELETE FROM document_fts WHERE document_id IN (SELECT id FROM documents WHERE project_id=?)', (project_id,))
            self.conn.execute('DELETE FROM documents WHERE project_id=?', (project_id,))
            self.conn.execute('DELETE FROM participants WHERE project_id=?', (project_id,))
            self.conn.execute('DELETE FROM projects WHERE id=?', (project_id,))
            self.conn.commit()
        return True

    def put_participant(self, p: Participant) -> Participant:
        self.conn.execute('INSERT OR REPLACE INTO participants VALUES(?,?,?)', (p.id, p.project_id, p.model_dump_json()))
        self.conn.commit()
        return p

    def get_participant(self, project_id: str, participant_id: str) -> Participant | None:
        r = self.conn.execute('SELECT data FROM participants WHERE project_id=? AND id=?', (project_id, participant_id)).fetchone()
        return Participant.model_validate_json(r['data']) if r else None

    def list_participants(self, project_id: str) -> list[Participant]:
        rows = self.conn.execute(
            'SELECT data FROM participants WHERE project_id=? ORDER BY id', (project_id,)
        ).fetchall()
        return [Participant.model_validate_json(r['data']) for r in rows]

    def delete_participant(self, project_id: str, participant_id: str) -> bool:
        existing = self.get_participant(project_id, participant_id)
        if not existing:
            return False
        with self.lock:
            self.conn.execute(
                'DELETE FROM spans WHERE document_id IN (SELECT id FROM documents WHERE project_id=? AND participant_id=?)',
                (project_id, participant_id))
            self.conn.execute(
                'DELETE FROM document_fts WHERE document_id IN (SELECT id FROM documents WHERE project_id=? AND participant_id=?)',
                (project_id, participant_id))
            self.conn.execute(
                'DELETE FROM documents WHERE project_id=? AND participant_id=?',
                (project_id, participant_id))
            self.conn.execute(
                'DELETE FROM runs WHERE project_id=? AND participant_id=?',
                (project_id, participant_id))
            self.conn.execute(
                'DELETE FROM interview_sessions WHERE project_id=? AND participant_id=?',
                (project_id, participant_id))
            self.conn.execute(
                'DELETE FROM personas WHERE project_id=? AND participant_id=?',
                (project_id, participant_id))
            self.conn.execute(
                'DELETE FROM participants WHERE project_id=? AND id=?',
                (project_id, participant_id))
            self.conn.commit()
        return True

    def put_document(self, d: SourceDocument) -> SourceDocument:
        self.conn.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)', (d.id, d.project_id, d.participant_id, d.type, d.model_dump_json()))
        self.conn.execute('DELETE FROM document_fts WHERE document_id=?', (d.id,))
        self.conn.execute('INSERT INTO document_fts(document_id,text) VALUES(?,?)', (d.id, d.text))
        self.conn.commit()
        return d

    def get_document(self, doc_id: str) -> SourceDocument | None:
        r = self.conn.execute('SELECT data FROM documents WHERE id=?', (doc_id,)).fetchone()
        return SourceDocument.model_validate_json(r['data']) if r else None

    def list_documents(self, project_id: str, participant_id: str | None = None) -> list[SourceDocument]:
        q = 'SELECT data FROM documents WHERE project_id=?'
        args: list[str] = [project_id]
        if participant_id is not None:
            q += ' AND participant_id=?'
            args.append(participant_id)
        return [SourceDocument.model_validate_json(r['data']) for r in self.conn.execute(q, args)]

    def list_spans_for_document(self, document_id: str) -> list[EvidenceSpan]:
        rows = self.conn.execute('SELECT data FROM spans WHERE document_id=?', (document_id,)).fetchall()
        return [EvidenceSpan.model_validate_json(r['data']) for r in rows]

    def list_theory_spans(self, project_id: str) -> list[EvidenceSpan]:
        rows = self.conn.execute(
            'SELECT data FROM spans WHERE document_id IN (SELECT id FROM documents WHERE project_id=? AND participant_id IS NULL)',
            (project_id,),
        ).fetchall()
        return [EvidenceSpan.model_validate_json(r['data']) for r in rows]

    def put_span(self, s: EvidenceSpan) -> EvidenceSpan:
        self.conn.execute('INSERT OR REPLACE INTO spans VALUES(?,?,?)', (s.id, s.document_id, s.model_dump_json()))
        self.conn.commit()
        return s

    def put_spans(self, spans: list[EvidenceSpan]) -> list[EvidenceSpan]:
        self.conn.executemany('INSERT OR REPLACE INTO spans VALUES(?,?,?)',
                              [(s.id, s.document_id, s.model_dump_json()) for s in spans])
        self.conn.commit()
        return spans

    def get_span(self, span_id: str) -> EvidenceSpan | None:
        r = self.conn.execute('SELECT data FROM spans WHERE id=?', (span_id,)).fetchone()
        return EvidenceSpan.model_validate_json(r['data']) if r else None

    def put_concept(self, c: ConceptCard) -> ConceptCard:
        self.conn.execute('INSERT OR REPLACE INTO concepts VALUES(?,?)', (c.id, c.model_dump_json()))
        self.conn.commit()
        return c

    def get_concept(self, concept_id: str) -> ConceptCard | None:
        r = self.conn.execute('SELECT data FROM concepts WHERE id=?', (concept_id,)).fetchone()
        return ConceptCard.model_validate_json(r['data']) if r else None

    def search(self, query: str, limit: int = 5) -> list[SourceDocument]:
        rows = self.conn.execute(
            'SELECT d.data FROM document_fts f JOIN documents d ON d.id=f.document_id WHERE document_fts MATCH ? LIMIT ?',
            (query, limit),
        ).fetchall()
        return [SourceDocument.model_validate_json(r['data']) for r in rows]

    def put_run(self, r: AnalysisRun) -> AnalysisRun:
        self.conn.execute(
            '''INSERT INTO runs(id,project_id,participant_id,idem,data) VALUES(?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id,
               participant_id=excluded.participant_id, idem=excluded.idem, data=excluded.data''',
            (r.id, r.project_id, r.participant_id, r.idempotency_key, r.model_dump_json()),
        )
        self.conn.commit()
        return r

    def create_run_atomic(self, r: AnalysisRun) -> AnalysisRun:
        try:
            self.conn.execute(
                'INSERT INTO runs(id,project_id,participant_id,idem,data) VALUES(?,?,?,?,?)',
                (r.id, r.project_id, r.participant_id, r.idempotency_key, r.model_dump_json()),
            )
            self.conn.commit()
            return r
        except sqlite3.IntegrityError:
            self.conn.rollback()
            existing = self.get_run_by_idem(r.project_id, r.idempotency_key)
            if existing is not None:
                if sorted(existing.source_ids) != sorted(r.source_ids):
                    raise ValueError('IDEMPOTENCY_SOURCE_MISMATCH')
                return existing
            raise

    def get_run(self, run_id: str) -> AnalysisRun | None:
        r = self.conn.execute('SELECT data FROM runs WHERE id=?', (run_id,)).fetchone()
        return AnalysisRun.model_validate_json(r['data']) if r else None

    def get_run_by_idem(self, project_id: str, idem: str) -> AnalysisRun | None:
        r = self.conn.execute('SELECT data FROM runs WHERE project_id=? AND idem=?', (project_id, idem)).fetchone()
        return AnalysisRun.model_validate_json(r['data']) if r else None

    def put_interview_session(self, session: InterviewSession) -> InterviewSession:
        self.conn.execute(
            '''INSERT INTO interview_sessions(id,project_id,participant_id,state,data,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET state=excluded.state,data=excluded.data,
               updated_at=excluded.updated_at''',
            (session.id, session.project_id, session.participant_id, session.state,
             session.model_dump_json(), session.created_at, session.updated_at),
        )
        self.conn.commit()
        return session

    def get_interview_session(self, session_id: str, project_id: str | None = None,
                              participant_id: str | None = None) -> InterviewSession | None:
        query = 'SELECT data FROM interview_sessions WHERE id=?'
        args: list[str] = [session_id]
        if project_id is not None:
            query += ' AND project_id=?'
            args.append(project_id)
        if participant_id is not None:
            query += ' AND participant_id=?'
            args.append(participant_id)
        row = self.conn.execute(query, args).fetchone()
        return InterviewSession.model_validate_json(row['data']) if row else None

    def list_interview_sessions(self, project_id: str, participant_id: str) -> list[InterviewSession]:
        rows = self.conn.execute(
            'SELECT data FROM interview_sessions WHERE project_id=? AND participant_id=? ORDER BY created_at DESC',
            (project_id, participant_id),
        ).fetchall()
        return [InterviewSession.model_validate_json(row['data']) for row in rows]

    def audit(self, run: AnalysisRun, actor: str, reason: str) -> AnalysisRun:
        run.audit.append({'actor': actor, 'timestamp': datetime.now(UTC).isoformat(), 'state': run.state, 'reason': reason})
        return self.put_run(run)

    def withdraw(self, project_id: str, participant_id: str) -> Participant | None:
        p = self.get_participant(project_id, participant_id)
        if not p:
            return None
        p.withdrawn_at = datetime.now(UTC).isoformat()
        p.consent_scope.withdrawn_at = p.withdrawn_at
        with self.conn:
            self.conn.execute('DELETE FROM spans WHERE document_id IN (SELECT id FROM documents WHERE project_id=? AND participant_id=?)', (project_id, participant_id))
            self.conn.execute('DELETE FROM document_fts WHERE document_id IN (SELECT id FROM documents WHERE project_id=? AND participant_id=?)', (project_id, participant_id))
            self.conn.execute('DELETE FROM documents WHERE project_id=? AND participant_id=?', (project_id, participant_id))
            self.conn.execute('DELETE FROM runs WHERE project_id=? AND participant_id=?', (project_id, participant_id))
            sessions = self.conn.execute(
                'SELECT id,data FROM interview_sessions WHERE project_id=? AND participant_id=?',
                (project_id, participant_id),
            ).fetchall()
            for row in sessions:
                session = InterviewSession.model_validate_json(row['data'])
                session.state = InterviewState.WITHDRAWN
                session.turns = []
                session.current_question_id = None
                session.current_question_text = None
                session.updated_at = datetime.now(UTC).isoformat()
                self.conn.execute(
                    'UPDATE interview_sessions SET state=?,data=?,updated_at=? WHERE id=?',
                    (session.state, session.model_dump_json(), session.updated_at, row['id']),
                )
            self.conn.execute('UPDATE participants SET data=? WHERE project_id=? AND id=?', (p.model_dump_json(), project_id, participant_id))
            persona_ids = [r['id'] for r in self.conn.execute('SELECT id FROM personas WHERE project_id=? AND participant_id=?', (project_id, participant_id))]
            for persona_id in persona_ids:
                self.conn.execute('DELETE FROM persona_artifacts WHERE persona_id=?', (persona_id,))
                self.conn.execute('DELETE FROM topology_metrics WHERE persona_id=?', (persona_id,))
                self.conn.execute('DELETE FROM conversation_messages WHERE conversation_id IN (SELECT id FROM conversations WHERE persona_id=?)', (persona_id,))
                self.conn.execute('DELETE FROM conversations WHERE persona_id=?', (persona_id,))
                self.conn.execute('DELETE FROM personas WHERE id=?', (persona_id,))
        return p

    def put_persona(self, persona: dict) -> dict:
        self.conn.execute('INSERT OR REPLACE INTO personas(id,project_id,participant_id,data) VALUES(?,?,?,?)',
                          (persona['id'], persona['project_id'], persona['participant_id'], json.dumps(persona, ensure_ascii=False)))
        self.conn.commit()
        return persona

    def get_persona(self, persona_id: str) -> dict | None:
        row = self.conn.execute('SELECT data FROM personas WHERE id=?', (persona_id,)).fetchone()
        return json.loads(row['data']) if row else None

    def list_personas(self, project_id: str, participant_id: str | None = None) -> list[dict]:
        query = 'SELECT data FROM personas WHERE project_id=?'
        args: list[str] = [project_id]
        if participant_id is not None:
            query += ' AND participant_id=?'
            args.append(participant_id)
        return [json.loads(row['data']) for row in self.conn.execute(query, args)]

    def delete_persona(self, persona_id: str) -> None:
        with self.conn:
            self.conn.execute('DELETE FROM persona_artifacts WHERE persona_id=?', (persona_id,))
            self.conn.execute('DELETE FROM topology_metrics WHERE persona_id=?', (persona_id,))
            self.conn.execute('DELETE FROM conversation_messages WHERE conversation_id IN (SELECT id FROM conversations WHERE persona_id=?)', (persona_id,))
            self.conn.execute('DELETE FROM conversations WHERE persona_id=?', (persona_id,))
            self.conn.execute('DELETE FROM personas WHERE id=?', (persona_id,))

    def put_persona_artifact(self, artifact: dict) -> dict:
        self.conn.execute('INSERT INTO persona_artifacts(id,persona_id,version,data,created_at) VALUES(?,?,?,?,?)',
                          (artifact['id'], artifact['persona_id'], artifact['version'], json.dumps(artifact, ensure_ascii=False), artifact['created_at']))
        self.conn.commit()
        return artifact

    def list_persona_artifacts(self, persona_id: str) -> list[dict]:
        return [json.loads(row['data']) for row in self.conn.execute(
            'SELECT data FROM persona_artifacts WHERE persona_id=? ORDER BY version DESC', (persona_id,))]

    def put_conversation(self, conversation: dict) -> dict:
        self.conn.execute('INSERT OR REPLACE INTO conversations(id,persona_id,data,created_at,updated_at) VALUES(?,?,?,?,?)',
                          (conversation['id'], conversation['persona_id'], json.dumps(conversation, ensure_ascii=False), conversation['created_at'], conversation['updated_at']))
        self.conn.commit()
        return conversation

    def get_conversation(self, conversation_id: str) -> dict | None:
        row = self.conn.execute('SELECT data FROM conversations WHERE id=?', (conversation_id,)).fetchone()
        return json.loads(row['data']) if row else None

    def put_message(self, message: dict) -> dict:
        self.conn.execute('INSERT INTO conversation_messages(id,conversation_id,role,content,data,created_at) VALUES(?,?,?,?,?,?)',
                          (message['id'], message['conversation_id'], message['role'], message['content'], json.dumps(message, ensure_ascii=False), message['created_at']))
        self.conn.commit()
        return message

    def list_messages(self, conversation_id: str) -> list[dict]:
        return [json.loads(row['data']) for row in self.conn.execute(
            'SELECT data FROM conversation_messages WHERE conversation_id=? ORDER BY created_at, id', (conversation_id,))]

    def put_topology_metric(self, metric: dict) -> dict:
        self.conn.execute('INSERT INTO topology_metrics(id,persona_id,conversation_id,data,created_at) VALUES(?,?,?,?,?)',
                          (metric['id'], metric['persona_id'], metric.get('conversation_id'), json.dumps(metric, ensure_ascii=False), metric['created_at']))
        self.conn.commit()
        return metric

    def list_topology_metrics(self, persona_id: str, limit: int = 100) -> list[dict]:
        return [json.loads(row['data']) for row in self.conn.execute(
            'SELECT data FROM topology_metrics WHERE persona_id=? ORDER BY created_at DESC LIMIT ?', (persona_id, limit))]


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}'
