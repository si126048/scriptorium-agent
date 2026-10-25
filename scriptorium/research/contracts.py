"""Stable OpenAPI response shapes used by every workbench client."""
from pydantic import BaseModel, ConfigDict, Field


class Resource(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str


class ProjectOut(Resource):
    name: str
    description: str
    owner_id: str
    created_at: float


class RecordPayload(BaseModel):
    model_config = ConfigDict(extra='allow')
    title: str = ''
    text: str = ''
    editor_json: dict | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)
    provider_mode: str | None = None
    status: str | None = None


class RecordOut(Resource):
    project_id: str
    kind: str
    revision: int
    payload: dict
    created_at: float
    updated_at: float


class VersionOut(Resource):
    quality: dict
    created_at: float


class MaterialOut(Resource):
    name: str
    status: str
    revision: int
    metadata: dict
    versions: list[VersionOut]


class AnchorOut(Resource):
    project_id: str
    segment_id: str
    start_codepoint: int
    end_codepoint: int
    exact_quote: str
    quote_sha256: str


class JobOut(Resource):
    project_id: str
    kind: str
    state: str
    payload: dict
    attempts: int = 0
    error: str | None = None
    result: dict | None = None
    created_at: float


class MessageOut(Resource):
    project_id: str
    conversation_id: str
    role: str
    content: str
    artifact_ids: list[str]
    metadata: dict
    created_at: float


class ScopeItem(BaseModel):
    asset_id: str
    version_id: str | None = None
    segment_id: str | None = None
    start_codepoint: int | None = None
    end_codepoint: int | None = None
    exact_quote: str | None = None


class ConversationOut(Resource):
    project_id: str
    title: str
    archived: bool
    revision: int
    workspace: dict
    created_at: float


class DecisionOut(Resource):
    run_id: str
    project_id: str
    conversation_id: str | None = None
    kind: str
    state: str
    payload: dict


class ChapterOut(Resource):
    record_id: str
    project_id: str
    ordinal: int
    revision: int
    payload: dict
    created_at: float


class SegmentOut(Resource):
    asset_id: str
    version_id: str
    xml_id: str
    text: str
    page_label: str | None = None


class ReadingPartOut(BaseModel):
    segment: SegmentOut
    start: int
    end: int
    text: str


class ReadingOut(BaseModel):
    version: VersionOut
    page: int
    total: int
    parts: list[ReadingPartOut]
    total_segments: int
    total_codepoints: int


class CitationLabelOut(BaseModel):
    anchor_id: str
    label: str
    version_id: str
