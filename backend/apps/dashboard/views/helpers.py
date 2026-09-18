# backend/apps/dashboard/views/helpers.py
import logging
import traceback
from datetime import datetime, timezone as dt_timezone

import boto3
from django.db import connection
from django.conf import settings
from django.utils import timezone
from django.db.models import Count
from django.db.models import Q
from apps.core.models import (
    ProductSource,
    ContentSnapshot,
    ProductSourceSnapshot,BrandSource,
    Source,Brand,Category,CategorySource, 
)

ROBOTS_S3_PREFIX = "config/robots/"

def s3_client():
    return boto3.client(
        "s3",
        region_name=getattr(
            settings,
            "AWS_REGION",
            None,
        ),
    )


def s3_bucket():
    return getattr(
        settings,
        "AWS_STORAGE_BUCKET_NAME",
        None,
    )


# 기존 코드 호환
_s3_client = s3_client
_s3_bucket = s3_bucket


class ConsoleLogHandler(logging.Handler):
    """
    Dashboard에서 실행 중 발생한 로그를
    화면 출력용으로 수집한다.
    """

    MAX_RECORDS = 400

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        if len(self.records) >= self.MAX_RECORDS:
            return

        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            message = str(record.msg)

        if record.exc_info:
            message += "\n" + "".join(
                traceback.format_exception(
                    *record.exc_info
                )
            ).rstrip()

        self.records.append(
            {
                "time": timezone.localtime(
                    datetime.fromtimestamp(
                        record.created,
                        tz=dt_timezone.utc,
                    )
                ).strftime("%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
        )


# 기존 코드 호환
_ConsoleLogHandler = ConsoleLogHandler

# ============================================================
# CONSOLE LINE
# ============================================================

def console_line(
    level,
    message,
):
    return {
        "time": (
            timezone.localtime()
            .strftime("%H:%M:%S")
        ),
        "level": level,
        "logger": "dashboard",
        "message": message,
    }


_console_line = console_line


# ============================================================
# CELERY WORKERS
# ============================================================

def inspect_workers(
    timeout=0.6,
):
    """
    Celery worker 상태 확인.
    """

    from config.celery import (
        app as celery_app,
    )

    inspector = (
        celery_app.control.inspect(
            timeout=timeout
        )
    )

    stats = (
        inspector.stats()
        or {}
    )

    active = (
        inspector.active()
        or {}
    ) if stats else {}

    return (
        celery_app,
        stats,
        active,
    )


_inspect_workers = inspect_workers


# ============================================================
# MASK
# ============================================================

def mask(
    value,
    keep=4,
):
    """
    관리자 화면에서 민감값 간단 마스킹.
    """

    text = str(
        value or ""
    )

    if not text:
        return ""

    if len(text) <= keep:
        return "*" * len(text)

    return (
        text[:keep]
        + "*"
        * min(
            len(text) - keep,
            12,
        )
    )


_mask = mask

# ============================================================
# SOURCE
# ============================================================




# ============================================================
# PRODUCT SOURCE SNAPSHOT
# ============================================================


def attach_latest_product_snapshot(
    product_sources,
):
    """
    ProductSource 목록 각각에
    최신 ProductSourceSnapshot을 붙인다.

    결과:
        row.latest_snapshot
    """

    for product_source in product_sources:

        product_source.latest_snapshot = (
            product_source.snapshots
            .order_by(
                "-observed_at"
            )
            .first()
        )

    return product_sources

# ============================================================
# QUERYSTRING
# ============================================================



# ============================================================
# SNAPSHOT CHANGE
# ============================================================

def build_snapshot_changes(current, previous):
    """
    현재 ProductSourceSnapshot과 동일 ranking_scope의
    직전 ProductSourceSnapshot을 비교한다.

    rank_position은 숫자가 작아질수록 순위 상승이므로
    다른 지표와 반대로 previous - current 로 계산한다.
    """

    fields = (
        "list_price",
        "sale_price",
        "discount_rate",
        "rating",
        "review_count",
        "like_count",
        "view_count",
        "sales_count",
    )

    changes = {}

    for field in fields:
        current_value = getattr(current, field, None)
        previous_value = (
            getattr(previous, field, None)
            if previous is not None
            else None
        )

        delta = None
        if current_value is not None and previous_value is not None:
            delta = current_value - previous_value

        changes[field] = {
            "current": current_value,
            "previous": previous_value,
            "delta": delta,
        }

    current_rank = getattr(current, "rank_position", None)
    previous_rank = (
        getattr(previous, "rank_position", None)
        if previous is not None
        else None
    )

    rank_delta = None
    if current_rank is not None and previous_rank is not None:
        rank_delta = previous_rank - current_rank

    changes["rank_position"] = {
        "current": current_rank,
        "previous": previous_rank,
        "delta": rank_delta,
    }

    return changes


SOURCE_LABELS = {
    "musinsa": "무신사",
    "musinsa_used": "무신사 중고",
    "zigzag": "지그재그",
    "ably": "에이블리",
    "kream": "크림",
    "naver": "네이버",
    "youtube": "유튜브",
}


SOURCE_ORDER = [
    "musinsa",
    "zigzag",
    "ably",
    "kream",
    "naver",
    "youtube",
    "musinsa_used",
]


def source_label(source):
    """
    Source 한글 라벨.
    """

    if source is None:
        return "-"

    return SOURCE_LABELS.get(
        source.code,
        source.name or source.code,
    )


_source_label = source_label


# ============================================================
# GROUP COUNT
# ============================================================

def group_count(
    queryset,
    key="source_id",
    **filters,
):
    """
    source_id 등 특정 key 기준으로
    건수를 한 번의 쿼리로 집계.

    Example:

    group_count(
        queryset,
        success=Q(status="SUCCESS"),
        failed=Q(status="FAILED"),
    )
    """

    annotations = {
        "n": Count("id")
    }

    for name, condition in filters.items():
        annotations[name] = Count(
            "id",
            filter=condition,
        )

    result = {}

    rows = (
        queryset
        .values(key)
        .annotate(**annotations)
    )

    for row in rows:
        result[row[key]] = row

    return result


_group_count = group_count


# ============================================================
# ORDERED SOURCES
# ============================================================

def ordered_sources():
    """
    SOURCE_ORDER 순서대로 Source 반환.
    정의되지 않은 Source는 뒤에 붙인다.
    """

    by_code = {
        source.code: source
        for source in Source.objects.all()
    }

    ordered = []

    for code in SOURCE_ORDER:
        source = by_code.pop(
            code,
            None,
        )

        if source is not None:
            ordered.append(
                source
            )

    remaining = sorted(
        by_code.values(),
        key=lambda source: source.code,
    )

    ordered.extend(
        remaining
    )

    return ordered


_ordered_sources = ordered_sources


def attach_latest_content_snapshot(rows):
    """
    ContentItem 목록 각각에
    최신 ContentSnapshot을 latest_snapshot으로 붙인다.
    """

    if not rows:
        return rows

    latest = {}

    for snapshot in (
        ContentSnapshot.objects
        .filter(
            content_item_id__in=[
                row.id
                for row in rows
            ]
        )
        .order_by(
            "content_item_id",
            "-observed_at",
        )
    ):
        latest.setdefault(
            snapshot.content_item_id,
            snapshot,
        )

    for row in rows:
        row.latest_snapshot = (
            latest.get(
                row.id
            )
        )

    return rows


# 기존 코드 호환
_attach_latest_content_snapshot = (
    attach_latest_content_snapshot
)

def find_source(*codes):
    """
    전달받은 source code 후보 중
    DB에 실제 존재하는 첫 Source 반환.

    Example:
        find_source(
            "musinsa",
            "MUSINSA",
        )
    """

    for code in codes:

        source = (
            Source.objects
            .filter(
                code=code
            )
            .first()
        )

        if source is not None:
            return source

    return None


# 기존 코드 호환
_find_source = find_source



def qs_without_page(request):
    """
    page 파라미터를 제외한 querystring 반환.

    예:
        source=1&q=test&
    """

    params = request.GET.copy()

    params.pop(
        "page",
        None,
    )

    encoded = params.urlencode()

    return (
        f"{encoded}&"
        if encoded
        else ""
    )


_qs_without_page = qs_without_page


def qs_without(
    request,
    *keys,
):
    """
    page + 지정한 key들을 제외한 querystring 반환.

    Example:
        qs_without(
            request,
            "order",
            "source",
        )
    """

    params = request.GET.copy()

    # page는 항상 제거
    params.pop(
        "page",
        None,
    )

    for key in keys:
        params.pop(
            key,
            None,
        )

    encoded = params.urlencode()

    return (
        f"{encoded}&"
        if encoded
        else ""
    )


_qs_without = qs_without


def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


def execute_query(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return dictfetchall(cursor)


# 기존 underscore import 호환
_dictfetchall = dictfetchall
_execute_query = execute_query
def _get_comment_summary():
    sql = """
    WITH comments AS (
        SELECT
            id,
            body,
            analysis_metadata,

            jsonb_array_length(
                COALESCE(
                    analysis_metadata->'mentions',
                    '[]'::jsonb
                )
            ) AS mention_count

        FROM analysis.text_document
        WHERE document_type = 'COMMENT'
    )

    SELECT
        -- 전체 댓글
        COUNT(*) AS total_comments,

        -- LLM이 keep=true로 판단한 댓글
        COUNT(*) FILTER (
            WHERE analysis_metadata->>'keep' = 'true'
        ) AS active_comments,

        -- 분석 메타데이터 존재
        COUNT(*) FILTER (
            WHERE analysis_metadata IS NOT NULL
              AND analysis_metadata <> '{}'::jsonb
        ) AS analyzed_comments,

        -- 전체 mention
        COALESCE(
            SUM(mention_count),
            0
        ) AS total_mentions,

        -- 댓글당 평균 mention
        ROUND(
            AVG(mention_count),
            2
        ) AS avg_mentions_per_comment,

        -- mention 2개 이상 댓글
        COUNT(*) FILTER (
            WHERE mention_count >= 2
        ) AS multi_tag_comments,

        -- 복합 태그 댓글 비율
        ROUND(
            COUNT(*) FILTER (
                WHERE mention_count >= 2
            ) * 100.0
            / NULLIF(COUNT(*), 0),
            2
        ) AS multi_tag_rate,

        -- 평균 댓글 길이
        ROUND(
            AVG(LENGTH(body))
            FILTER (
                WHERE body IS NOT NULL
                  AND BTRIM(body) <> ''
            ),
            2
        ) AS avg_body_length,

        -- JSON metadata 내부 published_at 기준 최신 댓글
        MAX(
            NULLIF(
                analysis_metadata->>'published_at',
                ''
            )::timestamptz
        ) AS latest_comment_at

    FROM comments;
    """

    rows = execute_query(sql)

    return rows[0] if rows else {
        "total_comments": 0,
        "active_comments": 0,
        "analyzed_comments": 0,
        "total_mentions": 0,
        "avg_mentions_per_comment": 0,
        "multi_tag_comments": 0,
        "multi_tag_rate": 0,
        "avg_body_length": 0,
        "latest_comment_at": None,
    }


def _get_intent_stats():
    sql = """
    WITH stats AS (
        SELECT
            analysis_metadata->>'intent' AS intent,
            COUNT(*) AS count
        FROM analysis.text_document
        WHERE document_type = 'COMMENT'
          AND analysis_metadata->>'intent' IS NOT NULL
        GROUP BY analysis_metadata->>'intent'
    )
    SELECT
        intent,
        count,
        ROUND(
            count * 100.0
            / SUM(count) OVER (),
            2
        ) AS percentage
    FROM stats
    ORDER BY count DESC;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        return dictfetchall(cursor)

def _get_slot_stats():
    sql = """
    WITH stats AS (
        SELECT
            mention->>'slot' AS slot,
            COUNT(*) AS count
        FROM analysis.text_document td

        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(
                td.analysis_metadata->'mentions',
                '[]'::jsonb
            )
        ) AS mention

        WHERE td.document_type = 'COMMENT'
          AND mention->>'slot' IS NOT NULL

        GROUP BY mention->>'slot'
    )
    SELECT
        slot,
        count,
        ROUND(
            count * 100.0
            / SUM(count) OVER (),
            2
        ) AS percentage
    FROM stats
    ORDER BY count DESC;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        return dictfetchall(cursor)

def _get_polarity_stats():
    sql = """
    WITH stats AS (
        SELECT
            mention->>'polarity' AS polarity,
            COUNT(*) AS count
        FROM analysis.text_document td

        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(
                td.analysis_metadata->'mentions',
                '[]'::jsonb
            )
        ) AS mention

        WHERE td.document_type = 'COMMENT'
          AND mention->>'polarity' IS NOT NULL

        GROUP BY mention->>'polarity'
    )
    SELECT
        polarity,
        count,
        ROUND(
            count * 100.0
            / SUM(count) OVER (),
            2
        ) AS percentage
    FROM stats
    ORDER BY count DESC;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        return dictfetchall(cursor)

def _get_tag_count_stats():
    sql = """
    WITH comment_tags AS (
        SELECT
            td.id,
            jsonb_array_length(
                COALESCE(
                    td.analysis_metadata->'mentions',
                    '[]'::jsonb
                )
            ) AS tag_count
        FROM analysis.text_document td
        WHERE td.document_type = 'COMMENT'
    )
    SELECT
        tag_count,
        COUNT(*) AS comment_count,

        ROUND(
            COUNT(*) * 100.0
            / SUM(COUNT(*)) OVER (),
            2
        ) AS percentage

    FROM comment_tags

    GROUP BY tag_count
    ORDER BY tag_count;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        return dictfetchall(cursor)


def _get_slot_combinations(limit=20):
    sql = """
    WITH comment_slots AS (
        SELECT
            td.id,

            ARRAY_AGG(
                DISTINCT mention->>'slot'
                ORDER BY mention->>'slot'
            ) AS slots

        FROM analysis.text_document td

        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(
                td.analysis_metadata->'mentions',
                '[]'::jsonb
            )
        ) AS mention

        WHERE td.document_type = 'COMMENT'
          AND mention->>'slot' IS NOT NULL

        GROUP BY td.id
    )

    SELECT
        array_to_string(slots, ' + ') AS combination,
        COUNT(*) AS comment_count

    FROM comment_slots

    WHERE CARDINALITY(slots) >= 2

    GROUP BY slots
    ORDER BY comment_count DESC

    LIMIT %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, [limit])
        return dictfetchall(cursor)


def _get_term_pairs(limit=50):
    sql = """
    WITH mentions AS (
        SELECT DISTINCT
            td.id AS text_document_id,
            mention->>'slot' AS slot,
            mention->>'term' AS term

        FROM analysis.text_document td

        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(
                td.analysis_metadata->'mentions',
                '[]'::jsonb
            )
        ) AS mention

        WHERE td.document_type = 'COMMENT'
          AND mention->>'term' IS NOT NULL
          AND mention->>'slot' IS NOT NULL
    )

    SELECT
        a.slot AS slot_1,
        a.term AS term_1,

        b.slot AS slot_2,
        b.term AS term_2,

        COUNT(*) AS co_count

    FROM mentions a

    JOIN mentions b
        ON a.text_document_id = b.text_document_id
       AND (a.slot, a.term) < (b.slot, b.term)

    GROUP BY
        a.slot,
        a.term,
        b.slot,
        b.term

    HAVING COUNT(*) >= 5

    ORDER BY co_count DESC

    LIMIT %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, [limit])
        return dictfetchall(cursor)


