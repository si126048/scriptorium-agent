# Derived from MISAKA-Agent (https://github.com/Luciole-Studio/Misaka-Agent)
# Copyright 2026 Luciole Studio. Licensed under Apache License 2.0.
# See NOTICE and LICENSE-MISAKA in the project root.

"""Hierarchical outline detection for plain-text and Markdown documents.

Ported from MISAKA-Agent's text_outline.py. Reads structure from a text
file's own headings -- CHAPTER XII, LIVRE III, BOOK IV, Markdown # headings.
Conservative: requires at least 3 headings, drops running heads, rejects
all-caps noise.
"""
from __future__ import annotations

import re
from collections import Counter

MIN_NODES = 3
MAX_TITLE_CHARS = 120
MAX_TITLE_WORDS = 14
LOOKAHEAD_LINES = 3
RUNNING_HEAD_REPEATS = 3
CAPS_NOISE_RATIO = 0.4

_LEVEL_KEYWORDS = {
    1: ("BOOK", "PART", "VOLUME", "VOL", "TOME", "LIVRE", "PARTIE", "BUCH", "TEIL", "LIBRO", "PARTE"),
    2: ("CHAPTER", "CHAP", "CHAPITRE", "KAPITEL", "CAPITOLO", "CAPITULO", "CAPÍTULO", "LETTER", "LETTRE",
        "APPENDIX", "APPENDICE", "ANNEXE", "ANHANG"),
    3: ("SECTION", "SECT", "ARTICLE", "ART", "§"),
}
_KEYWORD_LEVEL = {word: level for level, words in _LEVEL_KEYWORDS.items() for word in words}
_ORDINALS = ("FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH|"
             "PREMIER|PREMIÈRE|PREMIERE|DEUXIÈME|DEUXIEME|SECONDE?|TROISIÈME|TROISIEME|QUATRIÈME|QUATRIEME|"
             "CINQUIÈME|CINQUIEME|SIXIÈME|SIXIEME|SEPTIÈME|SEPTIEME|HUITIÈME|HUITIEME|NEUVIÈME|NEUVIEME|"
             "DIXIÈME|DIXIEME|DERNIER|DERNIÈRE|DERNIERE")
_NUMBER = rf"(?:[IVXLCDM]+|\d+|(?-i:[A-Z])|{_ORDINALS})"
_STRUCTURAL = re.compile(
    r"^(?P<kw>" + "|".join(re.escape(word) for word in sorted(_KEYWORD_LEVEL, key=len, reverse=True)) + r")"
    rf"(?:\.\s*|\s+|(?<=§)\s*)(?P<num>{_NUMBER})(?![A-Za-z])\.?:?(?P<rest>.*)$",
    re.IGNORECASE)
_ORDINAL_FIRST = re.compile(
    rf"^(?P<num>{_ORDINALS})\s+(?P<kw>LIVRE|PARTIE|CHAPITRE|LETTRE|TOME|BOOK|PART|CHAPTER)\b\.?:?(?P<rest>.*)$",
    re.IGNORECASE)
_MARKDOWN = re.compile(r"^(#{1,6})\s+(\S.*?)\s*#*\s*$")
_ROMAN_LINE = re.compile(r"^(?:[IVXLCDM]{2,8}\.?|[IVXLCDM]\.)$")
_CAPS_LINE = re.compile(r"^[A-Z0-9À-Þ][A-Z0-9À-Þ ,.;:'\-—–()&]{3,}$")
_STANDALONE = frozenset({
    "CONTENTS", "TABLE OF CONTENTS", "PREFACE", "INTRODUCTION", "INDEX", "EPILOGUE", "PROLOGUE",
    "CONCLUSION", "BIBLIOGRAPHY", "NOTES", "GLOSSARY", "APPENDIX", "AVANT-PROPOS", "PRÉFACE", "PREFACE.",
    "AVERTISSEMENT", "TABLE DES MATIÈRES", "TABLE", "ERRATA", "DEDICATION", "FOREWORD", "AFTERWORD",
})


def build_text_tree(pages: list[str], *, markdown: bool = False) -> list[dict] | None:
    candidates = _without_running_heads(_candidates(pages, markdown=markdown))
    if sum(1 for c in candidates if c["kind"] != "caps") >= MIN_NODES:
        candidates = [c for c in candidates if c["kind"] != "caps" or c["standalone"]]
    elif sum(1 for c in candidates if c["kind"] == "caps") > CAPS_NOISE_RATIO * max(1, len(pages)):
        candidates = [c for c in candidates if c["kind"] != "caps"]
    candidates = _dedup(candidates)
    if len(candidates) < MIN_NODES or len(candidates) > max(20, 2 * len(pages)):
        return None
    return _nest(candidates, len(pages))


