"""TEI subset and immutable reading.v1 projection. No normalization of anchor text."""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

from lxml import etree as ET

NS = 'http://www.tei-c.org/ns/1.0'
XML_ID = '{http://www.w3.org/XML/1998/namespace}id'


def tag(name):
    return f'{{{NS}}}{name}'


OCR_ENGINES = ('auto', 'rapidocr', 'tesseract')


def rapidocr_available() -> bool:
    import importlib.util
    return importlib.util.find_spec('rapidocr_onnxruntime') is not None


def resolve_ocr_engine(requested: str = 'auto') -> str:
    """Pick the OCR engine. Explicit choices are honoured or fail loudly, never silently downgraded."""
    if requested not in OCR_ENGINES:
        raise ValueError('UNKNOWN_OCR_ENGINE')
    if requested == 'auto':
        return 'rapidocr' if rapidocr_available() else 'tesseract'
    return requested


def character_error_rate(expected: str, actual: str) -> float:
    """Levenshtein-style character error rate for OCR quality records (0.0 is exact)."""
    import difflib
    clean = lambda value: re.sub(r'\s+', '', value or '')
    left, right = clean(expected), clean(actual)
    if not left:
        return 0.0 if not right else 1.0
    matched = sum(block.size for block in difflib.SequenceMatcher(None, left, right).get_matching_blocks())
    return round(1 - matched / len(left), 4)


def ocr_pdf(raw, language='chi_sim+eng', engine='auto'):
    """Local OCR only. An OCR transcription is never marked scholarly verified.

    Pages that already carry a text layer are kept as-is. A page without text is OCR'd; if the
    engine or its language data is unavailable that page is listed instead of failing the whole
    material, so a mixed document still yields the readable part plus explicit unreadable pages.
    """
    chosen = resolve_ocr_engine(engine)
    if chosen == 'rapidocr':
        return _ocr_rapidocr(raw, language)
    return _ocr_tesseract(raw, language)


def _quality(engine, language):
    return {'extractor': f'ocr:{engine}', 'engine': engine, 'language': language,
            'review_state': 'unreviewed', 'empty_pages': [], 'page_status': [],
            'ocr_unavailable_pages': [], 'page_labels_are_printed': False}


def _ocr_tesseract(raw, language):
    import pymupdf
    pages, quality = [], _quality('tesseract', language)
    engine_error = None
    try:
        with pymupdf.open(stream=raw, filetype='pdf') as document:
            for i, page in enumerate(document):
                text = page.get_text()
                status = 'text'
                if not text.strip() and engine_error is None:
                    try:
                        text = page.get_text(textpage=page.get_textpage_ocr(language=language, dpi=200, full=True))
                        status = 'ocr' if text.strip() else 'empty'
                    except RuntimeError as exc:
                        engine_error = str(exc)
                        status = 'engine_unavailable'
                elif not text.strip():
                    status = 'engine_unavailable'
                pages.append(text)
                quality['page_status'].append(status)
                if not text.strip():
                    quality['empty_pages'].append(i + 1)
                    if status == 'engine_unavailable':
                        quality['ocr_unavailable_pages'].append(i + 1)
    except RuntimeError as exc:
        raise ValueError('OCR_ENGINE_OR_LANGUAGE_UNAVAILABLE') from exc
    if not any(t.strip() for t in pages):
        raise ValueError('OCR_ENGINE_OR_LANGUAGE_UNAVAILABLE' if engine_error else 'OCR_NO_TEXT')
    quality['ocr_engine'] = 'unavailable' if engine_error else 'available'
    return pages, quality


def _ocr_rapidocr(raw, language):
    """PP-OCR models cover Chinese and English; other languages must be declared unsupported."""
    tokens = [token for token in re.split(r'\+', language or '') if token]
    if not tokens or any(token not in {'chi_sim', 'eng', 'ch', 'en'} for token in tokens):
        raise ValueError('OCR_LANGUAGE_UNSUPPORTED_BY_ENGINE')
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise ValueError('OCR_ENGINE_OR_LANGUAGE_UNAVAILABLE') from exc
    import pymupdf
    engine = RapidOCR()
    pages, quality = [], _quality('rapidocr', language)
    with pymupdf.open(stream=raw, filetype='pdf') as document:
        for i, page in enumerate(document):
            text = page.get_text()
            if text.strip():
                pages.append(text)
                quality['page_status'].append('text')
                continue
            image = page.get_pixmap(dpi=200).tobytes('png')
            result, _ = engine(image)
            lines = [str(item[1]) for item in (result or []) if len(item) > 1 and str(item[1]).strip()]
            text = '\n'.join(lines)
            pages.append(text)
            quality['page_status'].append('ocr' if text.strip() else 'empty')
            if not text.strip():
                quality['empty_pages'].append(i + 1)
    if not any(t.strip() for t in pages):
        raise ValueError('OCR_NO_TEXT')
    quality['ocr_engine'] = 'available'
    return pages, quality


