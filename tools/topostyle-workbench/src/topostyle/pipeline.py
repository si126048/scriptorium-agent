from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

import networkx as nx
import numpy as np
from persim import PersistenceImager
from ripser import ripser
from sklearn.feature_extraction.text import TfidfVectorizer


@dataclass
class Segment:
    id: str
    source: str
    text: str
    index: int


@dataclass
class ExtractionResult:
    segments: list[Segment]
    embeddings: np.ndarray
    distance_matrix: np.ndarray
    diagrams: list[np.ndarray]
    landscape: np.ndarray
    graph: nx.Graph


def clean_text(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"[#*_>`~]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def segment_text(text: str, source: str, min_chars: int = 10, max_chars: int = 900) -> list[Segment]:
    pieces = [clean_text(p) for p in re.split(r"\n\s*\n|(?<=[。！？.!?])\s+", text)]
    pieces = [p for p in pieces if len(p) >= min_chars]
    result: list[Segment] = []
    for piece in pieces:
        for start in range(0, len(piece), max_chars):
            chunk = piece[start : start + max_chars].strip()
            if len(chunk) >= min_chars:
                result.append(Segment(f"{source}:{len(result)}", source, chunk, len(result)))
    return result


def load_segments(corpus_dir: Path) -> list[Segment]:
    segments: list[Segment] = []
    for path in sorted(corpus_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".txt", ".md"}:
            segments.extend(segment_text(path.read_text(encoding="utf-8"), path.name))
    if len(segments) < 2:
        raise ValueError("语料至少需要 2 个有效片段；请提供 .txt 或 .md 文件。")
    return segments


def _fallback_embeddings(texts: list[str]) -> np.ndarray:
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), min_df=1, max_features=384)
    matrix = vectorizer.fit_transform(texts).toarray().astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-8)


def build_cooccurrence_graph(texts: Iterable[str], window: int = 5, min_edge_count: int = 3) -> nx.Graph:
    graph = nx.Graph()
    for text in texts:
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        for i, token in enumerate(tokens):
            graph.add_node(token)
            for other in tokens[i + 1 : i + 1 + window]:
                if token != other:
                    if graph.has_edge(token, other):
                        graph[token][other]["weight"] += 1
                    else:
                        graph.add_edge(token, other, weight=1)
    graph.remove_edges_from([(a, b) for a, b, d in graph.edges(data=True) if d["weight"] < min_edge_count])
    graph.remove_nodes_from(list(nx.isolates(graph)))
    return graph


def _landscape(diagrams: list[np.ndarray], resolution: int = 100) -> np.ndarray:
    chunks: list[np.ndarray] = []
    for diagram in diagrams:
        finite = diagram[np.isfinite(diagram[:, 1])]
        finite = finite[(finite[:, 1] - finite[:, 0]) > 0.01]
        if len(finite) == 0:
            chunks.append(np.zeros(resolution, dtype=np.float32))
            continue
        pim = PersistenceImager(pixel_size=max((finite[:, 1].max() - finite[:, 0].min()) / resolution, 1e-3))
        pim.fit(finite)
        image = pim.transform(finite)
        chunks.append(np.asarray(image, dtype=np.float32).ravel()[:resolution])
        if chunks[-1].size < resolution:
            chunks[-1] = np.pad(chunks[-1], (0, resolution - chunks[-1].size))
    return np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)


def extract(segments: list[Segment], maxdim: int = 2) -> ExtractionResult:
    texts = [s.text for s in segments]
    embeddings = _fallback_embeddings(texts)
    similarity = np.clip(embeddings @ embeddings.T, -1, 1)
    distances = np.sqrt(np.maximum(0, 2 - 2 * similarity)).astype(np.float32)
    np.fill_diagonal(distances, 0)
    persistence = ripser(distances, distance_matrix=True, maxdim=maxdim)
    diagrams = persistence["dgms"]
    return ExtractionResult(segments, embeddings, distances, diagrams, _landscape(diagrams), build_cooccurrence_graph(texts))


def save_result(result: ExtractionResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "embeddings.npy", result.embeddings)
    np.save(output_dir / "distance_matrix.npy", result.distance_matrix)
    np.save(output_dir / "landscape.npy", result.landscape)
    for dim, diagram in enumerate(result.diagrams):
        np.savetxt(output_dir / f"persistence_h{dim}.csv", diagram, delimiter=",", header="birth,death", comments="")
    nx.write_graphml(result.graph, output_dir / "cooccurrence.graphml")
    (output_dir / "segments.json").write_text(json.dumps([asdict(s) for s in result.segments], ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "metadata.json").write_text(json.dumps({"n_segments": len(result.segments), "embedding_backend": "tfidf-char-fallback", "maxdim": len(result.diagrams) - 1}, indent=2), encoding="utf-8")
