import time

from django.utils import timezone

from apps.crawler.models import CrawlJob
from apps.crawler.services.musinsa import MusinsaService
from collection.musinsa.collector import MusinsaCollector


class MusinsaPipeline:
    """
    무신사 수집 전체 흐름을 조율하는 Pipeline.

    LIVE
        CrawlTarget
            ↓
        run_target()
            ↓
        run_url()

    BACKFILL
        year_month / gender / category
            ↓
        run_backfill()

    책임:
    - CrawlJob 생성 / 완료 / 실패 처리
    - Collector 호출
    - 요청 간격 제어
    - 현재 랭킹 문맥(rank / period / gender / category) 병합
    - 좋아요 batch 병합
    - Service를 통한 DB 저장
    """

    # LIVE는 개수 제한 없이 Collector가 발견한 전체를 사용
    DEFAULT_LIVE_LIMIT = None

    # 과거 Archive는 우선 30건 유지
    DEFAULT_BACKFILL_LIMIT = 30

    MAX_ERROR_MESSAGES = 30

    # ============================================================
    # LIVE ENTRY
    # ============================================================

    @classmethod
    def run_target(
        cls,
        crawl_target,
        *,
        trigger_type=CrawlJob.TriggerType.MANUAL,
        celery_task_id=None,
        limit=DEFAULT_LIVE_LIMIT,
        crawl_job=None,
    ):
        """
        CrawlTarget 기반 LIVE 수집 진입점.
        """

        if crawl_target.source.code != "MUSINSA":
            raise ValueError("MusinsaPipeline에는 MUSINSA 대상만 전달할 수 있습니다.")

        source = crawl_target.source

        job = crawl_job or CrawlJob.objects.create(
            source=source,
            crawl_target=crawl_target,
            status=CrawlJob.Status.RUNNING,
            trigger_type=trigger_type,
            celery_task_id=celery_task_id,
            started_at=timezone.now(),
        )

        return cls.run_url(
            target_url=crawl_target.target_value,
            source=source,
            crawl_job=job,
            crawl_target=crawl_target,
            limit=limit,
        )

    # ============================================================
    # LIVE URL PIPELINE
    # ============================================================

    @classmethod
    def run_url(
        cls,
        *,
        target_url,
        source,
        crawl_job,
        crawl_target=None,
        limit=DEFAULT_LIVE_LIMIT,
    ):
        """
        LIVE 수집.

        랭킹 URL이면:
        - Collector에서 현재 랭킹 목록 + 순위 수집
        - 상품 상세 수집
        - 현재 랭킹 문맥으로 snapshot 랭킹 정보 덮어쓰기
        - Snapshot 저장

        일반 상품/페이지 URL이면:
        - 기존 discover_product_urls() 흐름 사용
        """

        job = crawl_job

        # 같은 Job에서 수집한 Snapshot은 같은 기준 시각으로 묶는다.
        observed_at = timezone.now()

        try:
            with MusinsaCollector() as collector:

                collected_products = []
                errors = []

                delay = cls._get_request_delay(source)

                # =================================================
                # 1. CURRENT RANKING
                # =================================================

                if "/ranking" in target_url:

                    ranking_items = collector.discover_ranking_items(target_url)

                    if limit is not None:
                        ranking_items = ranking_items[:limit]

                    job.items_found = len(ranking_items)

                    job.save(
                        update_fields=[
                            "items_found",
                        ]
                    )

                    if not ranking_items:
                        raise RuntimeError("랭킹 상품을 찾지 못했습니다.")

                    ranking_year = observed_at.year

                    ranking_month = observed_at.month

                    for index, ranking_item in enumerate(ranking_items):
                        product_url = ranking_item["product_url"]

                        try:
                            parsed = collector.collect_product(product_url)

                            snapshot = parsed["snapshot"]

                            # =====================================
                            # 현재 랭킹 값으로 덮어쓰기
                            #
                            # 상품 상세의 rankingArchiveBadge가 아니라
                            # 지금 실행한 CrawlTarget 기준의 랭킹값 사용
                            # =====================================

                            snapshot["rank"] = ranking_item.get("rank")

                            snapshot["ranking_period"] = ranking_item.get(
                                "ranking_period"
                            )

                            snapshot["ranking_year"] = ranking_year

                            snapshot["ranking_month"] = ranking_month

                            snapshot["ranking_gender"] = ranking_item.get(
                                "ranking_gender"
                            )

                            snapshot["ranking_category_depth1_code"] = ranking_item.get(
                                "ranking_category_depth1_code"
                            )
                            snapshot["ranking_age_band"] = ranking_item.get(
                                "ranking_age_band"
                            )

                            collected_products.append(parsed)

                        except Exception as exc:
                            errors.append((f"[COLLECT] " f"{product_url} " f"- {exc}"))

                        if delay > 0 and index < len(ranking_items) - 1:
                            time.sleep(delay)

                # =================================================
                # 2. GENERAL URL
                # =================================================

                else:

                    product_urls = collector.discover_product_urls(target_url)

                    if limit is not None:
                        product_urls = product_urls[:limit]

                    job.items_found = len(product_urls)

                    job.save(
                        update_fields=[
                            "items_found",
                        ]
                    )

                    if not product_urls:
                        raise RuntimeError("상품 URL을 찾지 못했습니다.")

                    for index, product_url in enumerate(product_urls):

                        try:
                            parsed = collector.collect_product(product_url)

                            collected_products.append(parsed)

                        except Exception as exc:
                            errors.append((f"[COLLECT] " f"{product_url} " f"- {exc}"))

                        if delay > 0 and index < len(product_urls) - 1:
                            time.sleep(delay)

                # =================================================
                # 3. COLLECT RESULT CHECK
                # =================================================

                if not collected_products:

                    error_detail = (
                        "\n".join(errors[: cls.MAX_ERROR_MESSAGES])
                        if errors
                        else "상세 오류 없음"
                    )

                    raise RuntimeError(
                        ("정상적으로 수집된 상품이 없습니다.\n" f"{error_detail}")
                    )

                # =================================================
                # 4. LIKE BATCH
                # =================================================

                cls._merge_like_counts(
                    collector=collector,
                    collected_products=(collected_products),
                    errors=errors,
                )

                # =================================================
                # 5. DB SAVE
                # =================================================

                (
                    created_count,
                    updated_count,
                ) = cls._save_products(
                    collected_products=(collected_products),
                    crawl_job=job,
                    crawl_target=crawl_target,
                    observed_at=observed_at,
                    errors=errors,
                )

            # =====================================================
            # 6. COMPLETE
            # =====================================================

            cls._complete_job(
                job=job,
                created_count=created_count,
                updated_count=updated_count,
                errors=errors,
            )

            return job

        except Exception as exc:

            cls._fail_job(
                job=job,
                exc=exc,
            )

            raise

    # ============================================================
    # BACKFILL PIPELINE
    # ============================================================

    @classmethod
    def run_backfill(
        cls,
        *,
        source,
        crawl_job,
        year_month,
        gender_code,
        category_code,
        limit=DEFAULT_BACKFILL_LIMIT,
    ):
        """
        과거 월간 랭킹 수집.

        중요:
        - 과거 순위는 Archive API의 rank 사용
        - 상품 상세의 현재 랭킹 값은 사용하지 않음
        - 상품 상세 / 태그 / stat은 동일 Collector 사용
        """

        job = crawl_job

        observed_at = timezone.now()

        try:
            with MusinsaCollector() as collector:

                # =================================================
                # 1. ARCHIVE API
                # =================================================

                archive_items = collector.collect_archive_ranking(
                    year_month=year_month,
                    gender_code=gender_code,
                    category_code=category_code,
                )

                if limit is not None:
                    archive_items = archive_items[:limit]

                job.items_found = len(archive_items)

                job.save(
                    update_fields=[
                        "items_found",
                    ]
                )

                if not archive_items:
                    raise RuntimeError("Archive 랭킹 상품을 찾지 못했습니다.")

                # =================================================
                # 2. REQUEST DELAY
                # =================================================

                delay = cls._get_request_delay(source)

                # =================================================
                # 3. DETAIL + ARCHIVE RANKING MERGE
                # =================================================

                collected_products = []
                errors = []

                (
                    ranking_year,
                    ranking_month,
                ) = cls._parse_year_month(year_month)

                for index, archive_item in enumerate(archive_items):

                    goods_no = archive_item.get("goods_no")

                    try:
                        parsed = collector.collect_product(archive_item["product_url"])

                        snapshot = parsed["snapshot"]

                        # Archive 당시 값으로 덮어쓰기
                        snapshot["rank"] = archive_item.get("rank")

                        snapshot["ranking_period"] = "MONTHLY"

                        snapshot["ranking_year"] = ranking_year

                        snapshot["ranking_month"] = ranking_month

                        snapshot["ranking_gender"] = gender_code

                        snapshot["ranking_category_depth1_code"] = category_code

                        collected_products.append(parsed)

                    except Exception as exc:
                        errors.append((f"[COLLECT] " f"{goods_no} " f"- {exc}"))

                    if delay > 0 and index < len(archive_items) - 1:
                        time.sleep(delay)

                if not collected_products:

                    error_detail = (
                        "\n".join(errors[: cls.MAX_ERROR_MESSAGES])
                        if errors
                        else "상세 오류 없음"
                    )

                    raise RuntimeError(
                        (
                            "정상적으로 수집된 "
                            "Archive 상품이 없습니다.\n"
                            f"{error_detail}"
                        )
                    )

                # =================================================
                # 4. LIKE BATCH
                # =================================================

                cls._merge_like_counts(
                    collector=collector,
                    collected_products=(collected_products),
                    errors=errors,
                )

                # =================================================
                # 5. DB SAVE
                # =================================================

                (
                    created_count,
                    updated_count,
                ) = cls._save_products(
                    collected_products=(collected_products),
                    crawl_job=job,
                    crawl_target=None,
                    observed_at=observed_at,
                    errors=errors,
                )

            # =====================================================
            # 6. COMPLETE
            # =====================================================

            cls._complete_job(
                job=job,
                created_count=created_count,
                updated_count=updated_count,
                errors=errors,
            )

            return job

        except Exception as exc:

            cls._fail_job(
                job=job,
                exc=exc,
            )

            raise

    # ============================================================
    # HELPER - LIKE
    # ============================================================

    @classmethod
    def _merge_like_counts(
        cls,
        *,
        collector,
        collected_products,
        errors,
    ):
        goods_nos = [
            parsed["product"]["goods_no"]
            for parsed in collected_products
            if (parsed.get("product") and parsed["product"].get("goods_no") is not None)
        ]

        try:
            like_counts = collector.collect_like_counts(goods_nos)

        except Exception as exc:
            like_counts = {}

            errors.append(f"[LIKE_BATCH] {exc}")

        for parsed in collected_products:

            goods_no = parsed["product"].get("goods_no")

            parsed["snapshot"]["like_count"] = like_counts.get(goods_no)

    # ============================================================
    # HELPER - SAVE
    # ============================================================

    @classmethod
    def _save_products(
        cls,
        *,
        collected_products,
        crawl_job,
        crawl_target,
        observed_at,
        errors,
    ):
        created_count = 0
        updated_count = 0

        for parsed in collected_products:

            goods_no = parsed.get(
                "product",
                {},
            ).get("goods_no")

            try:
                saved = MusinsaService.save_product(
                    parsed=parsed,
                    crawl_job=crawl_job,
                    crawl_target=(crawl_target),
                    observed_at=(observed_at),
                )

                if saved["created"]:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as exc:
                errors.append((f"[SAVE] " f"{goods_no} " f"- {exc}"))

        return (
            created_count,
            updated_count,
        )

    # ============================================================
    # HELPER - JOB COMPLETE
    # ============================================================

    @classmethod
    def _complete_job(
        cls,
        *,
        job,
        created_count,
        updated_count,
        errors,
    ):
        job.items_created = created_count

        job.items_updated = updated_count

        job.finished_at = timezone.now()

        if created_count + updated_count > 0:
            job.status = CrawlJob.Status.SUCCESS

            if errors:
                job.error_type = "PARTIAL_ERROR"

                job.error_message = "\n".join(errors[: cls.MAX_ERROR_MESSAGES])

            else:
                job.error_type = None
                job.error_message = None

        else:
            job.status = CrawlJob.Status.FAILED

            job.error_type = "NO_PRODUCT_SAVED"

            job.error_message = (
                "\n".join(errors[: cls.MAX_ERROR_MESSAGES]) or "저장된 상품이 없습니다."
            )

        job.save()

    # ============================================================
    # HELPER - JOB FAIL
    # ============================================================

    @classmethod
    def _fail_job(
        cls,
        *,
        job,
        exc,
    ):
        job.status = CrawlJob.Status.FAILED

        job.error_type = exc.__class__.__name__

        job.error_message = str(exc)

        job.finished_at = timezone.now()

        job.save()

    # ============================================================
    # HELPER - REQUEST RATE
    # ============================================================

    @staticmethod
    def _get_request_delay(
        source,
    ) -> float:

        requests_per_minute = getattr(
            source,
            "requests_per_minute",
            None,
        )

        if not requests_per_minute:
            return 0

        if requests_per_minute <= 0:
            return 0

        return 60 / requests_per_minute

    # ============================================================
    # HELPER - YYYYMM
    # ============================================================

    @staticmethod
    def _parse_year_month(
        year_month,
    ):
        text = str(year_month).strip()

        if len(text) != 6 or not text.isdigit():
            raise ValueError("year_month는 YYYYMM 형식이어야 합니다.")

        year = int(text[:4])

        month = int(text[4:6])

        if not 1 <= month <= 12:
            raise ValueError("year_month의 월 값이 올바르지 않습니다.")

        return (
            year,
            month,
        )
