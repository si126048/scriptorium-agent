from __future__ import annotations

import sqlalchemy as sa
from elasticsearch import Elasticsearch

from . import schema as db
from .service import ResearchError, row, rows

ALIAS = 'scriptorium-passages'
MAPPING = {'properties': {
    'project_id': {'type': 'keyword'}, 'asset_id': {'type': 'keyword'},
    'version_id': {'type': 'keyword'}, 'segment_id': {'type': 'keyword'},
    'xml_id': {'type': 'keyword'}, 'page_label': {'type': 'keyword'},
    'name': {'type': 'text'}, 'text': {'type': 'text', 'analyzer': 'cjk',
                                    'fields': {'exact': {'type': 'keyword', 'ignore_above': 8192}}},
    'revision': {'type': 'long'}, 'revoked': {'type': 'boolean'},
}}


def enabled(service):
    """Search is optional: an empty SCRIPTORIUM_ELASTICSEARCH_URL disables indexing and querying."""
    return bool(str(getattr(service.settings, 'elasticsearch_url', '') or '').strip())


def client(service):
    if not enabled(service):
        raise ResearchError('SEARCH_DISABLED', 503)
    auth = {'basic_auth': (service.settings.elasticsearch_username, service.settings.elasticsearch_password)} if service.settings.elasticsearch_password else {}
    return Elasticsearch(service.settings.elasticsearch_url, request_timeout=15, max_retries=0, **auth)


def ensure_index(es):
    if not es.indices.exists(index=ALIAS):
        name = f'{ALIAS}-{db.uid()}'
        es.indices.create(index=name, mappings=MAPPING, settings={'number_of_shards': 1, 'number_of_replicas': 0},
                          aliases={ALIAS: {}})


def index_asset(service, es, c, asset_id, index=ALIAS):
    a = row(c, db.assets, db.assets.c.id == asset_id)
    current = rows(c, db.segments, db.segments.c.asset_id == asset_id)
    # Material tombstone prevents stale retries recreating revoked passages.
    es.index(index=index, id=f'asset-{asset_id}', version=a['revision'], version_type='external_gte',
        document={'project_id': a['project_id'], 'asset_id': asset_id, 'revision': a['revision'],
                  'revoked': a['status'] == 'revoked'})
    if a['status'] == 'revoked':
        es.delete_by_query(index=index, query={'bool': {'filter': [{'term': {'asset_id': asset_id}},
            {'exists': {'field': 'segment_id'}}]}}, conflicts='proceed')
        return
    for s in current:
        es.index(index=index, id=s['id'], version=a['revision'], version_type='external_gte', document={
            **{k: s[k] for k in ('project_id', 'asset_id', 'version_id', 'xml_id', 'page_label', 'text')},
            'segment_id': s['id'], 'name': a['name'], 'revision': a['revision'], 'revoked': False})


def sync_one(service):
    if not enabled(service):
        return False
    with service.engine.begin() as c:
        event = c.execute(sa.select(db.outbox).where(db.outbox.c.done.is_(False), db.outbox.c.attempts < 3)
            .order_by(db.outbox.c.created_at).with_for_update(skip_locked=True).limit(1)).mappings().first()
        if not event:
            return False
        try:
            # A material lock serializes indexing with revision/revocation and other consumers.
            c.execute(sa.select(db.assets.c.id).where(db.assets.c.id == event['asset_id']).with_for_update())
            with client(service) as es:
                ensure_index(es)
                index_asset(service, es, c, event['asset_id'])
            c.execute(db.outbox.update().where(db.outbox.c.id == event['id']).values(done=True, error=None))
        except Exception as exc:
            c.execute(db.outbox.update().where(db.outbox.c.id == event['id']).values(
                attempts=event['attempts'] + 1, error=type(exc).__name__))
        return True


def search(service, project_id, principal, query, asset_id=None, version_id=None,
           author=None, year_from=None, year_to=None, purpose=None):
    if not enabled(service):
        raise ResearchError('SEARCH_DISABLED', 503)
    with service.engine.connect() as c:
        service.access(c, project_id, principal)
        filters = [{'term': {'project_id': project_id}}, {'exists': {'field': 'segment_id'}},
                   {'term': {'revoked': False}}]
        if asset_id:
            service.asset(c, project_id, asset_id)
            filters.append({'term': {'asset_id': asset_id}})
        if version_id:
            filters.append({'term': {'version_id': version_id}})
        if author or year_from or year_to or purpose:
            allowed = []
            for material in rows(c, db.assets, db.assets.c.project_id == project_id,
                                 db.assets.c.status != 'revoked'):
                meta = material['metadata']
                year = str(meta.get('publication_date', ''))[:4]
                if author and author.casefold() not in str(meta.get('author', '')).casefold():
                    continue
                if purpose and meta.get('purpose') != purpose:
                    continue
                if (year_from or year_to) and (not year.isdigit() or
                        (year_from and int(year) < year_from) or (year_to and int(year) > year_to)):
                    continue
                allowed.append(material['id'])
            filters.append({'terms': {'asset_id': allowed}})
        try:
            with client(service) as es:
                result = es.search(index=ALIAS, size=50, query={'bool': {
                    'filter': filters, 'must': [{'match_phrase': {'text': query}}]}},
                    highlight={'fields': {'text': {}}, 'pre_tags': [''], 'post_tags': ['']})
        except Exception:
            raise ResearchError('SEARCH_UNAVAILABLE', 503) from None
        items = []
        for hit in result['hits']['hits']:
            source = hit['_source']
            a = row(c, db.assets, db.assets.c.id == source['asset_id'], db.assets.c.project_id == project_id)
            s = row(c, db.segments, db.segments.c.id == source['segment_id'])
            metadata = (a or {}).get('metadata', {})
            year = str(metadata.get('publication_date', ''))[:4]
            if author and author.casefold() not in str(metadata.get('author', '')).casefold():
                continue
            if purpose and metadata.get('purpose') != purpose:
                continue
            if (year_from or year_to) and (not year.isdigit() or
                    (year_from and int(year) < year_from) or (year_to and int(year) > year_to)):
                continue
            if a and a['status'] != 'revoked' and s:
                items.append({**s, 'name': a['name'], 'snippet': hit.get('highlight', {}).get('text', [s['text'][:200]])[0]})
        pending = c.execute(sa.select(sa.func.count()).select_from(db.outbox).where(
            db.outbox.c.project_id == project_id, db.outbox.c.done.is_(False))).scalar()
        return {'items': items, 'pending_index_events': pending}


def rebuild(service):
    # Workers and revocation are blocked at the material row during snapshot publication.
    with service.engine.begin() as c, client(service) as es:
        all_assets = list(c.execute(sa.select(db.assets.c.id).with_for_update()).scalars())
        index = f'{ALIAS}-{db.uid()}'
        es.indices.create(index=index, mappings=MAPPING,
                          settings={'number_of_shards': 1, 'number_of_replicas': 0})
        for aid in all_assets:
            index_asset(service, es, c, aid, index)
        es.indices.refresh(index=index)
        actions = [{'add': {'index': index, 'alias': ALIAS}}]
        if es.indices.exists_alias(name=ALIAS):
            old = list(es.indices.get_alias(name=ALIAS))
            actions = [{'remove': {'index': name, 'alias': ALIAS}} for name in old] + actions
        es.indices.update_aliases(actions=actions)
        return index
