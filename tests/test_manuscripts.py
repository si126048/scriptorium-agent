import hashlib
import sqlite3

import pytest

from scriptorium.plugin.core import ResearchTools
from scriptorium.plugin.manuscripts import Manuscripts


def test_paper_write_revise_restore_export_and_restart(tmp_path):
    tools = ResearchTools(str(tmp_path))
    source = tools.import_source("制度使自由成为可行的实践。", citation="合成作者. 合成资料, 2026.")
    papers = Manuscripts(tools)
    paper = papers.create("自由的实践条件", "如何理解制度条件？")
    assert not papers.create(paper["title"], "如何理解制度条件？")["created"]
    mid = paper["manuscript_id"]
    with pytest.raises(ValueError, match="NO_TEXT"):
        papers.export(mid, 1)
    refs = [{"source_id": source["source_id"], "quote": "制度使自由成为可行的实践。"}]
    body = "本文将制度理解为行动的条件，而非单纯限制。[[cite:1]]"
    assert papers.write(mid, "intro", "引言", body, 1, refs)["revision"] == 2
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        papers.write(mid, "intro", "引言", "过时修改", 1)
    papers.write(mid, "intro", "引言", "待修订的表述。", 2)
    old = papers.read(mid, "intro", 2)
    assert old["content"] == body
    papers.write(mid, "intro", old["title"], old["content"], 3, refs)
    export = papers.export(mid, 4)
    assert "[^1]" in export["markdown"] and "合成作者" in export["markdown"]
    assert export["evidence_trace"][0]["exact_quote"] == refs[0]["quote"]
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        papers.export(mid, 2)
    tools.close()
    restarted = ResearchTools(str(tmp_path))
    assert Manuscripts(restarted).export(mid, 4)["markdown"] == export["markdown"]
    other = tmp_path / "other"
    other.mkdir()
    isolated = ResearchTools(str(other), str(tmp_path / ".scriptorium/research.sqlite3"))
    with pytest.raises(ValueError, match="NOT_AVAILABLE"):
        Manuscripts(isolated).read(mid)
    isolated.close()
    restarted.close()


@pytest.mark.parametrize(
    "kind,quote,body,reason",
    [
        ("text", "重复", "正文[[cite:1]]", "AMBIGUOUS"),
        ("bibliography", "重复", "正文[[cite:1]]", "BIBLIOGRAPHY"),
        ("text", "不存在", "正文[[cite:1]]", "QUOTE_NOT_FOUND"),
        ("text", "重复", "正文[[cite:x]]", "MALFORMED"),
    ],
)
def test_invalid_references_never_commit(tmp_path, kind, quote, body, reason):
    tools = ResearchTools(str(tmp_path))
    text = "重复" if kind == "bibliography" else "重复。重复。"
    source = tools.import_source(text, source_kind=kind)
    papers = Manuscripts(tools)
    mid = papers.create("测试", "测试问题")["manuscript_id"]
    with pytest.raises(ValueError, match=reason):
        papers.write(
            mid, "one", "正文", body, 1, [{"source_id": source["source_id"], "quote": quote}]
        )
    assert papers.read(mid)["revision"] == 1
    assert not papers.read(mid)["sections"]
    tools.close()


@pytest.mark.parametrize("withdraw", [True, False])
def test_export_rechecks_source_permission_and_integrity(tmp_path, withdraw):
    tools = ResearchTools(str(tmp_path))
    source = tools.import_source("可定位的证据。")
    papers = Manuscripts(tools)
    mid = papers.create("标题", "问题")["manuscript_id"]
    papers.write(
        mid,
        "one",
        "正文",
        "推论[[cite:1]]",
        1,
        [{"source_id": source["source_id"], "quote": "可定位的证据。"}],
    )
    doc = tools.store.get_document(source["source_id"])
    if withdraw:
        doc.consent_scope.withdrawn_at = "2026-10-27T00:00:00Z"
    else:
        doc.text += "篡改"
    tools.store.put_document(doc)
    with pytest.raises(ValueError, match="SOURCE_"):
        papers.export(mid, 2)
    tools.close()


def test_unrelated_database_is_not_modified(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE private_data(value TEXT)")
        db.execute("INSERT INTO private_data VALUES('preserve')")
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="NOT_A_PLUGIN_DATABASE"):
        ResearchTools(str(tmp_path), str(database))
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_future_plugin_schema_is_not_downgraded(tmp_path):
    database = tmp_path / "future.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE scriptorium_plugin(version INTEGER)")
        db.execute("INSERT INTO scriptorium_plugin VALUES(999)")
    with pytest.raises(ValueError, match="PLUGIN_SCHEMA_NOT_SUPPORTED"):
        ResearchTools(str(tmp_path), str(database))
