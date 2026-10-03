from __future__ import annotations

import hashlib

import json

import os

import time

import traceback

from datetime import timedelta

from typing import Any

from django.db import transaction

from django.utils import timezone

from apps.core.models import (

    CrawlRun,

    CrawlTarget,

    RawDocument,

)

from collection.registry import (

    register_all_pipelines,

)

from .registry import get_pipeline_class

from .schemas import CollectionResult

from .storage import S3RawStorage

from pipeline.product_processing import (
    run_step01_step02,
)
from pipeline.text_processing import run_text_step02

# ============================================================

# Progress Logger

# ============================================================

class CollectionLogger:

    def __init__(

        self,

        target: CrawlTarget,

    ):

        self.target = target

        self.started = time.perf_counter()

        self.current_step = 0

        self.total_steps = 8

    def header(self) -> None:

        print()

        print("=" * 80)

        print("[수집 시작]")

        print(f"Target ID   : {self.target.id}")

        print(f"Target Name : {self.target.name}")

        print(f"Source      : {self.target.source.code}")

        print(f"Type        : {self.target.target_type}")

        print("=" * 80)

    def step(

        self,

        title: str,

        detail: str | None = None,

    ) -> None:

        self.current_step += 1

        print()

        print(

            f"[{self.current_step}/{self.total_steps}] "

            f"{title}"

        )

        if detail:

            print(f"      {detail}")

    def success(

        self,

        crawl_run: CrawlRun,

        raw_document: RawDocument,

        result: CollectionResult,

        ingestion_result: dict | None,
        normalization_result: dict | None,

    ) -> None:

        elapsed = (

            time.perf_counter()

            - self.started

        )

        print()

        print("=" * 80)

        print("[수집 완료]")

        print(f"CrawlRun ID     : {crawl_run.id}")

        print(f"RawDocument ID  : {raw_document.id}")

        print(f"발견             : {result.discovered_count}")

        print(f"수집 성공        : {result.success_count}")

        print(f"수집 실패        : {result.failure_count}")

        if ingestion_result is not None:
            print("STEP01           : 완료")
        else:
            print("STEP01           : 대상 아님")

        if normalization_result is None:
            print("STEP02           : 대상 아님")
        else:
            print(
                "STEP02           : "
                f"{normalization_result.get('status')} "
                f"(성공 {normalization_result.get('success', 0)} / "
                f"실패 {normalization_result.get('failed', 0)})"
            )

        print(f"소요 시간        : {elapsed:.2f}초")

        print("=" * 80)

    def failure(

        self,

        exc: Exception,

    ) -> None:

        elapsed = (

            time.perf_counter()

            - self.started

        )

        print()

        print("=" * 80)

        print("[수집 실패]")

        print(

            f"실패 단계 : "

            f"{self.current_step}/{self.total_steps}"

        )

        print(

            f"오류 유형 : "

            f"{type(exc).__name__}"

        )

        print(

            f"오류 내용 : "

            f"{exc}"

        )

        print(

            f"소요 시간 : "

            f"{elapsed:.2f}초"

        )

        print("=" * 80)

# ============================================================

# Helpers

# ============================================================

def _create_storage() -> S3RawStorage:

    bucket = os.getenv(

        "AWS_STORAGE_BUCKET_NAME"

    )

    if not bucket:

        raise RuntimeError(

            "AWS_STORAGE_BUCKET_NAME "

            "환경변수가 없습니다."

        )

    return S3RawStorage(

        bucket=bucket,

        region_name=os.getenv(

            "AWS_REGION",

            "ap-northeast-2",

        ),

    )

def _make_content_hash(

    payload: dict[str, Any],

) -> str:

    raw = json.dumps(

        payload,

        ensure_ascii=False,

        sort_keys=True,

        default=str,

    ).encode("utf-8")

    return hashlib.sha256(

        raw

    ).hexdigest()

def _next_crawl_at(

    target: CrawlTarget,

):

    if not target.interval_minutes:

        return None

    return (

        timezone.now()

        + timedelta(

            minutes=target.interval_minutes

        )

    )

