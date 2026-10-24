from __future__ import annotations

import itertools
import json
import logging
import os
import re
from dataclasses import dataclass

from .models import CulturalAnnotation, EvidenceSpan

logger = logging.getLogger(__name__)

GAZETTEER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "cultural_gazetteer.json"
)


@dataclass
class GazetteerEntry:
    name: str
    aliases: list[str]
    entity_type: str
    context: str

    @property
    def all_names(self) -> list[str]:
        return [self.name] + self.aliases


def load_gazetteer(path: str | None = None) -> list[GazetteerEntry]:
    path = path or GAZETTEER_PATH
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = []
    for item in data:
        entries.append(GazetteerEntry(
            name=item["name"],
            aliases=item.get("aliases", []),
            entity_type=item["type"],
            context=item["context"],
        ))
    return entries


class CulturalAnnotator:
    def __init__(self, gazetteer_path: str | None = None,
                 confidence_threshold: float = 0.5):
        self._entries = load_gazetteer(gazetteer_path)
        self._patterns = self._compile_patterns()
        self._confidence_threshold = confidence_threshold
        self._counter = itertools.count(1)

    def _compile_patterns(self) -> list[tuple[re.Pattern, GazetteerEntry]]:
        patterns = []
        for entry in self._entries:
            for name in entry.all_names:
                escaped = re.escape(name)
                is_cjk = bool(re.search(r'[\u4e00-\u9fff]', name))
                if is_cjk:
                    pat = re.compile(escaped, re.IGNORECASE)
                else:
                    pat = re.compile(rf'(?<![a-zA-Z]){escaped}(?![a-zA-Z])', re.IGNORECASE)
                patterns.append((pat, entry))
        return patterns

    def annotate(self, spans: list[EvidenceSpan]) -> list[CulturalAnnotation]:
        annotations: list[CulturalAnnotation] = []
        seen: set[tuple[str, str]] = set()

        for span in spans:
            for pat, entry in self._patterns:
                if pat.search(span.excerpt):
                    key = (span.id, entry.name)
                    if key not in seen:
                        seen.add(key)
                        annotation = CulturalAnnotation(
                            id=f"ca_{next(self._counter):04d}",
                            span_id=span.id,
                            entity_name=entry.name,
                            entity_type=entry.entity_type,
                            confidence=1.0,
                            context_brief=entry.context,
                            source="gazetteer",
                        )
                        if annotation.confidence >= self._confidence_threshold:
                            annotations.append(annotation)

        logger.info("annotated %d spans, found %d cultural references",
                     len(spans), len(annotations))
        return annotations

    def annotate_text(self, text: str, span_id: str = "inline") -> list[CulturalAnnotation]:
        span = EvidenceSpan(
            id=span_id, document_id="inline",
            char_start=0, char_end=len(text),
            excerpt=text, excerpt_hash="inline",
        )
        return self.annotate([span])
