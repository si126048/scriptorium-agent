import uuid
from scriptorium.db import Store, checksum
from scriptorium.models import (
    ConsentScope, Participant, Project, SourceDocument,
    EvidenceSpan, AnalysisRun, RunState,
)


def _store(tmp_path):
    db = str(tmp_path / f"test-{uuid.uuid4().hex}.sqlite")
    return Store(db)


def test_project_roundtrip(tmp_path):
    s = _store(tmp_path)
    p = Project(id="proj1", owner_id="u1", policy_version="2.0")
    s.create_project(p)
    got = s.get_project("proj1")
    assert got is not None
    assert got.owner_id == "u1"
    assert got.policy_version == "2.0"


def test_project_not_found(tmp_path):
    s = _store(tmp_path)
    assert s.get_project("missing") is None


def test_participant_roundtrip(tmp_path):
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    cs = ConsentScope()
    part = Participant(id="A", project_id="p", pseudonym="anon_A", consent_scope=cs)
    s.put_participant(part)
    got = s.get_participant("p", "A")
    assert got is not None
    assert got.pseudonym == "anon_A"
    assert got.consent_scope.withdrawn_at is None


def test_participant_not_found(tmp_path):
    s = _store(tmp_path)
    assert s.get_participant("p", "ghost") is None


def test_document_fts_dedup(tmp_path):
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    d = SourceDocument(id="d1", project_id="p", origin="x.txt", type="txt",
                       checksum="abc", text="hello world")
    s.put_document(d)
    s.put_document(d)
    rows = s.conn.execute("SELECT COUNT(*) as c FROM document_fts WHERE document_id='d1'").fetchone()
    assert rows["c"] == 1


def test_document_fts_search(tmp_path):
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    d = SourceDocument(id="d1", project_id="p", origin="x.txt", type="txt",
                       checksum="abc", text="repetition changes meaning")
    s.put_document(d)
    results = s.search("repetition")
    assert len(results) == 1
    assert results[0].id == "d1"


def test_list_documents(tmp_path):
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    d1 = SourceDocument(id="d1", project_id="p", participant_id="A", origin="a.txt", type="txt", checksum="a", text="aaa")
    d2 = SourceDocument(id="d2", project_id="p", participant_id="B", origin="b.txt", type="txt", checksum="b", text="bbb")
    d3 = SourceDocument(id="d3", project_id="p", origin="theory.txt", type="txt", checksum="c", text="ccc")
    s.put_document(d1); s.put_document(d2); s.put_document(d3)
    assert len(s.list_documents("p")) == 3
    assert len(s.list_documents("p", "A")) == 1


def test_list_spans_for_document(tmp_path):
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    d = SourceDocument(id="d1", project_id="p", origin="x.txt", type="txt", checksum="abc", text="hello")
    s.put_document(d)
    sp1 = EvidenceSpan(id="s1", document_id="d1", char_start=0, char_end=5, excerpt="hello", excerpt_hash=checksum("hello"))
    sp2 = EvidenceSpan(id="s2", document_id="d1", char_start=0, char_end=5, excerpt="hello", excerpt_hash=checksum("hello"))
    s.put_spans([sp1, sp2])
    spans = s.list_spans_for_document("d1")
    assert len(spans) == 2


def test_list_theory_spans(tmp_path):
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    dt = SourceDocument(id="dt", project_id="p", origin="theory.md", type="md", checksum="t", text="theory text")
    dp = SourceDocument(id="dp", project_id="p", participant_id="A", origin="chat.txt", type="txt", checksum="c", text="chat text")
    s.put_document(dt); s.put_document(dp)
    st = EvidenceSpan(id="st1", document_id="dt", char_start=0, char_end=11, excerpt="theory text", excerpt_hash=checksum("theory text"))
    sp = EvidenceSpan(id="sp1", document_id="dp", char_start=0, char_end=9, excerpt="chat text", excerpt_hash=checksum("chat text"))
    s.put_spans([st, sp])
    theory = s.list_theory_spans("p")
    assert len(theory) == 1
    assert theory[0].id == "st1"


def test_withdraw(tmp_path):
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    cs = ConsentScope(research_analysis=True)
    s.put_participant(Participant(id="A", project_id="p", pseudonym="A", consent_scope=cs))
    w = s.withdraw("p", "A")
    assert w is not None
    assert w.withdrawn_at is not None
    assert w.consent_scope.withdrawn_at is not None


def test_withdraw_nonexistent(tmp_path):
    s = _store(tmp_path)
    assert s.withdraw("p", "ghost") is None


def test_run_roundtrip(tmp_path):
    s = _store(tmp_path)
    r = AnalysisRun(id="r1", project_id="p", participant_id="A",
                    source_ids=["d1"], state=RunState.CREATED, idempotency_key="k1")
    s.put_run(r)
    got = s.get_run("r1")
    assert got is not None
    assert got.state == RunState.CREATED


def test_run_by_idem(tmp_path):
    s = _store(tmp_path)
    r = AnalysisRun(id="r1", project_id="p", participant_id="A",
                    source_ids=["d1"], state=RunState.CREATED, idempotency_key="unique")
    s.put_run(r)
    got = s.get_run_by_idem("p", "unique")
    assert got is not None
    assert got.id == "r1"
    assert s.get_run_by_idem("p", "other") is None


def test_audit_appends(tmp_path):
    s = _store(tmp_path)
    r = AnalysisRun(id="r1", project_id="p", participant_id="A",
                    source_ids=["d1"], state=RunState.CREATED, idempotency_key="k")
    s.put_run(r)
    s.audit(r, "actor1", "reason1")
    s.audit(r, "actor2", "reason2")
    got = s.get_run("r1")
    assert len(got.audit) == 2
    assert got.audit[0]["actor"] == "actor1"
    assert got.audit[1]["reason"] == "reason2"


def test_migrations_table_created(tmp_path):
    s = _store(tmp_path)
    row = s.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'").fetchone()
    assert row is not None


def test_migrate_empty_by_default(tmp_path):
    s = _store(tmp_path)
    applied = s.migrate()
    assert applied == []


def test_migrate_applies_pending(tmp_path):
    s = _store(tmp_path)

    s.MIGRATIONS.append((1, "add test_index", "CREATE INDEX IF NOT EXISTS idx_test ON projects(id);"))
    applied = s.migrate()
    assert applied == [1]
    rows = s.conn.execute("SELECT version FROM _migrations").fetchall()
    assert len(rows) == 1
    assert rows[0]["version"] == 1

    s.MIGRATIONS.pop()


def test_migrate_idempotent(tmp_path):
    s = _store(tmp_path)
    s.MIGRATIONS.append((1, "add test_index", "CREATE INDEX IF NOT EXISTS idx_test2 ON projects(id);"))
    s.migrate()
    applied = s.migrate()
    assert applied == []
    s.MIGRATIONS.pop()


def test_migrate_multiple_in_order(tmp_path):
    s = _store(tmp_path)
    s.MIGRATIONS.extend([
        (2, "second", "CREATE INDEX IF NOT EXISTS idx_m2 ON projects(id);"),
        (1, "first", "CREATE INDEX IF NOT EXISTS idx_m1 ON projects(id);"),
    ])
    applied = s.migrate()
    assert applied == [1, 2]
    s.MIGRATIONS.clear()
