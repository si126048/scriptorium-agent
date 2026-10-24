"""ACP server — JSON-RPC 2.0 over newline-delimited stdio.

Run: python -m hermeneut.acp [--mock] [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import threading
import uuid
from enum import Enum

from ..db import Store
from ..dialectical import DialecticalWorkflow
from ..models import ConsentScope, Participant, Project
from ..perspectives import list_perspectives
from ..rag import ingest, search
from ..workflow import Workflow

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
AGENT_NAME = "hermeneut-agent"
AGENT_VERSION = "2.2.0"
DEFAULT_PROJECT = "acp-session"
DEFAULT_PARTICIPANT = "user"
DEFAULT_DB = "./data/acp.db"
CHUNK_SIZE = 1000


def _configure_console() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


class Transport:
    def __init__(self):
        self._lock = threading.Lock()

    def read_message(self) -> dict | None:
        try:
            line = sys.stdin.readline()
            if not line:
                return None
            return json.loads(line)
        except (json.JSONDecodeError, EOFError):
            return None

    def write_json(self, obj: dict) -> None:
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            sys.stdout.write(data + "\n")
            sys.stdout.flush()


class Session:
    def __init__(self, session_id: str, project_id: str, participant_id: str):
        self.session_id = session_id
        self.project_id = project_id
        self.participant_id = participant_id
        self.source_ids: list[str] = []
        self.cancel_event = threading.Event()


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, project_id: str, participant_id: str) -> Session:
        sid = f"sess_{uuid.uuid4().hex[:12]}"
        s = Session(sid, project_id, participant_id)
        self._sessions[sid] = s
        return s

    def get(self, sid: str) -> Session | None:
        return self._sessions.get(sid)

    def remove(self, sid: str) -> None:
        self._sessions.pop(sid, None)


class Intent(Enum):
    LIST_PERSPECTIVES = "list_perspectives"
    SEARCH = "search"
    DIALECTICAL = "dialectical"
    ANALYZE = "analyze"
    HELP = "help"


def parse_intent(text: str) -> tuple[Intent, str]:
    t = text.lower()
    if any(k in t for k in ("perspective", "视角", "list perspective")):
        return Intent.LIST_PERSPECTIVES, text
    if any(k in t for k in ("search", "搜索", "查找", "检索", "find")):
        return Intent.SEARCH, text
    if any(k in t for k in ("dialectical", "辩证", "多视角", "对抗")):
        return Intent.DIALECTICAL, text
    if any(k in t for k in ("analy", "分析", "解读", "interpret")):
        return Intent.ANALYZE, text
    return Intent.HELP, text


def _extract_text(prompt_blocks) -> str:
    if isinstance(prompt_blocks, str):
        return prompt_blocks
    parts = []
    for block in prompt_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def _get_provider(mock: bool):
    if mock or os.getenv("LACAN_MOCK"):
        from ..llm import FakeProvider
        return FakeProvider()
    if os.getenv("DASHSCOPE_API_KEY"):
        from ..llm import QwenProvider
        return QwenProvider()
    from ..llm import FakeProvider
    return FakeProvider()


def _ensure_project(store: Store, project_id: str) -> None:
    if not store.get_project(project_id):
        store.create_project(Project(id=project_id))


def _ensure_participant(store: Store, project_id: str, participant_id: str) -> None:
    if not store.get_participant(project_id, participant_id):
        store.put_participant(Participant(
            id=participant_id, project_id=project_id,
            pseudonym="ACP User", consent_scope=ConsentScope(),
        ))


def _format_perspectives(perspectives) -> str:
    lines = ["## 可用理论视角\n"]
    for p in perspectives:
        lines.append(f"### {p.id} — {p.name}\n")
        lines.append(f"**概念**: {', '.join(p.concept_inventory)}\n")
        lines.append(f"**盲区**: {'; '.join(p.blind_spots)}\n")
        if p.vocabulary:
            terms = [f"`{k}` = {v}" for k, v in list(p.vocabulary.items())[:5]]
            lines.append(f"**术语**: {'; '.join(terms)}\n")
    return "\n".join(lines)


def _format_search_results(results: list[dict]) -> str:
    if not results:
        return "## 搜索结果\n\n未找到匹配结果。"
    lines = [f"## 搜索结果（{len(results)} 条）\n"]
    for i, r in enumerate(results, 1):
        doc_id = r.get("document_id", "?")
        snip = r.get("snippet", r.get("text", ""))[:200]
        lines.append(f"{i}. **[{doc_id}]** {snip}\n")
    return "\n".join(lines)


def _format_analysis_packet(packet) -> str:
    lines = ["## 分析结果\n"]
    if packet.observations:
        lines.append(f"### 观察（{len(packet.observations)}）\n")
        for o in packet.observations:
            reg = f" [{o.rsi_register}]" if o.rsi_register else ""
            lines.append(f"- **{o.id}**: {o.label}{reg}\n")
    if packet.hypotheses:
        lines.append(f"\n### 假设（{len(packet.hypotheses)}）\n")
        for h in packet.hypotheses:
            status = h.status or "candidate"
            lines.append(f"- **{h.id}** [{status}]")
            if h.concept_ids:
                lines.append(f"  - 概念: {', '.join(h.concept_ids)}")
            if h.alternatives:
                lines.append(f"  - 替代: {'; '.join(h.alternatives)}")
            if h.counterexamples:
                ce_texts = [c.text[:80] for c in h.counterexamples]
                lines.append(f"  - 反例: {'; '.join(ce_texts)}")
            lines.append("")
    return "\n".join(lines)


def _format_dialectical_result(result) -> str:
    lines = ["## 辩证分析结果\n"]
    lines.append(f"**运行 ID**: {result.run_id}\n")
    lines.append(f"**视角**: {', '.join(result.perspective_ids)}\n")

    if result.phase1_analyses:
        lines.append("\n---\n### Phase 1: 独立分析\n")
        for a in result.phase1_analyses:
            lines.append(f"\n#### {a.perspective_id}\n")
            lines.append(f"观察: {len(a.observations)} | 假设: {len(a.hypotheses)}\n")
            for o in a.observations[:5]:
                lines.append(f"- {o.label}")
            for h in a.hypotheses[:5]:
                concepts = ", ".join(h.concept_ids[:3]) if h.concept_ids else ""
                lines.append(f"- [{h.status}] {concepts}")

    if result.phase2_cross_critiques:
        lines.append("\n---\n### Phase 2: 交叉批评\n")
        for cc in result.phase2_cross_critiques:
            lines.append(f"\n**{cc.source_perspective_id}** → {cc.target_perspective_id}")
            if cc.counterexamples:
                for ce in cc.counterexamples[:3]:
                    lines.append(f"- 反例: {ce.text[:100]}")
            if cc.blind_spot_alerts:
                lines.append(f"- 盲区: {'; '.join(cc.blind_spot_alerts[:3])}")

    if result.phase3_synthesis:
        s = result.phase3_synthesis
        lines.append("\n---\n### Phase 3: 综合\n")
        if s.convergence:
            conv_text = '; '.join(str(c) for c in s.convergence)
            lines.append(f"**收敛**: {conv_text[:500]}\n")
        if s.divergence:
            div_text = '; '.join(str(d) for d in s.divergence)
            lines.append(f"**分歧**: {div_text[:500]}\n")
        if s.unique_insights:
            ins_text = '; '.join(str(u) for u in s.unique_insights)
            lines.append(f"**独特洞见**: {ins_text[:500]}\n")
        if s.recommended_hypotheses:
            lines.append(f"**推荐假设**: {len(s.recommended_hypotheses)} 条\n")

    if result.phase4_report:
        lines.append("\n---\n### Phase 4: 报告\n")
        lines.append(result.phase4_report[:2000])

    return "\n".join(lines)


def _format_help() -> str:
    return """## Hermeneut Agent — ACP 帮助

