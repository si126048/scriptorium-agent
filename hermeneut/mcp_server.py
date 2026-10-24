"""Hermeneut MCP server — exposes discourse analysis as MCP tools.

Run: python -m hermeneut.mcp_server [--mock] [--db PATH]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tempfile
import uuid

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .db import Store
from .dialectical import DialecticalWorkflow
from .models import ConsentScope, Participant, Project
from .perspectives import list_perspectives
from .rag import ingest, search
from .workflow import Workflow

logger = logging.getLogger(__name__)

DEFAULT_PROJECT = "mcp-session"
DEFAULT_PARTICIPANT = "user"
DEFAULT_DB = "./data/mcp.db"

server = Server("hermeneut")

_store: Store | None = None
_provider = None


def _get_provider(mock: bool):
    if mock or os.getenv("LACAN_MOCK"):
        from .llm import FakeProvider
        return FakeProvider()
    if os.getenv("DASHSCOPE_API_KEY"):
        from .llm import QwenProvider
        return QwenProvider()
    from .llm import FakeProvider
    return FakeProvider()


def _ensure_setup():
    global _store, _provider, DEFAULT_PARTICIPANT
    if _store is None:
        if os.getenv('HERMENEUT_DATABASE_URL') and os.getenv('HERMENEUT_RUNTIME') != 'sqlite':
            from .research.runtime import open_store, get_provider
            DEFAULT_PARTICIPANT = '__corpus__'
            _store = open_store(DEFAULT_PROJECT, corpus=True)
            _provider = get_provider(os.getenv('LACAN_MOCK') == '1')
            return
        db_path = os.getenv("LACAN_DB_PATH", DEFAULT_DB)
        _store = Store(db_path)
        _provider = _get_provider(os.getenv("LACAN_MOCK") == "1")
    if not _store.get_project(DEFAULT_PROJECT):
        _store.create_project(Project(id=DEFAULT_PROJECT))
    if not _store.get_participant(DEFAULT_PROJECT, DEFAULT_PARTICIPANT):
        _store.put_participant(Participant(
            id=DEFAULT_PARTICIPANT, project_id=DEFAULT_PROJECT,
            pseudonym="MCP User", consent_scope=ConsentScope(),
        ))


def _ingest_text(text: str) -> str:
    _ensure_setup()
    tmp = tempfile.NamedTemporaryFile(
        suffix=".txt", delete=False, mode="w", encoding="utf-8",
    )
    try:
        tmp.write(text)
        tmp.close()
        doc = ingest(_store, tmp.name, DEFAULT_PROJECT, DEFAULT_PARTICIPANT)
        return doc.id
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _format_packet(packet) -> str:
    parts = []
    if packet.observations:
        parts.append(f"## Observations ({len(packet.observations)})\n")
        for o in packet.observations:
            reg = f" [{o.rsi_register}]" if o.rsi_register else ""
            parts.append(f"- **{o.id}**: {o.label}{reg}")
    if packet.hypotheses:
        parts.append(f"\n## Hypotheses ({len(packet.hypotheses)})\n")
        for h in packet.hypotheses:
            concepts = ", ".join(h.concept_ids) if h.concept_ids else "—"
            parts.append(f"- **{h.id}** [{h.status or 'candidate'}] concepts: {concepts}")
            if h.alternatives:
                parts.append(f"  alternatives: {'; '.join(h.alternatives)}")
            if h.counterexamples:
                ce = "; ".join(c.text[:80] for c in h.counterexamples)
                parts.append(f"  counterexamples: {ce}")
    return "\n".join(parts) if parts else "No results."


def _format_dialectical(result) -> str:
    parts = [f"## Dialectical Analysis\nrun: {result.run_id}\nperspectives: {', '.join(result.perspective_ids)}\n"]

    if result.phase1_analyses:
        parts.append("### Phase 1: Independent Analysis\n")
        for a in result.phase1_analyses:
            parts.append(f"**{a.perspective_id}** — {len(a.observations)} obs, {len(a.hypotheses)} hyp")
            for o in a.observations[:5]:
                parts.append(f"  - {o.label}")
            for h in a.hypotheses[:5]:
                c = ", ".join(h.concept_ids[:3]) if h.concept_ids else ""
                parts.append(f"  - [{h.status}] {c}")

    if result.phase2_cross_critiques:
        parts.append("\n### Phase 2: Cross-Critique\n")
        for cc in result.phase2_cross_critiques:
            parts.append(f"**{cc.source_perspective_id}** → {cc.target_perspective_id}")
            if cc.blind_spot_alerts:
                parts.append(f"  blind spots: {'; '.join(cc.blind_spot_alerts[:3])}")

    if result.phase3_synthesis:
        s = result.phase3_synthesis
        parts.append("\n### Phase 3: Synthesis\n")
        if s.convergence:
            conv_text = '; '.join(str(c) for c in s.convergence)
            parts.append(f"Convergence: {conv_text[:500]}")
        if s.divergence:
            div_text = '; '.join(str(d) for d in s.divergence)
            parts.append(f"Divergence: {div_text[:500]}")
        if s.unique_insights:
            ins_text = '; '.join(str(u) for u in s.unique_insights)
            parts.append(f"Unique insights: {ins_text[:500]}")

    if result.phase4_report:
        parts.append(f"\n### Phase 4: Report\n{result.phase4_report[:2000]}")

    return "\n".join(parts)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="hermeneut_analyze",
            description="Run single-perspective evidence analysis on text. Returns observations and hypotheses with evidence spans.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to analyze"},
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="hermeneut_dialectical",
            description="Run adversarial multi-perspective dialectical analysis (Lacan vs Deleuze). Four phases: independent analysis → cross-critique → synthesis → report.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to analyze"},
                    "perspectives": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Perspective IDs (default: all registered, e.g. ['lacan', 'deleuze'])",
                    },
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="hermeneut_perspectives",
            description="List available theoretical perspectives with their concept inventories and blind spots.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="hermeneut_search",
            description="Full-text search across ingested documents.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    args = arguments or {}
    try:
        if name == "hermeneut_analyze":
            return await _analyze(args)
        if name == "hermeneut_dialectical":
            return await _dialectical(args)
        if name == "hermeneut_perspectives":
            return _perspectives()
        if name == "hermeneut_search":
            return _search_docs(args)
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        logger.exception("tool error: %s", e)
        return [types.TextContent(type="text", text=f"Error: {e}")]


async def _analyze(args: dict) -> list[types.TextContent]:
    text = args.get("text", "")
    if not text.strip():
        return [types.TextContent(type="text", text="Error: empty text")]

    loop = asyncio.get_running_loop()
    doc_id = await loop.run_in_executor(None, _ingest_text, text)

    _ensure_setup()
    idem = f"mcp_{uuid.uuid4().hex[:8]}"

    def _run():
        return Workflow(_store, _provider).run(DEFAULT_PROJECT, DEFAULT_PARTICIPANT, [doc_id], idem)

    run = await loop.run_in_executor(None, _run)
    md = _format_packet(run.packet) if run.packet else "Analysis completed, no packet generated."
    return [types.TextContent(type="text", text=md)]


async def _dialectical(args: dict) -> list[types.TextContent]:
    text = args.get("text", "")
    if not text.strip():
        return [types.TextContent(type="text", text="Error: empty text")]

    loop = asyncio.get_running_loop()
    doc_id = await loop.run_in_executor(None, _ingest_text, text)

    _ensure_setup()
    requested = args.get("perspectives")
    all_p = list_perspectives()
    if requested:
        perspectives = [p for p in all_p if p.id in requested]
    else:
        perspectives = all_p

    if not perspectives:
        return [types.TextContent(type="text", text="Error: no matching perspectives")]

    idem = f"mcp_d_{uuid.uuid4().hex[:8]}"

    def _run():
        dw = DialecticalWorkflow(_store, _provider, perspectives)
        return dw.run(DEFAULT_PROJECT, DEFAULT_PARTICIPANT, [doc_id], idem, generate_report=True)

    result = await loop.run_in_executor(None, _run)
    md = _format_dialectical(result)
    return [types.TextContent(type="text", text=md)]


def _perspectives() -> list[types.TextContent]:
    ps = list_perspectives()
    parts = [f"## Perspectives ({len(ps)})\n"]
    for p in ps:
        parts.append(f"### {p.id} — {p.name}")
        parts.append(f"Concepts: {', '.join(p.concept_inventory)}")
        parts.append(f"Blind spots: {'; '.join(p.blind_spots)}")
        if p.vocabulary:
            terms = [f"{k}={v}" for k, v in list(p.vocabulary.items())[:5]]
            parts.append(f"Key terms: {'; '.join(terms)}")
        parts.append("")
    return [types.TextContent(type="text", text="\n".join(parts))]


def _search_docs(args: dict) -> list[types.TextContent]:
    _ensure_setup()
    query = args.get("query", "")
    limit = args.get("limit", 5)
    if not query.strip():
        return [types.TextContent(type="text", text="Error: empty query")]
    results = search(_store, query, DEFAULT_PROJECT, limit)
    if not results:
        return [types.TextContent(type="text", text=f"No results for: {query}")]
    parts = [f"## Search Results ({len(results)})\n"]
    for i, r in enumerate(results, 1):
        doc_id = r.get("document_id", "?")
        snip = r.get("snippet", r.get("text", ""))[:200]
        parts.append(f"{i}. [{doc_id}] {snip}")
    return [types.TextContent(type="text", text="\n".join(parts))]


def main():
    parser = argparse.ArgumentParser(description="Hermeneut MCP Server")
    parser.add_argument("--db", default=os.getenv("LACAN_DB_PATH", DEFAULT_DB))
    parser.add_argument("--mock", action="store_true")
    parser.add_argument('--legacy-sqlite', action='store_true')
    args = parser.parse_args()
    if args.legacy_sqlite:
        os.environ['HERMENEUT_RUNTIME'] = 'sqlite'

    if args.mock:
        os.environ["LACAN_MOCK"] = "1"
    os.environ["LACAN_DB_PATH"] = args.db

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    logging.basicConfig(
        level=os.environ.get("LACAN_LOG_LEVEL", "WARNING"),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    _ensure_setup()

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
