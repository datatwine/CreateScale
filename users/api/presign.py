"""
Presigned URL generation for direct-to-R2 uploads.

Isolated from views for testability. The generate_presigned_url() call
is a LOCAL crypto operation (~5 ms) — it signs the request using the
secret key without making any network call to R2/S3.
"""

import uuid

import boto3
from django.conf import settings


def generate_upload_presign(
    user_id, content_type="image/jpeg", max_bytes=25 * 1024 * 1024
):
    """Generate a presigned PUT URL for direct-to-R2 upload.

    Returns { url, key, content_type } — the client PUTs raw file bytes
    directly to `url` with Content-Type header set to `content_type`.
    """
    ext = "mp4" if "video" in content_type else "jpg"
    key = f"profile_pics/user_{user_id}/{uuid.uuid4()}.{ext}"

    presign_endpoint = (
        getattr(settings, "PRESIGN_ENDPOINT_URL", None) or settings.AWS_S3_ENDPOINT_URL
    )

    s3 = boto3.client(
        "s3",
        endpoint_url=presign_endpoint,
        region_name=settings.AWS_S3_REGION_NAME,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=300,
    )

    return {"url": url, "key": key, "content_type": content_type}
