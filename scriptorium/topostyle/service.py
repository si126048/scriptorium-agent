from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from ..db import Store
from .provider import OllamaProvider


def now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def ensure_consent(store: Store, persona: dict[str, Any]) -> None:
    participant = store.get_participant(persona["project_id"], persona["participant_id"])
    if participant is None or participant.withdrawn_at or participant.consent_scope.withdrawn_at:
        raise PermissionError("PERSONA_CONSENT_WITHDRAWN")
    if participant.consent_scope.expires_at and participant.consent_scope.expires_at <= now():
        raise PermissionError("PERSONA_CONSENT_EXPIRED")


def create_persona(store: Store, project_id: str, participant_id: str, name: str, **values: Any) -> dict[str, Any]:
    participant = store.get_participant(project_id, participant_id)
    if participant is None:
        raise ValueError("PARTICIPANT_NOT_FOUND")
    if participant.withdrawn_at or participant.consent_scope.withdrawn_at:
        raise PermissionError("PERSONA_CONSENT_WITHDRAWN")
    persona = {"id": new_id("persona"), "project_id": project_id, "participant_id": participant_id, "name": name, "avatar": values.get("avatar", ""), "model": values.get("model", "qwen2.5:3b"), "mode": values.get("mode", "prompt"), "alpha": float(values.get("alpha", 0.8)), "status": "created", "created_at": now(), "updated_at": now()}
    return store.put_persona(persona)


def train_persona(store: Store, persona_id: str, provider: OllamaProvider | None = None) -> dict[str, Any]:
    import numpy as np
    from .pipeline import extract_features, serialize_result
    persona = store.get_persona(persona_id)
    if not persona:
        raise KeyError("PERSONA_NOT_FOUND")
    ensure_consent(store, persona)
    documents = store.list_documents(persona["project_id"], persona["participant_id"])
    texts = [d.text for d in documents if d.text.strip()]
    if len(texts) < 2:
        raise ValueError("TOPOSTYLE_INSUFFICIENT_SEGMENTS")
    provider = provider or OllamaProvider(model=persona["model"])
    embeddings = np.asarray(provider.embed(texts), dtype=np.float32)
    result = extract_features(texts, embeddings=embeddings)
    quadruples = []
    for segment in result.segments:
        try:
            item = provider.generate_structured("Extract one JSON quadruple with keys core, expression, sentiment, category, evidence.", {"text": segment["text"]})
        except RuntimeError:
            item = {"core": "", "expression": "", "sentiment": "", "category": "", "evidence": segment["text"]}
        item["segment_id"] = segment["id"]
        quadruples.append(item)
    payload = serialize_result(result)
    payload["quadruples"] = quadruples
    version = (store.list_persona_artifacts(persona_id)[0]["version"] + 1) if store.list_persona_artifacts(persona_id) else 1
    artifact = {"id": new_id("artifact"), "persona_id": persona_id, "version": version, "created_at": now(), "embedding_backend": "ollama", "data": payload}
    store.put_persona_artifact(artifact)
    persona.update({"status": "ready", "updated_at": now(), "latest_artifact_id": artifact["id"]})
    store.put_persona(persona)
    return artifact


def prompt_context(artifact: dict[str, Any], user_prompt: str) -> list[dict[str, str]]:
    data = artifact["data"]
    examples = [q.get("evidence", "") for q in data.get("quadruples", [])[:4] if q.get("evidence")]
    system = "你是一个风格模拟助手。你必须明确声明内容由 AI 生成，不声称自己是真实人物。保持授权 Persona 的表达风格，但不要泄露原文隐私。\n"
    if examples:
        system += "风格示例：\n" + "\n---\n".join(examples)
    return [{"role": "system", "content": system}, {"role": "user", "content": user_prompt}]
