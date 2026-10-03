"""RDS 안의 YouTube 댓글·설명란으로 용어별 일별 언급 이력을 다시 만든다.

SQLite 는 쓰지 않는다. 원천은 전부 RDS 다.
  analysis.text_term_mention  ×  analysis.text_document  ×  content.content_item

날짜 기준 — '글이 쓰인 날' (KST)
  COMMENT     : text_document.analysis_metadata.published_at (댓글 작성 시각)
  DESCRIPTION : content_item.published_at (영상 게시 시각)

★ 기본은 DB 에 쓰지 않는다 (CSV + 적재 예정 요약만). --write 를 줄 때만 쓴다.
  쓰는 곳: analysis.term_metric_daily, source=YOUTUBE, metric_version=feedit-yt-history-v1
  같은 (source, version) 행만 지우고 다시 넣는다 — 몇 번 돌려도 같다. 다른 버전은 건드리지 않는다.

★ 지표 공식은 feedit-crawler/feedit_crawler/metrics.py (feedit-l2) 를 그대로 옮겼다.
  raw       = 그날 그 용어가 나온 문서 수 (문서당 1)
  percentile= 그날 언급된 용어들 사이에서 log(1+raw) 의 백분위 (0~100, 동률 평균)
  level     = percentile  ← 크롤러의 '플랫폼별 행'과 같다 (합산 행의 0.25 가중은 쓰지 않는다)
  ma7/ma28  = level 이동평균, 언급 없는 날은 0
  momentum  = 100 / (1 + exp(-6 (ma7/ma28 - 1)))
  temp      = round(0.6 level + 0.4 momentum)
  크롤러처럼 언급이 있는 날만 행을 만든다.

★ 끝 날짜는 자동으로 자른다 (--until 을 주지 않으면).
  수집이 멈춘 뒤 며칠은 문서가 몇 건뿐이라(9/7 308건 → 9/9 7건) 모든 용어가 급락으로 보인다.
  '그날 문서 수 ≥ 직전 28일 중앙값의 30%' 를 만족하는 마지막 날까지만 쓴다.

★ 점유율(share)을 같이 낸다.
  2025-09 → 2026-08 사이 하루 전체 언급량이 약 6배 늘었다(수집 표본 증가).
  원 건수로 이동평균을 내면 모든 용어가 '상승'으로 나온다
  (DEVELOPLOG 2026-09-02: momentum 90.9% 가 99 이상으로 포화된 것과 같은 원인).
  share = 그 용어 언급 / 그날 전체 언급.

    python manage.py rebuild_term_history                       # 전체 → outputs/term_history_daily.csv
    python manage.py rebuild_term_history --terms 클래식 아메카지   # 일부 용어만
    python manage.py rebuild_term_history --since 2025-09-01 --out ../outputs/x.csv
    python manage.py rebuild_term_history --write                 # 실제 적재
"""
import csv
import math
import statistics
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

TZ = "Asia/Seoul"
VERSION = "feedit-yt-history-v1"
CUTOFF_RATIO = 0.3
TS_RE = r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"

# 언급 하나를 (용어, 날짜, 문서, 콘텐츠, 작성자) 한 줄로 편다.
EVENTS = f"""
    SELECT x.term_id,
           x.document_id,
           d.content_item_id,
           CASE WHEN d.document_type = 'COMMENT'
                THEN coalesce(d.analysis_metadata->>'author_channel_id',
                              d.analysis_metadata->>'author')
                ELSE 'profile:' || c.profile_id::text END AS creator,
           (CASE WHEN d.analysis_metadata->>'published_at' ~ '{TS_RE}'
                 THEN (d.analysis_metadata->>'published_at')::timestamptz
                 ELSE c.published_at END AT TIME ZONE '{TZ}')::date AS dt
    FROM analysis.text_term_mention x
    JOIN analysis.text_document d ON d.id = x.document_id
    JOIN collection.source s ON s.id = d.source_id AND upper(s.code) = 'YOUTUBE'
    LEFT JOIN content.content_item c ON c.id = d.content_item_id
"""

