from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError


@dataclass(slots=True)
class StorageResult:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class S3RawStorage:
    def __init__(
        self,
        *,
        bucket: str,
        region_name: str | None = None,
    ):
        self.bucket = bucket

        self.client = boto3.client(
            "s3",
            region_name=region_name,
        )

    @staticmethod
    def build_key(
        *,
        source_code: str,
        entity_type: str,
        source_entity_id: str,
        collected_at: datetime,
    ) -> str:

        timestamp = collected_at.strftime(
            "%Y%m%dT%H%M%S"
        )

        return (
            f"raw/{source_code.lower()}/"
            f"{entity_type.lower()}/"
            f"{collected_at:%Y/%m/%d}/"
            f"{source_entity_id}/"
            f"{timestamp}.json"
        )

    def save(
        self,
        *,
        source_code: str,
        entity_type: str,
        source_entity_id: str,
        collected_at: datetime,
        payload: dict[str, Any],
    ) -> StorageResult:

        key = self.build_key(
            source_code=source_code,
            entity_type=entity_type,
            source_entity_id=source_entity_id,
            collected_at=collected_at,
        )

        body = json.dumps(
            payload,
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

        return StorageResult(
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