def _get_term_reaction_stats(limit=30):
    """
    COMMENT analysis_metadata의 실제 mention/intent를 이용한 term별 반응 집계.
    가공 점수가 아니라 실제 댓글 건수 기반.
    """
    sql = """
    WITH mentions AS (
        SELECT
            td.id AS document_id,
            td.analysis_metadata->>'intent' AS intent,
            mention->>'term' AS term,
            mention->>'slot' AS slot,
            mention->>'polarity' AS polarity
        FROM analysis.text_document td
        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(
                td.analysis_metadata->'mentions',
                '[]'::jsonb
            )
        ) AS mention
        WHERE td.document_type = 'COMMENT'
          AND td.analysis_metadata->>'keep' = 'true'
          AND mention->>'term' IS NOT NULL
          AND BTRIM(mention->>'term') <> ''
    )
    SELECT
        term,
        slot,

        COUNT(DISTINCT document_id) AS comment_count,

        COUNT(DISTINCT document_id) FILTER (
            WHERE polarity = 'POS'
        ) AS pos_count,

        COUNT(DISTINCT document_id) FILTER (
            WHERE polarity = 'NEG'
        ) AS neg_count,

        COUNT(DISTINCT document_id) FILTER (
            WHERE intent = 'PURCHASE'
        ) AS purchase_count,

        COUNT(DISTINCT document_id) FILTER (
            WHERE intent = 'QUESTION'
        ) AS question_count,

        COUNT(DISTINCT document_id) FILTER (
            WHERE intent = 'EXPERIENCE'
        ) AS experience_count,

        COUNT(DISTINCT document_id) FILTER (
            WHERE intent = 'PRAISE'
        ) AS praise_count,

        COUNT(DISTINCT document_id) FILTER (
            WHERE intent = 'CRITIQUE'
        ) AS critique_count

    FROM mentions
    GROUP BY term, slot
    HAVING COUNT(DISTINCT document_id) >= 3
    ORDER BY comment_count DESC, term
    LIMIT %s;
    """

    return execute_query(sql, [limit])


