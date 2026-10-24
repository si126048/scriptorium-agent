from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_CREDENTIAL_PATTERNS = [
    re.compile(r'(?:sk|pk|ak|key|token|secret|password|passwd|pwd)[-_]?[a-zA-Z0-9]{16,}', re.IGNORECASE),
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),
    re.compile(r'gho_[a-zA-Z0-9]{36}'),
    re.compile(r'github_pat_[a-zA-Z0-9_]{82}'),
    re.compile(r'xox[baprs]-[a-zA-Z0-9-]+'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}'),
    re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----'),
    re.compile(r'AIza[a-zA-Z0-9_-]{35}'),
]

def detect_credentials(text: str) -> list[dict]:
    if not text:
        return []
    findings = []
    for i, pat in enumerate(_CREDENTIAL_PATTERNS):
        for m in pat.finditer(text):
            findings.append({
                'pattern_index': i,
                'start': m.start(),
                'end': m.end(),
                'match': m.group()[:8] + '...' if len(m.group()) > 8 else m.group(),
            })
    if findings:
        logger.warning("detected %d potential credential(s) in text", len(findings))
    return findings

def redact_credentials(text: str) -> str:
    if not text:
        return text
    result = text
    for pat in _CREDENTIAL_PATTERNS:
        result = pat.sub('[REDACTED]', result)
    return result

def has_credentials(text: str) -> bool:
    return bool(detect_credentials(text))
