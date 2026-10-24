from __future__ import annotations

import pytest

from scriptorium.annotation import CulturalAnnotator, load_gazetteer, GazetteerEntry
from scriptorium.models import EvidenceSpan


def _span(sid: str, text: str) -> EvidenceSpan:
    return EvidenceSpan(id=sid, document_id="d1", char_start=0, char_end=len(text),
                        excerpt=text, excerpt_hash="h" + sid)


class TestGazetteer:
    def test_load_gazetteer(self):
        entries = load_gazetteer()
        assert len(entries) > 0
        assert all(isinstance(e, GazetteerEntry) for e in entries)

    def test_entry_has_required_fields(self):
        entries = load_gazetteer()
        for e in entries:
            assert e.name
            assert e.entity_type
            assert e.context

    def test_entry_all_names(self):
        entry = GazetteerEntry(name="原神", aliases=["genshin"], entity_type="game", context="test")
        assert entry.all_names == ["原神", "genshin"]


class TestCulturalAnnotator:
    def test_annotate_game_reference(self):
        ann = CulturalAnnotator()
        spans = [_span("s1", "我最近在玩原神，感觉还不错")]
        results = ann.annotate(spans)
        names = [r.entity_name for r in results]
        assert "原神" in names

    def test_annotate_theorist(self):
        ann = CulturalAnnotator()
        spans = [_span("s1", "拉康的镜像阶段理论很有意思")]
        results = ann.annotate(spans)
        names = [r.entity_name for r in results]
        assert "拉康" in names

    def test_annotate_meme(self):
        ann = CulturalAnnotator()
        spans = [_span("s1", "每天都在内卷和躺平之间挣扎")]
        results = ann.annotate(spans)
        names = [r.entity_name for r in results]
        assert "内卷" in names
        assert "躺平" in names

    def test_no_false_positives(self):
        ann = CulturalAnnotator()
        spans = [_span("s1", "今天天气不错，我们去吃饭吧")]
        results = ann.annotate(spans)
        assert len(results) == 0

    def test_multiple_references_in_one_span(self):
        ann = CulturalAnnotator()
        spans = [_span("s1", "原神和明日方舟都是抽卡游戏")]
        results = ann.annotate(spans)
        names = [r.entity_name for r in results]
        assert "原神" in names
        assert "明日方舟" in names

    def test_alias_matching(self):
        ann = CulturalAnnotator()
        spans = [_span("s1", "genshin真的很好玩")]
        results = ann.annotate(spans)
        names = [r.entity_name for r in results]
        assert "原神" in names

    def test_confidence_is_one_for_gazetteer(self):
        ann = CulturalAnnotator()
        spans = [_span("s1", "拉康说的大他者")]
        results = ann.annotate(spans)
        for r in results:
            assert r.confidence == 1.0
            assert r.source == "gazetteer"

    def test_no_duplicate_annotations(self):
        ann = CulturalAnnotator()
        spans = [_span("s1", "原神原神原神")]
        results = ann.annotate(spans)
        genshin_results = [r for r in results if r.entity_name == "原神"]
        assert len(genshin_results) == 1

    def test_multiple_spans(self):
        ann = CulturalAnnotator()
        spans = [
            _span("s1", "我在玩原神"),
            _span("s2", "拉康的理论"),
            _span("s3", "今天天气好"),
        ]
        results = ann.annotate(spans)
        span_ids = {r.span_id for r in results}
        assert "s1" in span_ids
        assert "s2" in span_ids
        assert "s3" not in span_ids

    def test_annotate_text_convenience(self):
        ann = CulturalAnnotator()
        results = ann.annotate_text("三体是刘慈欣的杰作")
        names = [r.entity_name for r in results]
        assert "三体" in names

    def test_context_brief_populated(self):
        ann = CulturalAnnotator()
        results = ann.annotate_text("原神很好玩")
        for r in results:
            assert r.context_brief
            assert len(r.context_brief) > 5

    def test_entity_type_populated(self):
        ann = CulturalAnnotator()
        results = ann.annotate_text("原神和拉康")
        types = {r.entity_name: r.entity_type for r in results}
        assert types.get("原神") == "game"
        assert types.get("拉康") == "theorist"
