"""크롤러 SQLite 읽기 전용 어댑터.

★ 크롤러의 store.py 를 import 하지 않는다.
  `store._conn` · `store._lock` 은 비공개고, 쓰기 경로가 같이 딸려 온다.
  이 서비스는 **읽기만** 한다. 그래서 자기 것을 따로 갖는다.

★ 지표를 계산하지 않는다.
  온도·모멘텀·연관어는 crawler/metrics.py 가 원본이다.
  여기서 다시 계산하면 화면과 챗봇이 다른 숫자를 말한다 (AGENTS.md §6.1).
  여기서 하는 계산은 '읽은 값을 설명하기 위한 파생'뿐이다 — 예: ma7/ma28 배수.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .config import DB_PATH, METRIC_VERSION, RANK_WINDOW_DAYS


# ══════════════════════════════════════════════════════════
#  근거 한 줄을 원문으로 되돌리는 링크
# ══════════════════════════════════════════════════════════
#  ★ 왜 필요한가 (설계도 부록 12)
#    "커뮤니티 반응 82% 긍정" 은 **확인할 수 있을 때만** 주장이 된다.
#    원문으로 갈 수 없으면 인용은 장식으로 남는다.
#
#  ★ 2026-09-09 실측 — 전부는 안 된다
#    근거 831건 기준으로 링크를 만들 수 있는 것은 61% 다.
#      youtube  419건  product_uid 가 'yt:<video_id>' — 접두사만 떼면 100% 일치
#      musinsa   89건  product_uid 가 상품번호 — 상품 페이지로 간다
#      naver    323건  product_uid 가 'kw:나일론' — **검색 키워드다.**
#                      글 URL 이 아니라서 원문으로 되돌아갈 방법이 없다.
#    text_document.raw_id 는 14,240건 전부 NULL 이라 raw_document.url 에도 못 닿는다.
#    (크롤러가 글 URL 을 안 남긴 탓이고, 챗봇에서 고칠 수 있는 문제가 아니다)
#
#    그래서 **링크는 있으면 붙이고 없으면 없다고 적는다.** 링크를 필수로 걸면
#    네이버 39% 를 통째로 버리게 되는데, 언급량이 많은 축이라 그게 더 손해다.
#    "없으면 없다고 한다" 는 이 서비스의 원칙과도 같다.
#
#  ★ 여기가 교체 지점이다
#    지금은 크롤러 SQLite 를 본다. RDS 로 옮기면 analysis.text_document 에는
#    content_item FK 가 있고 content.content_item.content_url 이 URL 을 직접 준다 —
#    그때는 아래 조립을 지우고 그 칸을 그대로 쓰면 된다.
#    README 가 말한 "store.py 의 SQL 만 갈아 끼운다" 가 이 자리다.
#
#  URL 형식은 크롤러 코드에서 확인한 것이다(추측이 아니다):
#    feedit_crawler — https://www.youtube.com/watch?v={video_id}
#                     https://www.musinsa.com/products/{uid}
_PLATFORM_KO = {
    "youtube": "유튜브", "naver": "네이버", "musinsa": "무신사",
    "zigzag": "지그재그", "ably": "에이블리", "kream": "크림",
}
_KIND_KO = {
    "yt_comment": "유튜브 댓글", "yt_comment_reply": "유튜브 대댓글",
    "yt_video_context": "유튜브 영상", "yt_transcript": "유튜브 자막",
    "naver_blog": "네이버 블로그", "naver_cafearticle": "네이버 카페",
    "product_review": "무신사 리뷰",
}


def evidence_link(source_code: str, product_uid: str | None) -> str | None:
    """원문 주소. 만들 수 없으면 None — 지어내지 않는다."""
    uid = (product_uid or "").strip()
    if not uid:
        return None
    if source_code == "youtube" and uid.startswith("yt:"):
        vid = uid[3:]
        return f"https://www.youtube.com/watch?v={vid}" if vid else None
    if source_code == "musinsa" and uid.isdigit():
        return f"https://www.musinsa.com/products/{uid}"
    if source_code == "kream" and uid.isdigit():
        return f"https://kream.co.kr/products/{uid}"
    # naver 는 uid 가 'kw:<검색어>' 라 글로 되돌아갈 수 없다.
    return None


def at_iso(at) -> str | None:
    """시점 표기를 하나로 맞춘다.

    ★ 왜 필요한가 (2026-09-09 실측)
      같은 근거 목록 안에서 유튜브·무신사는 '2026-09-08', 네이버 블로그는
      '20260902' 로 나왔다. 모델은 받은 대로 적으므로 답변에 두 모양이 섞이고,
      읽는 사람은 뒤엣것을 숫자로 읽는다. 여기서 한 번만 맞춰 둔다.
      (RDS 로 바꾸면 timestamp 로 와서 이 함수는 그대로 통과만 시킨다)
    """
    t = str(at or "").strip()
    if not t:
        return None
    if len(t) == 8 and t.isdigit():
        return f"{t[:4]}-{t[4:6]}-{t[6:]}"
    return t[:10] if len(t) > 10 and t[4:5] == "-" else t


def platform_label(source_code: str, doc_kind: str | None) -> str:
    """사용자에게 보일 출처 이름. '어디서' 가 성립해야 한다."""
    platform = _PLATFORM_KO.get((source_code or "").lower()) or source_code or "출처 미상"
    if doc_kind == "COMMENT":
        return f"{platform} 댓글"
    if doc_kind == "REVIEW":
        return f"{platform} 리뷰"
    return _KIND_KO.get(doc_kind or "") or platform


class ReadOnlyStore:
    def __init__(self, path=None, version: str = METRIC_VERSION):
        self.path = str(path or DB_PATH)
        self.version = version
        self._conn: sqlite3.Connection | None = None

    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            # mode=ro — 실수로도 쓸 수 없게 한다
            self._conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True,
                                         check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def q(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn().execute(sql, args)]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        r = self.conn().execute(sql, args).fetchone()
        return dict(r) if r else None

    def scalar(self, sql: str, args: tuple = ()):
        r = self.conn().execute(sql, args).fetchone()
        return r[0] if r else None

    # ── 기준일 ────────────────────────────────────────────
    def latest_day(self) -> str | None:
        """종합 지표의 최신 관측일. 모든 답변의 '기준 시각'이 여기서 나온다."""
        return self.scalar(
            "SELECT max(observed_on) FROM metric_term_daily "
            "WHERE metric_version=? AND source_code='__all__'", (self.version,))

    # ── 지표에 실제로 적재된 canonical ────────────────────
    def metric_canonicals(self) -> set[str]:
        """접힘 되돌리기(설계서 3.3 4단)의 근거.

        사전이 '코트' 를 '아우터' 로 접는데 지표에는 '코트' 가 따로 있다.
        사용자가 쓴 말이 여기 있으면 접지 않는다.
        """
        return {r["canonical"] for r in self.q(
            "SELECT DISTINCT canonical FROM metric_term_daily WHERE metric_version=?",
            (self.version,))}

    def metric_facet(self, canonical: str) -> str | None:
        """지표 표에 있는 이름의 축. 사전에 없는 용어(브랜드)의 term_key 를 만든다."""
        return self.scalar(
            "SELECT facet FROM metric_term_daily WHERE metric_version=? AND canonical=? "
            "LIMIT 1", (self.version, canonical))

    def metric_terms_in(self, text: str, limit: int = 3) -> list[dict]:
        """질문 안에 **지표 표의 이름**이 들어 있으면 찾아 준다.

        ★ 왜 필요한가 (2026-09-09 실측)
          lexicon.yaml 은 브랜드·제품명을 **의도적으로** 담지 않는다
          ("사전에 넣으면 트렌드 지표가 특정 브랜드 홍보판이 됩니다").
          그런데 지표 표에는 brand 축 용어가 303개 있다 — 전체 588개의 절반이다.
          사전만 보고 답하면 "살로몬" 처럼 **지표에 8행이나 있는 용어**를
          "측정 자료가 없습니다" 라고 답하게 된다. 정직한 게 아니라 틀린 답이다.
          사전은 표기를 고르는 도구이지, 조회를 막는 관문이 아니다(설계 원칙 2).
        """
        q = " " + str(text or "") + " "
        rows = self.q(
            "SELECT DISTINCT canonical, facet FROM metric_term_daily WHERE metric_version=?",
            (self.version,))
        hit = [r for r in rows if r["canonical"] and r["canonical"] in q]
        # 긴 이름을 먼저 — '살로몬 XT-6' 이 '살로몬' 보다 구체적이다
        hit.sort(key=lambda r: -len(r["canonical"]))
        return hit[:limit]

    # ── term 하나의 최신 지표 ─────────────────────────────
    def term_latest(self, term_key: str) -> dict | None:
        day = self.scalar(
            "SELECT max(observed_on) FROM metric_term_daily WHERE metric_version=? "
            "AND term_key=? AND source_code='__all__'", (self.version, term_key))
        if not day:
            return None
        return self.one(
            "SELECT * FROM metric_term_daily WHERE metric_version=? AND term_key=? "
            "AND source_code='__all__' AND observed_on=?", (self.version, term_key, day))

    def term_series(self, term_key: str, days: int = 90) -> list[dict]:
        return self.q(
            "SELECT observed_on,raw_count,level,ma7,ma28,momentum,temp,pct_rank "
            "FROM metric_term_daily WHERE metric_version=? AND term_key=? "
            "AND source_code='__all__' ORDER BY observed_on DESC LIMIT ?",
            (self.version, term_key, days))

    def obs_count(self, term_key: str, window_days: int, as_of: str) -> int:
        """as_of 기준 최근 window_days 창 안의 관측일 수."""
        return self.scalar(
            "SELECT count(*) FROM metric_term_daily WHERE metric_version=? "
            "AND term_key=? AND source_code='__all__' "
            f"AND observed_on > date(?, '-{int(window_days)} day')",
            (self.version, term_key, as_of)) or 0

    def term_sources(self, term_key: str) -> list[dict]:
        """소스별 최신 스냅샷.

        수집 주기가 달라 유튜브처럼 하루 늦은 소스가 있다.
        종합 지표 날짜 하나로 맞추면 그런 소스가 화면에서 사라진다 — 각자 최신을 쓴다.
        (crawler/trend_chat.py 가 쓰는 방식과 같다)
        """
        return self.q(
            "WITH latest AS (SELECT source_code, max(observed_on) observed_on "
            " FROM metric_term_daily WHERE metric_version=? AND term_key=? "
            " AND source_code<>'__all__' GROUP BY source_code) "
            "SELECT m.source_code, m.raw_count, m.temp, m.pct_rank, m.share_pct, m.observed_on "
            "FROM metric_term_daily m JOIN latest l "
            "  ON l.source_code=m.source_code AND l.observed_on=m.observed_on "
            "WHERE m.metric_version=? AND m.term_key=? ORDER BY m.raw_count DESC",
            (self.version, term_key, self.version, term_key))

    def term_sentiment(self, term_key: str) -> dict | None:
        day = self.scalar(
            "SELECT max(observed_on) FROM metric_term_sentiment_daily "
            "WHERE metric_version=? AND term_key=?", (self.version, term_key))
        if not day:
            return None
        return self.one(
            "SELECT * FROM metric_term_sentiment_daily WHERE metric_version=? "
            "AND term_key=? AND observed_on=?", (self.version, term_key, day))

    def term_assoc(self, term_key: str, limit: int = 8) -> list[dict]:
        day = self.scalar(
            "SELECT max(observed_on) FROM metric_term_assoc_daily "
            "WHERE metric_version=? AND base_term_key=?", (self.version, term_key))
        if not day:
            return []
        return self.q(
            "SELECT assoc_canonical, assoc_facet, co_count, lift, pmi, score_v, is_new "
            "FROM metric_term_assoc_daily WHERE metric_version=? AND base_term_key=? "
            "AND observed_on=? ORDER BY score_v DESC, co_count DESC LIMIT ?",
            (self.version, term_key, day, limit))

    def term_evidence(self, term_key: str, limit: int = 3) -> list[dict]:
        """근거 스니펫.

        ★ 본문(text_document.body)을 240자로 자르던 방식을 버렸다.
          그 방식은 (1) 말 중간에서 잘리고 (2) 그 말과 상관없는 문장이 딸려오고
          (3) `&lt;아디다스&gt;` 같은 수집 찌꺼기를 그대로 화면에 올렸다.

        1순위 — text_entity_opinion.evidence.
          긍부정 분석이 '이 대목 때문에 이렇게 판정했다' 고 남긴 짧은 span 이다.
          즉 언급량·긍부정에 실제로 영향을 준 문장이고, 이미 그 term 범위로 좁혀져 있다.
          현재 137개 term / 633행에만 있다.
        2순위 — 그게 없는 term 은 본문에서 그 말이 든 문장 하나만 뽑는다.

        어느 쪽이든 textclean 을 통과시켜 엔티티·태그·링크를 씻는다.
        플랫폼별로 하나씩 돌아가며 담아 네이버가 슬롯을 독점하지 않게 한다.
        """
        import json as _json

        from .textclean import sentence_with, snippet

        rows = self.q(
            "SELECT o.evidence, o.sentiment, o.confidence, o.canonical, "
            "  d.source_code, d.doc_kind, d.product_uid, "
            "  COALESCE(d.published_at, d.collected_at) at "
            "FROM text_entity_opinion o JOIN text_document d ON d.id=o.text_document_id "
            "WHERE o.term_key=? AND COALESCE(d.quality_status,'active')='active' "
            "  AND o.evidence IS NOT NULL AND o.evidence NOT IN ('', '[]') "
            "ORDER BY o.confidence DESC, at DESC LIMIT 40", (term_key,))

        out: list[dict] = []
        seen: set[str] = set()
        for r in rows:
            try:
                spans = _json.loads(r["evidence"])
            except Exception:
                spans = [r["evidence"]]
            if not isinstance(spans, list):
                spans = [spans]
            for sp in spans:
                body = snippet(sp)
                if len(body) < 6 or body in seen:
                    continue
                seen.add(body)
                out.append({"source_code": r["source_code"], "doc_kind": r["doc_kind"],
                            "body": body, "at": at_iso(r["at"]), "sentiment": r["sentiment"],
                            "origin": "opinion",
                            "platform": platform_label(r["source_code"], r["doc_kind"]),
                            "url": evidence_link(r["source_code"], r["product_uid"])})
                break            # 문서 하나당 한 마디만 — 같은 글이 화면을 채우지 않게
        if out:
            return self._spread(out, limit)

        # 2순위 — opinion 이 없는 term.
        # ★ 그 말이 실제로 든 문장만 쓴다. 없으면 아무것도 내지 않는다.
        #   'material:다운' 이 '아름다운' 에 걸린 것 같은 사전 오탐을 근거랍시고
        #   올리면, 틀린 숫자보다 더 나쁘다.
        raw = self.q(
            "SELECT t.source_code, t.doc_kind, t.body, m.surface, t.product_uid, "
            "  COALESCE(t.published_at, t.collected_at) at "
            "FROM text_entity_mention m JOIN text_document t ON t.id=m.text_document_id "
            "WHERE m.term_key=? AND m.status='confirmed' "
            "  AND COALESCE(t.quality_status,'active')='active' "
            "GROUP BY t.id ORDER BY at DESC LIMIT 60", (term_key,))
        for r in raw:
            surface = (r["surface"] or "").strip()
            if len(surface) < 2:
                continue
            body = sentence_with(r["body"], surface)
            if len(body) < 10 or surface not in body or body in seen:
                continue
            seen.add(body)
            out.append({"source_code": r["source_code"], "doc_kind": r["doc_kind"],
                        "body": body, "at": at_iso(r["at"]), "sentiment": None,
                        "origin": "body",
                        "platform": platform_label(r["source_code"], r["doc_kind"]),
                        "url": evidence_link(r["source_code"], r["product_uid"])})
        return self._spread(out, limit)

    @staticmethod
    def _spread(rows: list[dict], limit: int) -> list[dict]:
        """플랫폼을 번갈아 담는다. 수집량이 많은 곳이 근거를 독점하면 편향으로 읽힌다."""
        buckets: dict[str, list[dict]] = {}
        for r in rows:
            buckets.setdefault(r["source_code"], []).append(r)
        out: list[dict] = []
        while len(out) < limit and any(buckets.values()):
            for k in list(buckets):
                if buckets[k]:
                    out.append(buckets[k].pop(0))
                    if len(out) >= limit:
                        break
        return out

    def top_terms(self, facet: str | None = None, limit: int = 10,
                  facets: list[str] | None = None,
                  window_days: int = RANK_WINDOW_DAYS) -> list[dict]:
        """온도 상위 용어. `facet` 은 한 축, `facets` 는 여러 축으로 좁힌다.

        ★ 2026-10-01 — 최근 window_days 일 안에서 용어마다 마지막 값으로 줄을 세운다
          (RDSStore.top_terms 와 같은 규칙, config.RANK_WINDOW_DAYS).

        ★ facets 를 추가한 이유 (2026-09-09)
          '요즘 뭐가 핫해' 가 축 제한 없이 돌면 브랜드(아디다스·키르시)와
          색(블랙)이 순위에 섞여 나온다. lexicon.yaml 은 브랜드를 **일부러**
          뺐다 — "사전에 넣으면 트렌드 지표가 특정 브랜드 홍보판이 됩니다".
          사전 정책과 지표 정책이 어긋나 있던 자리다.
        """
        day = self.latest_day()
        if not day:
            return []
        where = ["metric_version=?", "source_code='__all__'",
                 "observed_on > date(?, ?)"]
        args: list = [self.version, day, f"-{max(1, int(window_days))} days"]
        if facet:
            where.append("facet=?")
            args.append(facet)
        elif facets:
            where.append("facet IN (%s)" % ",".join("?" * len(facets)))
            args.extend(facets)
        cond = " AND ".join(where)
        return self.q(
            "SELECT m.canonical,m.facet,m.raw_count,m.temp,m.pct_rank,"
            "       m.observed_on AS metric_date FROM metric_term_daily m "
            "JOIN (SELECT canonical, max(observed_on) d FROM metric_term_daily "
            "       WHERE " + cond + " GROUP BY canonical) x "
            "  ON x.canonical=m.canonical AND x.d=m.observed_on "
            "WHERE m.metric_version=? AND m.source_code='__all__' "
            "ORDER BY m.temp DESC, m.raw_count DESC LIMIT ?",
            tuple(args + [self.version, limit]))


def default_store():
    """운영 기본값은 RDS. SQLite는 명시한 로컬 회귀 테스트에서만 쓴다."""
    from .config import DATA_BACKEND
    if DATA_BACKEND == "sqlite":
        return ReadOnlyStore()
    from .rds_store import RDSStore
    return RDSStore()
