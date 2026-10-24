"""Project-scoped PostgreSQL adapter for the existing algorithms and interview state machine.

No sqlite connection or hidden default project is used. Documents and spans project to the
unified material store; old identities remain usable through typed entity mappings.
"""
from __future__ import annotations

from datetime import UTC, datetime
import math


from hermeneut.models import (AnalysisRun, ConceptCard, ConsentScope, EvidenceSpan,
                              InterviewSession, Participant, Project, SourceDocument)
from . import schema as db
from .service import ResearchError, row, rows
from .texts import quote_hash


class PostgresStore:
    def __init__(self, service, project_id, principal, *, corpus=False, job=None):
        self.service, self.project_id, self.principal, self.corpus = service, project_id, principal, corpus
        self.job = job
        with service.engine.connect() as c:
            service.access(c, project_id, principal)

    def get(self, kind, identifier):
        with self.service.engine.connect() as c:
            self.service.access(c, self.project_id, self.principal)
            item = row(c, db.entities, db.entities.c.project_id == self.project_id,
                       db.entities.c.kind == kind, db.entities.c.external_id == identifier)
            return item['payload'] if item else None

    def all(self, kind):
        with self.service.engine.connect() as c:
            self.service.access(c, self.project_id, self.principal)
            return [r['payload'] for r in rows(c, db.entities, db.entities.c.project_id == self.project_id,
                                              db.entities.c.kind == kind)]

    def put(self, kind, value):
        payload = value.model_dump(mode='json') if hasattr(value, 'model_dump') else dict(value)
        def finite(item):
            if isinstance(item, float) and not math.isfinite(item):
                return None
            if isinstance(item, dict):
                return {k: finite(v) for k, v in item.items()}
            if isinstance(item, list):
                return [finite(v) for v in item]
            return item
        payload = finite(payload)
        if self.job:
            payload['operation_id'] = self.job['id']
        if payload.get('project_id', self.project_id) != self.project_id:
            raise ResearchError('PROJECT_SCOPE_MISMATCH', 403)
        identifier = str(payload['id'])
        with self.service.engine.begin() as c:
            self.service.access(c, self.project_id, self.principal, True)
            if self.job:
                self.service.locked_job(c, self.job)
            if kind in {'interview', 'analysis_run'} and payload.get('participant_id') != '__corpus__':
                person = row(c, db.entities, db.entities.c.project_id == self.project_id,
                    db.entities.c.kind == 'participant', db.entities.c.external_id == payload.get('participant_id'))
                p = (person or {}).get('payload', {})
                if payload.get('state') != 'WITHDRAWN' and (not p or p.get('withdrawn_at')
                        or not ConsentScope.model_validate(p.get('consent_scope') or {}).is_active()):
                    raise ResearchError('PARTICIPANT_CONSENT_INACTIVE', 403)
            if kind in {'persona', 'persona_artifact', 'persona_conversation', 'metric', 'persona_message'}:
                persona_id = payload.get('persona_id') or (identifier if kind == 'persona' else None)
                if kind == 'persona_message':
                    conv = row(c, db.entities, db.entities.c.project_id == self.project_id,
                               db.entities.c.kind == 'persona_conversation', db.entities.c.external_id == payload['conversation_id'])
                    persona_id = (conv or {}).get('payload', {}).get('persona_id')
                persona = payload if kind == 'persona' else (row(c, db.entities,
                    db.entities.c.project_id == self.project_id, db.entities.c.kind == 'persona',
                    db.entities.c.external_id == persona_id) or {}).get('payload', {})
                participant = row(c, db.entities, db.entities.c.project_id == self.project_id,
                    db.entities.c.kind == 'participant', db.entities.c.external_id == persona.get('participant_id'))
                person = (participant or {}).get('payload', {})
                consent = ConsentScope.model_validate(person.get('consent_scope') or {})
                if (not person or person.get('withdrawn_at') or not consent.is_active()
                        or not person.get('permissions', {}).get('agent_simulation')):
                    raise ResearchError('PERSONA_CONSENT_WITHDRAWN', 403)
            old = row(c, db.entities, db.entities.c.project_id == self.project_id,
                      db.entities.c.kind == kind, db.entities.c.external_id == identifier)
            if old:
                c.execute(db.entities.update().where(db.entities.c.id == old['id']).values(
                    payload=payload, revision=old['revision'] + 1))
            else:
                c.execute(db.entities.insert().values(id=db.uid(), project_id=self.project_id, kind=kind,
                    external_id=identifier, payload=payload, revision=1, created_at=db.now()))
        return value

    def delete(self, kind, identifier):
        with self.service.engine.begin() as c:
            self.service.access(c, self.project_id, self.principal, True)
            c.execute(db.entities.delete().where(db.entities.c.project_id == self.project_id,
                db.entities.c.kind == kind, db.entities.c.external_id == identifier))

    def get_project(self, project_id):
        if project_id != self.project_id:
            return None
        with self.service.engine.connect() as c:
            p = self.service.access(c, project_id, self.principal)
        return Project(id=p['id'], name=p['name'], description=p['description'], owner_id=p['owner_id'])

    def create_project(self, p):
        if p.id != self.project_id:
            raise ResearchError('PROJECT_SCOPE_MISMATCH')
        return self.get_project(p.id)

    def get_participant(self, project_id, participant_id):
        if project_id != self.project_id:
            return None
        if self.corpus and participant_id == '__corpus__':
            # Internal algorithm parameter only, not a persisted or user-facing participant.
            return Participant(id='__corpus__', project_id=project_id, pseudonym='Material corpus', consent_scope=ConsentScope())
        p = self.get('participant', participant_id)
        return Participant.model_validate(p) if p else None

    def put_participant(self, p):
        return self.put('participant', p)

    def list_participants(self, project_id):
        return [Participant.model_validate(p) for p in self.all('participant')] if project_id == self.project_id else []

    def get_document(self, identifier):
        alias = self.get('document', identifier)
        aid = (alias or {}).get('metadata', {}).get('asset_id', identifier)
        try:
            result = self.service.get_segments(self.project_id, self.principal, aid)
        except ResearchError:
            return None
        with self.service.engine.connect() as c:
            a = self.service.asset(c, self.project_id, aid)
        participant = a['metadata'].get('participant_id')
        if participant:
            p = self.get_participant(self.project_id, participant)
            if not p or p.withdrawn_at or not p.consent_scope.is_active():
                return None
        text = '\n\n'.join(s['text'] for s in result['segments'])
        return SourceDocument(id=identifier, project_id=self.project_id,
            participant_id='__corpus__' if self.corpus else participant,
            origin=a['name'], type='txt', checksum=quote_hash(text), text=text,
            metadata={**a['metadata'], 'asset_id': aid})

    def list_documents(self, project_id, participant_id=None):
        if project_id != self.project_id:
            return []
        docs = []
        for a in self.service.list_materials(project_id, self.principal):
            if a['status'] != 'ready':
                continue
            if (participant_id is not None and not (self.corpus and participant_id == '__corpus__')
                    and a['metadata'].get('participant_id') != participant_id):
                continue
            doc = self.get_document(a['id'])
            if doc:
                docs.append(doc)
        return docs

    def put_document(self, d):
        from .worker import run_one
        j = self.service.import_material(self.project_id, self.principal, d.text.encode('utf-8'),
            f'{d.id}.txt', f'document-{d.id}', {'participant_id': None if self.corpus else d.participant_id,
                'purpose': 'theory' if d.participant_id is None else 'research'})
        run_one(self.service, j['id'])
        d.metadata['asset_id'] = j['payload']['asset_id']
        self.put('document', d)
        return d

    def find_document_by_checksum(self, project_id, checksum):
        return next((d for d in self.list_documents(project_id) if d.checksum == checksum), None)

    def search_materials(self, query, project_id=None, limit=5):
        from .search import search
        if project_id not in {None, self.project_id}:
            return []
        result = search(self.service, self.project_id, self.principal, query)
        return [{'document_id': r['asset_id'], 'span_id': r['id'], 'text': r['text'],
                 'snippet': r['snippet']} for r in result['items'][:limit]]

    def list_spans_for_document(self, identifier):
        d = self.get_document(identifier)
        if not d:
            return []
        aid = d.metadata['asset_id']
        segments = self.service.get_segments(self.project_id, self.principal, aid)['segments']
        offset, result = 0, []
        for s in segments:
            result.append(EvidenceSpan(id=s['id'], document_id=identifier, char_start=offset,
                char_end=offset + len(s['text']), excerpt=s['text'], excerpt_hash=quote_hash(s['text'])))
            offset += len(s['text']) + 2
        return result

    def get_span(self, identifier):
        with self.service.engine.connect() as c:
            s = row(c, db.segments, db.segments.c.id == identifier, db.segments.c.project_id == self.project_id)
        if s:
            return next((x for x in self.list_spans_for_document(s['asset_id']) if x.id == identifier), None)
        p = self.get('span', identifier)
        return EvidenceSpan.model_validate(p) if p else None

    def put_span(self, s):
        return self.put('span', s)

    def put_spans(self, spans):
        for s in spans:
            self.put_span(s)
        return spans

    def list_theory_spans(self, project_id):
        if project_id != self.project_id:
            return []
        result = []
        for d in self.list_documents(project_id):
            if d.metadata.get('purpose') == 'theory':
                result.extend(self.list_spans_for_document(d.id))
        return result

    def get_concept(self, identifier):
        p = self.get('concept', identifier)
        return ConceptCard.model_validate(p) if p else None

    def put_concept(self, value):
        return self.put('concept', value)

    def get_run(self, identifier):
        p = self.get('analysis_run', identifier)
        return AnalysisRun.model_validate(p) if p else None

    def get_run_by_idem(self, project_id, idem):
        if project_id != self.project_id:
            return None
        return next((AnalysisRun.model_validate(p) for p in self.all('analysis_run') if p.get('idempotency_key') == idem), None)

    def create_run_atomic(self, value):
        with self.service.engine.begin() as c:
            self.service.access(c, self.project_id, self.principal, True)
            old = self.get_run_by_idem(self.project_id, value.idempotency_key)
            if old:
                return old
            payload = value.model_dump(mode='json')
            c.execute(db.entities.insert().values(id=db.uid(), project_id=self.project_id,
                kind='analysis_run', external_id=value.id, payload=payload, revision=1, created_at=db.now()))
        return value

    def put_run(self, value):
        return self.put('analysis_run', value)

    def audit(self, run, actor, reason):
        run.audit.append({'actor': actor, 'timestamp': datetime.now(UTC).isoformat(), 'state': run.state, 'reason': reason})
        return self.put_run(run)

    def put_interview_session(self, value):
        return self.put('interview', value)

    def get_interview_session(self, identifier, project_id=None, participant_id=None):
        p = self.get('interview', identifier)
        if p and (project_id is None or p['project_id'] == project_id) and (
                participant_id is None or p['participant_id'] == participant_id):
            return InterviewSession.model_validate(p)
        return None

    def list_interview_sessions(self, project_id, participant_id):
        return [InterviewSession.model_validate(p) for p in self.all('interview')
                if p['participant_id'] == participant_id] if project_id == self.project_id else []

    def put_persona(self, p):
        return self.put('persona', p)

    def get_persona(self, identifier):
        return self.get('persona', identifier)

    def list_personas(self, project_id, participant_id=None):
        return [p for p in self.all('persona') if participant_id is None or p['participant_id'] == participant_id] if project_id == self.project_id else []

    def delete_persona(self, identifier):
        with self.service.engine.begin() as c:
            self.service.access(c, self.project_id, self.principal, True)
            for message in rows(c, db.messages, db.messages.c.project_id == self.project_id):
                if message['metadata'].get('persona_id') == identifier:
                    c.execute(db.messages.update().where(db.messages.c.id == message['id']).values(
                        content='[模拟对象已删除]', artifact_ids=[], metadata={'withdrawn': True}))
        conversation_ids = {p['id'] for p in self.all('persona_conversation') if p.get('persona_id') == identifier}
        for p in self.all('persona_message'):
            if p.get('conversation_id') in conversation_ids:
                self.delete('persona_message', p['id'])
        for kind in ('persona_artifact', 'persona_conversation', 'metric'):
            for p in self.all(kind):
                if p.get('persona_id') == identifier:
                    self.delete(kind, p['id'])
        self.delete('persona', identifier)

    def put_persona_artifact(self, p):
        return self.put('persona_artifact', p)

    def list_persona_artifacts(self, identifier):
        return sorted([p for p in self.all('persona_artifact') if p['persona_id'] == identifier],
                      key=lambda p: p['version'], reverse=True)

    def put_conversation(self, p):
        return self.put('persona_conversation', p)

    def get_conversation(self, identifier):
        return self.get('persona_conversation', identifier)

    def put_message(self, p):
        return self.put('persona_message', p)

    def list_messages(self, identifier):
        return sorted([p for p in self.all('persona_message') if p['conversation_id'] == identifier], key=lambda p: p.get('created_at', ''))

    def put_topology_metric(self, p):
        return self.put('metric', p)

    def list_topology_metrics(self, identifier, limit=100):
        return [p for p in self.all('metric') if p['persona_id'] == identifier][-limit:]
