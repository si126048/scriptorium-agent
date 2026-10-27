"""Versioned academic drafts. The host writes; the plugin verifies, saves and exports."""

import hashlib
import json
import re
import time

from .core import ResearchTools

MARKER = re.compile(r"\[\[cite:(\d+)\]\]")


class Manuscripts:
    def __init__(self, tools: ResearchTools):
        self.tools = tools
        self.store = tools.store

    def _get(self, identifier):
        value = self.store.conn.execute(
            "SELECT * FROM manuscripts WHERE id=? AND project_id=?",
            (identifier, self.tools.project_id),
        ).fetchone()
        if not value:
            raise ValueError("MANUSCRIPT_NOT_AVAILABLE")
        return dict(value)

    def create(self, title: str, question: str) -> dict:
        if not title.strip() or len(title) > 300 or not question.strip() or len(question) > 10000:
            raise ValueError("INVALID_MANUSCRIPT")
        identifier = (
            "ms_"
            + hashlib.sha256(
                json.dumps([self.tools.project_id, title, question], ensure_ascii=False).encode()
            ).hexdigest()[:32]
        )
        with self.store.lock, self.store.conn:
            created = self.store.conn.execute(
                "INSERT OR IGNORE INTO manuscripts VALUES(?,?,?,?,?,?)",
                (identifier, self.tools.project_id, title, question, 1, time.time()),
            )
            value = self._get(identifier)
        return {
            "manuscript_id": identifier,
            "revision": value["revision"],
            "status": "draft",
            "title": title,
            "created": bool(created.rowcount),
        }

    def _check_references(self, references):
        for ref in references:
            doc = self.tools._document(ref["source_id"])
            current = self.tools.verify_quote(doc.id, ref["exact_quote"], ref["start"])
            if not current["verified"] or current["source_sha256"] != ref["source_sha256"]:
                raise ValueError("SOURCE_CHANGED_OR_UNAVAILABLE")

    def read(
        self, identifier: str, section_id: str | None = None, revision: int | None = None
    ) -> dict:
        with self.store.lock:
            manuscript = self._get(identifier)
            if not section_id:
                if revision is not None:
                    raise ValueError("SECTION_REQUIRED_FOR_HISTORY")
                sections = [
                    dict(s)
                    for s in self.store.conn.execute(
                        "SELECT section_id,title,position,revision,length(content) AS characters "
                        "FROM manuscript_sections WHERE manuscript_id=? ORDER BY position,section_id",
                        (identifier,),
                    )
                ]
                return {
                    "manuscript_id": identifier,
                    "title": manuscript["title"],
                    "question": manuscript["question"],
                    "revision": manuscript["revision"],
                    "sections": sections,
                    "status": "draft",
                }
            if revision is not None:
                found = self.store.conn.execute(
                    "SELECT payload FROM manuscript_history "
                    "WHERE manuscript_id=? AND section_id=? AND revision=?",
                    (identifier, section_id, revision),
                ).fetchone()
                if not found:
                    raise ValueError("SECTION_REVISION_NOT_FOUND")
                value = json.loads(found["payload"])
                self._check_references(value["citations"])
                return {**value, "historical": True, "manuscript_revision": manuscript["revision"]}
            found = self.store.conn.execute(
                "SELECT * FROM manuscript_sections WHERE manuscript_id=? AND section_id=?",
                (identifier, section_id),
            ).fetchone()
            if not found:
                raise ValueError("SECTION_NOT_FOUND")
            value = dict(found)
            value["citations"] = json.loads(value["citations"])
            self._check_references(value["citations"])
            value["available_revisions"] = [
                r[0]
                for r in self.store.conn.execute(
                    "SELECT revision FROM manuscript_history WHERE manuscript_id=? AND section_id=? ORDER BY revision",
                    (identifier, section_id),
                )
            ]
            return {**value, "manuscript_revision": manuscript["revision"], "historical": False}

    def write(
        self,
        identifier: str,
        section_id: str,
        title: str,
        content: str,
        expected_revision: int,
        citations: list[dict] | None = None,
        position: int = 0,
    ) -> dict:
        if not re.fullmatch(r"[\w-]{1,80}", section_id) or not title.strip() or len(title) > 300:
            raise ValueError("INVALID_SECTION")
        if len(content) > 50000 or not 0 <= position <= 1000:
            raise ValueError("SECTION_LIMIT_EXCEEDED")
        citations = citations or []
        if len(citations) > 50:
            raise ValueError("TOO_MANY_CITATIONS")
        markers = {int(n) for n in MARKER.findall(content)}
        if "[[cite:" in MARKER.sub("", content):
            raise ValueError("MALFORMED_CITATION_MARKER")
        if markers != set(range(1, len(citations) + 1)):
            raise ValueError("CITATION_MARKERS_MUST_MATCH_REFERENCES")
        with self.store.lock:
            self.store.conn.execute("BEGIN IMMEDIATE")
            try:
                manuscript = self._get(identifier)
                if manuscript["revision"] != expected_revision:
                    raise ValueError(
                        "REVISION_CONFLICT: read the current draft before applying changes"
                    )
                verified = []
                for reference in citations:
                    value = self.tools.verify_quote(
                        reference["source_id"], reference["quote"], reference.get("start")
                    )
                    if not value["verified"]:
                        raise ValueError(
                            "UNVERIFIED_MANUSCRIPT_CITATION:" + value.get("reason", "unknown")
                        )
                    verified.append(value)
                used = self.store.conn.execute(
                    "SELECT coalesce(sum(length(content)),0),count(*) FROM manuscript_sections "
                    "WHERE manuscript_id=? AND section_id!=?",
                    (identifier, section_id),
                ).fetchone()
                if used[0] + len(content) > 200000 or used[1] >= 100:
                    raise ValueError("MANUSCRIPT_LIMIT_EXCEEDED")
                revision = manuscript["revision"] + 1
                value = {
                    "manuscript_id": identifier,
                    "section_id": section_id,
                    "title": title,
                    "content": content,
                    "citations": verified,
                    "position": position,
                    "revision": revision,
                }
                self.store.conn.execute(
                    "INSERT OR REPLACE INTO manuscript_sections VALUES(?,?,?,?,?,?,?)",
                    (
                        identifier,
                        section_id,
                        position,
                        title,
                        content,
                        json.dumps(verified, ensure_ascii=False),
                        revision,
                    ),
                )
                self.store.conn.execute(
                    "INSERT INTO manuscript_history VALUES(?,?,?,?)",
                    (identifier, section_id, revision, json.dumps(value, ensure_ascii=False)),
                )
                self.store.conn.execute(
                    "UPDATE manuscripts SET revision=? WHERE id=?", (revision, identifier)
                )
                self.store.conn.commit()
                return {
                    "manuscript_id": identifier,
                    "section_id": section_id,
                    "revision": revision,
                    "verified_citations": len(verified),
                    "status": "draft",
                }
            except Exception:
                self.store.conn.rollback()
                raise

    def export(self, identifier: str, expected_revision: int) -> dict:
        with self.store.lock:
            self.store.conn.execute("BEGIN")
            try:
                manuscript = self._get(identifier)
                if manuscript["revision"] != expected_revision:
                    raise ValueError("REVISION_CONFLICT")
                sections = list(
                    self.store.conn.execute(
                        "SELECT * FROM manuscript_sections "
                        "WHERE manuscript_id=? ORDER BY position,section_id",
                        (identifier,),
                    )
                )
                if not sections or not any(s["content"].strip() for s in sections):
                    raise ValueError("MANUSCRIPT_HAS_NO_TEXT")
                text = "# " + manuscript["title"] + "\n\n"
                notes, trace, warnings = [], [], []
                for section in sections:
                    references = json.loads(section["citations"])
                    self._check_references(references)
                    mapping = {}
                    for index, ref in enumerate(references, 1):
                        doc = self.tools._document(ref["source_id"])
                        current = self.tools.verify_quote(doc.id, ref["exact_quote"], ref["start"])
                        if (
                            not current["verified"]
                            or current["source_sha256"] != ref["source_sha256"]
                        ):
                            raise ValueError("SOURCE_CHANGED_OR_UNAVAILABLE")
                        number = len(notes) + 1
                        mapping[index] = number
                        citation = doc.metadata.get("citation") or doc.metadata.get(
                            "title", doc.origin
                        )
                        citation = " ".join(citation.split())
                        uri = doc.metadata.get("source_uri")
                        notes.append(
                            f"[^{number}]: {citation}" + (f" — {uri}" if uri else "") + "."
                        )
                        trace.append({"footnote": number, **ref})
                    body = MARKER.sub(
                        lambda m, mapping=mapping: f"[^{mapping[int(m.group(1))]}]",
                        section["content"],
                    )
                    text += "## " + section["title"] + "\n\n" + body + "\n\n"
                    if not references:
                        warnings.append(
                            {"section_id": section["section_id"], "reason": "NO_LINKED_EVIDENCE"}
                        )
                if notes:
                    text += "---\n\n" + "\n\n".join(notes) + "\n"
                self.store.conn.commit()
                return {
                    "manuscript_id": identifier,
                    "revision": expected_revision,
                    "status": "draft",
                    "markdown": text,
                    "evidence_trace": trace,
                    "warnings": warnings,
                    "review_required": [
                        "核查作者归属和论据支持关系",
                        "按目标期刊整理书目和格式",
                        "人工审核后再使用",
                    ],
                }
            except Exception:
                self.store.conn.rollback()
                raise
