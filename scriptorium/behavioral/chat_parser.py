"""Chat file parsers for WeChat export formats."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

RETURN_SYMBOL = "\u23ce"
SEPARATOR_RE = re.compile(r"^-{10,}$")
TIMESTAMP_RE = re.compile(r"^\[(\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})\]$")
MESSAGE_RE = re.compile(r"^【(.+?)】：(.*)$")
MENTION_RE = re.compile(r"@([^\s@：:，,。！？!?]+)")
QUOTE_RE = re.compile(r"(?:引用|回复|reply)\s*[:：]?\s*([\w-]+)", re.IGNORECASE)


def load_participant_messages(path: str | Path) -> list[str]:
    """Load messages from participant_texts/*.txt format.

    Each line is one message, terminated by ⏎ (U+238E).
    Returns list of message strings with ⏎ stripped.
    """
    text = read_text(path)
    messages = []
    for line in text.splitlines():
        msg = line.rstrip().removesuffix(RETURN_SYMBOL).strip()
        if msg:
            messages.append(msg)
    return messages


def read_text(path: str | Path) -> str:
    """Read exports with UTF-8 first and GB18030 fallback."""
    p = Path(path)
    try:
        return p.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        return p.read_text(encoding='gb18030')


def stable_message_id(source_id: str, index: int, content: str) -> str:
    digest = hashlib.sha256(f'{source_id}:{index}:{content}'.encode()).hexdigest()[:16]
    return f'msg_{digest}'


def load_message_records(path: str | Path, source_id: str | None = None,
                         participant_id: str | None = None,
                         default_sender: str | None = None,
                         scene: str | None = None) -> list[dict[str, Any]]:
    """Parse a chat export without discarding sender, timing or raw offsets."""
    source_id = source_id or Path(path).stem
    participant_id = participant_id or source_id
    raw_text = read_text(path)
    parsed = parse_wechat_chat(path)
    records: list[dict[str, Any]] = []
    if parsed:
        cursor = 0
        for i, item in enumerate(parsed):
            content = item.content
            start = raw_text.find(content, cursor)
            if start < 0:
                start = cursor
            mid = stable_message_id(source_id, i, content)
            mentions = MENTION_RE.findall(content)
            quote_match = QUOTE_RE.search(content)
            has_reply = '回复' in content
            has_quote = '引用' in content
            records.append({
                'message_id': mid, 'source_id': source_id, 'participant_id': participant_id,
                'sender_id': item.sender, 'sender_raw': item.sender,
                'timestamp': item.timestamp.isoformat() if item.timestamp else None,
                'raw_text': content, 'normalized_text': content, 'index': i,
                'message_index': i, 'content': content, 'char_start': start,
                'char_end': start + len(content), 'mention_targets': mentions,
                'reply_to_message_id': (quote_match.group(1) if has_reply and quote_match else None),
                'quote_message_id': (quote_match.group(1) if has_quote and quote_match else None), 'scene': scene,
                'transform_annotations': [],
            })
            cursor = start + len(content)
        return records
    cursor = 0
    for i, line in enumerate(raw_text.splitlines()):
        content = line.rstrip().removesuffix(RETURN_SYMBOL).strip()
        if not content:
            continue
        start = raw_text.find(line, cursor)
        if start < 0:
            start = cursor
        mid = stable_message_id(source_id, i, content)
        quote_match = QUOTE_RE.search(content)
        has_reply = '回复' in content
        has_quote = '引用' in content
        records.append({
            'message_id': mid, 'source_id': source_id, 'participant_id': participant_id,
            'sender_id': default_sender, 'sender_raw': default_sender, 'timestamp': None,
            'raw_text': content, 'normalized_text': content, 'index': len(records),
            'message_index': len(records), 'content': content, 'char_start': start,
            'char_end': start + len(content), 'mention_targets': MENTION_RE.findall(content),
            'reply_to_message_id': (quote_match.group(1) if has_reply and quote_match else None),
            'quote_message_id': (quote_match.group(1) if has_quote and quote_match else None), 'scene': scene,
            'transform_annotations': [],
        })
        cursor = start + len(line)
    return records


def load_normalized_messages(path: str | Path, source_id: str | None = None,
                             participant_id: str | None = None,
                             default_sender: str | None = None,
                             scene: str | None = None) -> list[dict]:
    """Return stable, serializable messages for profile artifacts."""
    return load_message_records(path, source_id, participant_id, default_sender, scene)


@dataclass
class ChatMessage:
    sender: str
    content: str
    timestamp: datetime | None = None


def parse_wechat_chat(path: str | Path) -> list[ChatMessage]:
    """Parse WeChat multi-line export format from E:\\archive\\chat_*.txt.

    Format:
        -----------------------
        [YY-MM-DD HH:MM]
        -----------------------
        【sender】：content⏎
    """
    text = read_text(path)
    lines = text.splitlines()

    messages: list[ChatMessage] = []
    current_ts: datetime | None = None
    sep_count = 0

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        if SEPARATOR_RE.match(stripped):
            sep_count += 1
            continue

        ts_match = TIMESTAMP_RE.match(stripped)
        if ts_match and sep_count >= 1:
            try:
                current_ts = datetime.strptime(ts_match.group(1), "%y-%m-%d %H:%M")
            except ValueError:
                pass
            sep_count = 0
            continue

        sep_count = 0

        msg_match = MESSAGE_RE.match(stripped)
        if msg_match:
            sender = msg_match.group(1)
            content = msg_match.group(2).removesuffix(RETURN_SYMBOL).strip()

            if sender == "系统":
                continue

            messages.append(ChatMessage(sender=sender, content=content, timestamp=current_ts))
            continue

        # WeChat exports may wrap a single message across physical lines.
        # Preserve the continuation instead of silently dropping it.
        if messages and not stripped.startswith('【'):
            continuation = stripped.removesuffix(RETURN_SYMBOL).strip()
            if continuation:
                messages[-1].content = f"{messages[-1].content}\n{continuation}"

    return messages
