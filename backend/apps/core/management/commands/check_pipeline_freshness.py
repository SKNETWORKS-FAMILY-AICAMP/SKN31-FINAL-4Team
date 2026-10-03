"""파이프라인이 어디까지 살아 있나 (2026-09-22)

"양"이 아니라 "마지막 시각"을 본다. 적재량은 매일 변하는 값이라 재 봐야 의미가 적고,
정작 모르는 건 **어느 단계에서 끊겼는가** 이기 때문이다.

수집 ─▶ 동기화 ─▶ 분석 ─▶ 근거검증 ─▶ 지표
 ①        ②        ③        ④          ⑤

  ① commerce.product_review        DB팀 크롤러가 넣는다 (우리 코드 아님)
  ② analysis.text_document         sync_product_reviews() 가 옮긴다
  ③ analysis_status = DONE         LLM 분석
  ④ evidence_status                근거를 원문에 고정 — 실패하면 INVALID
  ⑤ analysis.term_metric_daily     ④를 통과한 언급만 집계된다

④가 이 파이프라인에서 제일 안 보이는 단계다.
resolve_evidence() 는 **표면형이 원문에 문자 그대로 없으면 INVALID** 로 돌린다.
유튜브 댓글은 스타일 이름을 그대로 쓰지만("고프코어 진짜 예쁨"),
커머스 리뷰는 안 쓴다("핏이 넉넉해서 좋아요"). 그래서 리뷰만 조용히 탈락한다.
⑤가 비어 있을 때 ③까지는 멀쩡해 보이므로, ④를 같이 봐야 원인이 잡힌다.

그리고 ⑤의 **버전별 마지막 기록 시각**도 본다.
feedit-l2-v2 는 이 레포가 만드는 값이 아닌데 최근 날짜 행이 있다 —
다른 파이프라인이 같은 표에 쓰고 있다는 뜻이고, 그러면 재계산이 계속 덮인다.

    python manage.py check_pipeline_freshness
    python manage.py check_pipeline_freshness --days 30
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection


def _rows(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


def _fmt(v, width=19):
    return str(v)[:width] if v is not None else "-"


class Command(BaseCommand):
    help = "수집 → 동기화 → 분석 → 근거검증 → 지표 각 단계의 최신 시각을 본다"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7,
                            help="'최근 N일 증가분' 의 N (기본 7)")

    def handle(self, *args, **opts):
        n = opts["days"]

        # ── ① 수집 ────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n① 수집 — commerce.product_review (DB팀 크롤러)"))
        try:
            rows = _rows("""
                SELECT s.code,
                       count(*),
                       max(r.source_created_at),
                       max(r.created_at),
                       count(*) FILTER (WHERE r.created_at >= now() - (%s || ' days')::interval)
                  FROM commerce.product_review r
                  JOIN commerce.product_source ps ON ps.id = r.product_source_id
                  JOIN collection.source s ON s.id = ps.source_id
                 GROUP BY s.code ORDER BY 2 DESC
            """, [n])
            self.stdout.write(f"    {'소스':<10} {'총건수':>9}  {'리뷰 최신작성':<12} "
                              f"{'마지막 적재':<20} {f'최근{n}일':>8}")
            for code, total, last_src, last_ins, recent in rows:
                flag = "" if recent else "   ← 멈춤?"
                self.stdout.write(f"    {code:<10} {total:>9,}  {_fmt(last_src,10):<12} "
                                  f"{_fmt(last_ins):<20} {recent:>8,}{flag}")
            if not rows:
                self.stdout.write("    (없음)")
        except Exception as exc:                      # noqa: BLE001
            self.stdout.write(f"    조회 실패: {exc}")

        # ── ②③ 동기화 · 분석 ──────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n②③ 동기화 · 분석 — analysis.text_document"))
        rows = _rows("""
            SELECT COALESCE(s.code,'(없음)'), d.document_type, d.analysis_status,
                   count(*), max(d.source_published_at), max(d.created_at)
              FROM analysis.text_document d
              LEFT JOIN collection.source s ON s.id = d.source_id
             GROUP BY 1,2,3 ORDER BY 1,2,3
        """)
        self.stdout.write(f"    {'소스':<10} {'종류':<12} {'상태':<10} {'건수':>8}  "
                          f"{'원문최신':<12} {'적재':<20}")
        for code, dtype, status, cnt, last_pub, last_ins in rows:
            self.stdout.write(f"    {code:<10} {dtype:<12} {status:<10} {cnt:>8,}  "
                              f"{_fmt(last_pub,10):<12} {_fmt(last_ins):<20}")

        # ── ④ 근거검증 ── 여기가 핵심 ─────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n④ 근거검증 — analysis.text_term_mention (★ 리뷰가 조용히 탈락하는 자리)"))
        rows = _rows("""
            SELECT COALESCE(s.code,'(없음)'), d.document_type,
                   m.evidence_status, count(*)
              FROM analysis.text_term_mention m
              JOIN analysis.text_document d ON d.id = m.document_id
              LEFT JOIN collection.source s ON s.id = d.source_id
             GROUP BY 1,2,3 ORDER BY 1,2,3
        """)
        by_key = {}
        for code, dtype, status, cnt in rows:
            by_key.setdefault((code, dtype), {})[status] = cnt
        self.stdout.write(f"    {'소스':<10} {'종류':<12} {'EXACT':>8} {'EXPANDED':>9} "
                          f"{'INVALID':>8} {'LEGACY':>8}   통과율")
        for (code, dtype), d in sorted(by_key.items()):
            ex, xp = d.get("EXACT", 0), d.get("EXPANDED", 0)
            iv, lg = d.get("INVALID", 0), d.get("LEGACY", 0)
            total = ex + xp + iv + lg
            rate = ((ex + xp + lg) / total * 100) if total else 0
            mark = "  ← 대부분 탈락" if total and rate < 40 else ""
            self.stdout.write(f"    {code:<10} {dtype:<12} {ex:>8,} {xp:>9,} "
                              f"{iv:>8,} {lg:>8,}   {rate:5.1f}%{mark}")
        if not by_key:
            self.stdout.write("    (없음)")
        self.stdout.write(
            "\n    ※ INVALID 는 '용어가 원문에 문자 그대로 없어서' 버려진 언급입니다.\n"
            "      리뷰에서 이 비율이 높으면, 사전이 아니라 근거검증이 병목입니다.")

        # ── ⑤ 지표 · 버전 ─────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n⑤ 지표 — analysis.term_metric_daily (버전별)"))
        rows = _rows("""
            SELECT metric_version, count(*), max(metric_date),
                   max(created_at), max(updated_at)
              FROM analysis.term_metric_daily
             GROUP BY 1 ORDER BY 2 DESC
        """)
        self.stdout.write(f"    {'버전':<26} {'행수':>9}  {'지표최신일':<12} "
                          f"{'마지막 기록':<20}")
        for ver, cnt, last_date, last_cr, last_up in rows:
            newest = max([x for x in (last_cr, last_up) if x], default=None)
            self.stdout.write(f"    {ver:<26} {cnt:>9,}  {_fmt(last_date,10):<12} "
                              f"{_fmt(newest):<20}")
        self.stdout.write(
            "\n    ※ 이 레포는 feedit-unified-text-v1 만 씁니다.\n"
            "      l2-v2 의 '마지막 기록' 이 최근이면 다른 파이프라인이 같은 표에\n"
            "      쓰고 있다는 뜻입니다 — 그러면 우리가 재계산해도 계속 섞입니다.")

        # 소스별로도 한 번
        rows = _rows("""
            SELECT COALESCE(s.code,'(합산)'), t.metric_version, count(*),
                   max(t.metric_date), max(t.updated_at)
              FROM analysis.term_metric_daily t
              LEFT JOIN collection.source s ON s.id = t.source_id
             GROUP BY 1,2 ORDER BY 1,2
        """)
        self.stdout.write(f"\n    {'소스':<10} {'버전':<26} {'행수':>9}  "
                          f"{'최신일':<12} {'마지막 기록':<20}")
        for code, ver, cnt, last_date, last_up in rows:
            self.stdout.write(f"    {code:<10} {ver:<26} {cnt:>9,}  "
                              f"{_fmt(last_date,10):<12} {_fmt(last_up):<20}")

        self.stdout.write("\n" + "─" * 70)