DAILY = f"""
    WITH ev AS ({EVENTS}),
    ev2 AS (SELECT * FROM ev WHERE dt BETWEEN %(since)s AND %(until)s),
    tot AS (
      SELECT dt, count(*) AS all_mentions, count(DISTINCT document_id) AS all_documents
      FROM ev2 GROUP BY dt
    )
    SELECT e.dt, e.term_id, t.canonical_name, t.term_type,
           count(*)                        AS mention_count,
           count(DISTINCT e.document_id)   AS document_count,
           count(DISTINCT e.content_item_id) AS content_count,
           count(DISTINCT e.creator)       AS creator_count,
           tot.all_mentions, tot.all_documents
    FROM ev2 e
    JOIN tot ON tot.dt = e.dt
    JOIN dictionary.dictionary_term t ON t.id = e.term_id
    WHERE (%(terms)s::text[] IS NULL OR t.canonical_name = ANY(%(terms)s::text[]))
    GROUP BY e.dt, e.term_id, t.canonical_name, t.term_type, tot.all_mentions, tot.all_documents
    ORDER BY t.canonical_name, e.dt
"""

TOTALS = f"""
    WITH ev AS ({EVENTS})
    SELECT dt, count(*) AS all_mentions, count(DISTINCT document_id) AS all_documents
    FROM ev WHERE dt BETWEEN %(since)s AND %(until)s GROUP BY dt ORDER BY dt
"""


def percentile_ranks(values):
    """metrics.py 와 같다 — 0..100, 동률은 평균 순위, 하나뿐이면 100."""
    if not values:
        return {}
    ordered = sorted((float(v), k) for k, v in values.items())
    if len(ordered) == 1:
        return {ordered[0][1]: 100.0}
    out, i = {}, 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        rank = 100.0 * ((i + j - 1) / 2) / (len(ordered) - 1)
        for _, k in ordered[i:j]:
            out[k] = rank
        i = j
    return out


def momentum(ma7, ma28):
    if ma28 <= 0:
        return 50.0 if ma7 <= 0 else 100.0
    return 100.0 / (1.0 + math.exp(-6.0 * (ma7 / ma28 - 1.0)))


def auto_cutoff(totals):
    """문서 수가 직전 28일 중앙값의 30% 이상인 마지막 날."""
    days = [(d, docs) for d, _m, docs in totals]
    last_ok = None
    for i, (d, docs) in enumerate(days):
        prev = [x for _, x in days[max(0, i - 28):i]]
        if len(prev) < 7 or docs >= CUTOFF_RATIO * statistics.median(prev):
            last_ok = d
    return last_ok


def build_metrics(rows, cols, until):
    """CSV 행 → 적재할 지표 행. 언급 있는 날만."""
    c = {name: i for i, name in enumerate(cols)}
    by_day = {}
    for r in rows:
        if r[c["dt"]] > until:
            continue
        by_day.setdefault(r[c["dt"]], []).append(r)
    level = {}
    for d, rs in by_day.items():
        ranks = percentile_ranks({r[c["term_id"]]: math.log1p(r[c["document_count"]]) for r in rs})
        for tid, v in ranks.items():
            level[(d, tid)] = v
    out = []
    for d in sorted(by_day):
        for r in by_day[d]:
            tid = r[c["term_id"]]
            hist = [level.get((d - timedelta(days=n), tid), 0.0) for n in range(27, -1, -1)]
            ma7, ma28 = sum(hist[-7:]) / 7, sum(hist) / 28
            mom = momentum(ma7, ma28)
            lv = level[(d, tid)]
            docs = r[c["document_count"]]
            out.append({
                "term_id": tid, "metric_date": d,
                "raw_count": docs, "mention_count": r[c["mention_count"]],
                "document_count": docs, "content_count": r[c["content_count"]],
                "creator_count": r[c["creator_count"]],
                "log_count": round(math.log1p(docs), 6), "percentile": round(lv, 3),
                "level": round(lv, 2), "ma7": round(ma7, 4), "ma28": round(ma28, 4),
                "momentum": round(mom, 4),
                "trend_temperature": max(0, min(100, round(0.6 * lv + 0.4 * mom))),
                "metrics": {
                    "basis": "youtube comment(published_at) + description(content published_at)",
                    "share_pct": round(r[c["mention_count"]] / r[c["all_mentions"]] * 100, 4)
                    if r[c["all_mentions"]] else None,
                    "day_documents": r[c["all_documents"]],
                    "day_mentions": r[c["all_mentions"]],
                    "formula": "feedit-crawler metrics.py (feedit-l2), level=source percentile",
                },
            })
    return out


