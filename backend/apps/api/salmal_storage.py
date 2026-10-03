from __future__ import annotations

import base64
import binascii
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils import timezone


MAX_VOTE_IMAGE_BYTES = 1024 * 1024
DATA_URL_RE = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class VoteImageError(Exception):
    pass


@dataclass(frozen=True)
class VoteImageUpload:
    bucket: str
    key: str

    @property
    def uri(self):
        return f"s3://{self.bucket}/{self.key}"


def _bucket():
    bucket = str(getattr(settings, "AWS_STORAGE_BUCKET_NAME", "") or "").strip()
    if not bucket:
        raise VoteImageError("이미지 저장용 S3 버킷이 설정되어 있지 않습니다.")
    return bucket


@lru_cache(maxsize=1)
def _client():
    return boto3.client("s3", region_name=getattr(settings, "AWS_REGION", "ap-northeast-2"))


def _decode_image(data_url):
    value = str(data_url or "").strip()
    match = DATA_URL_RE.fullmatch(value)
    if match is None:
        raise VoteImageError("이미지는 JPEG, PNG, WebP 형식만 사용할 수 있습니다.")
    mime, payload = match.groups()
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise VoteImageError("이미지 데이터가 올바르지 않습니다.") from exc
    if len(raw) > MAX_VOTE_IMAGE_BYTES:
        raise VoteImageError("이미지는 1MB 이하만 등록할 수 있습니다.")
    signatures = {
        "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
        "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
    }
    if not signatures[mime]:
        raise VoteImageError("이미지 파일 형식과 실제 내용이 일치하지 않습니다.")
    return mime, raw


def upload_vote_image(data_url, *, now=None, s3_client=None):
    mime, raw = _decode_image(data_url)
    local_date = timezone.localtime(now or timezone.now())
    key = (
        f"images/vote_image/{local_date:%Y/%m/%d}/"
        f"{uuid.uuid4().hex}.{EXTENSIONS[mime]}"
    )
    bucket = _bucket()
    try:
        (s3_client or _client()).put_object(
            Bucket=bucket,
            Key=key,
            Body=raw,
            ContentType=mime,
            CacheControl="public, max-age=31536000, immutable",
        )
    except (BotoCoreError, ClientError) as exc:
        raise VoteImageError("이미지를 S3에 저장하지 못했습니다.") from exc
    return VoteImageUpload(bucket=bucket, key=key)


def parse_vote_image_uri(value):
    value = str(value or "")
    if not value.startswith("s3://"):
        return None
    bucket_and_key = value[5:].split("/", 1)
    if len(bucket_and_key) != 2 or not all(bucket_and_key):
        return None
    bucket, key = bucket_and_key
    if not key.startswith("images/vote_image/"):
        return None
    return VoteImageUpload(bucket=bucket, key=key)


def vote_image_url(value, *, s3_client=None):
    image = parse_vote_image_uri(value)
    if image is None:
        return value
    try:
        return (s3_client or _client()).generate_presigned_url(
            "get_object",
            Params={"Bucket": image.bucket, "Key": image.key},
            ExpiresIn=3600,
        )
    except (BotoCoreError, ClientError):
        return None


def delete_vote_image(value, *, s3_client=None):
    image = parse_vote_image_uri(value)
    if image is None:
        return False
    try:
        (s3_client or _client()).delete_object(Bucket=image.bucket, Key=image.key)
    except (BotoCoreError, ClientError) as exc:
        raise VoteImageError("S3 이미지를 삭제하지 못했습니다.") from exc
    return True
