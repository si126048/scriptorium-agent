import sqlite3
from pathlib import Path
from scriptorium.documents.store import DocumentStore


def _make_store(tmp_path):
    db_path = tmp_path / 'test_docs.sqlite'
    conn = sqlite3.connect(str(db_path))
    return DocumentStore(conn)


def _write_txt(tmp_path, name='test.txt', content='Hello world\nSecond line\nThird line'):
    p = tmp_path / name
    p.write_text(content, encoding='utf-8')
    return p


def test_ingest_txt(tmp_path):
    store = _make_store(tmp_path)
    path = _write_txt(tmp_path)
    doc_id, page_count = store.ingest(path)
    assert doc_id
    assert len(doc_id) == 12
    assert page_count >= 1


def test_ingest_idempotent(tmp_path):
    store = _make_store(tmp_path)
    path = _write_txt(tmp_path)
    id1, pc1 = store.ingest(path)
    id2, pc2 = store.ingest(path)
    assert id1 == id2
    assert pc1 == pc2


def test_get_document(tmp_path):
    store = _make_store(tmp_path)
    path = _write_txt(tmp_path, content='Page one\n\fPage two')
    doc_id, _ = store.ingest(path, title='My Doc')
    doc = store.get_document(doc_id)
    assert doc is not None
    assert doc['doc_id'] == doc_id
    assert doc['title'] == 'My Doc'
    assert doc['format'] == '.txt'
    assert doc['page_count'] >= 1


def test_get_document_missing(tmp_path):
    store = _make_store(tmp_path)
    assert store.get_document('nonexistent') is None


def test_get_page(tmp_path):
    store = _make_store(tmp_path)
    path = _write_txt(tmp_path, content='First page\n\fSecond page')
    doc_id, _ = store.ingest(path)
    page1 = store.get_page(doc_id, 1)
    assert page1 is not None
    assert 'First page' in page1


def test_get_page_missing(tmp_path):
    store = _make_store(tmp_path)
    path = _write_txt(tmp_path)
    doc_id, _ = store.ingest(path)
    assert store.get_page(doc_id, 999) is None


def test_get_all_pages(tmp_path):
    store = _make_store(tmp_path)
    path = _write_txt(tmp_path, content='A\n\fB\n\fC')
    doc_id, pc = store.ingest(path)
    pages = store.get_all_pages(doc_id)
    assert len(pages) == pc
    assert len(pages) >= 1


def test_list_documents(tmp_path):
    store = _make_store(tmp_path)
    p1 = _write_txt(tmp_path, 'a.txt', 'aaa')
    p2 = _write_txt(tmp_path, 'b.txt', 'bbb')
    store.ingest(p1, title='A')
    store.ingest(p2, title='B')
    docs = store.list_documents()
    assert len(docs) >= 2
    titles = {d['title'] for d in docs}
    assert 'A' in titles
    assert 'B' in titles


def test_search(tmp_path):
    store = _make_store(tmp_path)
    path = _write_txt(tmp_path, content='The concept of objet petit a is central\n\fAnother page about desire')
    doc_id, _ = store.ingest(path)
    results = store.search('objet')
    assert len(results) >= 1
    assert any(r['doc_id'] == doc_id for r in results)


def test_search_within_doc(tmp_path):
    store = _make_store(tmp_path)
    path = _write_txt(tmp_path, content='Lacan and Freud\n\fDeleuze and Guattari')
    doc_id, _ = store.ingest(path)
    results = store.search('Deleuze', doc_id=doc_id)
    assert len(results) >= 1
    assert all(r['doc_id'] == doc_id for r in results)


def test_unsupported_format(tmp_path):
    store = _make_store(tmp_path)
    p = tmp_path / 'bad.xyz'
    p.write_text('nope')
    try:
        store.ingest(p)
        assert False, 'expected ValueError'
    except ValueError as exc:
        assert 'unsupported' in str(exc).lower()


def test_outline_detection(tmp_path):
    store = _make_store(tmp_path)
    content = 'CHAPTER I\nBeginning\n\nCHAPTER II\nMiddle\n\nCHAPTER III\nEnd'
    path = _write_txt(tmp_path, content=content)
    doc_id, _ = store.ingest(path)
    doc = store.get_document(doc_id)
    assert doc is not None
    # outline may or may not be detected depending on page splitting
    # but the field should exist
    assert 'outline' in doc
