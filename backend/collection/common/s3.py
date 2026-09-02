from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

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

    # ============================================================
    # S3 KEY
    # ============================================================

    @staticmethod
    def build_raw_key(
        *,
        source: str,
        entity_type: str,
        source_entity_id: str,
        collected_at: str,
    ) -> str:

        dt = datetime.fromisoformat(
            collected_at
        )

        timestamp = dt.strftime(
            "%Y%m%dT%H%M%S"
        )

        return (
            f"raw/{source.lower()}/"
            f"{entity_type.lower()}/"
            f"{dt:%Y/%m/%d}/"
            f"{source_entity_id}/"
            f"{timestamp}.json"
        )

    # ============================================================
    # JSON UPLOAD
    # ============================================================

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
            ContentType=(
                "application/json; charset=utf-8"
            ),
        )

        return S3UploadResult(
            bucket=self.bucket,
            key=key,
        )

    # ============================================================
    # RAW JSON UPLOAD
    # ============================================================

    def upload_raw_json(
        self,
        *,
        source: str,
        entity_type: str,
        source_entity_id: str,
        collected_at: str,
        data,
    ) -> S3UploadResult:

        key = self.build_raw_key(
            source=source,
            entity_type=entity_type,
            source_entity_id=source_entity_id,
            collected_at=collected_at,
        )

        return self.upload_json(
            key=key,
            data=data,
        )

    # ============================================================
    # EXISTS
    # ============================================================

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
                .get(
                    "Error",
                    {},
                )
                .get(
                    "Code"
                )
            )

            if str(code) in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return False

            raise