def _get_reaction_comment_samples(limit=20):
    """
    실제 COMMENT 원문 샘플.
    likes가 높은 댓글 우선, 동률이면 published_at 최신순.
    한 댓글에 여러 mention이 있어도 댓글은 한 행만 반환.
    """
    sql = """
    SELECT
        td.id,
        td.body,
        td.analysis_metadata->>'intent' AS intent,

        CASE
            WHEN COALESCE(td.analysis_metadata->>'likes', '') ~ '^[0-9]+$'
            THEN (td.analysis_metadata->>'likes')::int
            ELSE 0
        END AS likes,

        td.analysis_metadata->>'published_at' AS published_at,

        COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'slot', m->>'slot',
                        'term', m->>'term',
                        'polarity', m->>'polarity'
                    )
                    ORDER BY m->>'slot', m->>'term'
                )
                FROM jsonb_array_elements(
                    COALESCE(
                        td.analysis_metadata->'mentions',
                        '[]'::jsonb
                    )
                ) AS m
                WHERE m->>'term' IS NOT NULL
                  AND BTRIM(m->>'term') <> ''
            ),
            '[]'::jsonb
        ) AS mentions

    FROM analysis.text_document td
    WHERE td.document_type = 'COMMENT'
      AND td.analysis_metadata->>'keep' = 'true'
      AND td.body IS NOT NULL
      AND BTRIM(td.body) <> ''
      AND jsonb_array_length(
            COALESCE(
                td.analysis_metadata->'mentions',
                '[]'::jsonb
            )
          ) > 0

    ORDER BY
        CASE
            WHEN COALESCE(td.analysis_metadata->>'likes', '') ~ '^[0-9]+$'
            THEN (td.analysis_metadata->>'likes')::int
            ELSE 0
        END DESC,
        CASE
            WHEN COALESCE(td.analysis_metadata->>'published_at', '') <> ''
            THEN (td.analysis_metadata->>'published_at')::timestamptz
            ELSE NULL
        END DESC NULLS LAST,
        td.id DESC

    LIMIT %s;
    """

    rows = execute_query(sql, [limit])

    # psycopg/jsonb -> Python list/dict이지만 혹시 문자열이면 안전하게 보정
    import json as _json

    for row in rows:
        mentions = row.get("mentions")
        if isinstance(mentions, str):
            try:
                row["mentions"] = _json.loads(mentions)
            except Exception:
                row["mentions"] = []

    return rows


