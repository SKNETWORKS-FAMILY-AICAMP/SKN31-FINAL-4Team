from __future__ import annotations

import json
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError


@dataclass
class S3UploadResult:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class S3Storage:
    def __init__(
        self,
        bucket: str,
        *,
        region_name: str | None = None,
    ):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region_name,
        )

    def upload_json(
        self,
        *,
        key: str,
        data,
    ) -> S3UploadResult:

        body = json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=str,
        ).encode("utf-8")

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json; charset=utf-8",
        )

        return S3UploadResult(
            bucket=self.bucket,
            key=key,
        )

    def exists(
        self,
        key: str,
    ) -> bool:

        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=key,
            )

            return True

        except ClientError as exc:
            code = (
                exc.response
                .get("Error", {})
                .get("Code")
            )

            if str(code) in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return False

            raise