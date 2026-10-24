from datetime import UTC, datetime

from scriptorium.db import Store
from scriptorium.models import ConsentScope, Participant, Project


def test_persona_artifact_and_conversation_roundtrip(tmp_path):
    store = Store(str(tmp_path / "topostyle.sqlite"))
    store.create_project(Project(id="p"))
    store.put_participant(Participant(id="u", project_id="p", pseudonym="u", consent_scope=ConsentScope()))
    persona = store.put_persona({"id": "persona_1", "project_id": "p", "participant_id": "u", "name": "demo"})
    assert store.get_persona(persona["id"])["name"] == "demo"
    timestamp = datetime.now(UTC).isoformat()
    store.put_persona_artifact({"id": "artifact_1", "persona_id": "persona_1", "version": 1, "created_at": timestamp, "data": {"diagrams": []}})
    assert store.list_persona_artifacts("persona_1")[0]["version"] == 1
    store.put_conversation({"id": "conv_1", "persona_id": "persona_1", "created_at": timestamp, "updated_at": timestamp})
    store.put_message({"id": "msg_1", "conversation_id": "conv_1", "role": "user", "content": "hello", "created_at": timestamp})
    assert store.list_messages("conv_1")[0]["content"] == "hello"
    store.delete_persona("persona_1")
    assert store.get_persona("persona_1") is None
