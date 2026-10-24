"""Interactive terminal UI — Lacanian aesthetic.

Design: Borromean RSI color coding, matheme decorations,
scholarly dark palette with gold (objet petit a) accents.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .behavioral import SubjectProfiler
from .behavioral.models import ProfileArtifact
from .cli import _ensure_project, _source_for
from .db import Store
from .models import ConsentScope, Participant, ReviewRequest
from .rag import ingest, search
from .workflow import Workflow

# ─── Color Palette ────────────────────────────────────────────────
# Lacan's three registers + scholarly accents
_NO_COLOR = os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb"

if _NO_COLOR:
    class _C:
        def __getattr__(self, _): return ""
    C = _C()
else:
    class _C:
        R = "\033[0m"        # reset
        B = "\033[1m"        # bold
        D = "\033[2m"        # dim
        I = "\033[3m"        # italic

        # The Symbolic — structure, language, law (steel blue)
        SY = "\033[38;5;67m"
        SY_D = "\033[38;5;60m"

        # The Imaginary — image, reflection, ego (soft violet)
        IM = "\033[38;5;139m"
        IM_D = "\033[38;5;96m"

        # The Real — that which resists symbolization (burnt gold)
        RE = "\033[38;5;216m"
        RE_D = "\033[38;5;180m"

        # Surface tones
        TX = "\033[38;5;252m"   # primary text
        TX_D = "\033[38;5;243m" # dim text
        LN = "\033[38;5;238m"   # lines / borders
        BK = "\033[38;5;234m"   # near-black bg hint

        # Status
        OK = "\033[38;5;114m"   # green
        WN = "\033[38;5;216m"   # amber
        ER = "\033[38;5;203m"   # red
        CY = "\033[38;5;116m"   # cyan
    C = _C()

# ─── Decorative Primitives ────────────────────────────────────────

def _borromean() -> str:
    """Three interlocking rings — the Borromean knot of RⓈⒾ."""
    return f"""\
{C.RE}       ◊{C.R}
{C.RE}      ╱ ╲{C.R}    {C.B}{C.TX}╔══════════════════════════════════════════════════╗{C.R}
{C.RE}     ╱   ╲{C.R}   {C.TX}║{C.R}                                                  {C.TX}║{C.R}
{C.RE}     ╲   ╱{C.R}   {C.TX}║{C.R}  {C.B}L A C A N  ·  A G E N T{C.R}                          {C.TX}║{C.R}
{C.RE}      ╲ ╱{C.R}    {C.TX}║{C.R}  {C.D}Evidence-Constrained Psychoanalytic Research{C.R}    {C.TX}║{C.R}
{C.RE}       ◊{C.R}     {C.TX}║{C.R}  {C.D}「 Le séminaire est le lieu... 」{C.R}               {C.TX}║{C.R}
{C.IM}      ╱ ╲{C.R}    {C.TX}║{C.R}                                                  {C.TX}║{C.R}
{C.IM}     ╱   ╲{C.R}   {C.TX}╚══════════════════════════════════════════════════╝{C.R}
{C.IM}     ◊───◊{C.R}
{C.IM}      ╱ ╲{C.R}    {C.SY}{C.D}R · S · I{C.R}   {C.D}Real · Symbolic · Imaginary{C.R}
{C.IM}     ╱   ╲{C.R}
{C.SY}     ◊   ◊{C.R}"""


def _divider(title: str = "") -> str:
    if title:
        pad = max(0, 56 - len(title))
        left = pad // 2
        right = pad - left
        return f"  {C.LN}{'─' * left}◈{C.R} {C.D}{title}{C.R} {C.LN}◈{'─' * right}{C.R}"
    return f"  {C.LN}{'─' * 60}{C.R}"


def _menu_row(num: str, label: str, latin: str = "", color: str = "") -> str:
    c = color or C.SY
    lat = f"  {C.D}{C.I}{latin}{C.R}" if latin else ""
    return f"  {c}{C.B}{num}{C.R}  {C.TX}{label}{C.R}{lat}"


def _matheme(symbol: str, label: str) -> str:
    return f"  {C.RE}{C.B}{symbol}{C.R} {C.D}{label}{C.R}"


def _status_dot(state: str) -> str:
    s = state.upper() if state else ""
    if s in ("APPROVED", "COMPILED"):
        return f"{C.OK}●{C.R} {C.TX}{state}{C.R}"
    if s in ("FAILED", "CANCELLED"):
        return f"{C.ER}●{C.R} {C.TX}{state}{C.R}"
    if s == "NEEDS_HUMAN_REVIEW":
        return f"{C.WN}◐{C.R} {C.TX}{state}{C.R}"
    if s in ("REVISION_REQUIRED",):
        return f"{C.WN}○{C.R} {C.TX}{state}{C.R}"
    return f"{C.SY}○{C.R} {C.D}{state}{C.R}"


def _workflow_bar(state: str) -> str:
    """Visual workflow progression."""
    stages = [
        ("CREATED", "∅"),
        ("INGESTED", "⊂"),
        ("OBSERVED", "⊃"),
        ("INTERPRETED", "◊"),
        ("CRITIQUED", "⊗"),
        ("NEEDS_HUMAN_REVIEW", "⊕"),
        ("APPROVED", "✓"),
        ("COMPILED", "∞"),
    ]
    current = state.upper() if state else ""
    try:
        idx = [s[0] for s in stages].index(current)
    except ValueError:
        idx = -1

    parts = []
    for i, (name, sym) in enumerate(stages):
        if i < idx:
            parts.append(f"{C.SY_D}{sym}{C.R}")
        elif i == idx:
            parts.append(f"{C.RE}{C.B}{sym}{C.R}")
        else:
            parts.append(f"{C.LN}{sym}{C.R}")
        if i < len(stages) - 1:
            parts.append(f"{C.LN}─{C.R}" if i < idx else f"{C.LN}·{C.R}")
    return "  " + "".join(parts)


def _box(lines: list[str]) -> str:
    """Wrap lines in an elegant box."""
    w = max(len(_strip_ansi(l)) for l in lines) if lines else 40
    w = min(w, 72)
    out = [f"  {C.LN}╭{'─' * (w + 2)}╮{C.R}"]
    for l in lines:
        pad = w - len(_strip_ansi(l))
        out.append(f"  {C.LN}│{C.R} {l}{' ' * max(0, pad)} {C.LN}│{C.R}")
    out.append(f"  {C.LN}╰{'─' * (w + 2)}╯{C.R}")
    return "\n".join(out)


def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)


# ─── Interaction Helpers ──────────────────────────────────────────

def _ask(label: str, default: str | None = None) -> str:
    suffix = f" {C.D}[{default}]{C.R}" if default else ""
    value = input(f"  {C.SY}›{C.R} {C.TX}{label}{C.R}{suffix} {C.SY}›{C.R} ").strip()
    return value or (default or "")


def _yes(label: str, default: bool = False) -> bool:
    hint = f"{C.OK}Y{C.R}/{C.D}n{C.R}" if default else f"{C.D}y{C.R}/{C.ER}N{C.R}"
    value = input(f"  {C.WN}?{C.R} {C.TX}{label}{C.R} ({hint}) {C.SY}›{C.R} ").strip().lower()
    return default if not value else value in {"y", "yes", "是", "好"}


def _show(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    lines = [f"{C.D}{line}{C.R}" for line in text.split("\n")]
    print()
    print(_box(lines))


def _pause() -> None:
    input(f"\n  {C.D}── press enter to continue ──{C.R}")


def _clear():
    print("\033[2J\033[H", end="")


def _header():
    _clear()
    print()
    print(_borromean())
    print()


# ─── Main Loop ────────────────────────────────────────────────────

def run_interactive(db_path: str) -> int:
    store = Store(db_path)
    flow = Workflow(store)

    _header()
    print(_matheme("𝔻", f"database  {C.TX}{Path(db_path).resolve()}{C.R}"))
    print(_matheme("𝕄", f"mode      {C.TX}local mock · no external LLM{C.R}"))
    print(_matheme("⚠", f"{C.WN}research tool only · not clinical diagnosis{C.R}"))
    print()

    while True:
        print(_divider("OPERATIONS"))
        print()

        # ── The Symbolic ──
        print(f"  {C.SY}{C.B}━━━ THE SYMBOLIC ━━━{C.R}  {C.D}structure · language · law{C.R}")
        print()
        print(_menu_row(" 1", "初始化项目", "Initium", C.SY))
        print(_menu_row(" 2", "导入理论文献", "Ingestio Theoriae", C.SY))
        print(_menu_row(" 3", "检索理论文献", "Quaestio", C.SY))
        print()

        # ── The Imaginary ──
        print(f"  {C.IM}{C.B}━━━ THE IMAGINARY ━━━{C.R}  {C.D}image · reflection · subject{C.R}")
        print()
        print(_menu_row(" 4", "添加参与者与授权", "Constitutio Subjecti", C.IM))
        print(_menu_row(" 5", "导入参与者文本", "Importio Textus", C.IM))
        print()

        # ── The Real ──
        print(f"  {C.RE}{C.B}━━━ THE REAL ━━━━━━━{C.R}  {C.D}that which resists symbolization{C.R}")
        print()
        print(_menu_row(" 6", "启动分析", "Analysis", C.RE))
        print(_menu_row(" 7", "查看运行状态", "Status", C.RE))
        print(_menu_row(" 8", "人工审核", "Recensio", C.RE))
        print(_menu_row(" 9", "导出结果", "Exportatio", C.RE))
        print()

        # ── Exit / Withdraw ──
        print(f"  {C.LN}────────────────────────────────────────────────────────────{C.R}")
        print()
        print(_menu_row("10", "撤回参与者", "Revocatio", C.WN))
        print(_menu_row("11", "构建主体结构画像", "Structura Subjecti", C.IM))
        print(_menu_row("12", "查看主体结构画像", "Inspectio Subjecti", C.IM))
        print(_menu_row("13", "审核结构候选", "Recensio Structurae", C.WN))
        print(_menu_row(" 0", "退出", "Finis", C.D))
        print()

        choice = input(f"  {C.RE}◊{C.R} {C.TX}选择{C.R} {C.D}[0-13]{C.R} {C.SY}›{C.R} ").strip()

        try:
            if choice == "0":
                print()
                print(f"  {C.D}{'─' * 50}{C.R}")
                print(f"  {C.RE}◊{C.R} {C.D}{C.I}Finis. The session ends, but the analysis continues elsewhere.{C.R}")
                print(f"  {C.D}{'─' * 50}{C.R}")
                print()
                return 0

            if choice == "1":
                print(f"\n  {C.SY}●{C.R} {C.TX}初始化项目{C.R}")
                project = _ask("项目 ID", "demo")
                result = _ensure_project(store, project).model_dump()
                print(f"  {C.OK}✓{C.R} {C.D}project initialized{C.R}")
                _show(result)

            elif choice == "2":
                print(f"\n  {C.SY}●{C.R} {C.TX}导入理论文献{C.R}")
                project = _ask("项目 ID", "demo")
                _ensure_project(store, project)
                path = _ask("理论文件路径")
                result = ingest(store, path, project).model_dump(exclude={"text"})
                print(f"  {C.OK}✓{C.R} {C.D}theory source ingested{C.R}")
                _show(result)

            elif choice == "3":
                print(f"\n  {C.SY}●{C.R} {C.TX}检索理论文献{C.R}")
                project = _ask("项目 ID", "demo")
                query = _ask("搜索词")
                _show({"items": search(store, query)})

            elif choice == "4":
                print(f"\n  {C.IM}●{C.R} {C.TX}添加参与者与授权{C.R}")
                project = _ask("项目 ID", "demo")
                _ensure_project(store, project)
                participant = _ask("参与者匿名 ID")
                consent_path = _ask("consent.json 路径")
                consent = ConsentScope.model_validate(
                    json.loads(Path(consent_path).read_text(encoding="utf-8"))
                )
                result = store.put_participant(Participant(
                    id=participant, project_id=project,
                    pseudonym=participant, consent_scope=consent
                )).model_dump()
                print(f"  {C.OK}✓{C.R} {C.D}participant registered{C.R}")
                _show(result)

            elif choice == "5":
                print(f"\n  {C.IM}●{C.R} {C.TX}导入参与者文本{C.R}")
                project = _ask("项目 ID", "demo")
                participant = _ask("参与者匿名 ID")
                person = store.get_participant(project, participant)
                if person is None:
                    raise ValueError(f"参与者不存在: {participant}")
                result = ingest(
                    store, _ask("文本文件路径"), project, participant, person.consent_scope
                ).model_dump(exclude={"text"})
                print(f"  {C.OK}✓{C.R} {C.D}source document ingested{C.R}")
                _show(result)

            elif choice == "6":
                print(f"\n  {C.RE}●{C.R} {C.TX}启动分析{C.R}")
                project = _ask("项目 ID", "demo")
                participant = _ask("参与者匿名 ID")
                source = _ask("文本文件名或 document ID")
                person = store.get_participant(project, participant)
                if person is None:
                    raise ValueError(f"参与者不存在: {participant}")
                document = _source_for(store, project, participant, source)
                key = _ask("幂等键", "interactive-run")
                run = flow.run(project, participant, [document.id], key)
                print(f"  {C.OK}✓{C.R} {C.D}analysis complete{C.R}")
                print()
                print(f"  {_status_dot(run.state)}")
                print(_workflow_bar(run.state))
                _show({"run_id": run.id, "state": run.state})

            elif choice == "7":
                print(f"\n  {C.RE}●{C.R} {C.TX}查看运行状态{C.R}")
                run_id = _ask("运行 ID")
                run = store.get_run(run_id)
                if run is None:
                    raise ValueError("运行不存在")
                print()
                print(f"  {_status_dot(run.state)}")
                print(_workflow_bar(run.state))
                _show(run.model_dump(mode="json"))

            elif choice == "8":
                print(f"\n  {C.RE}●{C.R} {C.TX}人工审核{C.R}")
                run_id = _ask("运行 ID")
                decision = _ask("审核决定 (approve/reject/revise)", "approve")
                reviewer = _ask("审核者 ID", "reviewer-1")
                reason = _ask("审核理由", "")
                result = flow.review(
                    run_id, ReviewRequest(
                        reviewer_id=reviewer, decision=decision, reason=reason
                    )
                ).model_dump(mode="json")
                print(f"  {C.OK}✓{C.R} {C.D}review recorded{C.R}")
                _show(result)

            elif choice == "9":
                print(f"\n  {C.RE}●{C.R} {C.TX}导出结果{C.R}")
                run_id = _ask("运行 ID")
                output = _ask("输出 JSON 路径", f"./data/{run_id}-export.json")
                result = flow.export(run_id)
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"  {C.OK}✓{C.R} {C.D}exported to{C.R} {C.TX}{Path(output).resolve()}{C.R}")

            elif choice == "10":
                print(f"\n  {C.WN}●{C.R} {C.TX}撤回参与者{C.R}")
                project = _ask("项目 ID", "demo")
                participant = _ask("参与者匿名 ID")
                if not _yes("确认撤回并阻止后续分析", False):
                    print(f"  {C.D}已取消{C.R}")
                else:
                    person = store.withdraw(project, participant)
                    if person is None:
                        raise ValueError(f"参与者不存在: {participant}")
                    print(f"  {C.WN}✓{C.R} {C.D}参与者 {C.TX}{participant}{C.D} 已进入撤回状态{C.R}")

            elif choice == "11":
                print(f"\n  {C.IM}●{C.R} {C.TX}构建主体结构画像{C.R}")
                participant = _ask("参与者 ID")
                sources = _ask("sources.json 路径")
                root = _ask("材料根目录", str(Path(sources).resolve().parent))
                cards_dir = _ask("画像输出目录", "./data/subject-artifacts")
                artifact = SubjectProfiler(sources, root=root).build(participant)
                out = Path(cards_dir) / f"{participant}.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
                print(f"  {C.OK}✓{C.R} {C.D}主体画像已生成：{C.TX}{out.resolve()}{C.R}")
                _show({
                    "participant": participant,
                    "sources": len(artifact.source_manifest),
                    "spans": artifact.quality.get("sample_size", 0),
                    "candidate_claims": len(artifact.structural_claims),
                    "review_state": artifact.review_state,
                })

            elif choice == "12":
                print(f"\n  {C.IM}●{C.R} {C.TX}查看主体结构画像{C.R}")
                participant = _ask("参与者 ID")
                cards_dir = _ask("画像目录", "./data/subject-artifacts")
                path = Path(cards_dir) / f"{participant}.json"
                artifact = json.loads(path.read_text(encoding="utf-8"))
                claims = artifact.get("structural_claims", [])
                _show({
                    "participant": artifact.get("participant_id"),
                    "sources": artifact.get("source_profiles", {}),
                    "claims": [{
                        "id": c.get("claim_id"), "dimension": c.get("dimension"),
                        "text": c.get("text"), "confidence": c.get("confidence"),
                        "status": c.get("status"), "evidence": len(c.get("evidence_span_ids", [])),
                    } for c in claims],
                    "review_state": artifact.get("review_state"),
                })

            elif choice == "13":
                print(f"\n  {C.WN}●{C.R} {C.TX}审核结构候选{C.R}")
                participant = _ask("参与者 ID")
                cards_dir = _ask("画像目录", "./data/subject-artifacts")
                review_path = _ask("审核 JSON 路径")
                path = Path(cards_dir) / f"{participant}.json"
                artifact = ProfileArtifact.model_validate_json(path.read_text(encoding="utf-8"))
                review = json.loads(Path(review_path).read_text(encoding="utf-8"))
                artifact = SubjectProfiler.apply_review(artifact, review)
                path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
                print(f"  {C.OK}✓{C.R} {C.D}审核已保存，状态：{C.TX}{artifact.review_state}{C.R}")

            else:
                print(f"  {C.ER}✗{C.R} {C.D}请输入 0 到 13{C.R}")

        except (OSError, ValueError, KeyError, PermissionError) as exc:
            print(f"\n  {C.ER}✗ 操作失败{C.R}  {C.D}{exc}{C.R}")

        if choice != "0":
            _pause()
            _header()
            print(_matheme("𝔻", f"database  {C.TX}{Path(db_path).resolve()}{C.R}"))
            print(_matheme("𝕄", f"mode      {C.TX}local mock · no external LLM{C.R}"))
            print(_matheme("⚠", f"{C.WN}research tool only · not clinical diagnosis{C.R}"))
            print()
