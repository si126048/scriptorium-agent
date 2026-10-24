from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    def put(self, data: bytes) -> tuple[str, str]: ...
    def read(self, key: str) -> bytes: ...


class S3Objects:
    """Same immutable content keys; credentials use the standard AWS credential chain.

    The local root stores withdrawal receipts, never a second writable object copy.
    Bucket creation and version retention are deployment responsibilities.
    """
    def __init__(self, settings):
        import boto3
        if not settings.s3_bucket:
            raise ValueError('S3_BUCKET_REQUIRED')
        self.root = settings.object_root.resolve()
        self.bucket = settings.s3_bucket
        self.client = boto3.client('s3', endpoint_url=settings.s3_endpoint, region_name=settings.s3_region)

    def validate(self, key):
        if not re.fullmatch(r'[0-9a-f]{2}/[0-9a-f]{64}', key) or key[:2] != key[3:5]:
            raise ValueError('INVALID_OBJECT_KEY')

    def put(self, data):
        from botocore.exceptions import ClientError
        sha = hashlib.sha256(data).hexdigest()
        key = f'{sha[:2]}/{sha}'
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data,
                Metadata={'sha256': sha}, IfNoneMatch='*')
        except ClientError as exc:
            if exc.response['Error']['Code'] not in {'PreconditionFailed', '412'}:
                raise
            self.read(key)
        return key, sha

    def read(self, key):
        self.validate(key)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        try:
            data = response['Body'].read()
        finally:
            response['Body'].close()
        if hashlib.sha256(data).hexdigest() != key[3:]:
            raise ValueError('OBJECT_CHECKSUM_MISMATCH')
        return data


def object_store(settings):
    if settings.object_backend == 'filesystem':
        return FileObjects(settings.object_root)
    if settings.object_backend == 's3':
        return S3Objects(settings)
    raise ValueError('UNKNOWN_OBJECT_BACKEND')


class FileObjects:
    """Content-addressed atomic writes. Only validated keys may be resolved."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key: str):
        if not re.fullmatch(r'[0-9a-f]{2}/[0-9a-f]{64}', key) or key[:2] != key[3:5]:
            raise ValueError('INVALID_OBJECT_KEY')
        result = (self.root / key).resolve()
        if not result.is_relative_to(self.root):
            raise ValueError('OBJECT_OUTSIDE_ROOT')
        return result

    def put(self, data: bytes):
        sha = hashlib.sha256(data).hexdigest()
        key = f'{sha[:2]}/{sha}'
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self.read(key)
            return key, sha
        fd, staging = tempfile.mkstemp(prefix='.pending-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staging, target)
        finally:
            Path(staging).unlink(missing_ok=True)
        return key, sha

    def read(self, key: str):
        data = self.path(key).read_bytes()
        if hashlib.sha256(data).hexdigest() != key[3:]:
            raise ValueError('OBJECT_CHECKSUM_MISMATCH')
        return data
