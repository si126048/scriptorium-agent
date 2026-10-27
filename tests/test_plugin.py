# ruff: noqa: SIM117
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from scriptorium.plugin.__main__ import configuration
from scriptorium.plugin.core import ResearchTools


def test_material_versions_unicode_quote_and_project_isolation(tmp_path):
    workspace = tmp_path / "one"
    workspace.mkdir()
    tools = ResearchTools(str(workspace), str(tmp_path / "shared.sqlite3"))
    text = "甲😀e\u0301\n自由与制度。自由与制度。"
    first = tools.import_source(text, "原典")
    assert tools.import_source(text)["deduplicated"]
    changed = tools.import_source(text + "修订", "新版")
    assert changed["source_id"] != first["source_id"]
    assert tools.read(first["source_id"])["text"] == text
    assert tools.verify_quote(first["source_id"], "自由")["reason"] == "AMBIGUOUS_QUOTE"
    verified = tools.verify_quote(first["source_id"], "自由", text.index("自由"))
    assert verified["verified"] and verified["start"] == 5
    assert tools.verify_quote(first["source_id"], "自由", 0)["verified"] is False
    other = tmp_path / "other"
    other.mkdir()
    isolated = ResearchTools(str(other), str(tmp_path / "shared.sqlite3"))
    assert not isolated.sources()["items"]
    with pytest.raises(ValueError, match="SOURCE_NOT_AVAILABLE"):
        isolated.read(first["source_id"])
    isolated.close()
    tools.close()


