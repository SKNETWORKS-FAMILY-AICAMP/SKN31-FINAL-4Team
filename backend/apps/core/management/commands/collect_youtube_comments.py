# backend/apps/core/management/commands/collect_youtube_comments.py

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import (
    ContentItem,
    CrawlRun,
    RawDocument,
    Source,
)
from apps.core.services.content import (
    upsert_youtube_comments,
)
from collection.common.s3 import S3Storage
from collection.youtube.collector import YoutubeCollector
from collection.youtube.constants import (
    DEFAULT_COMMENT_LIMIT,
)


DEFAULT_SOURCE_CODE = "YOUTUBE"


class Command(BaseCommand):
    help = (
        "YouTube 영상의 댓글을 수집해 "
        "S3(원본)와 TextDocument(분석용)에 적재합니다. "
        "조회수 수집(run_live_target)과 별도로 실행합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=DEFAULT_SOURCE_CODE,
            help=f"Source.code (기본: {DEFAULT_SOURCE_CODE})",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="처리할 영상 수 (미지정 시 전체)",
        )
        parser.add_argument(
            "--comments",
            type=int,
            default=DEFAULT_COMMENT_LIMIT,
            help=(
                "영상당 수집할 댓글 수 "
                f"(기본: {DEFAULT_COMMENT_LIMIT})"
            ),
        )
        parser.add_argument(
            "--channel",
            default=None,
            help="특정 채널만 (ContentProfile.external_profile_id)",
        )
        parser.add_argument(
            "--content-type",
            default=None,
            choices=["VIDEO", "SHORTS"],
            help="영상 유형 필터",
        )
        parser.add_argument(
            "--skip-collected",
            action="store_true",
            help="이미 댓글이 적재된 영상은 건너뜁니다.",
        )
        parser.add_argument(
            "--s3-only",
            action="store_true",
            help=(
                "S3에만 원본을 저장하고 "
                "TextDocument 적재는 하지 않습니다. "
                "정규화 기준이 정해진 뒤 "
                "S3에서 다시 읽어 적재할 수 있습니다."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="API 호출 없이 대상만 출력합니다.",
        )

    # --------------------------------------------------------

    def handle(self, *args, **options):
        source_code = options["source"]
        video_limit = options["limit"]
        comment_limit = max(1, int(options["comments"]))
        channel_id = options["channel"]
        content_type = options["content_type"]
        skip_collected = options["skip_collected"]
        s3_only = options["s3_only"]
        dry_run = options["dry_run"]

        try:
            source = Source.objects.get(
                code=source_code,
            )
        except Source.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    f"Source '{source_code}' 가 없습니다."
                )
            )
            return

        queryset = (
            ContentItem.objects
            .select_related("profile")
            .filter(source=source)
            .order_by("id")
        )

        if channel_id:
            queryset = queryset.filter(
                profile__external_profile_id=channel_id,
            )

        if content_type:
            queryset = queryset.filter(
                content_type=content_type,
            )

        if skip_collected:
            queryset = queryset.filter(
                text_documents__isnull=True,
            ).distinct()

        if video_limit:
            queryset = queryset[:video_limit]

        videos = list(queryset)

        self.stdout.write(
            f"source={source_code} "
            f"대상 영상 {len(videos)}건 / "
            f"영상당 댓글 {comment_limit}건 / "
            f"예상 쿼터 약 {len(videos)} units"
            + (" / S3 전용 모드" if s3_only else "")
        )

        if not videos:
            self.stdout.write(
                self.style.WARNING("대상 영상이 없습니다.")
            )
            return

        if dry_run:
            for item in videos[:20]:
                self.stdout.write(
                    f"  [dry-run] #{item.id} "
                    f"{item.external_content_id} "
                    f"[{item.content_type}] "
                    f"{(item.title or '')[:40]}"
                )
            if len(videos) > 20:
                self.stdout.write(
                    f"  ... 외 {len(videos) - 20}건"
                )
            return

        # ----------------------------------------------------
        # CRAWL RUN
        # ----------------------------------------------------

        crawl_run = CrawlRun.objects.create(
            source=source,
            run_type=CrawlRun.RunType.MANUAL,
            target="youtube:comments",
            params={
                "comment_limit": comment_limit,
                "video_count": len(videos),
                "content_type": content_type,
                "channel": channel_id,
                "s3_only": s3_only,
            },
            status=CrawlRun.Status.RUNNING,
            started_at=timezone.now(),
        )

        storage = S3Storage(
            bucket=settings.AWS_STORAGE_BUCKET_NAME,
            region_name=settings.AWS_REGION,
        )

        total_created = 0
        total_updated = 0
        total_failed = 0
        disabled_count = 0
        error_count = 0

        try:
            with YoutubeCollector(
                api_key=settings.YOUTUBE_API_KEY
            ) as collector:

                for index, item in enumerate(
                    videos,
                    start=1,
                ):
                    video_id = item.external_content_id

                    result = collector.collect_comments(
                        video_id,
                        limit=comment_limit,
                    )

                    if result["disabled"]:
                        disabled_count += 1
                        self.stdout.write(
                            f"{index}/{len(videos)} "
                            f"SKIP {video_id} 댓글 비활성"
                        )
                        continue

                    if result["error"]:
                        error_count += 1
                        self.stderr.write(
                            self.style.WARNING(
                                f"{index}/{len(videos)} "
                                f"FAIL {video_id} "
                                f"{result['error']['error_type']}"
                            )
                        )
                        continue

                    comments = result["comments"]

                    if not comments:
                        self.stdout.write(
                            f"{index}/{len(videos)} "
                            f"---- {video_id} 댓글 없음"
                        )
                        continue

                    collected_at = datetime.now(
                        dt_timezone.utc
                    ).isoformat()

                    # ------------------------------------
                    # S3 원본
                    # ------------------------------------

                    uploaded = storage.upload_raw_json(
                        source="YOUTUBE",
                        entity_type="COMMENT",
                        source_entity_id=video_id,
                        collected_at=collected_at,
                        data={
                            "video": {
                                "content_item_id": item.id,
                                "video_id": video_id,
                                "title": item.title,
                                "content_type": (
                                    item.content_type
                                ),
                            },
                            "comments": comments,
                            "meta": {
                                "source": "YOUTUBE",
                                "collected_at": collected_at,
                                "comment_limit": (
                                    comment_limit
                                ),
                                "summary": result[
                                    "summary"
                                ],
                            },
                        },
                    )

                    RawDocument.objects.create(
                        source=source,
                        crawl_run=crawl_run,
                        document_type="COMMENT",
                        external_id=video_id,
                        source_url=item.content_url,
                        s3_bucket=uploaded.bucket,
                        s3_key=uploaded.key,
                        http_status=200,
                        content_type="application/json",
                        collected_at=timezone.now(),
                    )

                    # ------------------------------------
                    # DB 적재
                    # ------------------------------------

                    if s3_only:
                        self.stdout.write(
                            f"{index}/{len(videos)} "
                            f"S3 {video_id} "
                            f"[{item.content_type}] "
                            f"댓글 {len(comments)}건 "
                            f"(원댓글 "
                            f"{result['summary']['top_level_count']}"
                            f" / 대댓글 "
                            f"{result['summary']['reply_count']})"
                        )
                        continue

                    saved = upsert_youtube_comments(
                        source=source,
                        content_item=item,
                        comments=comments,
                    )

                    total_created += saved["created"]
                    total_updated += saved["updated"]
                    total_failed += saved["failed"]

                    self.stdout.write(
                        f"{index}/{len(videos)} "
                        f"OK {video_id} "
                        f"[{item.content_type}] "
                        f"new={saved['created']} "
                        f"upd={saved['updated']} "
                        f"(원댓글 "
                        f"{result['summary']['top_level_count']}"
                        f" / 대댓글 "
                        f"{result['summary']['reply_count']})"
                    )

        except Exception as exc:
            crawl_run.status = CrawlRun.Status.FAILED
            crawl_run.error_code = exc.__class__.__name__
            crawl_run.error_message = str(exc)[:10000]
            crawl_run.finished_at = timezone.now()
            crawl_run.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "finished_at",
                ]
            )
            raise

        # ----------------------------------------------------
        # 마무리
        # ----------------------------------------------------

        processed = (
            len(videos)
            - disabled_count
            - error_count
        )

        crawl_run.status = (
            CrawlRun.Status.SUCCESS
            if error_count == 0
            else CrawlRun.Status.PARTIAL_SUCCESS
        )
        crawl_run.discovered_count = len(videos)
        crawl_run.success_count = processed
        crawl_run.failure_count = error_count
        crawl_run.finished_at = timezone.now()
        crawl_run.save(
            update_fields=[
                "status",
                "discovered_count",
                "success_count",
                "failure_count",
                "finished_at",
            ]
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"완료 | crawl_run={crawl_run.id} | "
                f"영상 {len(videos)}건 "
                f"(처리 {processed} / "
                f"댓글비활성 {disabled_count} / "
                f"오류 {error_count}) | "
                + (
                    "S3 저장만 완료 (DB 미적재)"
                    if s3_only
                    else (
                        f"댓글 신규 {total_created} "
                        f"갱신 {total_updated} "
                        f"실패 {total_failed}"
                    )
                )
            )
        )