def _dedup(candidates):
    out = []
    for candidate in candidates:
        if out and out[-1]["page"] == candidate["page"] and out[-1]["key"] == candidate["key"]:
            continue
        out.append(candidate)
    return out


def _candidates(pages, *, markdown):
    found = []
    for page_number, page in enumerate(pages, 1):
        lines = page.split("\n")
        taken = set()
        for index, raw in enumerate(lines):
            if index in taken:
                continue
            line = " ".join(raw.split())
            if not line or len(line) > MAX_TITLE_CHARS:
                continue
            if not _standalone_line(lines, index):
                continue
            heading = _classify(line, markdown=markdown)
            if heading is None:
                continue
            kind, level, title, wants_title, standalone = heading
            if wants_title:
                extra = _title_after(lines, index, taken)
                if extra:
                    title = f"{title} {extra}"
            found.append({"page": page_number, "level": level, "title": title, "kind": kind,
                          "standalone": standalone, "key": _running_head_key(title)})
    return found


def _standalone_line(lines, index):
    above = index == 0 or not lines[index - 1].strip()
    below = index + 1 >= len(lines) or not lines[index + 1].strip() or _CAPS_LINE.match(lines[index + 1].strip())
    return above and bool(below)


def _classify(line, *, markdown):
    if markdown:
        match = _MARKDOWN.match(line)
        if match:
            return "markdown", len(match.group(1)), match.group(2).strip(), False, False
    match = _STRUCTURAL.match(line) or _ORDINAL_FIRST.match(line)
    if match:
        level = _KEYWORD_LEVEL[match.group("kw").upper().rstrip(".")]
        rest = match.group("rest").strip(" .:-—–")
        return "numbered", level, line.rstrip(" ."), not rest, False
    if _ROMAN_LINE.match(line):
        return "numeral", 2, line.rstrip("."), True, False
    upper = line.rstrip(" .:").upper()
    if upper in _STANDALONE:
        return "caps", 1, line.rstrip(" .:"), False, True
    if _CAPS_LINE.match(line) and _looks_like_title(line):
        return "caps", 2, line.rstrip(" ."), False, False
    return None


def _looks_like_title(line):
    letters = sum(c.isalpha() for c in line)
    words = [w for w in re.split(r"[\s—–-]+", line) if w]
    return (letters >= 4 and letters / max(1, len(line)) >= 0.5 and len(words) <= MAX_TITLE_WORDS
            and any(sum(c.isalpha() for c in w) >= 3 for w in words) and not line.endswith((",", ";")))


def _title_after(lines, index, taken):
    for offset in range(1, LOOKAHEAD_LINES + 1):
        at = index + offset
        if at >= len(lines):
            return ""
        text = " ".join(lines[at].split())
        if not text:
            continue
        if _CAPS_LINE.match(text) and _looks_like_title(text) and not _STRUCTURAL.match(text):
            taken.add(at)
            return text.rstrip(" .")
        return ""
    return ""


def _running_head_key(title):
    return re.sub(r"\s+", " ", re.sub(r"[\d.,;:'()&\-—–]", " ", title.upper())).strip()


def _without_running_heads(candidates):
    def headish(c):
        return c["kind"] == "caps" or (c["kind"] == "numeral" and " " not in c["title"])
    repeats = Counter(c["key"] for c in candidates if headish(c))
    return [c for c in candidates if not (headish(c) and repeats[c["key"]] >= RUNNING_HEAD_REPEATS)]


def _nest(candidates, page_count):
    for position, current in enumerate(candidates):
        end = page_count
        for later in candidates[position + 1:]:
            if later["level"] <= current["level"]:
                end = max(current["page"], later["page"] - 1)
                break
        current["end"] = end
    roots, stack, counter = [], [], [0]

    def node_for(candidate):
        counter[0] += 1
        return {"title": candidate["title"], "node_id": f"{counter[0] - 1:04d}",
                "start_index": candidate["page"], "end_index": candidate["end"], "nodes": []}

    for candidate in candidates:
        while stack and stack[-1][0] >= candidate["level"]:
            stack.pop()
        node = node_for(candidate)
        (stack[-1][1]["nodes"] if stack else roots).append(node)
        stack.append((candidate["level"], node))
    return _prune(roots)


def _prune(nodes):
    for node in nodes:
        if node["nodes"]:
            _prune(node["nodes"])
        else:
            del node["nodes"]
    return nodes
