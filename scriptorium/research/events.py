"""Ordered conversation events: committed state and resumable user-visible progress."""
import sqlalchemy as sa
from . import schema as db


def emit(c, pid, cid, kind, payload):
    if not cid:
        return
    conversation = c.execute(sa.select(db.conversations.c.id).where(
        db.conversations.c.id == cid, db.conversations.c.project_id == pid).with_for_update()).first()
    if not conversation:
        return
    seq = c.execute(sa.select(sa.func.coalesce(sa.func.max(db.conversation_events.c.sequence), 0))
        .where(db.conversation_events.c.conversation_id == cid)).scalar() + 1
    item = {'id': db.uid(), 'project_id': pid, 'conversation_id': cid, 'sequence': seq,
            'type': kind, 'payload': payload, 'created_at': db.now()}
    c.execute(db.conversation_events.insert().values(**item))
    return item
