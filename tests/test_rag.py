import pytest
import uuid
from pathlib import Path
from scriptorium.db import Store, checksum
from scriptorium.models import ConsentScope, EvidenceSpan
from scriptorium.rag import ingest, search, validate_span, read_source, MAX_SPAN_CHARS


def _store(tmp_path):
    db = str(tmp_path / f"test-{uuid.uuid4().hex}.sqlite")
    return Store(db)


def _setup_project(tmp_path):
    s = _store(tmp_path)
    s.create_project(__import__("scriptorium.models", fromlist=["Project"]).Project(id="p"))
    return s


def test_read_source_txt(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    assert read_source(str(f)) == "hello world"


def test_read_source_md(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# Title", encoding="utf-8")
    assert read_source(str(f)) == "# Title"


def test_read_source_unsupported(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("a,b,c", encoding="utf-8")
    with pytest.raises(ValueError, match="UNSUPPORTED_SOURCE_TYPE"):
        read_source(str(f))


def test_ingest_creates_spans(tmp_path):
    s = _setup_project(tmp_path)
    f = tmp_path / "chat.txt"
    f.write_text("Line one.\nLine two.\nLine three.", encoding="utf-8")
    d = ingest(s, str(f), "p")
    assert d.text.startswith("Line one")
    spans = s.list_spans_for_document(d.id)
    assert len(spans) == 3


def test_ingest_dedup(tmp_path):
    s = _setup_project(tmp_path)
    f = tmp_path / "chat.txt"
    f.write_text("same content", encoding="utf-8")
    d1 = ingest(s, str(f), "p")
    d2 = ingest(s, str(f), "p")
    assert d1.id == d2.id
    docs = s.list_documents("p")
    assert len(docs) == 1


def test_ingest_empty_file_rejected(tmp_path):
    s = _setup_project(tmp_path)
    f = tmp_path / "empty.txt"
    f.write_text("   \n  \n  ", encoding="utf-8")
    with pytest.raises(ValueError, match="EMPTY_SOURCE"):
        ingest(s, str(f), "p")


def test_ingest_long_line_chunked(tmp_path):
    s = _setup_project(tmp_path)
    f = tmp_path / "long.txt"
    long_line = "x" * (MAX_SPAN_CHARS + 500)
    f.write_text(long_line, encoding="utf-8")
    d = ingest(s, str(f), "p")
    spans = s.list_spans_for_document(d.id)
    assert len(spans) >= 2
    for sp in spans:
        assert len(sp.excerpt) <= MAX_SPAN_CHARS


def test_search_returns_excerpts(tmp_path):
    s = _setup_project(tmp_path)
    f = tmp_path / "chat.txt"
    f.write_text("repetition is key\nother stuff\nmore repetition here", encoding="utf-8")
    ingest(s, str(f), "p")
    results = search(s, "repetition")
    assert len(results) >= 1
    assert "repetition" in results[0]["excerpt"].lower()


def test_validate_span_ok(tmp_path):
    s = _setup_project(tmp_path)
    f = tmp_path / "chat.txt"
    f.write_text("hello world", encoding="utf-8")
    d = ingest(s, str(f), "p")
    spans = s.list_spans_for_document(d.id)
    assert len(spans) >= 1
    assert validate_span(s, spans[0].id) is True


def test_validate_span_missing():
    assert validate_span(_store(Path(".")), "nonexistent") is False


def test_validate_span_tampered(tmp_path):
    s = _setup_project(tmp_path)
    f = tmp_path / "chat.txt"
    f.write_text("original text", encoding="utf-8")
    d = ingest(s, str(f), "p")
    spans = s.list_spans_for_document(d.id)
    tampered = EvidenceSpan(id=spans[0].id, document_id=spans[0].document_id,
                            char_start=0, char_end=6, excerpt="TAMPERED",
                            excerpt_hash=checksum("TAMPERED"))
    s.put_span(tampered)
    assert validate_span(s, tampered.id) is False


def test_ingest_with_participant(tmp_path):
    from scriptorium.models import Project
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    f = tmp_path / "chat.txt"
    f.write_text("participant says hello", encoding="utf-8")
    cs = ConsentScope()
    d = ingest(s, str(f), "p", "A", cs)
    assert d.participant_id == "A"
    assert d.consent_scope.withdrawn_at is None


def test_chat_format_detection(tmp_path):
    from scriptorium.rag import _is_chat_format
    chat = "[2024-01-01 10:00] Alice: hello\n[2024-01-01 10:01] Bob: hi there\n[2024-01-01 10:02] Alice: how are you?\n[2024-01-01 10:03] Bob: fine thanks"
    assert _is_chat_format(chat) is True
    plain = "This is a paragraph.\nAnother paragraph.\nThird paragraph."
    assert _is_chat_format(plain) is False


def test_chat_format_ingest(tmp_path):
    from scriptorium.models import Project
    s = _store(tmp_path)
    s.create_project(Project(id="p"))
    f = tmp_path / "chat.txt"
    chat = "[2024-01-01 10:00] Alice: hello world\n[2024-01-01 10:01] Bob: hi Alice\n[2024-01-01 10:02] Alice: how are you\n[2024-01-01 10:03] Bob: fine thanks"
    f.write_text(chat, encoding="utf-8")
    d = ingest(s, str(f), "p")
    spans = s.list_spans_for_document(d.id)
    assert len(spans) == 4
    assert "Alice" in spans[0].excerpt


def test_search_returns_snippet(tmp_path):
    s = _setup_project(tmp_path)
    f = tmp_path / "chat.txt"
    f.write_text("repetition is key\nother stuff\nmore repetition here", encoding="utf-8")
    ingest(s, str(f), "p")
    results = search(s, "repetition")
    assert len(results) >= 1
    assert "snippet" in results[0]
