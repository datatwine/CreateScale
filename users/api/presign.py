"""
Presigned URL generation for direct-to-R2 uploads.

Isolated from views for testability. The generate_presigned_post() call
is a LOCAL crypto operation (~5 ms) — it signs the request using the
secret key without making any network call to R2/S3.
"""

import uuid

import boto3
from django.conf import settings


def generate_upload_presign(user_id, content_type="image/jpeg", max_bytes=25 * 1024 * 1024):
    """Generate a presigned POST for direct-to-R2 upload.

    Returns { url, fields, key } — the client POSTs file bytes
    directly to `url` with `fields` as form data.
    """
    ext = "mp4" if "video" in content_type else "jpg"
    key = f"profile_pics/user_{user_id}/{uuid.uuid4()}.{ext}"

    # PRESIGN_ENDPOINT_URL: the URL the CLIENT will use to upload.
    # In production: not set → falls back to AWS_S3_ENDPOINT_URL (R2 public endpoint).
    # In local dev:  http://localhost:9000 (host-accessible MinIO port).
    # AWS_S3_ENDPOINT_URL stays http://minio:9000 for django-storages (server-side).
    presign_endpoint = getattr(settings, "PRESIGN_ENDPOINT_URL", None) or settings.AWS_S3_ENDPOINT_URL

    s3 = boto3.client(
        "s3",
        endpoint_url=presign_endpoint,
        region_name=settings.AWS_S3_REGION_NAME,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    presigned = s3.generate_presigned_post(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Conditions=[
            ["content-length-range", 0, max_bytes],
        ],
        ExpiresIn=300,  # 5 minutes
    )

    return {"url": presigned["url"], "fields": presigned["fields"], "key": key}
