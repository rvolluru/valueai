from __future__ import annotations

import io
from pathlib import Path

import boto3
from botocore.config import Config

from .settings import Settings


class Storage:
    def save_upload(self, item_id: str, filename: str, content_type: str, data: bytes) -> str:
        raise NotImplementedError

    def save_debug_artifact(self, item_id: str, filename: str, data: bytes) -> str:
        raise NotImplementedError


class LocalStorage(Storage):
    def __init__(self, base_dir: str):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def save_upload(self, item_id: str, filename: str, content_type: str, data: bytes) -> str:
        path = self.base / "uploads" / item_id / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def save_debug_artifact(self, item_id: str, filename: str, data: bytes) -> str:
        path = self.base / "debug" / item_id / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)


class S3Storage(Storage):
    def __init__(self, settings: Settings):
        session = boto3.session.Session()
        self.bucket = settings.s3_bucket
        self.client = session.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            use_ssl=False if settings.s3_endpoint_url and settings.s3_endpoint_url.startswith("http://") else True,
            config=Config(s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"}),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            create_args = {"Bucket": self.bucket}
            self.client.create_bucket(**create_args)

    def _put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.upload_fileobj(
            io.BytesIO(data),
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return f"s3://{self.bucket}/{key}"

    def save_upload(self, item_id: str, filename: str, content_type: str, data: bytes) -> str:
        key = f"uploads/{item_id}/{filename}"
        return self._put(key, data, content_type)

    def save_debug_artifact(self, item_id: str, filename: str, data: bytes) -> str:
        key = f"artifacts/{item_id}/{filename}"
        ctype = "application/json" if filename.endswith(".json") else "application/octet-stream"
        return self._put(key, data, ctype)


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings.local_storage_dir)
