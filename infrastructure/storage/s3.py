"""S3 presigned URL helpers."""

from __future__ import annotations

from typing import Any

import boto3
from django.conf import settings


def get_s3_client() -> Any:
    return boto3.client(
        "s3",
        region_name=settings.AWS_S3_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def generate_presigned_put_url(
    object_key: str,
    content_type: str,
    content_length: int,
    expiry: int | None = None,
) -> dict[str, Any]:
    """
    S3 presigned PUT URL을 생성한다.

    Returns dict with keys: url, headers
    """
    if expiry is None:
        expiry = settings.AWS_S3_PRESIGNED_URL_EXPIRY

    client = get_s3_client()
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.AWS_S3_BUCKET,
            "Key": object_key,
            "ContentType": content_type,
            "ContentLength": content_length,
        },
        ExpiresIn=expiry,
    )
    return {
        "url": url,
        "headers": {
            "Content-Type": content_type,
            "Content-Length": str(content_length),
        },
    }


def check_object_exists(object_key: str) -> bool:
    """S3에 오브젝트가 존재하는지 확인한다."""
    client = get_s3_client()
    try:
        client.head_object(Bucket=settings.AWS_S3_BUCKET, Key=object_key)
    except Exception:
        return False
    else:
        return True
