"""Compose current arguments, keeping superseded interpretations in the run history."""
from .documents import markdown


def assemble(question, reports, steps, mode):
    by_id = {r['id']: r for r in reports}
    current, background, audit = {}, [], []
    for step in sorted(steps, key=lambda x: x['step_key']):
        record = by_id.get((step.get('result') or {}).get('record_id'))
        if not record:
            continue
        p, data = step['payload'], record['payload']
        if p['method_id'] == 'review.v1':
            audit.append(record)
        elif p['method_id'] == 'situating.v1':
            background.append(record)
        else:
            batch = p.get('windows') or [p['window']]
            identity = tuple((w['segment_id'], w['start'], w['end']) for w in batch)
            key = (p.get('question', question), identity,
                   'explanation' if p['method_id'] == 'revision.v1' else p['method_id'])
            if p['method_id'] == 'revision.v1':
                for previous in [k for k in current if k[0] == key[0] and k[1] == key[1]]:
                    current.pop(previous)
            current[key] = record
    content = []
    def text(value):
        return {'type': 'text', 'text': value}
    def heading(value):
        content.append({'type': 'heading', 'attrs': {'level': 2}, 'content': [text(value)]})
    def paragraph(value, refs=()):
        content.append({'type': 'paragraph', 'content': [text(value)] + [
            {'type': 'citation', 'attrs': {'anchorId': ref}} for ref in refs]})
    heading('研究问题')
    paragraph(question)
    if mode == 'demo':
        paragraph('演示结果，仅验证流程，不构成学术结论。')
    heading('材料与构境')
    for record in background:
        paragraph(record['payload'].get('text', ''), record['payload'].get('evidence_ids', []))
    heading('当前解释与论证')
    chosen = list(current.values())
    for record in chosen:
        data = record['payload']
        paragraph(data.get('text', ''), data.get('evidence_ids', []))
        for finding in data.get('findings', []):
            paragraph(finding['title'] + '：' + finding['text'], finding.get('evidence_ids', []))
    if not chosen:
        paragraph('本轮未形成独立论点；构境与材料观察保留为候选。')
    heading('反例与审查')
    for record in audit:
        for finding in record['payload'].get('findings', []):
            paragraph(finding['title'] + '：' + finding['text'], finding.get('evidence_ids', []))
    questions = list(dict.fromkeys(q for r in reports for q in r['payload'].get('open_questions', [])))
    heading('覆盖限制与未决问题')
    paragraph('仅涵盖本次固定材料范围；引用可定位与论证是否成立须分别评议。')
    for q in questions:
        paragraph(q)
    editor = {'type': 'doc', 'content': content}
    return {'editor_json': editor, 'text': markdown(editor), 'open_questions': questions,
            'current_record_ids': [r['id'] for r in chosen],
            'historical_record_ids': [r['id'] for r in reports if r not in chosen]}