在 Zed 中选中文字后，用自然语言描述你想要的操作：

| 命令 | 示例 |
|------|------|
| **列出视角** | "列出可用视角" / "perspectives" |
| **单视角分析** | "分析以下文本：..." / "analyze: ..." |
| **辩证分析** | "辩证分析：..." / "dialectical: ..." |
| **搜索文档** | "搜索：能指" / "search: signifier" |

辩证分析会使用所有已注册视角（拉康 + 德勒兹）进行对抗性分析。
"""


class ACPServer:
    def __init__(self, store: Store, provider, transport: Transport):
        self.store = store
        self.provider = provider
        self.transport = transport
        self.sessions = SessionManager()

    def run(self) -> None:
        while True:
            msg = self.transport.read_message()
            if msg is None:
                break
            method = msg.get("method", "")
            params = msg.get("params", {})
            req_id = msg.get("id")

            if req_id is None:
                if method == "session/cancel":
                    self._handle_cancel(params)
                continue

            try:
                if method == "initialize":
                    self._handle_initialize(req_id, params)
                elif method == "session/new":
                    self._handle_session_new(req_id, params)
                elif method == "session/prompt":
                    self._handle_prompt(req_id, params)
                elif method == "session/close":
                    self._handle_close(req_id, params)
                else:
                    self._respond_error(req_id, -32601, f"method not found: {method}")
            except Exception as e:
                logger.exception("handler error: %s", e)
                self._respond_error(req_id, -32603, str(e))

    def _handle_initialize(self, req_id, params) -> None:
        client_version = params.get("protocolVersion", 1)
        version = min(client_version, PROTOCOL_VERSION)
        self._respond(req_id, {
            "protocolVersion": version,
            "agentCapabilities": {
                "promptCapabilities": {"embeddedContext": True},
                "sessionCapabilities": {"close": {}},
            },
            "agentInfo": {"name": AGENT_NAME, "version": AGENT_VERSION},
        })

    def _handle_session_new(self, req_id, params) -> None:
        _ensure_project(self.store, DEFAULT_PROJECT)
        _ensure_participant(self.store, DEFAULT_PROJECT, DEFAULT_PARTICIPANT)
        session = self.sessions.create(DEFAULT_PROJECT, DEFAULT_PARTICIPANT)
        self._respond(req_id, {"sessionId": session.session_id})

    def _handle_prompt(self, req_id, params) -> None:
        sid = params.get("sessionId", "")
        session = self.sessions.get(sid)
        if not session:
            self._respond_error(req_id, -32602, "unknown session")
            return

        text = _extract_text(params.get("prompt", ""))
        if not text.strip():
            self._respond_error(req_id, -32602, "empty prompt")
            return

        intent, query = parse_intent(text)
        session.cancel_event.clear()

        if intent == Intent.HELP:
            self._send_result(session, _format_help(), req_id)
        elif intent == Intent.LIST_PERSPECTIVES:
            self._send_result(session, _format_perspectives(list_perspectives()), req_id)
        elif intent == Intent.SEARCH:
            q = query.split(":", 1)[-1].split("：", 1)[-1].strip()
            q = q.replace("search", "").replace("搜索", "").replace("查找", "").replace("检索", "").strip()
            results = search(self.store, q, session.project_id) if q else []
            self._send_result(session, _format_search_results(results), req_id)
        elif intent == Intent.ANALYZE:
            body = self._extract_body(query)
            t = threading.Thread(target=self._run_single, args=(session, body, req_id), daemon=True)
            t.start()
        elif intent == Intent.DIALECTICAL:
            body = self._extract_body(query)
            t = threading.Thread(target=self._run_dialectical, args=(session, body, req_id), daemon=True)
            t.start()

    def _extract_body(self, text: str) -> str:
        for sep in (":", "："):
            if sep in text:
                candidate = text.split(sep, 1)[1].strip()
                if len(candidate) > 10:
                    return candidate
        keywords = ("分析", "analy", "interpret", "解读", "辩证", "dialectical", "search", "搜索")
        cleaned = text
        for kw in keywords:
            cleaned = cleaned.replace(kw, "")
        cleaned = cleaned.strip(" :：\t\n")
        return cleaned if len(cleaned) > 10 else text

    def _ingest_text(self, session: Session, text: str) -> str:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="w", encoding="utf-8",
        )
        try:
            tmp.write(text)
            tmp.close()
            doc = ingest(self.store, tmp.name, session.project_id, session.participant_id)
            if doc.id not in session.source_ids:
                session.source_ids.append(doc.id)
            return doc.id
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def _run_single(self, session: Session, text: str, req_id) -> None:
        try:
            self._emit_tool_call(session, "ingest", "文本摄入", "ingest_text", "other", "in_progress")
            doc_id = self._ingest_text(session, text)
            self._emit_tool_update(session, "ingest", "completed", f"文档 {doc_id}")

            self._emit_tool_call(session, "analyze", "单视角分析", "workflow_run", "analysis", "in_progress")
            idem = f"acp_{uuid.uuid4().hex[:8]}"
            run = Workflow(self.store, self.provider).run(
                session.project_id, session.participant_id, [doc_id], idem,
            )
            self._emit_tool_update(session, "analyze", "completed", "分析完成")

            if run.packet:
                md = _format_analysis_packet(run.packet)
            else:
                md = "分析完成，但未生成结果包。"
            self._send_result(session, md, req_id)
        except Exception as e:
            logger.exception("single analysis error: %s", e)
            self._emit_tool_update(session, "analyze", "failed", str(e))
            self._send_result(session, f"## 分析错误\n\n{e}", req_id)

    def _run_dialectical(self, session: Session, text: str, req_id) -> None:
        try:
            self._emit_tool_call(session, "ingest", "文本摄入", "ingest_text", "other", "in_progress")
            doc_id = self._ingest_text(session, text)
            self._emit_tool_update(session, "ingest", "completed", f"文档 {doc_id}")

            perspectives = list_perspectives()
            if not perspectives:
                self._send_result(session, "## 错误\n\n没有可用的理论视角。", req_id)
                return

            dw = DialecticalWorkflow(self.store, self.provider, perspectives)
            self._patch_phases(dw, session)

            self._emit_tool_call(session, "dial", "辩证分析", "dialectical_run", "analysis", "in_progress")
            idem = f"acp_dial_{uuid.uuid4().hex[:8]}"
            result = dw.run(
                session.project_id, session.participant_id,
                [doc_id], idem, generate_report=True,
            )
            self._emit_tool_update(session, "dial", "completed", "辩证分析完成")

            md = _format_dialectical_result(result)
            self._send_result(session, md, req_id)
        except Exception as e:
            logger.exception("dialectical error: %s", e)
            self._emit_tool_update(session, "dial", "failed", str(e))
            self._send_result(session, f"## 辩证分析错误\n\n{e}", req_id)

    def _patch_phases(self, dw: DialecticalWorkflow, session: Session) -> None:
        phases = [
            ("_phase1_independent", "phase1", "Phase 1: 独立分析"),
            ("_phase2_cross_critique", "phase2", "Phase 2: 交叉批评"),
            ("_phase3_synthesis", "phase3", "Phase 3: 综合"),
            ("_phase4_report", "phase4", "Phase 4: 报告生成"),
        ]
        for method_name, call_id, title in phases:
            original = getattr(dw, method_name)

            def make_wrapper(orig, cid, ttl):
                def wrapper(*args, **kwargs):
                    self._emit_tool_call(session, cid, ttl, cid, "analysis", "in_progress")
                    result = orig(*args, **kwargs)
                    self._emit_tool_update(session, cid, "completed", f"{ttl}完成")
                    return result
                return wrapper

            setattr(dw, method_name, make_wrapper(original, call_id, title))

    def _handle_cancel(self, params) -> None:
        sid = params.get("sessionId", "")
        session = self.sessions.get(sid)
        if session:
            session.cancel_event.set()

    def _handle_close(self, req_id, params) -> None:
        sid = params.get("sessionId", "")
        self.sessions.remove(sid)
        self._respond(req_id, {})

    def _send_result(self, session: Session, text: str, req_id) -> None:
        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        for i in range(0, max(len(text), 1), CHUNK_SIZE):
            chunk = text[i:i + CHUNK_SIZE]
            self._notify("session/update", {
                "sessionId": session.session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "messageId": msg_id,
                    "content": {"type": "text", "text": chunk},
                },
            })
        self._respond(req_id, {"stopReason": "end_turn"})

    def _emit_tool_call(self, session: Session, call_id: str, title: str,
                        name: str, kind: str, status: str) -> None:
        self._notify("session/update", {
            "sessionId": session.session_id,
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": call_id,
                "title": title,
                "name": name,
                "kind": kind,
                "status": status,
            },
        })

    def _emit_tool_update(self, session: Session, call_id: str, status: str,
                          content_text: str) -> None:
        self._notify("session/update", {
            "sessionId": session.session_id,
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": call_id,
                "status": status,
                "content": [{"type": "content", "content": {"type": "text", "text": content_text}}],
            },
        })

    def _respond(self, req_id, result) -> None:
        self.transport.write_json({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _respond_error(self, req_id, code: int, message: str) -> None:
        self.transport.write_json({
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message},
        })

    def _notify(self, method: str, params: dict) -> None:
        self.transport.write_json({"jsonrpc": "2.0", "method": method, "params": params})


def main() -> None:
    global DEFAULT_PARTICIPANT
    _configure_console()
    logging.basicConfig(
        level=os.environ.get("LACAN_LOG_LEVEL", "WARNING"),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description="Hermeneut ACP Server")
    parser.add_argument("--db", default=os.getenv("LACAN_DB_PATH", DEFAULT_DB))
    parser.add_argument("--mock", action="store_true", help="Use FakeProvider (no API key)")
    parser.add_argument('--legacy-sqlite', action='store_true')
    args = parser.parse_args()

    if args.legacy_sqlite:
        os.environ['HERMENEUT_RUNTIME'] = 'sqlite'
    if os.getenv('HERMENEUT_DATABASE_URL') and os.getenv('HERMENEUT_RUNTIME') != 'sqlite':
        from ..research.runtime import open_store, get_provider
        DEFAULT_PARTICIPANT = '__corpus__'
        store = open_store(DEFAULT_PROJECT, corpus=True)
        provider = get_provider(args.mock)
    else:
        store = Store(args.db)
        provider = _get_provider(args.mock)
    transport = Transport()
    server = ACPServer(store, provider, transport)
    server.run()


if __name__ == "__main__":
    main()