def get_brand_source_queryset(
    *,
    source_id=None,
    mapping_status=None,
    search=None,
):
    qs = (
        BrandSource.objects
        .select_related(
            "source",
            "brand",
        )
        .order_by("name", "id")
    )

    if source_id:
        qs = qs.filter(source_id=source_id)

    if mapping_status == "mapped":
        qs = qs.filter(brand__isnull=False)

    elif mapping_status == "unmapped":
        qs = qs.filter(brand__isnull=True)

    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(english_name__icontains=search)
        )

    return qs


def search_brands(query: str, limit: int = 30):
    """
    FEEDIT 표준 Brand 검색
    """
    qs = Brand.objects.all()

    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(english_name__icontains=query)
            | Q(code__icontains=query)
        )

    return qs.order_by("name")[:limit]



def get_category_source_queryset(
    *,
    source_id=None,
    mapping_status=None,
    search=None,
):
    qs = (
        CategorySource.objects
        .select_related(
            "source",
            "category",
        )
        .order_by(
            "source_id",
            "source_category_path",
            "id",
        )
    )

    if source_id:
        qs = qs.filter(source_id=source_id)

    if mapping_status == "mapped":
        qs = qs.filter(category_id__isnull=False)

    elif mapping_status == "unmapped":
        qs = qs.filter(category_id__isnull=True)

    if search:
        qs = qs.filter(
            Q(source_category_name__icontains=search)
            | Q(source_category_path__icontains=search)
        )

    return qs


