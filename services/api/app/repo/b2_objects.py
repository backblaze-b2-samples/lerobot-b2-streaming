"""LeRobot dataset / streaming S3 object ops (S3-compatible API only).

These back the dataset ingest, index, and the marquee B2 streaming bridge.
Every call reuses the same UA-bearing boto3 client built in `b2_client` — the
ranged GET is a plain S3 `Range` request, explicitly NOT a b2-native feature
(and the documented reason we don't call stock `StreamingLeRobotDataset`, which
is HuggingFace-Hub-only).
"""

import io

from botocore.exceptions import ClientError

from app.config import settings
from app.repo.b2_client import get_s3_client


def put_bytes(key: str, data: bytes, content_type: str | None = None) -> None:
    """Write a single object (one dataset shard / meta file) to B2."""
    client = get_s3_client()
    kwargs: dict = {
        "Bucket": settings.b2_bucket_name,
        "Key": key,
        "Body": io.BytesIO(data),
    }
    if content_type:
        kwargs["ContentType"] = content_type
    try:
        client.put_object(**kwargs)
    except ClientError as e:
        raise RuntimeError(f"B2 put failed for '{key}': {e}") from e


def upload_path(local_path: str, key: str, content_type: str | None = None) -> None:
    """Multipart-aware upload of a file on disk (used for large MP4 shards)."""
    client = get_s3_client()
    extra = {"ContentType": content_type} if content_type else None
    try:
        client.upload_file(local_path, settings.b2_bucket_name, key, ExtraArgs=extra)
    except ClientError as e:
        raise RuntimeError(f"B2 upload failed for '{key}': {e}") from e


def list_keys(prefix: str) -> list[dict]:
    """List objects under a prefix as {key, size} dicts (paginated)."""
    client = get_s3_client()
    out: list[dict] = []
    kwargs: dict = {
        "Bucket": settings.b2_bucket_name,
        "Prefix": prefix,
        "MaxKeys": 1000,
    }
    try:
        while True:
            response = client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                out.append({"key": obj["Key"], "size": obj["Size"]})
            if not response.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = response["NextContinuationToken"]
    except ClientError as e:
        raise RuntimeError(f"B2 list failed for '{prefix}': {e}") from e
    return out


def head_size(key: str) -> int | None:
    """Return an object's size in bytes via head_object, or None if absent."""
    client = get_s3_client()
    try:
        response = client.head_object(Bucket=settings.b2_bucket_name, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    return response["ContentLength"]


def get_object_bytes(key: str) -> bytes:
    """Full GET of a (small) object — used for v3 metadata files."""
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.b2_bucket_name, Key=key)
    except ClientError as e:
        raise RuntimeError(f"B2 get failed for '{key}': {e}") from e
    return response["Body"].read()


def get_object_range(key: str, start: int, end: int) -> bytes:
    """Ranged GET — fetch bytes [start, end] inclusive via the S3 Range header.

    This is the core of the streaming bridge: it pulls only the Parquet
    row-group / video byte-range a requested episode needs, never the whole
    shard. `end` is inclusive per the HTTP/S3 Range spec.
    """
    client = get_s3_client()
    try:
        response = client.get_object(
            Bucket=settings.b2_bucket_name,
            Key=key,
            Range=f"bytes={start}-{end}",
        )
    except ClientError as e:
        raise RuntimeError(f"B2 ranged get failed for '{key}': {e}") from e
    return response["Body"].read()


def delete_prefix(prefix: str) -> int:
    """Delete every object under a prefix (scoped delete). Returns count.

    Used by the Episode delete verb — the caller is responsible for passing
    the episode's own prefix so deletes never escape the dataset scope.
    """
    if not prefix:
        raise ValueError("delete_prefix requires a non-empty prefix")
    client = get_s3_client()
    deleted = 0
    objs = list_keys(prefix)
    for i in range(0, len(objs), 1000):
        batch = [{"Key": o["key"]} for o in objs[i : i + 1000]]
        if not batch:
            continue
        try:
            client.delete_objects(
                Bucket=settings.b2_bucket_name,
                Delete={"Objects": batch},
            )
        except ClientError as e:
            raise RuntimeError(f"B2 prefix delete failed for '{prefix}': {e}") from e
        deleted += len(batch)
    return deleted


def presign_key(key: str, expires_in: int = 600) -> str:
    """Presigned inline GET URL for a key (e.g. an MP4 for browser playback)."""
    client = get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.b2_bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 presign failed for '{key}': {e}") from e
