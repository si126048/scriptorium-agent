"""Single-pass feature extractor for message statistics."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

MEDIA_TAGS = {"[表情]", "[图片]", "[视频]", "[分享]", "[音频]", "[文件]"}
MEDIA_RE = re.compile(r"^\[(?:表情|图片|视频|分享|音频|文件)\]$")
QUOTE_RE = re.compile(r"^\[引用\]")
MENTION_RE = re.compile(r"@(\S+)")
BRACKET_RE = re.compile(r"[（(]([^）)]{1,30})[）)]")
REPEATED_PUNCT_RE = re.compile(r"([？！!?\?~～…\.])\1+")
EMOJI_RANGES = re.compile(
    "[\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f1e0-\U0001f1ff"
    "\U00002702-\U000027b0"
    "\U000024c2-\U0001f251"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\U00002600-\U000026ff"
    "\U00002300-\U000023ff]"
)
CJK_PUNCT = "？！。、，；：…—～·「」『』【】《》〈〉"
ASCII_PUNCT = "?!.,;:~"
ALL_PUNCT = CJK_PUNCT + ASCII_PUNCT + "()"
MODAL_PARTICLES = list("啊呢吧嘛哦呀啦呗喽哇呐")
SELF_CORRECTIONS = ["等等", "不对", "我是说", "我在说什么", "说错了", "重说", "算了"]
ONOMATOPOEIA_PATTERNS = [
    r"(.)\1{2,}",
]
SELF_REF = {"我": "我", "本人": "本人", "俺": "俺", "老子": "老子", "爷": "爷", "咱": "咱"}
JP_KANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
EN_WORD_RE = re.compile(r"[a-zA-Z]{2,}")


@dataclass
class ExtractorResult:
    """Raw extraction output before model conversion."""

    total_messages: int = 0
    total_chars: int = 0
    msg_lengths: list[int] = field(default_factory=list)

    bigram_counts: Counter = field(default_factory=Counter)
    trigram_counts: Counter = field(default_factory=Counter)
    media_counts: Counter = field(default_factory=Counter)
    emoji_total: int = 0
    emoji_msg_count: int = 0

    punct_counts: Counter = field(default_factory=Counter)
    question_msgs: int = 0
    exclamation_msgs: int = 0
    ellipsis_msgs: int = 0
    repeated_punct_msgs: int = 0
    bracket_contents: list[str] = field(default_factory=list)
    modal_counts: Counter = field(default_factory=Counter)

    first_chars: Counter = field(default_factory=Counter)
    last_chars: Counter = field(default_factory=Counter)
    mention_targets: Counter = field(default_factory=Counter)
    quote_replies: int = 0
    pure_media_msgs: int = 0

    self_corrections: int = 0
    onomatopoeia_samples: list[str] = field(default_factory=list)
    self_ref_counts: Counter = field(default_factory=Counter)
    jp_kana_msgs: int = 0
    en_word_msgs: int = 0
    en_word_samples: list[str] = field(default_factory=list)

    all_ngrams: Counter = field(default_factory=Counter)

    def msg_count_with(self, attr: str) -> int:
        return getattr(self, attr)


class MessageExtractor:
    """Single-pass message statistics accumulator."""

    def __init__(self):
        self.result = ExtractorResult()

    def feed(self, msg: str) -> None:
        r = self.result
        r.total_messages += 1
        text_len = len(msg)
        r.total_chars += text_len
        r.msg_lengths.append(text_len)

        is_media_only = bool(MEDIA_RE.match(msg))
        if is_media_only:
            r.pure_media_msgs += 1
            r.media_counts[msg] += 1
            return

        if QUOTE_RE.match(msg):
            r.quote_replies += 1

        for m in MENTION_RE.finditer(msg):
            target = m.group(1).strip()
            if target:
                r.mention_targets[target] += 1

        emoji_in_msg = EMOJI_RANGES.findall(msg)
        if emoji_in_msg:
            r.emoji_total += len(emoji_in_msg)
            r.emoji_msg_count += 1

        has_q = False
        has_excl = False
        has_ellipsis = False

        for ch in msg:
            if ch in ALL_PUNCT:
                r.punct_counts[ch] += 1
            if ch == "？" or ch == "?":
                has_q = True
            if ch == "！" or ch == "!":
                has_excl = True
            if ch in "…~" or (ch == "." and msg.count(".") >= 2):
                has_ellipsis = True
            if ch == "～":
                has_ellipsis = True

        if has_q:
            r.question_msgs += 1
        if has_excl:
            r.exclamation_msgs += 1
        if has_ellipsis:
            r.ellipsis_msgs += 1
        if REPEATED_PUNCT_RE.search(msg):
            r.repeated_punct_msgs += 1

        for bm in BRACKET_RE.finditer(msg):
            r.bracket_contents.append(bm.group(1))

        if text_len > 0:
            r.first_chars[msg[0]] += 1
            clean_end = msg.rstrip("⏎ \t")
            if clean_end:
                r.last_chars[clean_end[-1]] += 1

        for mp in MODAL_PARTICLES:
            count = msg.count(mp)
            if count > 0:
                r.modal_counts[mp] += count

        for sc in SELF_CORRECTIONS:
            if sc in msg:
                r.self_corrections += 1
                break

        for pattern in ONOMATOPOEIA_PATTERNS:
            for m in re.finditer(pattern, msg):
                char = m.group(1)
                if "\u4e00" <= char <= "\u9fff":
                    sample = m.group(0)
                    if len(sample) <= 6:
                        r.onomatopoeia_samples.append(sample)
                    break

        for term, label in SELF_REF.items():
            if term in msg:
                r.self_ref_counts[label] += 1

        if JP_KANA_RE.search(msg):
            r.jp_kana_msgs += 1

        msg_no_url = re.sub(r"https?://\S+", "", msg)
        en_words = EN_WORD_RE.findall(msg_no_url)
        if en_words:
            r.en_word_msgs += 1
            r.en_word_samples.extend(w.lower() for w in en_words)

        clean = re.sub(r"\s+", "", msg) if msg else ""
        clean = re.sub(r"\[(?:表情|图片|视频|分享|音频|文件|引用)\]", "", clean)
        clean = re.sub(r"https?://\S+", "", clean)
        clean = re.sub(r"[a-fA-F0-9]{8,}", "", clean)
        for ch in ALL_PUNCT + "[]" + "\u23ce":
            clean = clean.replace(ch, "")
        clean = clean.strip()

        cjk_count = sum(1 for c in clean if "\u4e00" <= c <= "\u9fff")
        if len(clean) >= 2 and (cjk_count >= len(clean) * 0.3 or len(clean) <= 6):
            for i in range(len(clean) - 1):
                r.bigram_counts[clean[i : i + 2]] += 1
            for i in range(len(clean) - 2):
                r.trigram_counts[clean[i : i + 3]] += 1
            for n in range(3, min(8, len(clean) + 1)):
                for i in range(len(clean) - n + 1):
                    r.all_ngrams[clean[i : i + n]] += 1

    def feed_all(self, messages: list[str]) -> None:
        for msg in messages:
            self.feed(msg)

    def summarize(self) -> dict:
        r = self.result
        n = r.total_messages or 1
        lengths = r.msg_lengths or [0]

        sorted_bigrams = r.bigram_counts.most_common(30)
        sorted_trigrams = r.trigram_counts.most_common(20)

        punct_density = {}
        total_chars = r.total_chars or 1
        for ch, cnt in r.punct_counts.most_common(15):
            punct_density[ch] = round(cnt / total_chars * 100, 3)

        sorted_openers = [ch for ch, _ in r.first_chars.most_common(10)]
        sorted_closers = [ch for ch, _ in r.last_chars.most_common(10)]

        unique_ono = list(dict.fromkeys(r.onomatopoeia_samples))[:10]
        unique_brackets = list(dict.fromkeys(r.bracket_contents))[:15]

        return {
            "total_messages": r.total_messages,
            "total_chars": r.total_chars,
            "avg_msg_length": round(statistics.mean(lengths), 1),
            "median_msg_length": round(statistics.median(lengths), 1),
            "msg_length_std": round(statistics.stdev(lengths), 1) if len(lengths) > 1 else 0,
            "short_msg_ratio": round(sum(1 for l in lengths if l <= 5) / n, 3),
            "single_char_ratio": round(sum(1 for l in lengths if l == 1) / n, 3),
            "long_msg_count": sum(1 for l in lengths if l > 100),
            "media_ratio": round(
                sum(r.media_counts.values()) / n, 3
            ),
            "emoji_density": round(r.emoji_total / n, 2),
            "emoji_msg_ratio": round(r.emoji_msg_count / n, 3),
            "top_bigrams": sorted_bigrams,
            "top_trigrams": sorted_trigrams,
            "top_punctuation": punct_density,
            "question_ratio": round(r.question_msgs / n, 3),
            "exclamation_ratio": round(r.exclamation_msgs / n, 3),
            "ellipsis_ratio": round(r.ellipsis_msgs / n, 3),
            "repeated_punct_ratio": round(r.repeated_punct_msgs / n, 3),
            "opening_patterns": sorted_openers,
            "closing_patterns": sorted_closers,
            "bracket_insertions": unique_brackets,
            "modal_particles": dict(r.modal_counts.most_common(12)),
            "quote_reply_ratio": round(r.quote_replies / n, 3),
            "pure_media_ratio": round(r.pure_media_msgs / n, 3),
            "mention_targets": dict(r.mention_targets.most_common(10)),
            "self_corrections": r.self_corrections,
            "onomatopoeia": unique_ono,
            "self_ref_counts": dict(r.self_ref_counts),
            "jp_kana_ratio": round(r.jp_kana_msgs / n, 3),
            "en_word_ratio": round(r.en_word_msgs / n, 3),
            "en_word_samples": list(dict.fromkeys(r.en_word_samples))[:20],
            "all_ngrams": r.all_ngrams,
        }


def compute_signature_phrases(
    profiles: dict[str, dict], top_k: int = 10
) -> dict[str, list[str]]:
    """Find n-grams that are distinctive for each participant vs others.

    Returns {pseudonym: [signature_ngram, ...]}.
    """
    results: dict[str, list[str]] = {}

    for pid, pdata in profiles.items():
        my_ngrams: Counter = pdata.get("all_ngrams", Counter())
        if not my_ngrams:
            results[pid] = []
            continue

        other_counts: Counter = Counter()
        for other_pid, other_data in profiles.items():
            if other_pid == pid:
                continue
            other_ngrams = other_data.get("all_ngrams", Counter())
            other_counts += other_ngrams

        total_my = sum(my_ngrams.values()) or 1
        total_other = sum(other_counts.values()) or 1

        scores: dict[str, float] = {}
        for ngram, cnt in my_ngrams.items():
            if cnt < 3:
                continue
            if len(set(ngram)) == 1:
                continue
            if "@" in ngram:
                continue
            my_freq = cnt / total_my
            other_freq = other_counts.get(ngram, 0) / total_other
            if other_freq == 0 and cnt >= 5:
                scores[ngram] = my_freq * 10
            elif other_freq > 0:
                ratio = my_freq / (other_freq + 1e-6)
                if ratio > 3 and cnt >= 3:
                    scores[ngram] = my_freq * ratio

        top = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
        results[pid] = [ng for ng, _ in top]

    return results


def compute_unique_expressions(
    profiles: dict[str, dict], top_k: int = 10
) -> dict[str, list[str]]:
    """Find n-grams that appear ONLY in one participant's messages."""
    results: dict[str, list[str]] = {}

    all_ngram_sets: dict[str, set[str]] = {}
    for pid, pdata in profiles.items():
        all_ngram_sets[pid] = set(pdata.get("all_ngrams", Counter()).keys())

    for pid, pdata in profiles.items():
        my_ngrams = pdata.get("all_ngrams", Counter())
        others_ngrams: set[str] = set()
        for other_pid, other_set in all_ngram_sets.items():
            if other_pid != pid:
                others_ngrams |= other_set

        unique = {ng for ng in my_ngrams if ng not in others_ngrams and my_ngrams[ng] >= 2 and len(set(ng)) > 1 and "@" not in ng}
        top = sorted(unique, key=lambda ng: -my_ngrams[ng])[:top_k]
        results[pid] = top

    return results
