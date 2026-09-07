from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import (
    CrawlRun,
    CrawlTarget,
    RawDocument,
)

from collection.zigzag.pipeline import (
    ZigzagPipeline,
)


# ============================================================
# PLATFORM ROUTER
# ============================================================


def get_platform_pipeline(
    *,
    source_code: str,
    bucket: str,
    region_name: str | None = None,
):
    source_code = (
        source_code
        or ""
    ).upper().strip()

    if source_code == "ZIGZAG":
        return ZigzagPipeline(
            bucket=bucket,
            region_name=region_name,
        )

    # 나중에 무신사도 동일하게
    #
    # if source_code == "MUSINSA":
    #     return MusinsaPipeline(
    #         bucket=bucket,
    #         region_name=region_name,
    #     )

    raise ValueError(
        f"지원하지 않는 source입니다: "
        f"{source_code}"
    )


# ============================================================
# DATETIME
# ============================================================


def _to_datetime(
    value,
):
    if value is None:
        return timezone.now()

    if hasattr(
        value,
        "tzinfo",
    ):
        return value

    parsed = parse_datetime(
        str(value)
    )

    if parsed is not None:
        return parsed

    return timezone.now()


# ============================================================
# MAIN RUNNER
# ============================================================


def run_crawl_target(
    *,
    target_id: int,
    bucket: str,
    region_name: str | None = None,
    run_type: str = CrawlRun.RunType.MANUAL,
) -> dict:

    # --------------------------------------------------------
    # TARGET
    # --------------------------------------------------------

    target = (
        CrawlTarget.objects
        .select_related(
            "source",
        )
        .get(
            id=target_id,
        )
    )

    source = target.source

    # --------------------------------------------------------
    # CRAWL RUN CREATE
    # --------------------------------------------------------

    crawl_run = (
        CrawlRun.objects
        .create(
            source=source,
            crawl_target=target,

            run_type=run_type,

            target=(
                target.name
                or target.target_url
                or f"target:{target.id}"
            ),

            params=target.params or {},

            status=(
                CrawlRun.Status.RUNNING
            ),

            started_at=timezone.now(),
        )
    )

    try:

        # ----------------------------------------------------
        # PLATFORM PIPELINE
        # ----------------------------------------------------

        pipeline = (
            get_platform_pipeline(
                source_code=source.code,
                bucket=bucket,
                region_name=region_name,
            )
        )

        # ----------------------------------------------------
        # COLLECT + S3
        # ----------------------------------------------------

        result = pipeline.run_target(
            target_type=(
                target.target_type
            ),
            target_url=(
                target.target_url
            ),
            params=(
                target.params
                or {}
            ),
        )

        # ----------------------------------------------------
        # S3 VERIFY
        # ----------------------------------------------------

        s3_data = (
            result.get("s3")
            or {}
        )

        if not s3_data.get(
            "verified"
        ):
            raise RuntimeError(
                "S3 업로드 후 "
                "파일 검증에 실패했습니다."
            )

        collected_at = (
            _to_datetime(
                result.get(
                    "collected_at"
                )
            )
        )

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        discovered_count = int(
            result.get(
                "discovered_count",
                0,
            )
            or 0
        )

        success_count = int(
            result.get(
                "success_count",
                0,
            )
            or 0
        )

        failure_count = int(
            result.get(
                "failure_count",
                0,
            )
            or 0
        )

        if (
            failure_count > 0
            and success_count > 0
        ):
            final_status = (
                CrawlRun.Status.PARTIAL_SUCCESS
            )

        elif (
            failure_count > 0
            and success_count == 0
        ):
            final_status = (
                CrawlRun.Status.FAILED
            )

        else:
            final_status = (
                CrawlRun.Status.SUCCESS
            )

        finished_at = (
            timezone.now()
        )

        # ----------------------------------------------------
        # DB SAVE
        # ----------------------------------------------------

        with transaction.atomic():

            raw_document = (
                RawDocument.objects
                .create(
                    source=source,
                    crawl_run=crawl_run,

                    document_type=(
                        result.get(
                            "entity_type"
                        )
                        or target.target_type
                    ),

                    external_id=(
                        result.get(
                            "source_entity_id"
                        )
                    ),

                    source_url=(
                        result.get(
                            "source_url"
                        )
                    ),

                    s3_bucket=(
                        s3_data[
                            "bucket"
                        ]
                    ),

                    s3_key=(
                        s3_data[
                            "key"
                        ]
                    ),

                    http_status=(
                        result.get(
                            "http_status"
                        )
                    ),

                    content_type=(
                        result.get(
                            "content_type"
                        )
                        or "application/json"
                    ),

                    collected_at=(
                        collected_at
                    ),
                )
            )

            # ----------------------------------------------
            # CrawlRun
            # ----------------------------------------------

            crawl_run.status = (
                final_status
            )

            crawl_run.discovered_count = (
                discovered_count
            )

            crawl_run.success_count = (
                success_count
            )

            crawl_run.failure_count = (
                failure_count
            )

            crawl_run.finished_at = (
                finished_at
            )

            crawl_run.error_code = None
            crawl_run.error_message = None

            crawl_run.save(
                update_fields=[
                    "status",
                    "discovered_count",
                    "success_count",
                    "failure_count",
                    "finished_at",
                    "error_code",
                    "error_message",
                ]
            )

            # ----------------------------------------------
            # CrawlTarget
            # ----------------------------------------------

            target.last_crawled_at = (
                finished_at
            )

            target.next_crawl_at = (
                finished_at
                + timedelta(
                    minutes=(
                        target.interval_minutes
                    )
                )
            )

            target.save(
                update_fields=[
                    "last_crawled_at",
                    "next_crawl_at",
                    "updated_at",
                ]
            )

        # ----------------------------------------------------
        # RETURN
        # ----------------------------------------------------

        return {
            "ok": True,

            "target_id":
                target.id,

            "crawl_run_id":
                crawl_run.id,

            "raw_document_id":
                raw_document.id,

            "source":
                source.code,

            "status":
                crawl_run.status,

            "counts": {
                "discovered":
                    discovered_count,

                "success":
                    success_count,

                "failure":
                    failure_count,
            },

            "s3": {
                "bucket":
                    s3_data["bucket"],

                "key":
                    s3_data["key"],

                "uri":
                    s3_data.get("uri"),

                "verified":
                    s3_data.get(
                        "verified"
                    ),
            },
        }

    # ========================================================
    # FAILURE
    # ========================================================

    except Exception as exc:

        crawl_run.status = (
            CrawlRun.Status.FAILED
        )

        crawl_run.error_code = (
            exc.__class__.__name__
        )

        crawl_run.error_message = (
            str(exc)
        )

        crawl_run.finished_at = (
            timezone.now()
        )

        crawl_run.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "finished_at",
            ]
        )

        raise