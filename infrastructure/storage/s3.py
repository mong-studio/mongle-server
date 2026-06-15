"""S3 presigned URL helpers."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config
from django.conf import settings


class StorageNotConfiguredError(RuntimeError):
    """AWS_S3_BUCKET 등 S3 스토리지 설정이 비어 있을 때 발생.

    botocore 의 모호한 ParamValidationError(빈 버킷 이름) 대신,
    호출부가 503 같은 명확한 응답으로 변환할 수 있도록 명시적으로 던진다.
    """


def _ensure_storage_configured() -> None:
    if not settings.AWS_S3_BUCKET:
        raise StorageNotConfiguredError("AWS_S3_BUCKET is not configured")


def with_prefix(key: str) -> str:
    """논리 키 앞에 공통 네임스페이스(settings.AWS_S3_PREFIX)를 붙인다.

    AI 워커의 S3 어댑터와 동일한 규칙으로, 모든 런타임 객체를
    `mongle-village/...` 아래로 모은다. prefix 가 비면 그대로 둔다.
    """
    prefix = (settings.AWS_S3_PREFIX or "").rstrip("/")
    return f"{prefix}/{key}" if prefix else key


def get_s3_client() -> Any:
    # 가상호스팅(virtual) 주소 + SigV4 로 리전 엔드포인트
    # (bucket.s3.<region>.amazonaws.com)를 직접 서명한다.
    # 기본값(s3.amazonaws.com 글로벌)으로 서명하면 S3 가 리전 호스트로 301
    # 리다이렉트하고, 브라우저는 cross-origin 리다이렉트를 CORS 정책상 차단한다.
    return boto3.client(
        "s3",
        region_name=settings.AWS_S3_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
        ),
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

    _ensure_storage_configured()
    # Content-Length 는 서명에 넣지 않는다(SignedHeaders=content-type;host).
    # 브라우저 Fetch API 는 Content-Length 를 금지 헤더로 취급해 앱이 지정한 값을
    # 무시하고 자동 설정하므로, 서명에 포함하면 정규 서명이 어긋나 403
    # SignatureDoesNotMatch 가 난다. 파일 크기 검증은 presign 단계의 serializer 가 한다.
    _ = content_length
    client = get_s3_client()
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.AWS_S3_BUCKET,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=expiry,
    )
    return {
        "url": url,
        "headers": {
            "Content-Type": content_type,
        },
    }


def check_object_exists(object_key: str) -> bool:
    """S3에 오브젝트가 존재하는지 확인한다."""
    _ensure_storage_configured()
    client = get_s3_client()
    try:
        client.head_object(Bucket=settings.AWS_S3_BUCKET, Key=object_key)
    except Exception:
        return False
    else:
        return True
