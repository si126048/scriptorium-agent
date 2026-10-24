# ruff: noqa: F811
"""OCR engine selection and transcription quality on a real (synthetic) scan."""
from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from test_research_integration import research, client, imported  # noqa: F401
from hermeneut.research import schema as db
from hermeneut.research.service import row
from hermeneut.research.texts import character_error_rate, ocr_pdf, resolve_ocr_engine, rapidocr_available
from hermeneut.research.worker import run_one

CJK_FONT = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'msyh.ttc'
SCAN_TEXT = '自主学习要求说明选择理由。'


def synthetic_scan(text: str = SCAN_TEXT) -> bytes:
    """Rasterise Chinese text into an image-only PDF page, i.e. what a scanner would produce."""
    from PIL import Image, ImageDraw, ImageFont
    import pymupdf

    font = ImageFont.truetype(str(CJK_FONT), 46)
    image = Image.new('RGB', (1500, 620), 'white')
    ImageDraw.Draw(image).text((80, 140), text, font=font, fill='black')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(40, 60, 555, 300), stream=buffer.getvalue())
        return pdf.tobytes()


def test_engine_selection_is_explicit_never_silent():
    assert resolve_ocr_engine('tesseract') == 'tesseract'
    assert resolve_ocr_engine('rapidocr') == 'rapidocr'
    assert resolve_ocr_engine('auto') in {'rapidocr', 'tesseract'}
    with pytest.raises(ValueError, match='UNKNOWN_OCR_ENGINE'):
        resolve_ocr_engine('magic')
    with pytest.raises(ValueError, match='OCR_LANGUAGE_UNSUPPORTED_BY_ENGINE'):
        ocr_pdf(b'%PDF-1.4\n', language='fra', engine='rapidocr')
    # Error rates are comparable across pages; identical text is exact.
    assert character_error_rate(SCAN_TEXT, SCAN_TEXT) == 0.0
    assert character_error_rate(SCAN_TEXT, '') == 1.0


@pytest.mark.skipif(not rapidocr_available(), reason='rapidocr-onnxruntime is not installed')
@pytest.mark.skipif(not CJK_FONT.exists(), reason='no CJK font available for the synthetic scan')
def test_synthetic_chinese_scan_is_transcribed_and_measured(research, client):
    raw = synthetic_scan()
    pid = research.create_project('tester', '扫描件')['id']
    job = research.import_material(pid, 'tester', raw, 'scan.pdf', 'scan-ocr')
    run_one(research, job['id'])
    aid = job['payload']['asset_id']
    with research.engine.connect() as c:
        assert row(c, db.jobs, db.jobs.c.id == job['id'])['error'] == 'NO_EXTRACTABLE_TEXT'
    requested = client.post(f'/api/v2/projects/{pid}/materials/{aid}/ocr?engine=rapidocr')
    assert requested.status_code == 202, requested.text
    run_one(research, requested.json()['id'])
    with research.engine.connect() as c:
        assert row(c, db.jobs, db.jobs.c.id == requested.json()['id'])['state'] == 'succeeded'
    version = research.get_segments(pid, 'tester', aid)['version']
    assert version['quality']['engine'] == 'rapidocr'
    assert version['quality']['page_status'] == ['ocr']
    assert version['quality']['review_state'] == 'unreviewed'
    text = '\n'.join(segment['text'] for segment in research.get_segments(pid, 'tester', aid)['segments'])
    error_rate = character_error_rate(SCAN_TEXT, text)
    # Measured on a clean synthetic scan; real scans need their own record.
    assert error_rate <= 0.2, (error_rate, text)


@pytest.mark.skipif(not rapidocr_available(), reason='rapidocr-onnxruntime is not installed')
def test_unsupported_language_fails_without_creating_a_version(research, client):
    import pymupdf
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), 'extractable text for the language check')
        raw = pdf.tobytes()
    pid = research.create_project('tester', '语言不支持')['id']
    job = research.import_material(pid, 'tester', raw, 'lang.pdf', 'lang')
    run_one(research, job['id'])
    aid = job['payload']['asset_id']
    before = research.get_segments(pid, 'tester', aid)['version']['id']
    requested = client.post(f'/api/v2/projects/{pid}/materials/{aid}/ocr?engine=rapidocr&language=fra')
    assert requested.status_code == 202, requested.text
    run_one(research, requested.json()['id'])
    with research.engine.connect() as c:
        job = row(c, db.jobs, db.jobs.c.id == requested.json()['id'])
    assert job['state'] == 'failed'
    assert job['error'] == 'OCR_LANGUAGE_UNSUPPORTED_BY_ENGINE'
    material = next(m for m in research.list_materials(pid, 'tester') if m['id'] == aid)
    assert material['metadata']['ocr']['state'] == 'failed'
    # The failed attempt must not replace or add a text version.
    assert len(material['versions']) == 1
    assert research.get_segments(pid, 'tester', aid)['version']['id'] == before