def _process_youtube_result(*, target: CrawlTarget, result: CollectionResult) -> dict[str, Any]:
    from apps.core.models import ContentItem
    from apps.core.services.content import (
        upsert_youtube_comments,
        upsert_youtube_content_items,
        upsert_youtube_content_profile,
    )

    platform_data = (result.metadata or {}).get("platform_data") or {}
    entity_type = result.entity_type.upper().strip()

    if entity_type == "CREATOR":
        profile_data = platform_data.get("profile") or {}
        profile = upsert_youtube_content_profile(
            source=target.source,
            data=profile_data,
        )
        videos = platform_data.get("videos") or []
        video_result = None
        if videos:
            video_result = upsert_youtube_content_items(
                source=target.source,
                videos=videos,
                profile=profile,
                observed_at=platform_data.get("collected_at"),
            )
        return {
            "entity_type": entity_type,
            "content_profile_id": profile.id,
            "video_result": video_result,
        }

    if entity_type == "COMMENT":
        video_id = str(platform_data.get("video_id") or result.source_entity_id)
        item = ContentItem.objects.get(
            source=target.source,
            external_content_id=video_id,
        )
        comment_result = upsert_youtube_comments(
            source=target.source,
            content_item=item,
            comments=platform_data.get("comments") or [],
        )
        return {
            "entity_type": entity_type,
            "content_item_id": item.id,
            "comment_result": comment_result,
            "comments_disabled": bool(platform_data.get("disabled")),
        }

    raise ValueError(f"지원하지 않는 YOUTUBE entity_type: {entity_type}")


# ============================================================

# Runner

# ============================================================

