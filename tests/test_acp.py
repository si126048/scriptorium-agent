"""Tests for the ACP (Agent Client Protocol) server."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time

import pytest

from scriptorium.acp.server import (
    Transport, Session, SessionManager, Intent,
    parse_intent, _extract_text, _format_help, _format_perspectives,
    ACPServer, _configure_console,
)


class TestParseIntent:
    def test_list_perspectives_en(self):
        intent, _ = parse_intent("list perspectives")
        assert intent == Intent.LIST_PERSPECTIVES

    def test_list_perspectives_zh(self):
        intent, _ = parse_intent("列出可用视角")
        assert intent == Intent.LIST_PERSPECTIVES

    def test_search_en(self):
        intent, _ = parse_intent("search: signifier")
        assert intent == Intent.SEARCH

    def test_search_zh(self):
        intent, _ = parse_intent("搜索：能指")
        assert intent == Intent.SEARCH

    def test_dialectical_en(self):
        intent, _ = parse_intent("dialectical analysis of this text")
        assert intent == Intent.DIALECTICAL

    def test_dialectical_zh(self):
        intent, _ = parse_intent("辩证分析：重复模式")
        assert intent == Intent.DIALECTICAL

    def test_analyze_en(self):
        intent, _ = parse_intent("analyze the following text")
        assert intent == Intent.ANALYZE

    def test_analyze_zh(self):
        intent, _ = parse_intent("分析以下文本")
        assert intent == Intent.ANALYZE

    def test_help_fallback(self):
        intent, _ = parse_intent("hello world")
        assert intent == Intent.HELP

    def test_help_explicit(self):
        intent, _ = parse_intent("help")
        assert intent == Intent.HELP


class TestExtractText:
    def test_string_input(self):
        assert _extract_text("hello") == "hello"

    def test_content_blocks(self):
        blocks = [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
        assert _extract_text(blocks) == "first\nsecond"

    def test_mixed_blocks(self):
        blocks = [
            {"type": "text", "text": "hello"},
            {"type": "image", "data": "base64..."},
            "raw string",
        ]
        result = _extract_text(blocks)
        assert "hello" in result
        assert "raw string" in result
        assert "base64" not in result

    def test_empty_blocks(self):
        assert _extract_text([]) == ""


class TestSessionManager:
    def test_create_and_get(self):
        mgr = SessionManager()
        s = mgr.create("proj", "user")
        assert s.session_id.startswith("sess_")
        assert s.project_id == "proj"
        assert mgr.get(s.session_id) is s

    def test_remove(self):
        mgr = SessionManager()
        s = mgr.create("proj", "user")
        mgr.remove(s.session_id)
        assert mgr.get(s.session_id) is None

    def test_get_nonexistent(self):
        mgr = SessionManager()
        assert mgr.get("nonexistent") is None


class TestTransport:
    def test_write_and_read(self, monkeypatch):
        input_buf = io.StringIO()
        output_buf = io.StringIO()
        monkeypatch.setattr(sys, "stdin", input_buf)
        monkeypatch.setattr(sys, "stdout", output_buf)

        transport = Transport()
        transport.write_json({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

        output_buf.seek(0)
        monkeypatch.setattr(sys, "stdin", output_buf)
        msg = transport.read_message()
        assert msg["jsonrpc"] == "2.0"
        assert msg["id"] == 1
        assert msg["result"]["ok"] is True

    def test_read_eof(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        transport = Transport()
        assert transport.read_message() is None

    def test_read_invalid_json(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json\n"))
        transport = Transport()
        assert transport.read_message() is None


class TestFormatHelpers:
    def test_format_help_contains_commands(self):
        help_text = _format_help()
        assert "分析" in help_text
        assert "辩证" in help_text
        assert "视角" in help_text

    def test_format_perspectives(self):
        from scriptorium.perspectives import list_perspectives
        perspectives = list_perspectives()
        text = _format_perspectives(perspectives)
        assert "lacan" in text
        assert "deleuze" in text
        assert "概念" in text


def _start_server():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "LACAN_DB_PATH": os.path.join(project_root, "data", "acp_pytest.db")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "scriptorium.acp", "--mock"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=project_root,
    )
    return proc, project_root


def _send(proc, req_id: int, method: str, params: dict, timeout: float = 15) -> tuple[dict, list[dict]]:
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
    proc.stdin.flush()
    notifications = []
    end = time.time() + timeout
    while time.time() < end:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
            continue
        try:
            msg = json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if "id" in msg and msg["id"] == req_id:
            return msg, notifications
        if "method" in msg and "id" not in msg:
            notifications.append(msg)
    return {"error": "timeout"}, notifications


class TestACPIntegration:
    def test_initialize_and_session(self):
        proc, root = _start_server()
        try:
            resp, _ = _send(proc, 1, "initialize", {
                "protocolVersion": 1,
                "clientInfo": {"name": "test", "version": "0.1"},
            })
            result = resp.get("result", {})
            assert result["protocolVersion"] == 1
            assert result["agentInfo"]["name"] == "scriptorium"

            resp, _ = _send(proc, 2, "session/new", {"cwd": "."})
            sid = resp.get("result", {}).get("sessionId", "")
            assert sid.startswith("sess_")

            resp, _ = _send(proc, 3, "session/close", {"sessionId": sid})
            assert "result" in resp
        finally:
            proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=5)
            try:
                os.unlink(os.path.join(root, "data", "acp_pytest.db"))
            except OSError:
                pass

    def test_prompt_list_perspectives(self):
        proc, root = _start_server()
        try:
            _send(proc, 1, "initialize", {"protocolVersion": 1, "clientInfo": {"name": "test", "version": "0.1"}})
            resp, _ = _send(proc, 2, "session/new", {"cwd": "."})
            sid = resp["result"]["sessionId"]

            resp, notifs = _send(proc, 3, "session/prompt", {
                "sessionId": sid,
                "prompt": [{"type": "text", "text": "perspectives"}],
            })
            assert resp.get("result", {}).get("stopReason") == "end_turn"

            chunks = []
            for n in notifs:
                update = n.get("params", {}).get("update", {})
                if update.get("sessionUpdate") == "agent_message_chunk":
                    chunks.append(update.get("content", {}).get("text", ""))
            full_text = "".join(chunks)
            assert "lacan" in full_text
            assert "deleuze" in full_text
        finally:
            proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=5)
            try:
                os.unlink(os.path.join(root, "data", "acp_pytest.db"))
            except OSError:
                pass
