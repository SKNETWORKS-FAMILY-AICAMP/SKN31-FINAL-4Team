import hashlib
import json

from django.utils import timezone

from apps.crawler.models import (
    CrawlJob,
    CrawlTarget,
    RawObject,
)
from apps.crawler.services.zigzag import ZigzagProductRepository
from collection.zigzag.collector import (
    ZigzagCollectError,
    ZigzagCollector,
)
from collection.zigzag.constant import (
    DEFAULT_PAGE_ID,
    SEARCH_RESULT_API_URL,
)


class ZigzagPipeline:
    """
    지그재그 카테고리 크롤링 파이프라인.

    책임:
    - CrawlJob 생성 및 상태 관리
    - Collector 호출
    - 페이지별 RawObject 기록
    - Repository를 통한 DB 반영
    - 수집 결과 집계

    하지 않는 일:
    - HTTP 요청 세부 처리
    - ORM upsert 세부 처리
    - Celery 스케줄링 및 재시도
    """

    def __init__(
        self,
        *,
        collector: ZigzagCollector | None = None,
        repository: ZigzagProductRepository | None = None,
        storage=None,
    ):
        self.collector = collector or ZigzagCollector()
        self.repository = repository or ZigzagProductRepository()
        self.storage = storage

    def run(
        self,
        *,
        crawl_target: CrawlTarget,
        category_id: str,
        sort: str = "200",
        page_id: str = DEFAULT_PAGE_ID,
        max_pages: int | None = None,
        trigger_type: str = CrawlJob.TriggerType.SCHEDULED,
    ) -> CrawlJob:

        crawl_job = CrawlJob.objects.create(
            source=crawl_target.source,
            crawl_target=crawl_target,
            status=CrawlJob.Status.RUNNING,
            trigger_type=trigger_type,
            started_at=timezone.now(),
        )

        observed_at = timezone.now()
        all_items: list[dict] = []

        try:
            # ====================================================
            # 1. COLLECT
            # ====================================================

            pages = self.collector.iter_category_pages(
                category_id=category_id,
                sort=sort,
                page_id=page_id,
                max_pages=max_pages,
            )

            for page_index, (
                raw_body,
                parsed_items,
                _has_next,
            ) in enumerate(
                pages,
                start=1,
            ):
                self._save_raw_object(
                    crawl_job=crawl_job,
                    crawl_target=crawl_target,
                    page_index=page_index,
                    raw_body=raw_body,
                    collected_at=observed_at,
                )

                all_items.extend(parsed_items)

            # ====================================================
            # 2. SAVE
            # ====================================================

            created_count, updated_count = self.repository.save_ranked_items(
                items=all_items,
                crawl_target=crawl_target,
                crawl_job=crawl_job,
                observed_at=observed_at,
            )

            # ====================================================
            # 3. SUCCESS
            # ====================================================

            crawl_job.status = CrawlJob.Status.SUCCESS
            crawl_job.items_found = len(all_items)
            crawl_job.items_created = created_count
            crawl_job.items_updated = updated_count
            crawl_job.finished_at = timezone.now()

            crawl_job.save(
                update_fields=[
                    "status",
                    "items_found",
                    "items_created",
                    "items_updated",
                    "finished_at",
                ]
            )

            return crawl_job

        except ZigzagCollectError as exc:
            self._mark_failed(
                crawl_job,
                exc,
            )
            raise

        except Exception as exc:
            self._mark_failed(
                crawl_job,
                exc,
            )
            raise

        finally:
            self.collector.close()

    # ============================================================
    # RAW OBJECT
    # ============================================================

    def _save_raw_object(
        self,
        *,
        crawl_job: CrawlJob,
        crawl_target: CrawlTarget,
        page_index: int,
        raw_body: dict,
        collected_at,
    ) -> None:

        raw_text = json.dumps(
            raw_body,
            ensure_ascii=False,
        )

        checksum = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        storage_key = (
            f"zigzag/{crawl_target.id}/"
            f"{collected_at:%Y/%m/%d}/"
            f"{crawl_job.id}_{page_index}.json"
        )

        if self.storage is not None:
            self.storage.upload_text(
                storage_key,
                raw_text,
            )

        RawObject.objects.create(
            source=crawl_target.source,
            crawl_target=crawl_target,
            crawl_job=crawl_job,
            request_url=SEARCH_RESULT_API_URL,
            storage_key=storage_key,
            content_type="application/json",
            http_status=200,
            checksum=checksum,
            collected_at=collected_at,
        )

    # ============================================================
    # JOB STATUS
    # ============================================================

    @staticmethod
    def _mark_failed(
        crawl_job: CrawlJob,
        exc: Exception,
    ) -> None:

        crawl_job.status = CrawlJob.Status.FAILED
        crawl_job.error_type = exc.__class__.__name__
        crawl_job.error_message = str(exc)
        crawl_job.finished_at = timezone.now()

        crawl_job.save(
            update_fields=[
                "status",
                "error_type",
                "error_message",
                "finished_at",
            ]
        )