def run_target(

    target_id: int,

) -> dict[str, Any]:

    # --------------------------------------------------------

    # 1. Target

    # --------------------------------------------------------

    target = (

        CrawlTarget.objects

        .select_related("source")

        .get(id=target_id)

    )

    logger = CollectionLogger(

        target

    )

    logger.header()

    crawl_run: CrawlRun | None = None

    try:

        logger.step(

            "CrawlTarget 확인 완료",

            (

                f"{target.source.code} / "

                f"{target.target_type}"

            ),

        )

        # ----------------------------------------------------

        # 2. CrawlRun

        # ----------------------------------------------------

        crawl_run = CrawlRun.objects.create(

            source=target.source,

            crawl_target=target,

            run_type=target.collection_mode,

            target=target.name,

            params=target.params or {},

            status="RUNNING",

            started_at=timezone.now(),

            discovered_count=0,

            success_count=0,

            failure_count=0,

        )

        logger.step(

            "CrawlRun 생성 완료",

            f"CrawlRun ID: {crawl_run.id}",

        )

        # ----------------------------------------------------

        # 3. Collection Pipeline

        # ----------------------------------------------------

        register_all_pipelines()

        pipeline_class = get_pipeline_class(

            target.source.code

        )

        pipeline = pipeline_class()

        result = pipeline.run(

            target_type=target.target_type,

            target_url=target.target_url,

            params=target.params or {},

        )

        logger.step(

            "플랫폼 데이터 수집 완료",

            (

                f"발견 {result.discovered_count} / "

                f"성공 {result.success_count} / "

                f"실패 {result.failure_count}"

            ),

        )

        # ----------------------------------------------------

        # 4. S3 RAW

        # ----------------------------------------------------

        storage = _create_storage()

        stored = storage.save(

            source_code=result.source_code,

            entity_type=result.entity_type,

            source_entity_id=(

                result.source_entity_id

            ),

            collected_at=result.collected_at,

            payload=result.payload,

        )

        logger.step(

            "S3 RAW 저장 완료",

            stored.uri,

        )

        # ----------------------------------------------------

        # 5. RawDocument

        # ----------------------------------------------------

        content_hash = _make_content_hash(

            result.payload

        )

        raw_document = (

            RawDocument.objects.create(

                source=target.source,

                crawl_run=crawl_run,

                document_type=(

                    result.entity_type

                ),

                external_id=(

                    result.source_entity_id

                ),

                source_url=(

                    result.source_url

                ),

                s3_bucket=stored.bucket,

                s3_key=stored.key,

                content_hash=content_hash,

                http_status=(

                    result.http_status

                ),

                content_type=(

                    "application/json"

                ),

                collected_at=(

                    result.collected_at

                ),

            )

        )

        logger.step(

            "RawDocument 등록 완료",

            (

                f"RawDocument ID: "

                f"{raw_document.id}"

            ),

        )

        # ----------------------------------------------------

        # 6. Source-specific processing

        # ----------------------------------------------------

        source_code = target.source.code.upper().strip()
        youtube_result = None
        text_normalization_result = None

        if source_code == "YOUTUBE":
            youtube_result = _process_youtube_result(
                target=target,
                result=result,
            )
            processing_result = {"step01": None, "step02": None}

            if youtube_result.get("entity_type") == "COMMENT":
                comment_result = youtube_result.get("comment_result") or {}
                text_document_ids = comment_result.get("text_document_ids") or []
                text_normalization_result = run_text_step02(
                    text_document_ids=text_document_ids,
                )
        else:
            processing_result = run_step01_step02(
                source_code=target.source.code,
                raw_document_id=raw_document.id,
            )
            text_normalization_result = processing_result.get("text_step02")

        ingestion_result = processing_result.get("step01")
        normalization_result = processing_result.get("step02")

        if ingestion_result is None:
            logger.step(
                "STEP01 대상 아님",
                f"Source: {target.source.code}",
            )
        else:
            logger.step(
                "STEP01 정제 및 적재 완료",
                f"ProductSource {len(ingestion_result.get('product_source_ids') or [])}개",
            )

        if normalization_result is None:
            logger.step(
                "STEP02 대상 아님",
                f"Source: {target.source.code}",
            )
        else:
            logger.step(
                "STEP02 상품 정규화 완료",
                (
                    f"Status={normalization_result.get('status')} / "
                    f"성공={normalization_result.get('success', 0)} / "
                    f"실패={normalization_result.get('failed', 0)}"
                ),
            )

        print()
        print("[STEP01 RESULT]")
        print(json.dumps(ingestion_result, ensure_ascii=False, indent=2, default=str))

        print()
        print("[STEP02 RESULT]")
        print(json.dumps(normalization_result, ensure_ascii=False, indent=2, default=str))

        # ----------------------------------------------------

        # 8. Complete

        # ----------------------------------------------------

        finished_at = timezone.now()

        with transaction.atomic():

            (

                CrawlRun.objects

                .filter(

                    id=crawl_run.id

                )

                .update(

                    status="SUCCESS",

                    finished_at=finished_at,

                    discovered_count=(

                        result.discovered_count

                    ),

                    success_count=(

                        result.success_count

                    ),

                    failure_count=(

                        result.failure_count

                    ),

                    error_code=None,

                    error_message=None,

                )

            )

            (

                CrawlTarget.objects

                .filter(

                    id=target.id

                )

                .update(

                    last_crawled_at=(

                        finished_at

                    ),

                    next_crawl_at=(

                        _next_crawl_at(

                            target

                        )

                    ),

                )

            )

        crawl_run.refresh_from_db()

        logger.step(

            "수집 실행 완료",

            (

                f"Status: "

                f"{crawl_run.status}"

            ),

        )

        logger.success(

            crawl_run,

            raw_document,

            result,

            ingestion_result,
            normalization_result,

        )

        return {

            "ok": True,

            "target_id":

                target.id,

            "target_name":

                target.name,

            "source":

                target.source.code,

            "crawl_run_id":

                crawl_run.id,

            "raw_document_id":

                raw_document.id,

            "s3_bucket":

                stored.bucket,

            "s3_key":

                stored.key,

            "discovered_count":

                result.discovered_count,

            "success_count":

                result.success_count,

            "failure_count":

                result.failure_count,

            "step01_ingestion":
                ingestion_result,

            "step02_normalization":
                normalization_result,

            "text_step02_normalization":
                text_normalization_result,

            "youtube_processing":
                youtube_result,

        }

    # ========================================================

    # Failure

    # ========================================================

    except Exception as exc:

        logger.failure(

            exc

        )

        if crawl_run is not None:

            (

                CrawlRun.objects

                .filter(

                    id=crawl_run.id

                )

                .update(

                    status="FAILED",

                    finished_at=(

                        timezone.now()

                    ),

                    failure_count=1,

                    error_code=(

                        type(exc).__name__

                    ),

                    error_message=(

                        str(exc)[:5000]

                    ),

                )

            )

        traceback.print_exc()

        raise
