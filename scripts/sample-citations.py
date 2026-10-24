"""Draw a reviewer sampling list from migrated evidence anchors.

The switch checklist requires a human spot-check of migrated citations. This prints a stable
sample (ordered by anchor id) with project, material, page label, code-point range and quote,
and re-verifies each one against the immutable text so the reviewer sees failures, not guesses.

    python scripts/sample-citations.py --out output/switch-rehearsal/sampling.md --count 20
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import sqlalchemy as sa

from hermeneut.research import schema as db
from hermeneut.research.config import ResearchSettings
from hermeneut.research.service import ResearchService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--database-url', default=os.getenv('HERMENEUT_DATABASE_URL', ''))
    args = parser.parse_args()
    if not args.database_url.startswith('postgresql+psycopg://'):
        raise SystemExit('HERMENEUT_DATABASE_URL must point at the migrated database')

    service = ResearchService(db.engine_for(args.database_url), ResearchSettings.from_env())
    with service.engine.connect() as c:
        anchors = c.execute(sa.select(db.anchors).order_by(db.anchors.c.id).limit(args.count)).mappings().all()
        rows = []
        for anchor in anchors:
            segment = c.execute(sa.select(db.segments).where(db.segments.c.id == anchor['segment_id'])).mappings().first()
            asset = c.execute(sa.select(db.assets).where(db.assets.c.id == segment['asset_id'])).mappings().first() if segment else None
            project = c.execute(sa.select(db.projects).where(db.projects.c.id == segment['project_id'])).mappings().first() if segment else None
            slash = segment['text'][anchor['start_codepoint']:anchor['end_codepoint']] if segment else None
            rows.append({
                'anchor': anchor['id'],
                'project': (project or {}).get('name', ''),
                'material': (asset or {}).get('name', ''),
                'page': segment['page_label'] if segment else '',
                'range': f"{anchor['start_codepoint']}:{anchor['end_codepoint']}",
                'quote': (anchor['exact_quote'] or '')[:120].replace('\n', ' '),
                'located': slash == anchor['exact_quote'],
            })

    lines = ['# 引用抽样核验表', '',
             f'- 数据库：`{args.database_url}`', f'- 抽样数：{len(rows)}（按 anchor id 排序，可复现）',
             '- 说明：`程序核验` 只证明摘录与不可变文本一致；是否支持论证仍需研究者判断。', '',
             '| # | 项目 | 材料 | 页 | 范围 | 摘录 | 程序核验 | 研究者判断 |', '|---|---|---|---|---|---|---|---|']
    for index, row in enumerate(rows, 1):
        lines.append(f"| {index} | {row['project']} | {row['material']} | {row['page']} | {row['range']} | "
                     f"{row['quote']} | {'可定位' if row['located'] else '**不符**'} |  |")
    lines += ['', '复现命令：', '', '```powershell',
              'python scripts/sample-citations.py --count 20 --out output/switch-rehearsal/sampling.md', '```', '']
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'out': str(args.out), 'sampled': len(rows),
                      'all_located': all(row['located'] for row in rows)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
