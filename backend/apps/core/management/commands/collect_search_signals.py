"""검색 신호 수집 → RDS (2026-09-21)

── 주기를 왜 나눴나 ───────────────────────────────────────────
네이버 데이터랩은 **하루 1,000회**다. 요청 하나에 키워드 5개 + 세그먼트 값 하나라,
543개 용어 기준 컷 하나당 ceil(543/5) = 109회가 든다.

    D1 전체 추이            109
    D2 성별 (m, f)          218
    D3 연령 11구간        1,199   ← 이것만으로 한도 초과
    D3 연령 5버킷           545
    D1+D2+D3(5버킷) 합계    872 / 1,000

돌긴 하지만 재시도 한 번이면 그날 끝난다. 그리고 검색 준비 용어가 543 → 787로
늘면 1,264회로 바로 넘친다.

그런데 진짜 이유는 쿼터가 아니다 —
**성별·연령 분포는 일간 변동값이 아니다.** "이 스타일은 20대 여성이 주도한다"는
캐릭터 규정이지 어제오늘 바뀌는 숫자가 아니다. 7일 간격으로 보면 노이즈도 덜하다.

    매일   D1 전체 추이 (109회) + 구글 트렌즈 전부
    월     D2 성별 m·f            (218회)
    화     D3 연령 10대·20대      (218회)
    수     D3 연령 30대·40대      (218회)
    목     D3 연령 50대+          (109회)
    금     (여유 — 재시도용)

하루 최대 109 + 218 = 327회. 용어가 787개로 늘어도 안 터진다.

── 여기서 하지 않는 것 ────────────────────────────────────────
네이버 검색광고(N1·N4·N6)와 구글 키워드플래너(K2)는 **절대 검색량**이라
상대지수 → 절대값 환산의 앵커가 된다. 그 환산은 processors/normalizer.py 가
CSV 단위로 하므로 기존 2단계를 그대로 쓴다:

    python collection/search_volume/main.py --source naver
    python manage.py load_search_metrics --dir collection/search_volume/output/processed/<타임스탬프>

── 쓰는 법 ────────────────────────────────────────────────────
    python manage.py collect_search_signals --mode daily
    python manage.py collect_search_signals --mode weekly              # 요일 보고 알아서 고름
    python manage.py collect_search_signals --mode weekly --cut gender
    python manage.py collect_search_signals --mode daily --dry-run     # API 안 부르고 계획만
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

SEARCH_METRIC_VERSION = "feedit-search-v1"

# 요일(월=0) → 그날 돌릴 세그먼트 컷
WEEKLY_PLAN = {
    0: ("gender", None),
    1: ("age", ["10s", "20s"]),
    2: ("age", ["30s", "40s"]),
    3: ("age", ["50s+"]),
    4: (None, None),      # 금요일은 비워 둔다 — 앞에서 실패한 컷 재시도용
    5: (None, None),
    6: (None, None),
}


class Command(BaseCommand):
    help = "검색 관심도(구글 트렌즈 · 네이버 데이터랩)를 수집해 analysis 스키마에 넣는다"

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
        parser.add_argument("--cut", choices=["gender", "age"], default=None,
                            help="weekly 에서 요일 대신 직접 지정")
        parser.add_argument("--buckets", default=None,
                            help="연령 버킷 쉼표 구분 (예: 10s,20s)")
        parser.add_argument("--limit", type=int, default=None,
                            help="용어 수 상한 (시험 실행용)")
        parser.add_argument("--dry-run", action="store_true",
                            help="API 를 부르지 않고 호출 예산만 센다")
        parser.add_argument("--skip-google", action="store_true")
        parser.add_argument("--skip-naver", action="store_true")

    # ──────────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        from apps.core.models import DictionaryTerm, Source

        dry = opts["dry_run"]
        today = date.today()

        from collection.search_volume.term_resolver import SearchTermResolver

        resolver = SearchTermResolver()
        search_terms = resolver.active_search_terms(limit=opts["limit"])
        keywords = [row.query for row in search_terms]
        by_keyword = {row.normalized_query.replace(" ", ""): row.term_id for row in search_terms}
        self.term_resolver = resolver

        self.stdout.write(f"📅 {today} · mode={opts['mode']} · 용어 {len(keywords):,}개"
                          + ("  [DRY-RUN]" if dry else ""))
        if not keywords:
            raise CommandError("ACTIVE 사전 용어가 없습니다.")

        result = {}
        if opts["mode"] == "daily":
            if not opts["skip_google"]:
                result["google"] = self._google(keywords, by_keyword, today, dry)
            if not opts["skip_naver"]:
                result["naver_all"] = self._datalab(
                    keywords, by_keyword, today, dry, segment="all")
        else:
            result["naver_segments"] = self._weekly(
                keywords, by_keyword, today, dry, opts)

        self.stdout.write("\n" + "─" * 56)
        for name, info in result.items():
            self.stdout.write(f"  {name:<16} {info}")
        self.stdout.write("─" * 56)

    # ── 구글 트렌즈 (G1 · G2 · G3 · G5) ───────────────────────

    def _google(self, keywords, by_keyword, today, dry):
        from collection.search_volume.collectors.google_trends import GoogleTrendsCollector
        from collection.search_volume.sv_config.settings import GoogleTrendsConfig

        batches = -(-len(keywords) // 5)
        region_n = min(GoogleTrendsConfig.REGION_LIMIT, len(keywords))
        plan = {"payload_builds": batches + region_n,
                "note": f"배치 {batches}회 + 지역 단건 {region_n}회"}
        if dry:
            return plan

        collector = GoogleTrendsCollector()
        data = collector.collect(keywords, timeframe="today 12-m",
                                 dictionary_terms=keywords)

        trend_rows = self._save_trend(
            data.get("interest_over_time") or [], by_keyword, "GOOGLE_SEARCH",
            segment="all", date_key="date", value_key="value")
        region_rows = self._save_region(data.get("interest_by_region") or [],
                                        by_keyword, today)
        assoc = self._save_assoc(data.get("related_queries") or {}, today)

        hits = data.get("trending_hits") or []
        if hits:
            self.stdout.write(f"  🔔 사전 용어가 전국 급상승에 진입: "
                              + ", ".join(h["term"] for h in hits[:5]))

        out = {**plan, "trend": trend_rows, "region": region_rows,
               "assoc": assoc, "trending_hits": len(hits)}
        if data.get("rate_limited"):
            # 조용히 끝내지 않는다. 0건 수집은 '없었다' 가 아니라 '못 받았다' 이다.
            out["rate_limited"] = True
            self.stderr.write(self.style.ERROR(
                "  ⛔ 구글 429 로 중간에 접었습니다 — 받은 만큼만 저장했습니다.\n"
                "     .env 의 FEEDIT_TRENDS_DELAY 를 올리거나(기본 5초) "
                "몇 시간 뒤에 다시 도세요."))
        return out

    # ── 네이버 데이터랩 (D1) ──────────────────────────────────

    def _datalab(self, keywords, by_keyword, today, dry, *, segment="all",
                 gender=None, ages=None):
        from collection.search_volume.collectors.naver_datalab import NaverDatalabCollector

        calls = -(-len(keywords) // 5)
        plan = {"calls": calls, "segment": segment}
        if dry:
            return plan

        collector = NaverDatalabCollector()
        data = collector.collect(keywords, time_unit="week",
                                 gender=gender, ages=ages, segment=segment)
        rows = self._save_datalab(data.get("data") or [], by_keyword, segment)
        return {**plan, "rows": rows, "calls_used": collector.calls_used}

    def _weekly(self, keywords, by_keyword, today, dry, opts):
        from collection.search_volume.collectors.naver_datalab import (
            AGE_BUCKETS, GENDERS, estimate_calls,
        )

        cut = opts["cut"]
        buckets = opts["buckets"].split(",") if opts["buckets"] else None
        if cut is None:
            cut, buckets = WEEKLY_PLAN.get(today.weekday(), (None, None))
        if cut is None:
            self.stdout.write("  오늘은 세그먼트 컷이 없는 요일입니다 (재시도 여유일).")
            return {"skipped": True}

        out = []
        if cut == "gender":
            need = estimate_calls(len(keywords), with_gender=True) - -(-len(keywords) // 5)
            self.stdout.write(f"  ▶ 성별 컷 — 예상 {need}회")
            for code, label in GENDERS.items():
                out.append(self._datalab(keywords, by_keyword, today, dry,
                                         segment=f"gender:{code}", gender=code))
        else:
            names = buckets or list(AGE_BUCKETS)
            need = estimate_calls(len(keywords), age_buckets=len(names)) - -(-len(keywords) // 5)
            self.stdout.write(f"  ▶ 연령 컷 {names} — 예상 {need}회")
            for name in names:
                codes = AGE_BUCKETS.get(name)
                if not codes:
                    raise CommandError(f"모르는 연령 버킷: {name} (가능: {list(AGE_BUCKETS)})")
                out.append(self._datalab(keywords, by_keyword, today, dry,
                                         segment=f"age:{name}", ages=codes))
        return out

    # ── 저장 ──────────────────────────────────────────────────

    def _source(self, code, label):
        from apps.core.models import Source
        row, _ = Source.objects.get_or_create(
            code=code,
            defaults={"name": label, "source_type": Source.SourceType.SEARCH,
                      "collection_method": Source.CollectionMethod.API,
                      "status": Source.Status.ACTIVE},
        )
        return row

    def _save_trend(self, rows, by_keyword, source_code, *, segment,
                    date_key, value_key):
        from apps.core.models import TermSearchTrend
        src = self._source(source_code, "구글 검색")
        objs, seen = [], set()
        for r in rows:
            tid = self.term_resolver.resolve(r.get("keyword"))
            if not tid:
                continue
            try:
                day = datetime.strptime(str(r.get(date_key))[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            key = (tid, day, segment)
            if key in seen:          # 변형 키워드가 같은 term 으로 붙으면 대표 하나만
                continue
            seen.add(key)
            objs.append(TermSearchTrend(
                term_id=tid, source=src, metric_date=day,
                time_unit=TermSearchTrend.TimeUnit.WEEK, segment=segment,
                ratio=r.get(value_key), metric_version=SEARCH_METRIC_VERSION,
            ))
        return self._upsert(TermSearchTrend, objs,
                            ["term", "source", "metric_date", "time_unit",
                             "segment", "metric_version"], ["ratio"])

    def _save_datalab(self, results, by_keyword, segment):
        from apps.core.models import TermSearchTrend
        src = self._source("NAVER_SEARCH", "네이버 검색")
        objs, seen = [], set()
        for group in results:
            name = str(group.get("title") or group.get("groupName") or "")
            tid = self.term_resolver.resolve(name)
            if not tid:
                continue
            for point in group.get("data") or []:
                try:
                    day = datetime.strptime(str(point.get("period"))[:10], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                key = (tid, day, segment)
                if key in seen:
                    continue
                seen.add(key)
                objs.append(TermSearchTrend(
                    term_id=tid, source=src, metric_date=day,
                    time_unit=TermSearchTrend.TimeUnit.WEEK, segment=segment,
                    ratio=point.get("ratio"), metric_version=SEARCH_METRIC_VERSION,
                ))
        return self._upsert(TermSearchTrend, objs,
                            ["term", "source", "metric_date", "time_unit",
                             "segment", "metric_version"], ["ratio"])

    def _save_region(self, rows, by_keyword, today):
        from apps.core.models import TermSearchRegion
        src = self._source("GOOGLE_SEARCH", "구글 검색")
        objs, seen = [], set()
        for r in rows:
            tid = self.term_resolver.resolve(r.get("keyword"))
            region = str(r.get("region") or "").strip()
            if not tid or not region:
                continue
            key = (tid, region)
            if key in seen:
                continue
            seen.add(key)
            objs.append(TermSearchRegion(
                term_id=tid, source=src, metric_date=today, region=region,
                value=int(r.get("value") or 0), metric_version=SEARCH_METRIC_VERSION,
            ))
        return self._upsert(TermSearchRegion, objs,
                            ["term", "source", "metric_date", "region", "metric_version"],
                            ["value"])

    def _save_assoc(self, related_queries, today):
        from analysis.search_signals.associations import rebuild_search_associations
        return rebuild_search_associations(related_queries=related_queries,
                                           metric_date=today, platform="GOOGLE")

    def _upsert(self, model, objects, unique_fields, update_fields):
        if not objects:
            return 0
        written = 0
        with transaction.atomic():
            for i in range(0, len(objects), 1000):
                chunk = objects[i:i + 1000]
                model.objects.bulk_create(chunk, update_conflicts=True,
                                          unique_fields=unique_fields,
                                          update_fields=update_fields)
                written += len(chunk)
        return written
