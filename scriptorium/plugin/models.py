"""The small persistence contract used by the plugin, without legacy business objects."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ConsentScope(BaseModel):
    withdrawn_at: str | None = None
    expires_at: str | None = None

    def is_active(self) -> bool:
        if self.withdrawn_at:
            return False
        if self.expires_at:
            try:
                expiry = datetime.fromisoformat(self.expires_at)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=UTC)
                return expiry > datetime.now(UTC)
            except ValueError:
                return False
        return True


class Project(BaseModel):
    id: str
    name: str = ""


class SourceDocument(BaseModel):
    id: str
    project_id: str
    participant_id: str | None = None
    origin: str
    type: str = "txt"
    checksum: str
    text: str
    consent_scope: ConsentScope = Field(default_factory=ConsentScope)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceSpan(BaseModel):
    id: str
    document_id: str
    char_start: int
    char_end: int
    excerpt: str
    excerpt_hash: str

    @model_validator(mode="after")
    def valid_offsets(self):
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("INVALID_SPAN_OFFSETS")
        return self


class CitationInput(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=12000)
    start: int | None = Field(default=None, ge=0)