def test_scoped_files_and_coverage_never_claim_completed_analysis(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    private = tmp_path / "private.txt"
    private.write_text("private", encoding="utf-8")
    tools = ResearchTools(str(root))
    with pytest.raises(ValueError, match="SOURCE_OUTSIDE_WORKSPACE"):
        tools.import_source(path="../private.txt")
    with pytest.raises(ValueError, match="REDACTION"):
        tools.import_source("sk-" + "x" * 28)
    material = tools.import_source("开篇。" * 2000 + "独特中段证据。" + "结尾。" * 2000)
    assert tools.search("独特中段证据")["items"][0]["start"] > 5000
    context = tools.prepare("独特中段证据", [material["source_id"]])
    assert context["analysis_status"] == "awaiting_host_inference"
    assert context["evidence"][0]["start"] > 5000
    assert context["coverage"][0]["uncovered_codepoints"] > 0
    assert context["model_calls"] == 0
    tools.close()


def test_bibliography_matches_are_not_original_text_evidence(tmp_path):
    tools = ResearchTools(str(tmp_path))
    book = tools.import_source("合成资料. 测试出版社, 2026.", source_kind="bibliography")
    verified = tools.verify_quote(book["source_id"], "测试出版社")
    assert verified["quote_scope"] == "bibliographic_metadata"
    assert not verified["verified"] and verified["metadata_match"]
    packet = tools.prepare("合成资料", [book["source_id"]])
    assert packet["evidence"][0]["source_kind"] == "bibliography"
    tools.close()


def test_acp_cancellation_stops_answer_and_releases_session(tmp_path):
    from scriptorium.plugin.acp import ContextAgent

    agent = ContextAgent(str(tmp_path))
    tools = ResearchTools(str(tmp_path))
    entered, release = threading.Event(), threading.Event()

    def prepare(_question):
        entered.set()
        release.wait(timeout=3)
        return {"kind": "research_context"}

    tools.prepare = prepare
    session = {"tools": tools, "cancel": threading.Event(), "busy": threading.Lock()}
    session["busy"].acquire()
    agent.sessions["one"] = session
    replies = []
    agent.send = replies.append
    thread = threading.Thread(
        target=agent.prompt, args=(7, "one", [{"type": "text", "text": "研究"}], session)
    )
    thread.start()
    assert entered.wait(timeout=3)
    agent.dispatch({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": "one"}})
    release.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert replies[-1]["result"]["stopReason"] == "cancelled"
    assert not any(
        r.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"
        for r in replies
    )
    assert session["busy"].acquire(blocking=False)
    session["busy"].release()
    tools.close()


def test_host_configuration_fragments(tmp_path):
    assert "mcp_servers.scriptorium" in configuration("codex", str(tmp_path))
    assert configuration("dsh", str(tmp_path))[0]["config"]["transport"] == "stdio"
    assert configuration("zed", str(tmp_path))["agent_servers"]["Scriptorium"]["args"][2] == "acp"
    assert configuration("cursor", str(tmp_path))["mcpServers"]["scriptorium"]["args"][2] == "mcp"


def test_academic_writing_has_evidence_and_genre_obligations(tmp_path):
    tools = ResearchTools(str(tmp_path))
    context = tools.prepare("制度如何影响实践？", writing_genre="argumentative_essay")
    contract = context["writing_contract"]
    assert contract["genre"] == "argumentative_essay"
    assert "真实情境反思" in contract["sections"]
    assert "source_evidence" in contract["argument_unit"]
    assert contract["citation_rules"] and contract["experience_rules"]
    assert "own_criterion" in context["method_contracts"]["immanent_critique"]["fields"]
    with pytest.raises(ValueError, match="UNKNOWN_WRITING_GENRE"):
        tools.prepare("问题", writing_genre="pretend_publication")
    tools.close()


@pytest.mark.asyncio
async def test_real_mcp_stdio_calls(tmp_path):
    root = str(Path(__file__).resolve().parents[1])
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "scriptorium.plugin", "mcp", "--workspace", str(tmp_path)],
        cwd=root,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            names = {t.name for t in (await client.list_tools()).tools}
            assert {"source_import", "source_search", "quote_verify", "research_prepare"} <= names
            imported = await client.call_tool(
                "source_import", {"text": "自由需要制度条件。", "title": "合成材料"}
            )
            assert not imported.isError
            source = imported.structuredContent["source_id"]
            result = await client.call_tool("source_search", {"query": "制度"})
            assert result.structuredContent["items"][0]["source_id"] == source
            result = await client.call_tool(
                "quote_verify", {"source_id": source, "quote": "制度条件"}
            )
            assert result.structuredContent["verified"]
            context = await client.call_tool("research_prepare", {"question": "比较自由的制度条件"})
            assert context.structuredContent["analysis_status"] == "awaiting_host_inference"
            denied = await client.call_tool("source_read", {"source_id": "outside"})
            assert denied.isError


def test_acp_subprocess_initialize_prompt_and_errors(tmp_path):
    root = str(Path(__file__).resolve().parents[1])
    proc = subprocess.Popen(
        [sys.executable, "-m", "scriptorium.plugin", "acp", "--workspace", str(tmp_path)],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    received = queue.Queue()

    def collect():
        for line in proc.stdout:
            received.put(json.loads(line))

    threading.Thread(target=collect, daemon=True).start()

    def send(identifier, method, params):
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params})
            + "\n"
        )
        proc.stdin.flush()
        updates = []
        for _ in range(12):
            value = received.get(timeout=10)
            if value.get("id") == identifier:
                return value, updates
            updates.append(value)
        raise AssertionError("No matching ACP response")

    try:
        denied, _ = send(0, "session/new", {"cwd": str(tmp_path)})
        assert denied["error"]["message"] == "INITIALIZE_REQUIRED"
        init, _ = send(1, "initialize", {"protocolVersion": 1})
        assert init["result"]["protocolVersion"] == 1
        created, _ = send(2, "session/new", {"cwd": str(tmp_path), "mcpServers": []})
        sid = created["result"]["sessionId"]
        reply, updates = send(
            3,
            "session/prompt",
            {
                "sessionId": sid,
                "prompt": [
                    {"type": "text", "text": "研究自由"},
                    {
                        "type": "resource",
                        "resource": {
                            "uri": "context://selected",
                            "mimeType": "text/plain",
                            "text": "自由需要制度条件。",
                        },
                    },
                ],
            },
        )
        assert reply["result"]["stopReason"] == "end_turn"
        text = "".join(
            x["params"]["update"].get("content", {}).get("text", "")
            for x in updates
            if x["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
        )
        assert "awaiting_host_inference" in text and "制度条件" in text
        assert send(4, "session/close", {"sessionId": sid})[0]["result"] == {}
        proc.stdin.write("not json\n")
        proc.stdin.flush()
        assert received.get(timeout=10)["error"]["code"] == -32700
        assert send(5, "initialize", {"protocolVersion": 1})[0]["result"]["protocolVersion"] == 1
    finally:
        proc.terminate()
        proc.wait(timeout=10)