class Command(BaseCommand):
    help = "YouTube 댓글·설명란으로 용어별 일별 언급 이력 집계 (DB 쓰기 없음, CSV 출력)"

    def add_arguments(self, parser):
        parser.add_argument("--since", default="2025-09-01")
        parser.add_argument("--until", default=None, help="기본값: 수집이 온전한 마지막 날(자동)")
        parser.add_argument("--write", action="store_true", help="term_metric_daily 에 실제로 적재")
        parser.add_argument("--terms", nargs="*", default=None)
        parser.add_argument("--out", default=None)

    def handle(self, *args, **opts):
        since = date.fromisoformat(opts["since"])
        until_arg = date.fromisoformat(opts["until"]) if opts["until"] else None
        until = until_arg or date.today() - timedelta(days=1)
        if since > until:
            raise CommandError("--since 가 --until 보다 늦습니다.")
        out_dir = Path(settings.BASE_DIR).parent / "outputs"
        out = Path(opts["out"]) if opts["out"] else out_dir / "term_history_daily.csv"
        out_tot = out.with_name(out.stem + "_totals.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        params = {"since": since, "until": until, "terms": opts["terms"] or None}

        with connection.cursor() as cur:
            cur.execute("BEGIN READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '300s'")
            try:
                cur.execute(TOTALS, params)
                totals = cur.fetchall()
                cur.execute(DAILY, params)
                cols = [c[0] for c in cur.description]
                rows = cur.fetchall()
            finally:
                cur.execute("ROLLBACK")

        with out_tot.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["date", "all_mentions", "all_documents"])
            w.writerows(totals)

        i_m, i_all = cols.index("mention_count"), cols.index("all_mentions")
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols + ["share_pct"])
            for r in rows:
                share = round(r[i_m] / r[i_all] * 100, 4) if r[i_all] else None
                w.writerow(list(r) + [share])

        days_with_data = len(totals)
        span = (until - since).days + 1
        terms = len({r[1] for r in rows})
        self.stdout.write(
            f"기간 {since} ~ {until} ({span}일 중 데이터 있는 날 {days_with_data}일)\n"
            f"용어 {terms}개 · 행 {len(rows)}개\n"
            f"→ {out}\n→ {out_tot}"
        )

        # ── 지표 계산 ─────────────────────────────────────────
        cutoff = until_arg or auto_cutoff(totals)
        if cutoff is None:
            raise CommandError("자를 날짜를 정하지 못했습니다 (데이터가 너무 적음).")
        metric_rows = build_metrics(rows, cols, cutoff)
        n_terms = len({m["term_id"] for m in metric_rows})
        by_term = {}
        for m in metric_rows:
            by_term[m["term_id"]] = by_term.get(m["term_id"], 0) + 1
        ge28 = sum(1 for v in by_term.values() if v >= 28)
        self.stdout.write(
            f"\n지표 기준 마지막 날: {cutoff}" + ("" if until_arg else " (자동)") + "\n"
            f"적재 예정: {len(metric_rows)}행 · 용어 {n_terms}개 · 28일 이상 이력 {ge28}개\n"
            f"대상: analysis.term_metric_daily  source=YOUTUBE  metric_version={VERSION}"
        )
        if opts["terms"]:
            if opts["write"]:
                raise CommandError("--terms 와 --write 는 같이 쓸 수 없습니다 (백분위가 전체 용어 기준이라서).")
        if not opts["write"]:
            self.stdout.write("DRY-RUN — DB 에 쓰지 않았습니다. 적재하려면 --write")
            return

        from apps.core.models import Source, TermMetricDaily
        source = Source.objects.filter(code__iexact="YOUTUBE").first()
        if source is None:
            raise CommandError("collection.source 에 YOUTUBE 가 없습니다.")
        objs = [TermMetricDaily(source=source, metric_version=VERSION, **m) for m in metric_rows]
        with transaction.atomic():
            deleted, _ = TermMetricDaily.objects.filter(source=source, metric_version=VERSION).delete()
            TermMetricDaily.objects.bulk_create(objs, batch_size=2000)
        self.stdout.write(f"적재 완료 — 지운 행 {deleted} · 넣은 행 {len(objs)}")
