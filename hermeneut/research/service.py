from __future__ import annotations

import json
import os
from pathlib import Path

import sqlalchemy as sa

from . import schema as db
from .storage import object_store
from .texts import build_tei, extract, project_tei, quote_hash


# A worker from an older build must never convert a newer job kind into a permanent failure.
SUPPORTED_JOB_KINDS = frozenset({'import', 'ocr', 'method', 'workspace', 'persona_train'})


class ResearchError(Exception):
    def __init__(self, code: str, status=400):
        self.code, self.status = code, status
        super().__init__(code)


class UnsupportedJobKind(ResearchError):
    """Raised by a worker that is older than the job it claimed; the job must stay queued."""

    def __init__(self, kind: str):
        self.kind = kind
        super().__init__('UNSUPPORTED_JOB_KIND', 409)


def row(connection, table, *where):
    value = connection.execute(sa.select(table).where(*where)).mappings().first()
    return dict(value) if value else None


def rows(connection, table, *where):
    return [dict(r) for r in connection.execute(sa.select(table).where(*where)).mappings()]


class ResearchService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.objects = object_store(settings)

    def access(self, c, project_id, principal, write=False):
        query = sa.select(db.projects).where(db.projects.c.id == project_id)
        if write:
            query = query.with_for_update()
        project_row = c.execute(query).mappings().first()
        project = dict(project_row) if project_row else None
        member = row(c, db.members, db.members.c.project_id == project_id, db.members.c.user_id == principal)
        if not project or not member or (write and member['role'] not in {'owner', 'editor'}):
            raise ResearchError('PROJECT_NOT_FOUND', 404)
        return project

    def create_project(self, principal, name, description='', project_id=None):
        p = {'id': project_id or db.uid(), 'name': name, 'description': description,
                 'owner_id': principal, 'created_at': db.now()}
        with self.engine.begin() as c:
            c.execute(db.projects.insert().values(**p))
            c.execute(db.members.insert().values(project_id=p['id'], user_id=principal, role='owner'))
        return p

    def list_projects(self, principal):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(sa.select(db.projects).join(db.members).where(
                db.members.c.user_id == principal).order_by(db.projects.c.created_at)).mappings()]

    def asset(self, c, project_id, asset_id, *, include_revoked=False, check_consent=True):
        a = row(c, db.assets, db.assets.c.id == asset_id, db.assets.c.project_id == project_id)
        if not a or (a['status'] == 'revoked' and not include_revoked):
            raise ResearchError('MATERIAL_NOT_FOUND', 404)
        if check_consent and not include_revoked and a['metadata'].get('participant_id'):
            from hermeneut.models import ConsentScope
            person = row(c, db.entities, db.entities.c.project_id == project_id,
                db.entities.c.kind == 'participant', db.entities.c.external_id == a['metadata']['participant_id'])
            p = (person or {}).get('payload', {})
            if not p or p.get('withdrawn_at') or not ConsentScope.model_validate(p.get('consent_scope') or {}).is_active():
                raise ResearchError('PARTICIPANT_CONSENT_INACTIVE', 403)
        return a

    def enqueue(self, c, project_id, kind, payload, idem):
        digest = quote_hash(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        # Lock the project to serialize concurrent identical submissions, including first insert.
        c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == project_id).with_for_update())
        existing = row(c, db.jobs, db.jobs.c.project_id == project_id,
                       db.jobs.c.kind == kind, db.jobs.c.idem == idem)
        if existing:
            if existing['request_hash'] != digest:
                raise ResearchError('IDEMPOTENCY_CONFLICT', 409)
            return existing
        job = {'id': db.uid(), 'project_id': project_id, 'kind': kind, 'idem': idem,
                   'request_hash': digest, 'payload': payload, 'state': 'queued', 'attempts': 0,
                   'created_at': db.now()}
        c.execute(db.jobs.insert().values(**job))
        self.event(c, job['id'], {'state': 'queued'})
        return job

    def event(self, c, job_id, data):
        c.execute(db.events.insert().values(id=db.uid(), job_id=job_id, created_at=db.now(), data=data))
        job = row(c, db.jobs, db.jobs.c.id == job_id)
        if job and job['payload'].get('conversation_id'):
            from .events import emit
            emit(c, job['project_id'], job['payload']['conversation_id'], 'job.progress',
                 {'job_id': job_id, 'run_id': job['payload'].get('run_id'), **data})

    def import_material(self, project_id, principal, raw, filename, idem, metadata=None):
        if len(raw) > self.settings.max_upload_bytes:
            raise ResearchError('UPLOAD_TOO_LARGE', 413)
        filename = Path(filename.replace('\\', '/')).name
        if (Path(filename).suffix.lower() not in {'.txt', '.md', '.pdf', '.xml', '.tei'}
                and not (metadata or {}).get('legacy_transcription')):
            raise ResearchError('UNSUPPORTED_FORMAT', 415)
        with self.engine.begin() as c:
            self.access(c, project_id, principal, True)
            # Authorization happens before object writes. Content keys disclose no project membership.
            key, digest = self.objects.put(raw)
            request = {'sha256': digest, 'filename': filename, 'metadata': metadata or {}}
            job = self.enqueue(c, project_id, 'import', request, idem)
            if job.get('payload', {}).get('asset_id'):
                return job
            if job['state'] != 'queued':
                raise ResearchError('IDEMPOTENCY_KEY_RETIRED', 409)
            work_id, edition_id, asset_id = db.uid(), db.uid(), db.uid()
            c.execute(db.works.insert().values(id=work_id, project_id=project_id,
                      title=filename, metadata=metadata or {}))
            c.execute(db.editions.insert().values(id=edition_id, work_id=work_id,
                      metadata={'status': 'unverified', **(metadata or {})}))
            c.execute(db.assets.insert().values(id=asset_id, project_id=project_id,
                      edition_id=edition_id, name=filename, object_key=key, sha256=digest,
                      size=len(raw), status='pending', revision=1,
                      metadata=metadata or {}, created_at=db.now()))
            payload = {**request, 'asset_id': asset_id}
            c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(payload=payload))
            return {**job, 'payload': payload}

    def register_text(self, c, a, tei, quality, *, parent=None):
        parsed = project_tei(tei)
        key, _ = self.objects.put(tei)
        version_id = db.uid()
        c.execute(db.versions.insert().values(id=version_id, asset_id=a['id'], parent_id=parent,
                  object_key=key, projection_version='reading.v1', quality=quality, created_at=db.now()))
        c.execute(db.segments.insert(), [dict(id=db.uid(), project_id=a['project_id'],
                  asset_id=a['id'], version_id=version_id, **segment) for segment in parsed])
        c.execute(db.assets.update().where(db.assets.c.id == a['id']).values(
            status='ready', revision=a['revision'] + 1))
        c.execute(db.outbox.insert().values(id=db.uid(), project_id=a['project_id'],
                  asset_id=a['id'], revision=a['revision'] + 1, done=False, attempts=0, created_at=db.now()))
        return version_id

    def list_materials(self, project_id, principal):
        with self.engine.connect() as c:
            self.access(c, project_id, principal)
            result = rows(c, db.assets, db.assets.c.project_id == project_id, db.assets.c.status != 'revoked')
            for a in result:
                a['versions'] = rows(c, db.versions, db.versions.c.asset_id == a['id'])
            return result

    def get_segments(self, project_id, principal, asset_id, version_id=None):
        with self.engine.connect() as c:
            self.access(c, project_id, principal)
            self.asset(c, project_id, asset_id)
            if version_id:
                v = c.execute(sa.select(db.versions).where(db.versions.c.asset_id == asset_id,
                    db.versions.c.id == version_id)).mappings().first()
            else:
                # The latest version is the revision chain's tip, not simply the newest timestamp:
                # two versions written in the same second must not be ordered arbitrarily.
                tip = self.latest_version_id(c, asset_id)
                v = c.execute(sa.select(db.versions).where(db.versions.c.id == tip)).mappings().first() if tip else None
            if not v:
                raise ResearchError('TEXT_VERSION_NOT_FOUND', 404)
            result = c.execute(sa.select(db.segments).where(db.segments.c.version_id == v['id'])
                               .order_by(db.segments.c.ordinal)).mappings()
            return {'version': dict(v), 'segments': [dict(r) for r in result]}

    @staticmethod
    def latest_version_id(c, asset_id):
        versions = c.execute(sa.select(db.versions.c.id, db.versions.c.parent_id, db.versions.c.created_at)
            .where(db.versions.c.asset_id == asset_id)).mappings().all()
        if not versions:
            return None
        parents = {v['parent_id'] for v in versions if v['parent_id']}
        tips = [v for v in versions if v['id'] not in parents]
        newest = max(tips or versions, key=lambda v: (v['created_at'], v['id']))
        return newest['id']

    def revise_text(self, project_id, principal, asset_id, tei, revision):
        with self.engine.begin() as c:
            self.access(c, project_id, principal, True)
            c.execute(sa.select(db.assets.c.id).where(db.assets.c.id == asset_id).with_for_update())
            a = self.asset(c, project_id, asset_id)
            if a['revision'] != revision:
                raise ResearchError('REVISION_CONFLICT', 409)
            return self.register_text(c, a, tei, {'responsibility': principal, 'status': 'researcher_revision'},
                                      parent=self.latest_version_id(c, asset_id))

    def make_anchor(self, c, project_id, segment_id, start, end, exact_quote):
        s = row(c, db.segments, db.segments.c.id == segment_id, db.segments.c.project_id == project_id)
        if not s:
            raise ResearchError('SEGMENT_NOT_FOUND', 404)
        c.execute(sa.select(db.assets.c.id).where(db.assets.c.id == s['asset_id']).with_for_update())
        self.asset(c, project_id, s['asset_id'])
        if not (0 <= start < end <= len(s['text'])) or s['text'][start:end] != exact_quote:
            raise ResearchError('QUOTE_RANGE_MISMATCH', 422)
        a = {'id': db.uid(), 'project_id': project_id, 'segment_id': segment_id,
                 'start_codepoint': start, 'end_codepoint': end, 'exact_quote': exact_quote,
                 'quote_sha256': quote_hash(exact_quote)}
        c.execute(db.anchors.insert().values(**a))
        return a

    def validate_evidence(self, c, project_id, payload):
        from .documents import citation_ids
        evidence_ids = list(payload.get('evidence_ids', [])) + citation_ids(payload.get('editor_json'))
        for finding in payload.get('findings', []):
            evidence_ids.extend(finding.get('evidence_ids', []))
        for aid in evidence_ids:
            anchor = row(c, db.anchors, db.anchors.c.id == aid, db.anchors.c.project_id == project_id)
            if not anchor:
                raise ResearchError('INVALID_EVIDENCE', 422)
            segment = row(c, db.segments, db.segments.c.id == anchor['segment_id'])
            self.asset(c, project_id, segment['asset_id'])
            if segment['text'][anchor['start_codepoint']:anchor['end_codepoint']] != anchor['exact_quote']:
                raise ResearchError('EVIDENCE_INTEGRITY_ERROR', 422)

    def put_record(self, c, project_id, kind, payload, record_id=None, revision=None):
        self.validate_evidence(c, project_id, payload)
        self.validate_references(c, project_id, kind, payload, record_id)
        t = db.now()
        if record_id:
            old = row(c, db.records, db.records.c.id == record_id,
                      db.records.c.project_id == project_id, db.records.c.kind == kind)
            if not old:
                raise ResearchError('RECORD_NOT_FOUND', 404)
            updated = c.execute(db.records.update().where(db.records.c.id == record_id,
                                db.records.c.revision == revision).values(
                                payload=payload, revision=revision + 1, updated_at=t))
            if not updated.rowcount:
                raise ResearchError('REVISION_CONFLICT', 409)
            c.execute(db.record_history.insert().values(record_id=record_id,
                      revision=old['revision'], payload=old['payload'], created_at=t))
            return {**old, 'payload': payload, 'revision': revision + 1, 'updated_at': t}
        result = {'id': db.uid(), 'project_id': project_id, 'kind': kind,
                      'revision': 1, 'payload': payload, 'created_at': t, 'updated_at': t}
        c.execute(db.records.insert().values(**result))
        return result

    def validate_references(self, c, project_id, kind, payload, record_id=None):
        refs = []
        for field in ('from_id', 'to_id', 'position_id', 'criterion_id', 'difficulty_id', 'target_id', 'parent_id'):
            if payload.get(field):
                refs.append(payload[field])
        refs.extend(payload.get('source_record_ids', []))
        for rid in refs:
            if not row(c, db.records, db.records.c.id == rid, db.records.c.project_id == project_id):
                raise ResearchError('INVALID_RECORD_REFERENCE', 422)
        if kind == 'branch' and record_id:
            seen = {record_id}
            parent = payload.get('parent_id')
            while parent:
                if parent in seen:
                    raise ResearchError('RESEARCH_CYCLE_FORBIDDEN', 422)
                seen.add(parent)
                parent_record = row(c, db.records, db.records.c.id == parent)
                parent = parent_record['payload'].get('parent_id') if parent_record else None
        if kind == 'difficulty' and payload.get('difficulty_type') == 'internal':
            if not payload.get('position_id') or not payload.get('criterion_id') or not payload.get('evidence_ids'):
                raise ResearchError('INTERNAL_DIFFICULTY_REQUIRES_POSITION_CRITERION_EVIDENCE', 422)
            criterion = row(c, db.records, db.records.c.id == payload['criterion_id'])
            if criterion['kind'] != 'criterion':
                raise ResearchError('CRITERION_REQUIRED', 422)
        if kind == 'transition' and (not payload.get('difficulty_id') or not payload.get('retained')
                                     or not payload.get('negated') or not payload.get('reason')
                                     or not payload.get('from_id') or not payload.get('to_id')):
            raise ResearchError('TRANSITION_REQUIRES_GROUNDS', 422)
        if kind == 'transition':
            d = row(c, db.records, db.records.c.id == payload['difficulty_id'])
            if d['kind'] != 'difficulty' or d['payload'].get('difficulty_type') != 'internal':
                raise ResearchError('TRANSITION_REQUIRES_INTERNAL_DIFFICULTY', 422)
            for field in ('from_id', 'to_id'):
                p = row(c, db.records, db.records.c.id == payload[field])
                if p['kind'] != 'position':
                    raise ResearchError('TRANSITION_REQUIRES_POSITIONS', 422)
        if kind == 'parallax' and payload.get('status') not in {
            'difference_only', 'resolvable', 'candidate_gap', 'reviewed_gap_hypothesis', 'undetermined'}:
            raise ResearchError('INVALID_PARALLAX_STATUS', 422)
        if (kind == 'parallax' and payload.get('status') in {'candidate_gap', 'reviewed_gap_hypothesis'}
                and not all(payload.get(f) for f in ('from_id', 'to_id', 'shift', 'excluded_causes',
                                                     'rebuttal_conditions', 'evidence_ids'))):
            raise ResearchError('PARALLAX_REQUIRES_POSITIONS_SHIFT_CHECKS_AND_EVIDENCE', 422)

    def claim_job(self, job_id=None, kinds=None):
        t = db.now()
        supported = sorted(SUPPORTED_JOB_KINDS if kinds is None else kinds)
        with self.engine.begin() as c:
            # Expired final attempts become failures rather than remaining stuck indefinitely.
            c.execute(db.jobs.update().where(db.jobs.c.state == 'running', db.jobs.c.lease_until < t,
                db.jobs.c.attempts >= self.settings.max_attempts).values(state='failed', error='LEASE_EXHAUSTED'))
            c.execute(db.jobs.update().where(db.jobs.c.state == 'cancel_requested',
                sa.or_(db.jobs.c.lease_until.is_(None), db.jobs.c.lease_until < t)).values(state='cancelled'))
            query = sa.select(db.jobs).where(sa.or_(sa.and_(db.jobs.c.state == 'queued',
                sa.or_(db.jobs.c.lease_until.is_(None), db.jobs.c.lease_until <= t)), sa.and_(
                db.jobs.c.state == 'running', db.jobs.c.lease_until < t)),
                db.jobs.c.kind.in_(supported),
                db.jobs.c.attempts < self.settings.max_attempts).order_by(db.jobs.c.created_at)
            if job_id:
                query = query.where(db.jobs.c.id == job_id)
            j = c.execute(query.with_for_update(skip_locked=True).limit(1)).mappings().first()
            if not j:
                return None
            token = db.uid()
            c.execute(db.jobs.update().where(db.jobs.c.id == j['id']).values(state='running',
                attempts=j['attempts'] + 1, lease_until=t + self.settings.lease_seconds, lease_token=token))
            self.event(c, j['id'], {'state': 'running', 'attempt': j['attempts'] + 1})
            return {**j, 'lease_token': token}

    def defer_job(self, c, job, delay_seconds=1):
        """Waiting for another worker is scheduling, not a failed processing attempt.

        lease_until also acts as the not-before time while queued. Clearing the token fences
        the yielding worker and lets the queue service child jobs instead of spinning on its
        older coordinator. Actual crashed attempts remain charged.
        """
        self.locked_job(c, job)
        c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(
            state='queued', lease_until=db.now() + delay_seconds, lease_token=None,
            attempts=sa.func.greatest(0, db.jobs.c.attempts - 1)))

    def heartbeat(self, job):
        with self.engine.begin() as c:
            c.execute(db.jobs.update().where(db.jobs.c.id == job['id'],
                db.jobs.c.state == 'running', db.jobs.c.lease_token == job['lease_token']).values(
                lease_until=db.now() + self.settings.lease_seconds))

    def locked_job(self, c, job):
        current = c.execute(sa.select(db.jobs).where(db.jobs.c.id == job['id']).with_for_update()).mappings().one()
        if current['lease_token'] != job['lease_token'] or current['state'] != 'running':
            raise ResearchError('JOB_NO_LONGER_OWNED', 409)

    def process_job(self, job):
        if job['kind'] in {'import', 'ocr'}:
            with self.engine.connect() as c:
                a = self.asset(c, job['project_id'], job['payload']['asset_id'], check_consent=False)
            raw = self.objects.read(a['object_key'])
            if job['kind'] == 'ocr':
                from .texts import ocr_pdf
                pages, quality = ocr_pdf(raw, job['payload'].get('language', 'chi_sim+eng'),
                                         job['payload'].get('engine') or self.settings.ocr_engine)
                tei = build_tei(pages, a['name'])
            elif a['metadata'].get('legacy_transcription'):
                tei = build_tei([a['metadata']['legacy_transcription']], a['name'])
                quality = {'extractor': 'legacy-transcription', 'review_state': 'unreviewed',
                           'original_processing': 'unsupported format retained; using legacy stored text'}
            elif Path(a['name']).suffix.lower() in {'.xml', '.tei'}:
                tei, quality = raw, {'extractor': 'tei-import', 'subset': 'hermeneut.v1'}
                project_tei(tei)
            else:
                pages, quality = extract(raw, a['name'])
                tei = build_tei(pages, a['name'])
            with self.engine.begin() as c:
                # Serialize text commits and revocation on the same material.
                c.execute(sa.select(db.assets).where(db.assets.c.id == a['id']).with_for_update())
                self.locked_job(c, job)
                a = self.asset(c, job['project_id'], a['id'], check_consent=False)
                result = {'asset_id': a['id'], 'version_id': self.register_text(c, a, tei, quality)}
                if job['kind'] == 'ocr':
                    # The original stays authoritative: OCR only adds an unreviewed transcription.
                    c.execute(db.assets.update().where(db.assets.c.id == a['id']).values(metadata={
                        **a['metadata'], 'ocr': {'state': 'succeeded', 'version_id': result['version_id'],
                            'language': job['payload'].get('language', 'chi_sim+eng'),
                            'review_state': quality.get('review_state', 'unreviewed'),
                            'empty_pages': quality.get('empty_pages', []), 'attempt_job_id': job['id'],
                            'at': db.now()}}))
                self.finish(c, job, result)
        elif job['kind'] == 'method':
            from .methods import execute
            execute(self, job)
        elif job['kind'] == 'workspace':
            from .workspace import execute_workspace
            execute_workspace(self, job)
        elif job['kind'] == 'persona_train':
            from .legacy_store import PostgresStore
            from hermeneut.topostyle.service import train_persona
            store = PostgresStore(self, job['project_id'], job['payload']['principal'], job=job)
            artifacts = store.list_persona_artifacts(job['payload']['persona_id'])
            artifact = next((a for a in artifacts if a.get('operation_id') == job['id']), None)
            if artifact:
                persona = store.get_persona(job['payload']['persona_id'])
                if not persona:
                    raise ResearchError('PERSONA_NO_LONGER_AVAILABLE')
                store.put_persona({**persona, 'status': 'ready', 'latest_artifact_id': artifact['id']})
            else:
                artifact = train_persona(store, job['payload']['persona_id'])
            with self.engine.begin() as c:
                self.locked_job(c, job)
                self.finish(c, job, {'artifact_id': artifact['id']})
        else:
            raise UnsupportedJobKind(job['kind'])

    def release(self, job, code='UNSUPPORTED_JOB_KIND'):
        """Put a claimed job back in the queue; a stale worker must not consume an attempt.

        This keeps an older worker (or a worker built before a new job kind existed) from
        turning a valid new task into a permanent failure: the job stays claimable by a
        current worker, while the mismatch is recorded once as an event.
        """
        with self.engine.begin() as c:
            current = row(c, db.jobs, db.jobs.c.id == job['id'])
            if not current or current['lease_token'] != job['lease_token']:
                return False
            c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(
                state='queued', attempts=max(0, current['attempts'] - 1),
                lease_until=None, lease_token=None))
            seen = any(event['data'].get('reason') == code
                       for event in rows(c, db.events, db.events.c.job_id == job['id']))
            if not seen:
                self.event(c, job['id'], {'state': 'queued', 'reason': code,
                                          'kind': current['kind'], 'attempts_restored': True})
        return True

    def queue_status(self):
        """Operator view of the queue: kinds, states, stale leases, and the oldest waiting job."""
        t = db.now()
        with self.engine.connect() as c:
            counts = {state: 0 for state in ('queued', 'running', 'failed', 'cancelled', 'cancel_requested')}
            for state, kind, count in c.execute(sa.select(db.jobs.c.state, db.jobs.c.kind,
                    sa.func.count()).group_by(db.jobs.c.state, db.jobs.c.kind)):
                counts[state] = counts.get(state, 0) + count
            stale = c.execute(sa.select(sa.func.count()).select_from(db.jobs).where(
                db.jobs.c.state == 'running', db.jobs.c.lease_until < t)).scalar()
            stuck = [dict(r) for r in c.execute(sa.select(db.jobs.c.id, db.jobs.c.kind, db.jobs.c.attempts)
                .where(db.jobs.c.state == 'queued', db.jobs.c.kind.not_in(sorted(SUPPORTED_JOB_KINDS)))
                .limit(20)).mappings()]
            oldest = c.execute(sa.select(db.jobs.c.created_at).where(db.jobs.c.state == 'queued')
                .order_by(db.jobs.c.created_at).limit(1)).scalar()
            revision = None
            if sa.inspect(c).has_table('alembic_version'):
                revision = c.execute(sa.text('select version_num from alembic_version')).scalar()
        return {'supported_job_kinds': sorted(SUPPORTED_JOB_KINDS), 'job_states': counts,
                'stale_leases': int(stale or 0), 'unknown_kind_jobs': stuck,
                'oldest_queued_age_seconds': None if oldest is None else round(t - float(oldest), 1),
                'schema_revision': revision}

    def finish(self, c, job, result):
        c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(
            state='succeeded', result=result, lease_until=None, error=None))
        self.event(c, job['id'], {'state': 'succeeded', 'result': result})

    def fail(self, job, exc):
        # Store error codes only; remote exception strings can contain credentials or source text.
        code = exc.code if isinstance(exc, ResearchError) else (
            str(exc).split(':')[0] if isinstance(exc, ValueError) else type(exc).__name__)
        with self.engine.begin() as c:
            current = row(c, db.jobs, db.jobs.c.id == job['id'])
            if current['lease_token'] != job['lease_token']:
                return
            if current['state'] in {'succeeded', 'cancelled'}:
                return
            state = 'cancelled' if current['state'] == 'cancel_requested' else 'failed'
            c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(
                state=state, error=code[:128], lease_until=None))
            self.event(c, job['id'], {'state': state, 'error': code[:128]})
            if job['kind'] == 'workspace':
                for run in rows(c, db.research_runs, db.research_runs.c.project_id == job['project_id']):
                    if run['settings'].get('origin_job_id') == job['id'] or run['id'] == job['payload'].get('resume_run_id'):
                        c.execute(db.research_runs.update().where(db.research_runs.c.id == run['id'],
                            db.research_runs.c.state != 'cancelled').values(state=state, reserved_tokens=0))
            if job['kind'] == 'import' and job['payload'].get('asset_id'):
                c.execute(db.assets.update().where(db.assets.c.id == job['payload']['asset_id'],
                    db.assets.c.status != 'revoked').values(status='error'))
            if job['kind'] == 'ocr' and job['payload'].get('asset_id'):
                # Keep the previous text version authoritative and expose the failed attempt.
                current_asset = row(c, db.assets, db.assets.c.id == job['payload']['asset_id'],
                                    db.assets.c.project_id == job['project_id'])
                if current_asset and current_asset['status'] != 'revoked':
                    c.execute(db.assets.update().where(db.assets.c.id == current_asset['id']).values(metadata={
                        **current_asset['metadata'], 'ocr': {'state': 'failed', 'error': code[:64],
                            'language': job['payload'].get('language', 'chi_sim+eng'),
                            'attempt_job_id': job['id'], 'at': db.now()}}))

    def revoke(self, project_id, principal, asset_id):
        with self.engine.begin() as c:
            self.access(c, project_id, principal, True)
            c.execute(sa.select(db.assets).where(db.assets.c.id == asset_id).with_for_update())
            a = self.asset(c, project_id, asset_id, include_revoked=True)
            if a['status'] == 'revoked':
                return
            # Persist withdrawal intent outside older database snapshots, without source text.
            self.objects.root.mkdir(parents=True, exist_ok=True)
            ledger = self.objects.root / 'withdrawals.jsonl'
            fd = os.open(ledger, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            try:
                os.write(fd, (json.dumps({'project_id': project_id, 'asset_id': asset_id,
                                         'created_at': db.now()}) + '\n').encode('utf-8'))
                os.fsync(fd)
            finally:
                os.close(fd)
            segment_ids = sa.select(db.segments.c.id).where(db.segments.c.asset_id == asset_id)
            source_tokens = set(c.execute(segment_ids).scalars()) | {asset_id}
            affected = set(c.execute(sa.select(db.anchors.c.id).where(db.anchors.c.segment_id.in_(segment_ids))).scalars())
            # Remove derived records to a fixed point, including references to earlier derived records.
            remove = set()
            candidates = rows(c, db.records, db.records.c.project_id == project_id)
            for chapter in rows(c, db.document_chapters, db.document_chapters.c.project_id == project_id):
                if set(_strings(chapter['payload'])) & (affected | source_tokens):
                    remove.add(chapter['record_id'])
            history = c.execute(sa.select(db.record_history).join(db.records).where(
                db.records.c.project_id == project_id)).mappings().all()
            for h in history:
                if set(_strings(h['payload'])) & (affected | {asset_id}):
                    remove.add(h['record_id'])
            while True:
                previous = len(remove)
                for r in candidates:
                    tokens = set(_strings(r['payload']))
                    if tokens & (affected | remove | {asset_id}):
                        remove.add(r['id'])
                if len(remove) == previous:
                    break
            if remove:
                c.execute(db.document_chapters.delete().where(db.document_chapters.c.record_id.in_(remove)))
                c.execute(db.record_history.delete().where(db.record_history.c.record_id.in_(remove)))
                c.execute(db.records.delete().where(db.records.c.id.in_(remove)))
            c.execute(db.anchors.delete().where(db.anchors.c.segment_id.in_(segment_ids)))
            # Keep tombstones for external identifiers, delete all readable text and stored object references.
            c.execute(db.segments.delete().where(db.segments.c.asset_id == asset_id))
            c.execute(db.versions.delete().where(db.versions.c.asset_id == asset_id))
            for j in rows(c, db.jobs, db.jobs.c.project_id == project_id):
                if (set(_strings(j['payload'])) & source_tokens
                        or set(_strings(j.get('result') or {})) & (remove | source_tokens)):
                    c.execute(db.events.delete().where(db.events.c.job_id == j['id']))
                    c.execute(db.jobs.update().where(db.jobs.c.id == j['id']).values(
                        state='cancelled', payload={}, result=None, error='MATERIAL_REVOKED'))
            # Trace both current and legacy identities; do not redact unrelated project material.
            source_tokens.add(str(a['metadata'].get('legacy_id', asset_id)))
            for draft in rows(c, db.method_drafts, db.method_drafts.c.project_id == project_id):
                if asset_id in draft['payload'].get('source_assets', []):
                    c.execute(db.method_drafts.delete().where(db.method_drafts.c.id == draft['id']))
            for call in rows(c, db.model_calls, db.model_calls.c.project_id == project_id):
                if asset_id in call['source_assets']:
                    c.execute(db.model_calls.update().where(db.model_calls.c.id == call['id']).values(source_assets=[]))
            for legacy_row in rows(c, db.legacy, db.legacy.c.project_id == project_id):
                if legacy_row['status'].startswith('anchor:') and legacy_row['status'][7:] in affected:
                    source_tokens.add(legacy_row['legacy_key'])
            for legacy_row in rows(c, db.legacy, db.legacy.c.project_id == project_id):
                data = legacy_row['payload']
                try:
                    data = {**data, **json.loads(data.get('data', '{}'))}
                except (ValueError, TypeError):
                    pass
                if legacy_row['legacy_key'] in source_tokens or set(_strings(data)) & source_tokens:
                    c.execute(db.legacy.update().where(db.legacy.c.id == legacy_row['id']).values(
                        payload={}, status='redacted_after_withdrawal'))
            for entity in rows(c, db.entities, db.entities.c.project_id == project_id):
                if set(_strings(entity['payload'])) & source_tokens:
                    c.execute(db.entities.delete().where(db.entities.c.id == entity['id']))
            run_ids = set()
            for run in rows(c, db.research_runs, db.research_runs.c.project_id == project_id):
                if set(_strings(run['scope'])) & source_tokens:
                    run_ids.add(run['id'])
                    c.execute(db.decisions.delete().where(db.decisions.c.run_id == run['id']))
                    c.execute(db.research_steps.delete().where(db.research_steps.c.run_id == run['id']))
                    c.execute(db.research_runs.update().where(db.research_runs.c.id == run['id']).values(
                        state='cancelled', question='[材料已撤回]', scope=[], settings={}, reserved_tokens=0))
            for m in rows(c, db.messages, db.messages.c.project_id == project_id):
                if (set(_strings(m['metadata'])) & (source_tokens | run_ids)
                        or set(m['artifact_ids']) & remove):
                    c.execute(db.messages.update().where(db.messages.c.id == m['id']).values(
                        content='[关联材料已撤回]', artifact_ids=[], metadata={'withdrawn': True}))
                    c.execute(db.conversation_events.update().where(
                        db.conversation_events.c.conversation_id == m['conversation_id']).values(
                        type='redacted', payload={'withdrawn': True}))
            c.execute(db.assets.update().where(db.assets.c.id == asset_id).values(
                status='revoked', object_key='', metadata={}, revision=a['revision'] + 1))
            c.execute(db.outbox.insert().values(id=db.uid(), project_id=project_id, asset_id=asset_id,
                revision=a['revision'] + 1, done=False, attempts=0, created_at=db.now()))


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
