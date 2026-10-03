"""운영 AWS RDS(PostgreSQL)를 챗봇의 기존 읽기 계약으로 바꾼다."""
from __future__ import annotations

import os
import queue
import threading
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import METRIC_VERSION, RANK_WINDOW_DAYS
from .store import at_iso, platform_label


def _plain(value: Any) -> Any:
    """Postgres numeric → 파이썬 숫자.

    ★ psycopg 는 numeric 을 Decimal 로 준다 (2026-09-18). 예전 SQLite 는 float 였다.
      Decimal 은 json.dumps 가 못 읽어 리포트를 화면에 보내다 TypeError 로 죽었고,
      float 와 곱하면 그 자리에서 TypeError 가 난다. 읽는 순간 바꿔 둔다.
      정수 값은 int 로 — "82.0" 이 답변에 찍히면 verify 가 도구 결과와 대조하지 못한다.
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _term(term_key: str) -> str:
    return str(term_key or "").split(":", 1)[-1]


# ★ 연결을 몇 개 돌려 쓴다 (2026-10-02 — 기수 30명 동시 테스트에서 렉).
#   예전에는 연결 하나를 모든 요청 스레드가 같이 썼다. psycopg 연결은 한 번에 쿼리 하나만
#   돌리므로, 서른 명이 동시에 물으면 모든 RDS 조회가 한 줄로 서서 차례를 기다렸다.
#   이제 최대 POOL_SIZE 개까지 열어 두고 빌려 쓴 뒤 돌려준다. 다 빌려 갔으면 잠깐 기다린다.
POOL_SIZE = max(1, int(os.getenv("FEEDIT_RDS_POOL", "4") or 4))
POOL_WAIT = 10        # 초 — 이보다 오래 빈 연결이 없으면 하나 더 연다(상한을 넘더라도 답은 낸다)


class RDSStore:
    def __init__(self, version: str = METRIC_VERSION):
        self.version = version
        self._conn = None
        self._idle: queue.LifoQueue = queue.LifoQueue()
        self._opened = 0
        self._lock = threading.Lock()

    @staticmethod
    def _connect():
        return psycopg.connect(
            host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"), row_factory=dict_row,
            autocommit=True, connect_timeout=6,
            options="-c statement_timeout=8000",
        )

    def conn(self):
        """예전 호출용 — 연결 하나를 돌려준다(쿼리는 q() 가 빌려 쓰는 연결로 돈다)."""
        if self._conn is None or self._conn.closed:
            self._conn = self._connect()
        return self._conn

    def _borrow(self):
        while True:
            try:
                c = self._idle.get_nowait()
            except queue.Empty:
                break
            if not c.closed:
                return c
            with self._lock:
                self._opened -= 1
        with self._lock:
            room = self._opened < POOL_SIZE
            if room:
                self._opened += 1
        if room:
            try:
                return self._connect()
            except Exception:
                with self._lock:
                    self._opened -= 1
                raise
        try:
            c = self._idle.get(timeout=POOL_WAIT)
            if not c.closed:
                return c
            with self._lock:
                self._opened -= 1
        except queue.Empty:
            pass
        with self._lock:
            self._opened += 1
        return self._connect()

    def _give_back(self, c, broken: bool):
        if broken or c.closed or self._idle.qsize() >= POOL_SIZE:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self._opened -= 1
            return
        self._idle.put(c)

    def q(self, sql: str, args=()) -> list[dict[str, Any]]:
        c = self._borrow()
        broken = False
        try:
            with c.cursor() as cursor:
                cursor.execute(sql, args)
                return [{k: _plain(v) for k, v in row.items()} for row in cursor.fetchall()]
        except (psycopg.OperationalError, psycopg.InterfaceError):
            broken = True                     # 끊긴 연결은 돌려놓지 않는다 — 다음 요청이 새로 연다
            raise
        finally:
            self._give_back(c, broken)

    def one(self, sql: str, args=()) -> dict | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def scalar(self, sql: str, args=()):
        row = self.one(sql, args)
        return next(iter(row.values())) if row else None

    def latest_day(self) -> str | None:
        value = self.scalar(
            "SELECT max(metric_date) d FROM analysis.term_metric_daily "
            "WHERE metric_version=%s AND source_id IS NULL", (self.version,)
        )
        return str(value) if value else None

    def lexicon_entries(self) -> list[dict]:
        return self.q(
            """SELECT t.canonical_name canonical,lower(t.term_type) facet,
                      coalesce(array_agg(a.alias) FILTER (WHERE a.alias IS NOT NULL),
                               ARRAY[]::varchar[]) aliases
                 FROM dictionary.dictionary_term t
                 LEFT JOIN dictionary.term_alias a ON a.term_id=t.id
                WHERE t.status='ACTIVE'
                GROUP BY t.id,t.canonical_name,t.term_type
                UNION ALL
               SELECT b.name,'brand',ARRAY[]::varchar[]
                 FROM dictionary.brand b WHERE b.status='ACTIVE' AND b.name IS NOT NULL"""
        )

    def metric_canonicals(self) -> set[str]:
        return {row["canonical"] for row in self.q(
            """SELECT DISTINCT t.canonical_name canonical
                 FROM analysis.term_metric_daily m
                 JOIN dictionary.dictionary_term t ON t.id=m.term_id
                WHERE m.metric_version=%s""", (self.version,)
        )}

    def metric_facet(self, canonical: str) -> str | None:
        return self.scalar(
            """SELECT lower(t.term_type) facet FROM analysis.term_metric_daily m
                 JOIN dictionary.dictionary_term t ON t.id=m.term_id
                WHERE m.metric_version=%s AND t.canonical_name=%s LIMIT 1""",
            (self.version, canonical),
        )

    def metric_terms_in(self, text: str, limit: int = 3) -> list[dict]:
        rows = self.q(
            """SELECT DISTINCT t.canonical_name canonical,lower(t.term_type) facet
                 FROM analysis.term_metric_daily m
                 JOIN dictionary.dictionary_term t ON t.id=m.term_id
                WHERE m.metric_version=%s""", (self.version,)
        )
        hits = [row for row in rows if row["canonical"] and row["canonical"] in str(text or "")]
        return sorted(hits, key=lambda row: -len(row["canonical"]))[:limit]

    def term_latest(self, term_key: str) -> dict | None:
        return self.one(
            """SELECT m.metric_date::text observed_on,m.raw_count,m.level,m.ma7,m.ma28,m.momentum,
                      m.trend_temperature temp,m.percentile pct_rank,
                      NULL::numeric share_pct
                 FROM analysis.term_metric_daily m
                 JOIN dictionary.dictionary_term t ON t.id=m.term_id
                WHERE m.metric_version=%s AND t.canonical_name=%s AND m.source_id IS NULL
                ORDER BY m.metric_date DESC LIMIT 1""", (self.version, _term(term_key)),
        )

    def term_series(self, term_key: str, days: int = 90) -> list[dict]:
        return self.q(
            """SELECT m.metric_date::text observed_on,m.raw_count,m.level,m.ma7,m.ma28,m.momentum,
                      m.trend_temperature temp,m.percentile pct_rank
                 FROM analysis.term_metric_daily m
                 JOIN dictionary.dictionary_term t ON t.id=m.term_id
                WHERE m.metric_version=%s AND t.canonical_name=%s AND m.source_id IS NULL
                ORDER BY m.metric_date DESC LIMIT %s""",
            (self.version, _term(term_key), max(1, min(int(days), 400))),
        )

    def obs_count(self, term_key: str, window_days: int, as_of: str) -> int:
        return int(self.scalar(
            """SELECT count(*) n FROM analysis.term_metric_daily m
                 JOIN dictionary.dictionary_term t ON t.id=m.term_id
                WHERE m.metric_version=%s AND t.canonical_name=%s AND m.source_id IS NULL
                  AND m.metric_date > %s::date-%s::int""",
            (self.version, _term(term_key), as_of, int(window_days)),
        ) or 0)

    def term_sources(self, term_key: str) -> list[dict]:
        return self.q(
            """SELECT DISTINCT ON (s.id) lower(s.code) source_code,m.raw_count,
                      m.trend_temperature temp,m.percentile pct_rank,NULL::numeric share_pct,
                      m.metric_date::text observed_on
                 FROM analysis.term_metric_daily m
                 JOIN dictionary.dictionary_term t ON t.id=m.term_id
                 JOIN collection.source s ON s.id=m.source_id
                WHERE m.metric_version=%s AND t.canonical_name=%s
                ORDER BY s.id,m.metric_date DESC""", (self.version, _term(term_key)),
        )

    def term_sentiment(self, term_key: str) -> dict | None:
        row = self.one(
            """SELECT m.purchase_intent_index index_value,
                      coalesce(m.positive_count,0)+coalesce(m.negative_count,0)+coalesce(m.neutral_count,0) n_total,
                      m.positive_count pos_count,m.negative_count neg_count,
                      m.positive_rate pos_pct,m.negative_rate neg_pct
                 FROM analysis.term_metric_daily m
                 JOIN dictionary.dictionary_term t ON t.id=m.term_id
                WHERE m.metric_version=%s AND t.canonical_name=%s AND m.source_id IS NULL
                ORDER BY m.metric_date DESC LIMIT 1""", (self.version, _term(term_key)),
        )
        return row if row and int(row.get("n_total") or 0) else None

    def term_assoc(self, term_key: str, limit: int = 8) -> list[dict]:
        return self.q(
            """SELECT target.canonical_name assoc_canonical,lower(target.term_type) assoc_facet,
                      a.cooccurrence_count co_count,a.lift,a.pmi,
                      a.association_percentile score_v,a.is_new
                 FROM analysis.term_assoc_daily a
                 JOIN dictionary.dictionary_term source ON source.id=a.source_term_id
                 JOIN dictionary.dictionary_term target ON target.id=a.target_term_id
                WHERE a.metric_version=%s AND source.canonical_name=%s
                  AND a.metric_date=(SELECT max(x.metric_date) FROM analysis.term_assoc_daily x
                                      WHERE x.source_term_id=a.source_term_id AND x.metric_version=a.metric_version)
                ORDER BY a.association_rank NULLS LAST,a.association_percentile DESC NULLS LAST
                LIMIT %s""", (self.version, _term(term_key), max(1, min(int(limit), 100))),
        )

    def term_evidence(self, term_key: str, limit: int = 3) -> list[dict]:
        # 0068 dropped text_term_mention.evidence_status. Recorded mention
        # context and sentence extraction below are the current evidence path.
        from .textclean import sentence_with
        rows = self.q(
            """SELECT lower(s.code) source_code,d.document_type doc_kind,d.body,
                      tm.mention_text surface,tm.sentiment_score sentiment,
                      coalesce(d.source_published_at,ci.published_at,d.created_at) at,
                      coalesce(ci.content_url,ps.product_url) url
                 FROM analysis.text_term_mention tm
                 JOIN analysis.text_document d ON d.id=tm.document_id
                 JOIN dictionary.dictionary_term t ON t.id=tm.term_id
                 JOIN collection.source s ON s.id=d.source_id
                 LEFT JOIN content.content_item ci ON ci.id=d.content_item_id
                 LEFT JOIN commerce.product_source ps ON ps.id=d.product_source_id
                WHERE t.canonical_name=%s AND d.body IS NOT NULL
                  AND tm.mention_text IS NOT NULL
                ORDER BY tm.confidence DESC NULLS LAST,d.created_at DESC LIMIT 60""",
            (_term(term_key),),
        )
        out, seen = [], set()
        for row in rows:
            body = sentence_with(row.get("body") or "", row.get("surface") or _term(term_key))
            if len(body) < 10 or body in seen:
                continue
            seen.add(body)
            out.append({"source_code": row["source_code"], "doc_kind": row["doc_kind"],
                        "body": body, "at": at_iso(row.get("at")),
                        "sentiment": row.get("sentiment"), "origin": "mention",
                        "platform": platform_label(row["source_code"], row["doc_kind"]),
                        "url": row.get("url")})
            if len(out) >= limit:
                break
        return out

    def top_terms(self, facet: str | None = None, limit: int = 10,
                  facets: list[str] | None = None,
                  window_days: int = RANK_WINDOW_DAYS) -> list[dict]:
        """온도 상위 용어 — 최근 window_days 일 안에서 용어마다 마지막 값으로 줄을 세운다.

        ★ 2026-10-01 — 예전엔 전체 최신일 **하루**의 행만 봤다. 행은 언급이 있는 날에만
          생기므로 그날 언급되지 않은 용어는 빠졌고, 스타일 축은 0개가 되기도 했다
          ("입혀볼 수 있는 스타일" 에 "스타일 축 반환 없음"). 용어마다 metric_date 를
          함께 돌려준다 — 그 값이 언제 것인지 답이 말할 수 있어야 한다.
        """
        where, args = ["m.metric_version=%s", "m.source_id IS NULL"], [self.version]
        if facet:
            where.append("lower(t.term_type)=%s"); args.append(facet.lower())
        elif facets:
            where.append("lower(t.term_type)=ANY(%s)"); args.append([x.lower() for x in facets])
        rows = self.q(
            """SELECT canonical,facet,raw_count,temp,pct_rank,metric_date FROM (
                 SELECT DISTINCT ON (m.term_id)
                        t.canonical_name canonical,lower(t.term_type) facet,m.raw_count,
                        m.trend_temperature temp,m.percentile pct_rank,m.metric_date
                   FROM analysis.term_metric_daily m
                   JOIN dictionary.dictionary_term t ON t.id=m.term_id
                  WHERE """ + " AND ".join(where) +
            """ AND m.metric_date > (SELECT max(metric_date) FROM analysis.term_metric_daily
                                       WHERE metric_version=%s) - (%s)::int
                  ORDER BY m.term_id,m.metric_date DESC) latest
              ORDER BY temp DESC NULLS LAST,raw_count DESC LIMIT %s""",
            tuple(args + [self.version, max(1, int(window_days)), max(1, min(int(limit), 100))]),
        )
        # 날짜는 글자로 — 도구 결과는 그대로 json 으로 모델에 간다(date 는 json 이 못 읽는다).
        for row in rows:
            if row.get("metric_date") is not None:
                row["metric_date"] = str(row["metric_date"])[:10]
        return rows
