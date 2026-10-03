from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Source, TermSearchMetricMonthly
from collection.search_volume.collectors.google_keyword import GoogleKeywordCollector
from collection.search_volume.collectors.naver_searchad import NaverSearchAdCollector
from collection.search_volume.term_resolver import SearchTermResolver


METRIC_VERSION = "feedit-search-v1"


class Command(BaseCommand):
    help = "FEEDIT DictionaryTerm 기준 월간 절대 검색량을 수집해 DB에 적재한다"

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=["all", "naver", "google"], default="all")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        resolver = SearchTermResolver()
        terms = resolver.active_search_terms(limit=opts["limit"])
        keywords = [row.query for row in terms]
        month = date.today().replace(day=1)

        self.stdout.write(
            f"search-volume terms={len(keywords)} source={opts['source']} dry_run={opts['dry_run']}"
        )
        if opts["dry_run"]:
            return

        written = {"naver": 0, "google": 0}
        if opts["source"] in {"all", "naver"}:
            written["naver"] = self._naver(keywords, resolver, month)
        if opts["source"] in {"all", "google"}:
            written["google"] = self._google(keywords, resolver, month)

        self.stdout.write(str(written))

    def _source(self, code: str, name: str):
        row, _ = Source.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "source_type": Source.SourceType.SEARCH,
                "collection_method": Source.CollectionMethod.API,
                "status": Source.Status.ACTIVE,
            },
        )
        return row

    def _naver(self, keywords, resolver, month):
        result = NaverSearchAdCollector().collect(keywords)
        src = self._source("NAVER_SEARCH", "네이버 검색")
        rows = []
        for item in result.get("data") or []:
            term_id = resolver.resolve(item.get("relKeyword"))
            if not term_id:
                continue
            pc = self._count(item.get("monthlyPcQcCnt"))
            mobile = self._count(item.get("monthlyMobileQcCnt"))
            rows.append(TermSearchMetricMonthly(
                term_id=term_id,
                source=src,
                metric_month=month,
                search_volume=pc + mobile,
                pc_volume=pc,
                mobile_volume=mobile,
                competition=item.get("compIdx") or None,
                data_type="monthly_absolute",
                metric_version=METRIC_VERSION,
            ))
        return self._upsert(rows)

    def _google(self, keywords, resolver, month):
        collector = GoogleKeywordCollector()
        if not collector.config.is_configured():
            self.stderr.write("Google Keyword API is not configured")
            return 0
        result = collector.collect(keywords)
        src = self._source("GOOGLE_SEARCH", "구글 검색")
        rows = []
        for item in result.get("data") or []:
            term_id = resolver.resolve(item.get("keyword"))
            if not term_id:
                continue
            volume = int(item.get("avg_monthly_searches") or item.get("total_search_volume") or 0)
            rows.append(TermSearchMetricMonthly(
                term_id=term_id,
                source=src,
                metric_month=month,
                search_volume=volume,
                data_type="monthly_absolute",
                metric_version=METRIC_VERSION,
            ))
        return self._upsert(rows)

    @staticmethod
    def _count(value) -> int:
        if isinstance(value, str):
            return 5 if "< 10" in value else int(value or 0)
        return int(value or 0)

    def _upsert(self, rows):
        if not rows:
            return 0
        # 같은 API 응답에서 같은 term이 여러 번 나오면 마지막 하나만 유지한다.
        dedup = {}
        for row in rows:
            dedup[(row.term_id, row.source_id, row.metric_month, row.metric_version)] = row
        objects = list(dedup.values())
        with transaction.atomic():
            TermSearchMetricMonthly.objects.bulk_create(
                objects,
                update_conflicts=True,
                unique_fields=["term", "source", "metric_month", "metric_version"],
                update_fields=[
                    "search_volume", "pc_volume", "mobile_volume",
                    "competition", "data_type",
                ],
            )
        return len(objects)