def search_product_categories(query: str, limit: int = 30):
    qs = (
        Category.objects
        .filter(category_type="PRODUCT")
        .select_related("parent")
    )

    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(code__icontains=query)
        )

    return qs.order_by(
        "level",
        "sort_order",
        "name",
    )[:limit]

__all__ = [
    # S3
    "s3_client",
    "s3_bucket",
    "_s3_client",
    "_s3_bucket",

    # console / system
    "ConsoleLogHandler",
    "_ConsoleLogHandler",
    "console_line",
    "_console_line",
    "inspect_workers",
    "_inspect_workers",
    "mask",
    "_mask",

    # source helpers
    "ordered_sources",
    "_ordered_sources",
    "source_label",
    "_source_label",
    "find_source",
    "_find_source",

    # snapshot
    "attach_latest_product_snapshot",
    "attach_latest_content_snapshot",
    "_attach_latest_content_snapshot",
    "build_snapshot_changes",

    # queryset / querystring
    "group_count",
    "_group_count",
    "qs_without_page",
    "_qs_without_page",
    "qs_without",
    "_qs_without",

    # raw sql
    "dictfetchall",
    "execute_query",

    # comment analytics
    "_get_comment_summary",
    "_get_intent_stats",
    "_get_slot_stats",
    "_get_polarity_stats",
    "_get_tag_count_stats",
    "_get_slot_combinations",
    "_get_term_pairs",

    "_get_reaction_comment_samples",
    "_get_term_reaction_stats"
]