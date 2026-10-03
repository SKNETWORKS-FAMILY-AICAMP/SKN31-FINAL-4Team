"""일별 지표만 다시 계산한다 (LLM 없이) — 2026-09-21

── 왜 필요한가 ────────────────────────────────────────────────
2026-09-21 확인: 플랫폼별 온도에 뜬 커머스 행이 전부 **feedit-l2-v2** 였다.
그 버전 행은 mention_count 가 0 인데 trend_temperature 만 82 로 차 있다.
언급이 0 인데 온도가 82 면 화면이 거짓말을 한다 — 유튜브의 86.8(댓글 24건 기반)과
나란히 세우면 "무신사가 유튜브보다 약간 낮다"는 틀린 해석을 부른다.

l2-v2 는 이 레포가 만드는 값이 아니다(코드 어디에도 그 문자열을 쓰지 않는다).
지금 파이프라인의 버전은 feedit-unified-text-v1 이고, 그쪽은 언급·감성·의도를
전부 채운다. 그래서 커머스 구간을 unified-text-v1 로 다시 계산해 덮는다.

── 안전한가 ───────────────────────────────────────────────────
rebuild_text_metrics 는 지울 때 metric_version 을 함께 걸고 지운다:

    TermMetricDaily.objects.filter(
        metric_version=metric_version, metric_date__range=(since, until)
    ).delete()

즉 **unified-text-v1 행만** 지우고 다시 쓴다. l2-v2 · yt-history 는 안 건드린다.
LLM 은 부르지 않는다 — 이미 분석이 끝난 text_term_mention 을 집계할 뿐이다.

── 쓰는 법 ────────────────────────────────────────────────────
    python manage.py rebuild_term_metrics --plan --days 365     # 세어만 본다
    python manage.py rebuild_term_metrics --days 365
    python manage.py rebuild_term_metrics --since 2025-09-01 --until 2026-09-22

기본 파이프라인(core.refresh_text_signals_daily)은 35일치만 다시 계산한다.
커머스 리뷰는 '리뷰가 쓰인 날'로 지표가 쌓여 과거로 흩어지므로,
처음 한 번은 넉넉한 기간(365일)으로 돌려야 과거 구간이 채워진다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, Max, Min

from analysis.text_signals.metrics import METRIC_VERSION, rebuild_text_metrics
from apps.core.models import TermMetricDaily, TextDocument


class Command(BaseCommand):
    help = "검증된 텍스트 언급을 일별 지표로 다시 계산한다 (LLM 호출 없음)"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=365,
                            help="오늘부터 거슬러 며칠 (기본 365)")
        parser.add_argument("--since", default=None, help="YYYY-MM-DD")
        parser.add_argument("--until", default=None, help="YYYY-MM-DD")
        parser.add_argument("--metric-version", default=METRIC_VERSION)
        parser.add_argument("--plan", action="store_true",
                            help="쓰지 않고 대상 건수만 센다")

    def handle(self, *args, **opts):
        version = opts["metric_version"]
        until = self._date(opts["until"]) or date.today()
        since = self._date(opts["since"]) or (until - timedelta(days=opts["days"]))
        if since > until:
            raise CommandError("--since 가 --until 보다 뒤입니다.")

        self.stdout.write(f"📅 {since} ~ {until} · 버전 {version}"
                          + ("  [PLAN — 쓰지 않습니다]" if opts["plan"] else ""))

        self.stdout.write("\n── 지금 상태 ──")
        before = self._snapshot(version)

        # 이 구간에 분석이 끝난 문서가 실제로 몇 건인지 (없으면 돌려도 안 채워진다)
        docs = (TextDocument.objects
                .filter(analysis_status="DONE", source_published_at__isnull=False,
                        source_published_at__date__range=(since, until))
                .values("document_type").annotate(n=Count("id")).order_by("-n"))
        self.stdout.write("\n── 이 구간의 분석 완료 문서 ──")
        for row in docs:
            self.stdout.write(f"    {row['document_type']:<12} {row['n']:>7,}")
        if not docs:
            self.stdout.write("    없음 — 재계산해도 채워지지 않습니다.")
            self.stdout.write("    먼저 run_text_signal_pipeline 로 분석을 돌려야 합니다.")

        # ★ 2026-09-22 — 문서가 DONE 이어도 '사전 용어 언급' 이 없으면 지표는 0 행이다.
        #   rebuild_text_metrics 는 text_term_mention 을 집계하지 text_document 를 세지 않는다.
        #   커머스 리뷰가 1,478건 DONE 인데 지표가 안 생긴다면 여기서 답이 나온다:
        #   리뷰는 짧고("사이즈 딱 맞아요") 사전 용어를 거의 안 쓴다.
        self.stdout.write("\n── 소스별: 분석된 문서 vs 실제로 잡힌 언급 ──")
        with connection.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(s.code, '(없음)') AS code,
                       d.document_type,
                       count(DISTINCT d.id)  AS docs,
                       count(m.id)           AS mentions,
                       count(DISTINCT CASE WHEN m.id IS NOT NULL THEN d.id END) AS docs_with
                  FROM analysis.text_document d
                  LEFT JOIN analysis.text_term_mention m
                         ON m.document_id = d.id
                        AND m.evidence_status IN ('EXACT','EXPANDED','LEGACY')
                  LEFT JOIN collection.source s ON s.id = d.source_id
                 WHERE d.analysis_status = 'DONE'
                   AND d.source_published_at IS NOT NULL
                   AND (d.source_published_at AT TIME ZONE 'Asia/Seoul')::date
                       BETWEEN %s AND %s
                 GROUP BY 1, 2
                 ORDER BY 4 DESC, 1, 2
            """, [since, until])
            rows = cur.fetchall()
        self.stdout.write(f"    {'소스':<12} {'종류':<12} {'문서':>7} {'언급':>8} {'언급있는문서':>12}  적중률")
        for code, dtype, docs, mentions, docs_with in rows:
            rate = (docs_with / docs * 100) if docs else 0
            self.stdout.write(
                f"    {code:<12} {dtype:<12} {docs:>7,} {mentions:>8,} {docs_with:>12,}  {rate:5.1f}%")
        self.stdout.write(
            "\n    ※ '언급' 이 0 이면 지표도 0 행입니다 — 재계산 창을 넓혀도 안 채워집니다.")

        if opts["plan"]:
            self.stdout.write("\n[PLAN] 아무것도 쓰지 않았습니다.")
            return

        self.stdout.write("\n⏳ 재계산 중… (문서 수에 따라 몇 분 걸립니다)")
        result = rebuild_text_metrics(since=since, until=until, metric_version=version)
        self.stdout.write(f"   ✓ 용어 지표 {result['term_metrics']:,}행")
        self.stdout.write(f"   ✓ 연관어 {result['term_associations']:,}행")
        self.stdout.write(f"   ✓ 플랫폼 지표 {result['platform_metrics']:,}행")

        self.stdout.write("\n── 바뀐 뒤 ──")
        after = self._snapshot(version)

        self.stdout.write("\n── 소스별 증감 ──")
        for code in sorted(set(before) | set(after)):
            b, a = before.get(code, (0, None)), after.get(code, (0, None))
            delta = a[0] - b[0]
            mark = "＋" if delta > 0 else ("－" if delta < 0 else "  ")
            self.stdout.write(
                f"    {code:<12} {b[0]:>7,} → {a[0]:>7,}  {mark}{abs(delta):,}"
                f"   최신 {a[1] or '-'}")
        self.stdout.write(
            "\n  ※ 커머스(musinsa·zigzag·ABLY·kream)가 0 에서 늘었다면 성공입니다.")
        self.stdout.write(
            "    늘지 않았다면 그 플랫폼 리뷰가 아직 분석(analysis_status=DONE)되지 "
            "않은 것입니다 — 위 '분석 완료 문서' 에 REVIEW 가 있는지 보세요.")

    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(f"날짜 형식이 아닙니다: {value} (YYYY-MM-DD)")

    def _snapshot(self, version):
        rows = (TermMetricDaily.objects.filter(metric_version=version,
                                               source__isnull=False)
                .values("source__code")
                .annotate(n=Count("id"), last=Max("metric_date"))
                .order_by("-n"))
        out = {}
        for r in rows:
            code = r["source__code"] or "?"
            out[code] = (r["n"], r["last"])
            self.stdout.write(f"    {code:<12} {r['n']:>7,}행  최신 {r['last']}")
        allrows = TermMetricDaily.objects.filter(metric_version=version,
                                                 source__isnull=True).count()
        self.stdout.write(f"    {'(합산)':<12} {allrows:>7,}행")
        return out