def extract(raw: bytes, filename: str):
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or '' for page in reader.pages]
        quality = {'extractor': 'pypdf', 'empty_pages': [i + 1 for i, p in enumerate(pages) if not p.strip()]}
    elif suffix in {'.txt', '.md'}:
        try:
            text = raw.decode('utf-8-sig')
            encoding = 'utf-8'
        except UnicodeDecodeError:
            text = raw.decode('gb18030')
            encoding = 'gb18030'
        pages = text.split('\f')
        quality = {'extractor': 'text', 'encoding': encoding, 'page_labels_are_printed': False}
    else:
        raise ValueError('SUPPORTED_FORMATS: .txt .md .pdf .xml .tei')
    if not any(p.strip() for p in pages):
        raise ValueError('NO_EXTRACTABLE_TEXT: original retained; OCR required')
    return pages, quality


def build_tei(pages: list[str], title: str):
    root = ET.Element(tag('TEI'), nsmap={None: NS})
    header = ET.SubElement(root, tag('teiHeader'))
    desc = ET.SubElement(header, tag('fileDesc'))
    titles = ET.SubElement(desc, tag('titleStmt'))
    ET.SubElement(titles, tag('title')).text = title
    publication = ET.SubElement(desc, tag('publicationStmt'))
    ET.SubElement(publication, tag('p')).text = 'Scriptorium research transcription; not a critical edition.'
    source = ET.SubElement(desc, tag('sourceDesc'))
    ET.SubElement(source, tag('p')).text = 'Derived from retained original. Page labels are extraction sequence.'
    revision = ET.SubElement(header, tag('revisionDesc'))
    ET.SubElement(revision, tag('change'), who='#scriptorium').text = 'Generated transcription, reading.v1'
    # Responsibility is declared without pretending the generated text is scholarly reviewed.
    resp = ET.SubElement(titles, tag('respStmt'))
    ET.SubElement(resp, tag('resp')).text = 'transcription software'
    ET.SubElement(resp, tag('name'), {XML_ID: 'scriptorium'}).text = 'Scriptorium'
    body = ET.SubElement(ET.SubElement(root, tag('text')), tag('body'))
    for index, page in enumerate(pages, 1):
        ET.SubElement(body, tag('pb'), n=str(index))
        for paragraph in re.split(r'\n[ \t]*\n', page.replace('\r\n', '\n')):
            if paragraph.strip():
                p = ET.SubElement(body, tag('p'), {XML_ID: f'p_{index}_{len(body)}'})
                p.text = paragraph.strip()
    return ET.tostring(root, xml_declaration=True, encoding='UTF-8')


def project_tei(raw: bytes):
    parser = ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = ET.fromstring(raw, parser)
    except ET.XMLSyntaxError as exc:
        raise ValueError('TEI_XML_INVALID') from exc
    if root.getroottree().docinfo.doctype or any(isinstance(x, ET._Entity) for x in root.iter()):
        raise ValueError('DTD_AND_ENTITIES_FORBIDDEN')
    schema = ET.RelaxNG(ET.parse(str(Path(__file__).with_name('tei-subset.rng'))))
    if not schema.validate(root):
        raise ValueError(f'TEI_SUBSET_INVALID: {schema.error_log.last_error}')
    ids = [x.get(XML_ID) for x in root.iter() if x.get(XML_ID)]
    if len(ids) != len(set(ids)):
        raise ValueError('DUPLICATE_XML_ID')
    for element in root.iter():
        for attribute in ('target', 'facs', 'corresp', 'who'):
            for ref in element.get(attribute, '').split():
                if ref.startswith('#') and ref[1:] not in ids:
                    raise ValueError('UNRESOLVED_TEI_REFERENCE')
    body = root.find(f'{tag("text")}/{tag("body")}')
    if body is None:
        raise ValueError('TEI_BODY_REQUIRED')
    result, page = [], None
    for element in body.iter():
        if element.tag == tag('pb'):
            page = element.get('n')
        if element.tag not in {tag('p'), tag('head'), tag('note')}:
            continue
        if any(a.tag in {tag('p'), tag('head'), tag('note')} for a in element.iterancestors()):
            continue
        # reading.v1 preserves all descendant text including inline notes/choice readings.
        text = ''.join(element.itertext())
        if not text.strip():
            continue
        xml_id = element.get(XML_ID)
        if not xml_id:
            raise ValueError('BLOCK_XML_ID_REQUIRED')
        result.append({'xml_id': xml_id, 'ordinal': len(result), 'page_label': page, 'text': text})
    if not result:
        raise ValueError('NO_TEXT_SEGMENTS')
    return result


def quote_hash(text: str):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
