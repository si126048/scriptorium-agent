"""Object storage against a real S3 HTTP endpoint (SeaweedFS gateway on loopback).

Skipped unless SCRIPTORIUM_TEST_S3_ENDPOINT is set, so a normal run never pretends to have tested
object storage. This is a real object service over the S3 wire protocol, but it is not the
institution's storage: versioning, retention, replication and IAM still need separate checks.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import replace

import pytest

sa = pytest.importorskip('sqlalchemy')
pytest.importorskip('psycopg')
boto3 = pytest.importorskip('boto3')
from botocore.exceptions import ClientError

from test_research_integration import research  # noqa: F401
from scriptorium.research import schema as db
from scriptorium.research.backup import backup, restore
from scriptorium.research.service import ResearchService
from scriptorium.research.storage import S3Objects
from scriptorium.research.worker import run_one

ENDPOINT = os.getenv('SCRIPTORIUM_TEST_S3_ENDPOINT', '').strip()
pytestmark = pytest.mark.skipif(not ENDPOINT, reason='SCRIPTORIUM_TEST_S3_ENDPOINT not configured')


@pytest.fixture
def endpoint(monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'scriptorium-acceptance')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'scriptorium-acceptance')
    client = boto3.client('s3', endpoint_url=ENDPOINT, region_name='us-east-1')
    bucket = 'scriptorium-test-' + uuid.uuid4().hex[:12]
    client.create_bucket(Bucket=bucket)
    try:
        yield client, bucket
    finally:
        try:
            listed = client.list_objects_v2(Bucket=bucket).get('Contents', [])
            for item in listed:
                client.delete_object(Bucket=bucket, Key=item['Key'])
            client.delete_bucket(Bucket=bucket)
        except ClientError:
            pass


def live_store(settings, endpoint, bucket, tmp_path):
    return S3Objects(replace(settings, object_backend='s3', s3_bucket=bucket,
                             s3_endpoint=endpoint, object_root=tmp_path / 'objects'))


def test_adapter_speaks_to_a_real_s3_endpoint(research, endpoint, tmp_path):  # noqa: F811
    client, bucket = endpoint
    store = live_store(research.settings, ENDPOINT, bucket, tmp_path)
    data = b'real object storage round trip'
    key, digest = store.put(data)
    assert store.read(key) == data
    # Content addressing means the second write resolves to the same server-side object.
    assert store.put(data) == (key, digest)
    listed = client.list_objects_v2(Bucket=bucket).get('Contents', [])
    assert [item['Key'] for item in listed] == [key]
    # Values returned by the server are trustworthy only after re-hashing locally.
    client.put_object(Bucket=bucket, Key=key, Body=b'tampered')
    with pytest.raises(ValueError, match='OBJECT_CHECKSUM_MISMATCH'):
        store.read(key)
    # Path traversal and malformed keys never reach the service.
    with pytest.raises(ValueError, match='INVALID_OBJECT_KEY'):
        store.read('../' + digest)
    missing = live_store(research.settings, ENDPOINT, bucket + '-missing', tmp_path)
    with pytest.raises(ClientError):
        missing.read(key)


def test_service_round_trip_backup_and_restore_over_s3(research, endpoint, tmp_path):  # noqa: F811
    client, bucket = endpoint
    settings = replace(research.settings, object_backend='s3', s3_bucket=bucket,
                       s3_endpoint=ENDPOINT, object_root=tmp_path / 'objects')
    service = ResearchService(research.engine, settings)
    pid = service.create_project('tester', 'S3 项目')['id']
    job = service.import_material(pid, 'tester', '对象存储需要真实往返。'.encode(), 's3.txt', 's3-live-1')
    run_one(service, job['id'])
    asset = service.list_materials(pid, 'tester')[0]
    assert asset['status'] == 'ready'
    served = client.get_object(Bucket=bucket, Key=asset['object_key'])['Body'].read()
    assert served == '对象存储需要真实往返。'.encode()
    assert service.get_segments(pid, 'tester', asset['id'])['segments'][0]['text'] == '对象存储需要真实往返。'
    archive = tmp_path / 'archive'
    assert backup(service, archive)['objects'] >= 2  # original + generated reading.v1 TEI
    # Restore into a fresh schema that shares the same S3 bucket through a second service.
    name = 'test_restore_' + db.uid()
    base = db.engine_for(research.settings.database_url)
    with base.begin() as c:
        c.execute(sa.text(f'CREATE SCHEMA {name}'))
    engine = sa.create_engine(research.settings.database_url,
                              connect_args={'options': f'-csearch_path={name}'})
    db.metadata.create_all(engine)
    restored_service = ResearchService(engine, replace(settings, object_root=tmp_path / 'restored-objects'))
    try:
        result = restore(restored_service, archive)
        assert result['status'] == 'restored'
        projects = restored_service.list_projects('tester')
        assert [p['name'] for p in projects] == ['S3 项目']
        materials = restored_service.list_materials(projects[0]['id'], 'tester')
        assert materials[0]['status'] == 'ready'
        assert restored_service.get_segments(projects[0]['id'], 'tester', materials[0]['id'])['segments']
    finally:
        engine.dispose()
        with base.begin() as c:
            c.execute(sa.text(f'DROP SCHEMA {name} CASCADE'))
        base.dispose()
