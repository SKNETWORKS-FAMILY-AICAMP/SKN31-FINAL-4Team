from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand, CommandError

from analysis.text_signals import run_text_signal_pipeline, sync_content_documents, sync_product_reviews


class Command(BaseCommand):
    help = "YouTube 댓글·커머스 리뷰 공통 텍스트 신호 파이프라인"

    def add_arguments(self, parser):
        parser.add_argument("--plan", action="store_true", help="DB·LLM을 건드리지 않고 대상 건수만 확인")
        parser.add_argument("--collect-youtube", action="store_true", help="최근 영상 댓글 수집부터 실행")
        parser.add_argument("--skip-review-sync", action="store_true", help="commerce.product_review 동기화 생략")
        parser.add_argument("--skip-content-sync", action="store_true",
                            help="content_item(영상 제목+설명) → DESCRIPTION 문서 동기화 생략")
        parser.add_argument("--include-stale", action="store_true", help="이전 분석 버전 문서까지 재분석(비용 발생)")
        parser.add_argument("--limit", type=int, default=None, help="이번 실행의 최대 LLM 분석 문서 수")
        parser.add_argument("--metric-days", type=int, default=35, help="다시 계산할 최근 지표 일수")
        parser.add_argument("--no-metrics", action="store_true", help="분석 후 일별 지표 재계산 생략")

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] <= 0:
            raise CommandError("--limit은 1 이상이어야 합니다.")
        if options["metric_days"] <= 0:
            raise CommandError("--metric-days는 1 이상이어야 합니다.")

        if options["plan"]:
            from apps.core.models import ProductReview, TextDocument
            from analysis.text_signals.metrics import METRIC_VERSION
            pending = TextDocument.objects.filter(
                document_type__in=["COMMENT", "REVIEW", "DESCRIPTION", "TRANSCRIPT", "ARTICLE"],
                analysis_status="PENDING",
            ).count()
            stale = TextDocument.objects.filter(
                document_type__in=["COMMENT", "REVIEW", "DESCRIPTION", "TRANSCRIPT", "ARTICLE"],
            ).exclude(analysis_version="feedit-text-signals-v2").count()
            result = {
                "product_reviews": ProductReview.objects.count(),
                "pending_documents": pending,
                "stale_documents": stale,
                "include_stale_requested": options["include_stale"],
                "writes": False,
                "llm_calls": False,
                "pipeline_metric_version": METRIC_VERSION,
                "configured_metric_version": os.getenv("FEEDIT_METRIC_VERSION", ""),
            }
            if result["configured_metric_version"] != METRIC_VERSION:
                result["warning"] = (
                    "FEEDIT_METRIC_VERSION을 pipeline_metric_version과 같게 설정해야 "
                    "백엔드와 챗봇이 새 지표를 읽습니다."
                )
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return

        result = {}
        if options["collect_youtube"]:
            from collection.youtube.daily import collect_daily_youtube_comments
            result["youtube"] = collect_daily_youtube_comments()
        if not options["skip_review_sync"]:
            result["reviews"] = sync_product_reviews()
        if not options["skip_content_sync"]:
            result["content"] = sync_content_documents()
        result["analysis"] = run_text_signal_pipeline(
            limit=options["limit"],
            include_stale=options["include_stale"],
            rebuild_metrics=not options["no_metrics"],
            metric_days=options["metric_days"],
        )
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
