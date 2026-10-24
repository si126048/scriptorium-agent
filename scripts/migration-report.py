"""Turn migration and anchor-verification reports into a reviewable switch-rehearsal summary.

    python scripts/migration-report.py --apply output/switch-rehearsal/apply.json \
        --anchors output/switch-rehearsal/anchors.json --out output/switch-rehearsal/report.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

MATERIAL_STATES = ('succeeded', 'failed', 'skipped')


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', type=Path, required=True)
    parser.add_argument('--anchors', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    report = load(args.apply)
    lines = ['# 迁移演练报告', '',
             f"- 源快照：`{report.get('source_id', '')}`",
             f"- 快照指纹：`{report.get('snapshot_sha256', '')}`",
             f"- 干跑：`{report.get('dry_run')}`", '']
    tables = report.get('tables', {})
    lines += ['## 源记录', '', '| 表 | 行数 |', '|---|---|']
    lines += [f'| {name} | {count} |' for name, count in sorted(tables.items())]
    lines += ['', f"合计：{sum(tables.values())} 行", '']

    lines += ['## 去向', '',
              f"- 本次新保存原始记录：{report.get('preserved', 0)}",
              f"- 已存在原始记录：{report.get('already_present', 0)}",
              f"- 新增可操作业务实体：{report.get('operational_entities', 0)}",
              f"- 新增映射锚点：{report.get('anchors_migrated', 0)}",
              f"- 项目映射：{len(report.get('project_map', {}))} 个", '']

    materials = report.get('materials', [])
    if materials:
        states = Counter(item.get('status') for item in materials)
        lines += ['## 材料', '', f"共 {len(materials)} 份：", '']
        lines += [f'- {state}：{count}' for state, count in sorted(states.items())]
        originals = Counter(item.get('origin_status') for item in materials)
        lines += ['', '原件状态：', '']
        lines += [f'- {key}：{value}' for key, value in sorted(originals.items())]
        missing = [item for item in materials if item.get('origin_status') != 'original_retained']
        if missing:
            lines += ['', f'其中 {len(missing)} 份使用存量文本或兼容档案，不视为已恢复原件；'
                          '原件状态继续显示，正式切换前需逐项确认处理方式。']
        lines += ['']

    exceptions = report.get('exceptions', [])
    reasons = Counter(item.get('reason', 'UNKNOWN') for item in exceptions)
    lines += ['## 异常分类（MIG-02）', '', f"共 {len(exceptions)} 条：", '',
              '| 原因 | 数量 | 处理要求 |', '|---|---|---|']
    guidance = {
        'MISSING_ORIGINAL': '原件缺失；保留存量文本，原件状态必须继续显示，不得称为已恢复原件',
        'AMBIGUOUS_OR_MISSING_QUOTE': '无法唯一定位；保留为未核验，禁止批量猜测位置',
        'UNSUPPORTED_FORMAT': '格式不可重解析；保留兼容档案，原件仍可下载',
        'PARTICIPANT_CONSENT_INACTIVE': '授权失效或撤回；阻断相关参与者派生内容，无关合法材料可继续',
        'UNKNOWN_PROJECT': '归属不明；单列待研究者确认，不并入其他项目',
    }
    lines += [f'| {reason} | {count} | {guidance.get(reason, "需研究者逐条审阅")} |' for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1])]
    samples: dict[str, list] = defaultdict(list)
    for item in exceptions:
        samples[item.get('reason', 'UNKNOWN')].append(item)
    for reason, items in sorted(samples.items(), key=lambda kv: -len(kv[1])):
        lines += ['', f'### {reason}（示例 {min(5, len(items))} 条）', '']
        for item in items[:5]:
            key = item.get('key') or item.get('legacy_key') or item.get('id')
            table = item.get('table') or ''
            lines += [f"- `{table}:{key}`"]
    lines += ['']

    if args.anchors and args.anchors.exists():
        anchors = load(args.anchors)
        problems = anchors.get('problems', [])
        problem_reasons = Counter(item.get('reason') for item in problems)
        lines += ['## 引用重核（切换检查表：已核验引用必须全部可定位）', '',
                  f"- 锚点总数：{anchors.get('anchors_total')}",
                  f"- 可定位：{anchors.get('located')}",
                  f"- 异常：{anchors.get('problem_count')}",
                  f"- 报告截断：{anchors.get('truncated')}", '']
        if problem_reasons:
            lines += ['| 异常原因 | 数量 |', '|---|---|']
            lines += [f'| {reason} | {count} |' for reason, count in problem_reasons.most_common()]
        else:
            lines += ['全部锚点均可定位。']
        lines += ['']

    lines += ['## 解释边界', '',
              '- “已说明去向”不等于每条数据都可操作或引用已定位。',
              '- 原件缺失时恢复的文本不等于恢复原始文件。',
              '- 本次演练不执行正式停写与切换；源库仍以冻结快照为准。',
              '- 画像分析业务状态不要求等价迁移（用户决定 2026-10-24），只保全有授权的研究材料、文本与引用。', '']

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(line for line in lines if line is not None), encoding='utf-8')
    print(json.dumps({'out': str(args.out), 'exceptions': len(exceptions), 'materials': len(materials),
                      'reasons': dict(reasons)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
