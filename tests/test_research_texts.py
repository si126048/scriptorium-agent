from pathlib import Path

import pytest

pytest.importorskip('lxml')

from hermeneut.research.storage import FileObjects
from hermeneut.research.texts import build_tei, project_tei, quote_hash


def test_tei_codepoints_and_no_normalization():
    text = '甲😀e\u0301乙\n带 空格'
    segments = project_tei(build_tei([text], 'Test'))
    assert segments[0]['text'] == text
    assert text[1:4] == '😀e\u0301'
    assert quote_hash(text) != quote_hash(text.replace(' ', ''))


def test_inline_projection_is_explicit_and_stable():
    tei = build_tei(['before'], 'Test').replace(b'before',
        b'A<quote>B<hi>C</hi>D</quote>E<note>N</note>F')
    assert project_tei(tei)[0]['text'] == 'ABCDENF'


@pytest.mark.parametrize('raw', [
    b'<!DOCTYPE TEI [<!ENTITY x SYSTEM "file:///C:/Windows/win.ini">]><TEI>&x;</TEI>',
    b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>no id</p></body></text></TEI>',
    build_tei(['text'], 'Test').replace(b'who="#hermeneut"', b'who="#missing"'),
    build_tei(['text'], 'Test').replace(b'<p ', b'<unsupported '),
])
def test_invalid_or_unsafe_tei_rejected(raw):
    with pytest.raises((ValueError, __import__('lxml.etree', fromlist=['XMLSyntaxError']).XMLSyntaxError)):
        project_tei(raw)


def test_object_store_atomic_immutable_and_contained(tmp_path):
    objects = FileObjects(tmp_path)
    key, digest = objects.put(b'original')
    assert objects.put(b'original') == (key, digest)
    assert objects.read(key) == b'original'
    with pytest.raises(ValueError):
        objects.read('../outside')
    objects.path(key).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='CHECKSUM'):
        objects.read(key)
    assert not list(Path(tmp_path).glob('**/.pending-*'))
