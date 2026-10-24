"""Run the eight academic-quality cases (Q-01…Q-08) through the unified research pipeline.

Two modes:
  --mode demo   deterministic demo provider: validates the harness plumbing only, produces no
                academic conclusion (the acceptance document forbids using demo output as evidence)
  --mode live   calls the configured provider; requires DASHSCOPE_API_KEY

The script never decides whether a case passes. It records materials, prompts, method version,
model, coverage, evidence anchors and proposals, runs the objective checks it can (citation,
coverage, provenance, export), and writes a review sheet whose verdict is left blank for the
researcher.

    $env:SCRIPTORIUM_DATABASE_URL = 'postgresql+psycopg://.../scriptorium_quality'
    python scripts/quality-cases.py --mode live
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path


CASES = [
    {
        'id': 'Q-01', 'focus': '同词异义、引述对手及反讽',
        'material': (
            '某作者写道：“自由不过是必然性的认识。”他随即提到对手主张“自由就是不受任何限制”。\n\n'
            '作者本人随后说明：他所说的自由指“在认识必然性之后的自愿行动”，与“不受限制”并非同一概念。\n\n'
            '在同一篇文章里，“自由”还出现在引用黑格尔的段落中，那是被引述的立场，不是作者本人的定义。'),
        'question': '材料中“自由”一词有哪几种不同用法？作者接受哪一种？',
        'methods': ['situating.v1'],
        'expect': '区分概念用途、说话者与引述归属',
        'fail': '仅凭相同词形把不同概念合并，或把论敌引语当作作者立场',
    },
    {
        'id': 'Q-02', 'focus': '背景材料不足',
        'material': (
            '这份笔记只写下一句话：“实践是把观念变成现实的活动。”没有出处、时期、作者与论辩对象。\n\n'
            '笔记末尾有一处残缺：“参见 19 世——”之后内容缺失。'),
        'question': '这句话属于什么思想脉络？它的历史实践背景是什么？',
        'methods': ['situating.v1'],
        'expect': '历史实践、话语来源等明确未知；提出补证方向和竞争档案',
        'fail': '编造时期、来源或思想影响',
    },
    {
        'id': 'Q-03', 'focus': '无有效内在矛盾',
        'material': (
            '该立场主张：判断一个行为是否正当，只需看它是否遵守事先公布的规则。\n\n'
            '它同时规定：规则必须能被所有受影响者接受。文本中没有出现与这两条相冲突的进一步规定。'),
        'question': '这一立场自身是否存在必须被克服的内在困难？',
        'methods': ['immanent_critique.v1'],
        'expect': '按立场自身尺度检验，允许停止和无合理转化',
        'fail': '为完成流程制造“正反合”或强制生成转化',
    },
    {
        'id': 'Q-04', 'focus': '外部批评、经验反例与内部困难并存',
        'material': (
            '研究者记录：某理论认为“所有承认都产生于相互依赖”。\n\n'
            '（一）外部批评：有学者认为该理论忽视了权力不对称。\n'
            '（二）经验反例：材料记载一个完全孤立的个体仍获得自我承认。\n'
            '（三）内部困难：该理论同时要求承认先于个体，又要求个体先于承认。'),
        'question': '这些批评中，哪一项构成该理论按自身尺度的困难？',
        'methods': ['immanent_critique.v1'],
        'expect': '分类准确；转化说明保留、否定及改变的具体规定',
        'fail': '把任何反例都称作规定性否定',
    },
    {
        'id': 'Q-05', 'focus': '事实、术语或时期差异可以消解',
        'material': (
            '甲文（1900 年）把“共同体”理解为血缘村落；乙文（1990 年）把“共同体”理解为自愿结成的协会。\n\n'
            '两文的作者从未互相批评，讨论对象也不同：一个是乡村治理，一个是城市社团。'),
        'question': '这两处“共同体”用法是否构成不可化约的视差？',
        'methods': ['parallax.v1'],
        'expect': '先消解差异，保留 difference_only／resolvable 等结论',
        'fail': '将普通意见不同自动升级为不可化约视差',
    },
    {
        'id': 'Q-06', 'focus': '确有不同观察位置和对象位移',
        'material': (
            '同一座桥：工程师的记录把它描述为受力结构，附近居民的记录把它描述为通往集市的必经之路。\n\n'
            '两份记录都没有事实错误；工程师在检测报告中说明自己只关心承载，居民在访谈中说明自己只关心通行。'),
        'question': '两种记录之间是否存在由观察位置造成的对象位移？',
        'methods': ['parallax.v1'],
        'expect': '说明位置条件、对象显现、位移、裂隙假说及反驳条件',
        'fail': '只列两种意见，或宣称证明最终不可化约',
    },
    {
        'id': 'Q-07', 'focus': '原文反例与覆盖遗漏',
        'material': (
            '一份解释草稿声称：该文本从未承认国家在福利供给中的作用。\n\n'
            '然而同一文本第三节写道：“国家必须承担最基本的供给责任，否则市场无从稳定。”\n\n'
            '该草稿还遗漏了第五节关于地方社团的整段讨论。'),
        'question': '请检查“从未承认国家作用”这一解释，并指出原文反例。',
        'methods': ['review.v1'],
        'expect': '返回具体原文，修订结论并公开未覆盖材料',
        'fail': '只批评摘要，或把未读部分算作已处理',
    },
    {
        'id': 'Q-08', 'focus': '从解释到论证和文稿',
        'material': (
            '文本甲：制度要求参与者说明理由。\n\n'
            '文本乙：同一制度又规定，说明理由不得被用作申辩依据。\n\n'
            '文本丙（附录）：起草者承认这两条存在张力，但未说明如何处理。'),
        'question': '这一制度设计内部存在什么困难？能否支持一个可反驳的论证？',
        'methods': ['situating.v1', 'immanent_critique.v1', 'parallax.v1'],
        'expect': '每项关键事实可定位；区分引文存在与引文支持论点；修订可追溯',
        'fail': '可定位引文被当作充分论证，或文稿包含无来源的确定性判断',
    },
]


def service_for(database_url: str, object_root: Path, es_url: str):
    from dataclasses import replace

    from scriptorium.research import schema as db
    from scriptorium.research.config import ResearchSettings
    from scriptorium.research.service import ResearchService
    settings = replace(ResearchSettings.from_env(), database_url=database_url, object_root=object_root,
                       elasticsearch_url=es_url, principal='quality-reviewer')
    engine = db.engine_for(database_url)
    return ResearchService(engine, settings), engine


def drain(service, limit=200):
    from scriptorium.research.worker import run_one
    processed = 0
    while processed < limit and run_one(service):
        processed += 1
    return processed


def run_case(service, case, mode, out: Path):
    from scriptorium.research.workspace import create_conversation, submit

    principal = 'quality-reviewer'
    project = service.create_project(principal, f"质量案例 {case['id']}", case['focus'])
    material = f"# {case['id']} {case['focus']}\n\n{case['material']}\n".encode()
    job = service.import_material(project['id'], principal, material, f"{case['id']}.md", f"{case['id']}-material")
    drain(service)
    asset_id = job['payload']['asset_id']
    conversation = create_conversation(service, project['id'], principal, f"{case['id']} 案例")
    body = {'text': case['question'], 'tool': 'research', 'asset_ids': [asset_id], 'segment_ids': [],
            'provider_mode': mode, 'methods': case['methods'], 'token_budget': 40000,
            'conversation_id': conversation['id'], 'principal': principal}
    submitted = submit(service, project['id'], principal, conversation['id'], body, f"{case['id']}-run")
    drain(service)
    return collect_case(service, case, mode, out, project['id'], asset_id, conversation['id'], submitted['id'])


def collect_case(service, case, mode, out, project_id, asset_id, conversation_id, job_id):
    from scriptorium.research import schema as db
    from scriptorium.research.service import rows
    project = {'id': project_id}
    material = f"# {case['id']} {case['focus']}\n\n{case['material']}\n".encode()
    with service.engine.connect() as c:
        runs = rows(c, db.research_runs, db.research_runs.c.project_id == project['id'])
        records = rows(c, db.records, db.records.c.project_id == project['id'])
        anchors = rows(c, db.anchors, db.anchors.c.project_id == project['id'])
        segments = rows(c, db.segments, db.segments.c.project_id == project['id'])
        run = runs[-1] if runs else {}
        steps = rows(c, db.research_steps, db.research_steps.c.run_id == run.get('id')) if run else []
    anchor_map = {a['id']: a for a in anchors}
    segment_map = {s['id']: s for s in segments}

    checks = {}
    evidence_items, broken = 0, []
    for record in records:
        payload = record['payload']
        ids = list(payload.get('evidence_ids', []))
        for finding in payload.get('findings', []) or []:
            ids.extend(finding.get('evidence_ids', []))
            if finding.get('claim_type') in {'fact', 'quotation'} and not finding.get('evidence_ids'):
                broken.append({'record': record['id'], 'reason': 'FACT_WITHOUT_CITATION', 'title': finding.get('title')})
        for anchor_id in ids:
            evidence_items += 1
            anchor = anchor_map.get(anchor_id)
            segment = segment_map.get(anchor['segment_id']) if anchor else None
            if not anchor or not segment:
                broken.append({'record': record['id'], 'reason': 'ANCHOR_MISSING', 'anchor': anchor_id})
            elif segment['text'][anchor['start_codepoint']:anchor['end_codepoint']] != anchor['exact_quote']:
                broken.append({'record': record['id'], 'reason': 'QUOTE_MISMATCH', 'anchor': anchor_id})
    checks['evidence_anchors_located'] = evidence_items - len([b for b in broken if b['reason'] != 'FACT_WITHOUT_CITATION'])
    checks['evidence_problems'] = broken
    checks['coverage_recorded'] = any(r['payload'].get('coverage') for r in records)
    checks['provider_mode_stamped'] = all(r['payload'].get('provider_mode') == mode for r in records if r['kind'] in {'method_report', 'context'})
    checks['method_sources_present'] = all(r['payload'].get('method_source') for r in records
                                           if r['kind'] in {'method_report', 'context'})
    checks['run_state'] = run.get('state')
    checks['steps'] = len(steps)

    case_dir = out / case['id']
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / 'material.md').write_text(material.decode('utf-8'), encoding='utf-8')
    payload = {
        'case': case, 'mode': mode, 'project_id': project['id'], 'asset_id': asset_id,
        'conversation_id': conversation_id, 'job_id': job_id, 'run_id': run.get('id'),
        'run': run, 'records': [{k: record[k] for k in ('id', 'kind', 'revision', 'payload')} for record in records],
        'anchors': anchors, 'mechanical_checks': checks,
        'review': {'verdict': '', 'reasons': '', 'material_locations': '', 'reviewer': '', 'reviewed_at': ''},
    }
    (case_dir / 'packet.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['demo', 'live'], default='demo')
    parser.add_argument('--out', default='')
    parser.add_argument('--only', default='', help='comma separated case ids, e.g. Q-01,Q-03')
    args = parser.parse_args()

    database_url = os.getenv('SCRIPTORIUM_DATABASE_URL', '')
    if not database_url.startswith('postgresql+psycopg://'):
        print(json.dumps({'error': 'SCRIPTORIUM_DATABASE_URL must point at a dedicated PostgreSQL database'}, ensure_ascii=False))
        return 2
    if args.mode == 'live' and not os.getenv('DASHSCOPE_API_KEY'):
        print(json.dumps({'error': 'MODEL_NOT_CONFIGURED: set DASHSCOPE_API_KEY for --mode live; '
                                   'demo output can never serve as academic evidence'}, ensure_ascii=False))
        return 2

    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    out = Path(args.out or f'output/quality-cases/{stamp}-{args.mode}')
    out.mkdir(parents=True, exist_ok=True)
    object_root = Path(os.getenv('SCRIPTORIUM_OBJECT_ROOT', './data/research-objects'))
    es_url = os.getenv('SCRIPTORIUM_ELASTICSEARCH_URL', 'http://127.0.0.1:9200')
    service, engine = service_for(database_url, object_root, es_url)
    selected = [case for case in CASES if not args.only or case['id'] in {x.strip().upper() for x in args.only.split(',')}]
    packets = []
    try:
        for case in selected:
            packet = run_case(service, case, args.mode, out)
            packets.append(packet)
            print(json.dumps({'case': case['id'], 'run': packet['mechanical_checks']['run_state'],
                              'evidence_problems': len(packet['mechanical_checks']['evidence_problems'])}, ensure_ascii=False))
    finally:
        engine.dispose()

    lines = ['# 学术质量案例评议表', '',
             f'- 运行：`{stamp}`　模式：`{args.mode}`', f'- 数据库：`{__import__("scriptorium.research.config",fromlist=["redacted_service_url"]).redacted_service_url(database_url)}`',
             '- 说明：机械检查只证明引文可定位、覆盖已记录、来源已标注；判断是否成立必须由研究者签认。', '',
             '| 编号 | 关注点 | 应观察到 | 判为失败的情况 | 机械检查 | 结论（通过/需修订/不通过） | 理由与材料位置 |',
             '|---|---|---|---|---|---|---|']
    for packet in packets:
        checks = packet['mechanical_checks']
        mechanical = (f"证据异常 {len(checks['evidence_problems'])}；覆盖记录 {'有' if checks['coverage_recorded'] else '无'}；"
                      f"来源标注 {'有' if checks['method_sources_present'] else '无'}；run={checks['run_state']}")
        case = packet['case']
        lines.append(f"| {case['id']} | {case['focus']} | {case['expect']} | {case['fail']} | {mechanical} |  |  |")
    lines += ['', '每个案例的完整产物见 `<case>/packet.json`，材料见 `<case>/material.md`。', '']
    (out / 'review.md').write_text('\n'.join(lines), encoding='utf-8')
    (out / 'run.json').write_text(json.dumps({'mode': args.mode, 'database': __import__('scriptorium.research.config',fromlist=['redacted_service_url']).redacted_service_url(database_url),
        'cases': [p['case']['id'] for p in packets], 'review_sheet': str(out / 'review.md')},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'out': str(out), 'cases': len(packets), 'review': str(out / 'review.md')}, ensure_ascii=False))
    return 0 if packets and all(p['mechanical_checks']['run_state']=='completed_with_open_questions' and not p['mechanical_checks']['evidence_problems'] and p['records'] for p in packets) else 1


if __name__ == '__main__':
    raise SystemExit(main())
