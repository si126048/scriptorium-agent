"""Tests for the Scriptorium MCP server."""
from __future__ import annotations

import asyncio

import pytest

from scriptorium.mcp_server import (
    handle_list_tools,
    handle_call_tool,
    _perspectives,
    _search_docs,
    _ensure_setup,
)


@pytest.fixture(autouse=True)
def _set_mock_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "mcp_test.db")
    monkeypatch.setenv("LACAN_DB_PATH", db_path)
    monkeypatch.setenv("LACAN_MOCK", "1")
    import scriptorium.mcp_server as mod
    mod._store = None
    mod._provider = None


class TestListTools:
    def test_returns_four_tools(self):
        tools = asyncio.run(handle_list_tools())
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert names == {
            "scriptorium_analyze",
            "scriptorium_dialectical",
            "scriptorium_perspectives",
            "scriptorium_search",
        }

    def test_tools_have_descriptions(self):
        tools = asyncio.run(handle_list_tools())
        for t in tools:
            assert t.description
            assert t.inputSchema


class TestCallTool:
    def test_perspectives(self):
        result = asyncio.run(
            handle_call_tool("scriptorium_perspectives", {})
        )
        assert len(result) == 1
        text = result[0].text
        assert "lacan" in text
        assert "deleuze" in text

    def test_analyze_text(self):
        result = asyncio.run(
            handle_call_tool("scriptorium_analyze", {"text": "重复是一种习惯性的享乐。"})
        )
        assert len(result) == 1
        text = result[0].text
        assert "Observation" in text or "Hypothesis" in text or "obs" in text.lower()

    def test_analyze_empty_text(self):
        result = asyncio.run(
            handle_call_tool("scriptorium_analyze", {"text": ""})
        )
        assert "Error" in result[0].text

    def test_dialectical(self):
        result = asyncio.run(
            handle_call_tool("scriptorium_dialectical", {"text": "重复是一种习惯性的享乐。"})
        )
        assert len(result) == 1
        text = result[0].text
        assert "Phase 1" in text
        assert "Phase 2" in text or "Phase 3" in text

    def test_search_empty(self):
        result = asyncio.run(
            handle_call_tool("scriptorium_search", {"query": ""})
        )
        assert "Error" in result[0].text

    def test_unknown_tool(self):
        result = asyncio.run(
            handle_call_tool("nonexistent", {})
        )
        assert "Unknown tool" in result[0].text


class TestFormatters:
    def test_perspectives_format(self):
        result = _perspectives()
        assert len(result) == 1
        assert "lacan" in result[0].text
        assert "Concepts" in result[0].text

    def test_search_no_results(self):
        _ensure_setup()
        result = _search_docs({"query": "nonexistent_term_xyz"})
        assert "No results" in result[0].text
