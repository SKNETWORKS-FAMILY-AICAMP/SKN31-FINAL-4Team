from __future__ import annotations

from abc import ABC, abstractmethod

from .s3 import S3Storage


class BasePlatformPipeline(ABC):

    SOURCE: str

    def __init__(
        self,
        *,
        bucket: str,
        region_name: str | None = None,
    ):
        self.storage = S3Storage(
            bucket=bucket,
            region_name=region_name,
        )

    def run_target(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict | None = None,
    ) -> dict:

        collected = self.collect(
            target_type=target_type,
            target_url=target_url,
            params=params or {},
        )

        entity_type = collected["entity_type"]
        source_entity_id = collected[
            "source_entity_id"
        ]
        collected_at = collected[
            "collected_at"
        ]
        payload = collected["payload"]

        uploaded = self.storage.upload_raw_json(
            source=self.SOURCE,
            entity_type=entity_type,
            source_entity_id=source_entity_id,
            collected_at=collected_at,
            data=payload,
        )

        verified = self.storage.exists(
            uploaded.key
        )

        return {
            "source": self.SOURCE,

            "entity_type": entity_type,

            "source_entity_id": (
                source_entity_id
            ),

            "source_url": collected.get(
                "source_url"
            ),

            "collected_at": collected_at,

            "http_status": collected.get(
                "http_status"
            ),

            # S3에 저장되는 실제 파일은 JSON
            "content_type": "application/json",

            "s3": {
                "bucket": uploaded.bucket,
                "key": uploaded.key,
                "uri": uploaded.uri,
                "verified": verified,
            },

            "discovered_count": (
                collected.get(
                    "discovered_count",
                    0,
                )
            ),

            "success_count": (
                collected.get(
                    "success_count",
                    0,
                )
            ),

            "failure_count": (
                collected.get(
                    "failure_count",
                    0,
                )
            ),
        }

    @abstractmethod
    def collect(
        self,
        *,
        target_type: str,
        target_url: str | None,
        params: dict,
    ) -> dict:
        raise NotImplementedError