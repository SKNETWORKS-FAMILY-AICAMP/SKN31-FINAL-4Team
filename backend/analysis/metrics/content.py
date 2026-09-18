from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db.models import Avg, Count, Max
from django.utils import timezone

from apps.core.models import ContentItem, ContentSnapshot, DictionaryTerm, Source

from .common import METRIC_VERSION, ensure_metric, merge_json


def _day_bounds(metric_date: date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(metric_date, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def _content_term_filter(qs, term: DictionaryTerm):
    """
    ContentItem의 title/description/metadata 구조가 소스마다 달라질 수 있으므로
    현재 확실한 문자열 필드가 있을 때만 좁힌다.

    핵심 term mention 자체는 reaction.py가 TextDocument 기반으로 집계한다.
    여기서는 조회/좋아요/댓글 등 CONTENT snapshot 보조 신호를 붙인다.
    """
    from django.db.models import Q

    names = {
        str(getattr(term, "canonical_name", "") or "").strip(),
        str(getattr(term, "normalized_name", "") or "").strip(),
    }
    names.discard("")

    if not names:
        return qs.none()

    q = Q()
    model_fields = {f.name for f in ContentItem._meta.get_fields()}

    for name in names:
        if "title" in model_fields:
            q |= Q(title__icontains=name)
        if "description" in model_fields:
            q |= Q(description__icontains=name)

    return qs.filter(q) if q else qs.none()


def apply_content_metrics(
    metric_date: date,
    *,
    metric_version: str = METRIC_VERSION,
) -> dict:
    """
    ContentItem / ContentSnapshot의 실제 engagement 보조 신호 저장.
    TextDocument mention 집계와 중복되지 않게 metrics['content']에 보존.
    """
    start, end = _day_bounds(metric_date)

    content_fields = {f.name for f in ContentItem._meta.get_fields()}
    snapshot_fields = {f.name for f in ContentSnapshot._meta.get_fields()}

    sources = list(Source.objects.all())
    terms = DictionaryTerm.objects.filter(status="ACTIVE")
    saved = 0

    for source in sources:
        item_qs = ContentItem.objects.all()

        if "source" in content_fields:
            item_qs = item_qs.filter(source=source)
        else:
            continue

        # published_at이 있으면 해당 날짜 콘텐츠, 없으면 전체에서 term 후보를 잡되
        # snapshot 날짜가 있을 때 snapshot 쪽에서 날짜 제한.
        if "published_at" in content_fields:
            item_qs = item_qs.filter(
                published_at__gte=start,
                published_at__lt=end,
            )

        if not item_qs.exists():
            continue

        for term in terms.iterator(chunk_size=500):
            matched_items = _content_term_filter(item_qs, term)
            if not matched_items.exists():
                continue

            content_count = matched_items.values("id").distinct().count()

            creator_count = 0
            for candidate in ("creator", "profile", "channel"):
                if candidate in content_fields:
                    creator_count = (
                        matched_items
                        .exclude(**{f"{candidate}__isnull": True})
                        .values(f"{candidate}_id")
                        .distinct()
                        .count()
                    )
                    break

            snapshots = ContentSnapshot.objects.filter(
                content_item_id__in=matched_items.values("id")
            )

            if "observed_at" in snapshot_fields:
                snapshots = snapshots.filter(
                    observed_at__gte=start,
                    observed_at__lt=end,
                )

            agg_kwargs = {"snapshot_count": Count("id")}
            for field in ("view_count", "like_count", "comment_count"):
                if field in snapshot_fields:
                    agg_kwargs[f"max_{field}"] = Max(field)
                    agg_kwargs[f"avg_{field}"] = Avg(field)

            agg = snapshots.aggregate(**agg_kwargs)

            metric = ensure_metric(
                term=term,
                source=source,
                metric_date=metric_date,
                metric_version=metric_version,
            )

            metric.content_count = max(metric.content_count or 0, content_count)
            metric.creator_count = max(metric.creator_count or 0, creator_count)

            content = {
                "content_count": content_count,
                "creator_count": creator_count,
                "snapshot_count": int(agg.get("snapshot_count") or 0),
            }

            for field in ("view_count", "like_count", "comment_count"):
                max_key = f"max_{field}"
                avg_key = f"avg_{field}"
                if max_key in agg:
                    content[max_key] = int(agg.get(max_key) or 0)
                    content[avg_key] = (
                        round(float(agg[avg_key]), 4)
                        if agg.get(avg_key) is not None
                        else None
                    )

            metric.metrics = merge_json(
                metric.metrics,
                {"content": content},
            )
            metric.save()
            saved += 1

    return {"saved": saved}
