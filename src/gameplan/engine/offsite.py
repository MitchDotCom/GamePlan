"""Offsite copy of the newest verified backup to an S3-compatible bucket (AWS S3, Backblaze B2, Cloudflare R2, Wasabi all speak it).

Set OFFSITE_BUCKET (and OFFSITE_ENDPOINT for non-AWS stores; credentials come from the usual AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY). Without a bucket the job reports `not_configured`
and the health check says so: a backup on the same disk as the database is not a backup against losing the disk.
The copy is verified by reading its size back. Retention belongs to the bucket (set a lifecycle rule), not to this code, so a bug here can never delete history.
"""
from __future__ import annotations

import os
import pathlib


def configured() -> bool:
    return bool(os.environ.get("OFFSITE_BUCKET"))


def newest_backup(backup_dir: pathlib.Path) -> pathlib.Path | None:
    files = sorted(pathlib.Path(backup_dir).glob("engine-*.db"))
    return files[-1] if files else None


def _client():
    import boto3
    return boto3.client("s3", endpoint_url=os.environ.get("OFFSITE_ENDPOINT") or None)


def push(backup_dir: pathlib.Path, client=None, bucket: str | None = None, prefix: str | None = None) -> dict:
    bucket = bucket or os.environ.get("OFFSITE_BUCKET")
    if not bucket:
        return dict(status="not_configured")
    f = newest_backup(backup_dir)
    if f is None:
        raise RuntimeError("no backup file to copy")
    client = client or _client()
    key = f"{(prefix if prefix is not None else os.environ.get('OFFSITE_PREFIX', 'recognition-engine')).strip('/')}/{f.name}"
    client.upload_file(str(f), bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"} if os.environ.get("OFFSITE_SSE", "1") == "1" else {})
    size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
    if size != f.stat().st_size:
        raise RuntimeError(f"offsite copy is {size} bytes, local is {f.stat().st_size}")
    return dict(status="ok", key=key, bytes=size)
