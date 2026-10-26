"""Pinned official Pandoc runtime and citation-aware, non-executable document exports."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from .service import ResearchError, row, rows
from . import schema as db

BASE = Path(__file__).parent


def ensure_pandoc(root=None):
    manifest = json.loads((BASE / 'pandoc-runtime.json').read_text(encoding='utf-8'))
    cache = Path(root or os.getenv('SCRIPTORIUM_PANDOC_CACHE') or (Path(os.getenv('LOCALAPPDATA', Path.home())) / 'Scriptorium' / 'pandoc'))
    cache.mkdir(parents=True, exist_ok=True)
    marker = cache / 'installed.json'
    if marker.exists():
        saved = json.loads(marker.read_text(encoding='utf-8')); binary = cache / saved['binary']
        if saved['version'] == manifest['version'] and binary.is_file():
            with binary.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() == saved['sha256']:
                    return binary
    entry = manifest['files']['windows' if os.name == 'nt' else 'linux']
    with tempfile.TemporaryDirectory(prefix='pandoc-', dir=cache) as temp:
        staging = Path(temp); archive = staging / 'download'
        urllib.request.urlretrieve(entry['url'], archive)
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
                raise ResearchError('PANDOC_CHECKSUM_MISMATCH', 503)
        unpacked = staging / 'unpacked'; unpacked.mkdir()
        if os.name == 'nt':
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    if not (unpacked / member.filename).resolve().is_relative_to(unpacked.resolve()):
                        raise ResearchError('UNSAFE_RUNTIME_ARCHIVE', 503)
                bundle.extractall(unpacked)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(unpacked, filter='data')
        folder = next(p for p in unpacked.iterdir() if p.is_dir())
        destination = cache / manifest['version']
        shutil.copytree(folder, destination, dirs_exist_ok=True)
        binary = next(destination.rglob('pandoc.exe' if os.name == 'nt' else 'pandoc'))
        if os.name != 'nt':
            binary.chmod(0o755)
        with binary.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        temporary = cache / ('installed-' + str(os.getpid()) + '.json')
        temporary.write_text(json.dumps({'version': manifest['version'], 'binary': binary.relative_to(cache).as_posix(), 'sha256': digest}), encoding='utf-8')
        os.replace(temporary, marker)
    return binary


def strings(value):
    return [{'t': 'Str', 'c': value}]


def inlines(node, anchors, segments):
    typ = node['type']; children = [n for child in node.get('content', []) for n in inlines(child, anchors, segments)]
    if typ == 'text':
        value = strings(node.get('text', ''))
        for mark in node.get('marks', []):
            name = {'bold': 'Strong', 'italic': 'Emph', 'strike': 'Strikeout'}.get(mark['type'])
            if name:
                value = [{'t': name, 'c': value}]
            elif mark['type'] == 'code':
                value = [{'t': 'Code', 'c': [['', [], []], node.get('text', '')]}]
            elif mark['type'] == 'link':
                value = [{'t': 'Link', 'c': [['', [], []], value, [mark['attrs']['href'], '']]}]
        return value
    if typ == 'citation':
        anchor = anchors[node['attrs']['anchorId']]; segment = segments[anchor['segment_id']]
        locator = segment.get('citation_locator') or segment['page_label'] or ('段落 ' + segment['xml_id'])
        return [{'t': 'Cite', 'c': [[{'citationId': segment['asset_id'], 'citationPrefix': [],
            'citationSuffix': strings(', ' + locator), 'citationMode': {'t': 'NormalCitation'},
            'citationNoteNum': 0, 'citationHash': 0}], []]}]
    if typ == 'footnote':
        return [{'t': 'Note', 'c': [{'t': 'Para', 'c': strings(str(node.get('attrs', {}).get('text', '')))}]}]
    if typ == 'hardBreak':
        return [{'t': 'LineBreak'}]
    return children


def blocks(node, anchors, segments):
    typ = node['type']; content = node.get('content', [])
    if typ == 'paragraph':
        return [{'t': 'Para', 'c': inlines(node, anchors, segments)}]
    if typ == 'heading':
        return [{'t': 'Header', 'c': [int(node.get('attrs', {}).get('level', 2)), ['', [], []], inlines(node, anchors, segments)]}]
    if typ in {'rawBlock', 'codeBlock'}:
        text = node.get('attrs', {}).get('source', '') if typ == 'rawBlock' else ''.join(x.get('text', '') for x in content)
        return [{'t': 'CodeBlock', 'c': [['', [], []], text]}]
    if typ in {'bulletList', 'orderedList'}:
        items = [[n for child in item.get('content', []) for n in blocks(child, anchors, segments)] for item in content]
        return [{'t': 'BulletList', 'c': items}] if typ == 'bulletList' else [{'t': 'OrderedList', 'c': [[node.get('attrs', {}).get('start', 1), {'t': 'Decimal'}, {'t': 'Period'}], items]}]
    if typ == 'blockquote':
        return [{'t': 'BlockQuote', 'c': [n for child in content for n in blocks(child, anchors, segments)]}]
    if typ == 'horizontalRule':
        return [{'t': 'HorizontalRule'}]
    return [n for child in content for n in blocks(child, anchors, segments)]


def execute(s, job):
    p = job['payload']; pid = job['project_id']; actor = p['principal']
    with s.engine.connect() as c:
        s.access(c, pid, actor)
        snapshot = p.get('snapshot')
        record = snapshot['record'] if snapshot else row(c, db.records, db.records.c.id == p['record_id'], db.records.c.project_id == pid)
        if not record:
            raise ResearchError('ARTIFACT_NOT_FOUND', 404)
        s.validate_evidence(c, pid, record['payload'])
        chapters = snapshot['chapters'] if snapshot else list(c.execute(db.document_chapters.select().where(db.document_chapters.c.record_id == record['id']).order_by(db.document_chapters.c.ordinal)).mappings())
        for ch in chapters:
            s.validate_evidence(c, pid, ch['payload'])
        from .documents import citation_ids
        used_anchors = {aid for item in [record, *chapters] for aid in citation_ids(item['payload'].get('editor_json'))}
        anchors = {r['id']: r for r in rows(c, db.anchors, db.anchors.c.project_id == pid, db.anchors.c.id.in_(used_anchors))}
        segments = {r['id']: r for r in rows(c, db.segments, db.segments.c.project_id == pid,
            db.segments.c.id.in_([a['segment_id'] for a in anchors.values()]))}
        assets = snapshot['assets'] if snapshot else rows(c, db.assets, db.assets.c.project_id == pid, db.assets.c.status != 'revoked')
    from .documents import citation_ids
    documents = [record['payload'], *[ch['payload'] for ch in chapters]]
    used = {segments[anchors[aid]['segment_id']]['asset_id'] for payload in documents for aid in citation_ids(payload.get('editor_json'))}
    by_asset = {a['id']: a for a in assets}
    for segment in segments.values():
        metadata = by_asset.get(segment['asset_id'], {}).get('metadata', {})
        if metadata.get('source_quality') == 'search_excerpt': segment['citation_locator'] = '摘要快照'
        elif metadata.get('source_url') and metadata.get('source_mime') != 'application/pdf': segment['citation_locator'] = '网页快照，段落 ' + segment['xml_id']
    references = []
    for asset in assets:
        if asset['id'] not in used:
            continue
        m = asset['metadata']; ref = {'id': asset['id'], 'type': m.get('csl_type', 'article-journal' if m.get('journal') else 'webpage' if m.get('source_url') else 'book'), 'title': m.get('title') or asset['name']}
        for field in ('author', 'translator'):
            if m.get(field):
                ref[field] = [{'literal': m[field]}]
        year = str(m.get('publication_date', ''))[:4]
        if year.isdigit():
            ref['issued'] = {'date-parts': [[int(year)]]}
        if m.get('publisher'):
            ref['publisher'] = m['publisher']
        for field, key in {'journal': 'container-title', 'volume': 'volume', 'issue': 'issue', 'pages': 'page', 'doi': 'DOI', 'isbn': 'ISBN', 'language': 'language'}.items():
            if m.get(field):
                ref[key] = m[field]
        if m.get('source_url'): ref['URL'] = m['source_url']
        references.append(ref)
    body = []
    for payload in documents:
        editor = payload.get('editor_json')
        if not editor:
            # Markdown is retained as a literal source block when no canonical editor exists.
            editor = {'type': 'doc', 'content': [{'type': 'rawBlock', 'attrs': {'source': payload.get('text', '')}}]}
        if payload.get('title'):
            body.append({'t': 'Header', 'c': [1, ['', [], []], strings(payload['title'])]})
        body.extend(blocks(editor, anchors, segments))
    meta = {'lang': {'t': 'MetaString', 'c': p['locale']}, 'references': {'t': 'MetaList', 'c': [
        {'t': 'MetaMap', 'c': {k: {'t': 'MetaString', 'c': str(v)} if isinstance(v, str) else
            {'t': 'MetaList', 'c': [{'t': 'MetaMap', 'c': {a: {'t': 'MetaString', 'c': b} for a, b in x.items()}} for x in v]} if k in {'author', 'translator'} else
            {'t': 'MetaMap', 'c': {'date-parts': {'t': 'MetaList', 'c': [{'t': 'MetaList', 'c': [{'t': 'MetaString', 'c': str(v['date-parts'][0][0])}]}]}}} for k, v in ref.items()}} for ref in references]}}
    ast = {'pandoc-api-version': [1, 23, 1], 'meta': meta, 'blocks': body}
    binary = ensure_pandoc()
    fmt = {'docx': 'docx', 'md': 'markdown', 'html': 'html5'}[p['format']]
    style = BASE / 'styles' / (('zh-note' if p['locale'] == 'zh-CN' else 'en-note') + '.csl') if p['style'] == 'note' else BASE / 'styles' / 'author-date.csl'
    with tempfile.TemporaryDirectory(prefix='scriptorium-export-') as temp:
        output = Path(temp) / ('manuscript.' + p['format'])
        result = subprocess.run([str(binary), '--from=json', '--to=' + fmt, '--standalone', '--citeproc', '--csl=' + str(style), '--output=' + str(output)], input=json.dumps(ast, ensure_ascii=False).encode(), capture_output=True, check=False, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ResearchError('DOCUMENT_EXPORT_FAILED', 422)
        key, _ = s.objects.put(output.read_bytes())
    with s.engine.begin() as c:
        s.access(c, pid, actor); s.locked_job(c, job)
        current = row(c, db.records, db.records.c.id == record['id'], db.records.c.project_id == pid)
        if not current:
            raise ResearchError('SOURCE_NO_LONGER_AVAILABLE', 404)
        for document in [record, *chapters]:
            s.validate_evidence(c, pid, document['payload'])
        from .governance import audit
        audit(c, pid, actor, 'artifact.exported', record['id'], {'format': p['format'], 'revision': record['revision']})
        s.finish(c, job, {'object_key': key, 'filename': 'manuscript.' + p['format'], 'revision': record['revision'], 'record_id': record['id'], 'format': p['format'], 'chapter_revisions': {ch['id']: ch['revision'] for ch in chapters}, 'created_at': db.now()})
