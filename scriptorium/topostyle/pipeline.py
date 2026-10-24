from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    from ripser import ripser
except ImportError:  # pragma: no cover
    ripser = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
except ImportError:  # pragma: no cover
    TfidfVectorizer = None


@dataclass
class FeatureResult:
    segments: list[dict[str, Any]]
    embeddings: np.ndarray
    distance_matrix: np.ndarray
    diagrams: list[np.ndarray]
    betti_curve: list[list[float]]
    quadruples: list[dict[str, Any]]


def clean_text(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"[#*_>`~]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def segment_text(text: str, source: str, min_chars: int = 10, max_chars: int = 900) -> list[dict[str, Any]]:
    pieces = [clean_text(p) for p in re.split(r"\n\s*\n|(?<=[。！？.!?])\s+", text)]
    pieces = [p for p in pieces if len(p) >= min_chars]
    result: list[dict[str, Any]] = []
    for piece in pieces:
        for start in range(0, len(piece), max_chars):
            chunk = piece[start : start + max_chars].strip()
            if len(chunk) >= min_chars:
                result.append({"id": f"{source}:{len(result)}", "source": source, "text": chunk})
    return result


def _embed(texts: list[str], embeddings: np.ndarray | None = None) -> np.ndarray:
    if embeddings is not None:
        matrix = np.asarray(embeddings, dtype=np.float32)
    else:
        if TfidfVectorizer is None:
            raise RuntimeError("TOPOSTYLE_EMBEDDING_BACKEND_UNAVAILABLE")
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), max_features=384)
        matrix = vectorizer.fit_transform(texts).toarray().astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-8)


def _betti_curve(diagrams: list[np.ndarray], points: int = 32) -> list[list[float]]:
    result: list[list[float]] = []
    for diagram in diagrams:
        finite = diagram[np.isfinite(diagram[:, 1])] if len(diagram) else diagram
        if len(finite) == 0:
            result.append([0.0] * points)
            continue
        hi = max(float(finite[:, 1].max()), 1e-6)
        grid = np.linspace(0.0, hi, points)
        result.append([float(np.sum((finite[:, 0] <= t) & (finite[:, 1] > t))) for t in grid])
    return result


def extract_features(texts: list[str], embeddings: np.ndarray | None = None, maxdim: int = 2) -> FeatureResult:
    if len(texts) < 2:
        raise ValueError("TOPOSTYLE_INSUFFICIENT_SEGMENTS")
    matrix = _embed(texts, embeddings)
    similarity = np.clip(matrix @ matrix.T, -1.0, 1.0)
    distances = np.sqrt(np.maximum(0.0, 2.0 - 2.0 * similarity)).astype(np.float32)
    np.fill_diagonal(distances, 0)
    if ripser is None:
        raise RuntimeError("TOPOSTYLE_RIPS_DEPENDENCY_MISSING")
    diagrams = ripser(distances, distance_matrix=True, maxdim=maxdim)["dgms"]
    segments = [{"id": f"segment_{i}", "text": text} for i, text in enumerate(texts)]
    quadruples = [{"segment_id": s["id"], "core": "", "expression": "", "sentiment": "", "category": "", "evidence": s["text"]} for s in segments]
    return FeatureResult(segments, matrix, distances, diagrams, _betti_curve(diagrams), quadruples)


def serialize_result(result: FeatureResult) -> dict[str, Any]:
    return {
        "segments": result.segments,
        "embeddings": result.embeddings.tolist(),
        "distance_matrix": result.distance_matrix.tolist(),
        "diagrams": [d.tolist() for d in result.diagrams],
        "betti_curve": result.betti_curve,
        "quadruples": result.quadruples,
    }


def serialize_json(result: FeatureResult) -> str:
    return json.dumps(serialize_result(result), ensure_ascii=False)
