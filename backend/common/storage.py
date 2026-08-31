import json
import os
from datetime import datetime
from typing import Any

import boto3


AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")


s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
)


def upload_json(
    key: str,
    data: dict[str, Any],
) -> str:
    """
    Python dict 데이터를 JSON으로 변환하여 S3에 저장한다.
    """

    if not AWS_STORAGE_BUCKET_NAME:
        raise ValueError("AWS_STORAGE_BUCKET_NAME is not configured.")

    s3_client.put_object(
        Bucket=AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Body=json.dumps(
            data,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8"),
        ContentType="application/json",
    )

    return f"s3://{AWS_STORAGE_BUCKET_NAME}/{key}"


def build_raw_key(
    source: str,
    filename: str,
) -> str:
    """
    FEEDIT Raw 데이터용 S3 Key 생성.
    """

    now = datetime.now()

    return (
        f"raw/{source.lower()}/"
        f"{now:%Y/%m/%d}/"
        f"{filename}"
    )