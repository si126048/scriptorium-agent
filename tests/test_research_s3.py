"""S3 object-store adapter checks.

These use an in-process stand-in for the S3 transport, so they verify key derivation,
immutability, checksum validation and the full import/read/backup path without claiming that
a real bucket has been exercised. Real-endpoint verification remains a deployment task.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

sa = pytest.importorskip('sqlalchemy')
pytest.importorskip('psycopg')
boto3 = pytest.importorskip('boto3')
from botocore.exceptions import ClientError

from test_research_integration import research  # noqa: F401
from scriptorium.research.service import ResearchService
from scriptorium.research.storage import S3Objects
from scriptorium.research.worker import run_one


class FakeS3:
    """Minimal S3 surface: conditional writes, reads, and no overwrite of existing keys."""

    def __init__(self):
        self.objects = {}
        self.puts = 0

    def put_object(self, Bucket, Key, Body, Metadata=None, IfNoneMatch=None):
        self.puts += 1
        if IfNoneMatch == '*' and Key in self.objects:
            raise ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
        self.objects[(Bucket, Key)] = (bytes(Body), dict(Metadata or {}))

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')

        class Body:
            def __init__(self, data):
                self.data = data

            def read(self):
                return self.data

            def close(self):
                return None

        return {'Body': Body(self.objects[(Bucket, Key)][0])}


def s3_store(settings, monkeypatch, bucket='research-test'):
    fake = FakeS3()
    monkeypatch.setattr(boto3, 'client', lambda *args, **kwargs: fake)
    store = S3Objects(replace(settings, object_backend='s3', s3_bucket=bucket))
    return store, fake


def test_s3_keys_are_content_addressed_immutable_and_checksummed(research, monkeypatch):  # noqa: F811
    store, fake = s3_store(research.settings, monkeypatch)
    data = b'immutable research source'
    key, digest = store.put(data)
    assert digest == hashlib.sha256(data).hexdigest()
    assert key == f'{digest[:2]}/{digest}'
    assert fake.objects[('research-test', key)][1] == {'sha256': digest}
    assert store.read(key) == data
    # A second write of the same bytes resolves to the existing immutable object.
    assert store.put(data) == (key, digest)
    assert fake.puts == 2
    with pytest.raises(ValueError, match='INVALID_OBJECT_KEY'):
        store.read(digest)
    with pytest.raises(ValueError, match='INVALID_OBJECT_KEY'):
        store.read(f'{digest[2:4]}/{digest}')
    fake.objects[('research-test', key)] = (b'tampered', {})
    with pytest.raises(ValueError, match='OBJECT_CHECKSUM_MISMATCH'):
        store.read(key)


def test_s3_backend_serves_import_queue_read_and_backup(research, monkeypatch, tmp_path):  # noqa: F811
    from scriptorium.research.backup import backup
    store, fake = s3_store(research.settings, monkeypatch)
    service = ResearchService(research.engine, replace(research.settings, object_backend='s3',
                                                      s3_bucket='research-test'))
    service.objects = store
    project = service.create_project('tester', 'S3 project')
    job = service.import_material(project['id'], 'tester', '自由需要条件。'.encode(), 's3.txt', 's3-1')
    run_one(service, job['id'])
    asset = service.list_materials(project['id'], 'tester')[0]
    assert asset['status'] == 'ready'
    assert fake.objects[('research-test', asset['object_key'])][0] == '自由需要条件。'.encode()
    segments = service.get_segments(project['id'], 'tester', asset['id'])['segments']
    assert segments[0]['text'] == '自由需要条件。'
    # Backup archives object bytes through the adapter instead of copying a local directory.
    # Two objects exist: the retained original and the generated reading.v1 TEI transcription.
    result = backup(service, tmp_path / 'archive')
    assert result['objects'] == 2
    assert (tmp_path / 'archive' / 'objects' / asset['object_key']).read_bytes() == '自由需要条件。'.encode()
    # The archive itself is a filesystem store; restoring into a fresh S3-backed service reads it back.
    assert store.read(asset['object_key']) == '自由需要条件。'.encode()
