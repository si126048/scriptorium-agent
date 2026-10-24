from pathlib import Path

import numpy as np

from topostyle.pipeline import build_cooccurrence_graph, extract, load_segments


def test_extract_and_persist(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("我喜欢把复杂问题拆开。然后逐步验证每一个假设。\n\n我会记录结果，并在下一轮继续改进。", encoding="utf-8")
    segments = load_segments(corpus)
    result = extract(segments)
    assert len(segments) >= 2
    assert result.distance_matrix.shape == (len(segments), len(segments))
    assert np.allclose(np.diag(result.distance_matrix), 0)

def test_graph_filters_weak_edges():
    graph = build_cooccurrence_graph(["alpha beta gamma", "alpha beta gamma", "alpha beta gamma"])
    assert graph["alpha"]["beta"]["weight"] == 3
