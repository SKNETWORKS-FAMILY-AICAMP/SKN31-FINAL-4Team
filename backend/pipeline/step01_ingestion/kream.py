from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import (
    BrandSource, CategorySource, ProductSource, ProductSourceSnapshot,
    ResaleSnapshot, RawDocument, Source,
)
from pipeline.step01_ingestion.common import load_raw_json, extract_payload

KST = ZoneInfo("Asia/Seoul")


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return None


def _integer(value):
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _model_fields(model):
    return {f.name for f in model._meta.concrete_fields}


def _aware(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise ValueError("timezone-aware raw.collected_at이 필요합니다.")
    return value


def _source_upsert(model, lookup, values, observed_at, *, count_detection=False):
    """Preserve normalized FK/mapping fields and never let older RAW overwrite newer source data."""
    fields = _model_fields(model)
    values = {k: v for k, v in values.items() if k in fields}
    with transaction.atomic():
        obj, created = model.objects.select_for_update().get_or_create(
            **lookup,
            defaults={
                **values,
                **({"first_seen_at": observed_at, "last_seen_at": observed_at}
                   if "first_seen_at" in fields else {}),
            },
        )
        if created:
            return obj, "created"
        updates = []
        last_seen = getattr(obj, "last_seen_at", None)
        is_newer = last_seen is None or observed_at > last_seen
        if is_newer:
            for key, value in values.items():
                # A feed-only record must not erase an existing detailed value.
                if value is None or (value == {} and getattr(obj, key, None)):
                    continue
                if getattr(obj, key) != value:
                    setattr(obj, key, value)
                    updates.append(key)
            if "last_seen_at" in fields:
                obj.last_seen_at = observed_at
                updates.append("last_seen_at")
        if "first_seen_at" in fields and (
            obj.first_seen_at is None or observed_at < obj.first_seen_at
        ):
            obj.first_seen_at = observed_at
            updates.append("first_seen_at")
        if updates:
            obj.save(update_fields=list(dict.fromkeys(updates)))
        return obj, "updated" if updates else "skipped"


def _daily_upsert(model, lookup, values, observed_at):
    fields = _model_fields(model)
    if "snapshot_date" not in fields:
        raise RuntimeError(
            f"{model.__name__}에 snapshot_date 필드가 없습니다. "
            "일별 최신 스냅샷 마이그레이션을 먼저 적용하세요."
        )
    with transaction.atomic():
        try:
            obj, created = model.objects.select_for_update().get_or_create(
                **lookup, defaults={"observed_at": observed_at, **values}
            )
        except IntegrityError:
            obj = model.objects.select_for_update().get(**lookup)
            created = False
        if created:
            return "created"
        if obj.observed_at >= observed_at:
            return "skipped"
        for key, value in values.items():
            setattr(obj, key, value)
        obj.observed_at = observed_at
        obj.save(update_fields=["observed_at", *values.keys()])
        return "updated"


class KreamIngestion:
    def __init__(self, source=None):
        self.source = source or Source.objects.get(code__iexact="kream")

    @staticmethod
    def _records(payload):
        if payload.get("entity_type") == "PRODUCT":
            product = _dict(payload.get("product"))
            pid = payload.get("source_product_id") or product.get("product_id")
            if pid is None:
                raise ValueError("PRODUCT RAW에 product_id가 없습니다.")
            return [(str(pid), {}, payload)]
        if payload.get("entity_type") != "DISCOVERY":
            raise ValueError(f"지원하지 않는 KREAM RAW: {payload.get('entity_type')}")
        feeds = {}
        for feed in _list(payload.get("products")):
            if isinstance(feed, dict) and feed.get("product_id") is not None:
                feeds[str(feed["product_id"])] = feed
        details = {}
        for row in _list(payload.get("details")):
            row = _dict(row)
            detail = _dict(row.get("detail"))
            nested_feed = _dict(row.get("feed"))
            pid = (detail.get("source_product_id")
                   or _dict(detail.get("product")).get("product_id")
                   or nested_feed.get("product_id"))
            if pid is not None and detail:
                details[str(pid)] = detail
                feeds.setdefault(str(pid), nested_feed)
        return [(pid, feed, details.get(pid)) for pid, feed in feeds.items()]

    def preview(self, payload, observed_at, *, limit=1):
        """Pure-Python field mapping preview: no DB writes."""
        observed_at = _aware(observed_at)
        discovery = _dict(payload.get("discovery"))
        return [self._build(pid, feed, detail, discovery, observed_at)
                for pid, feed, detail in self._records(payload)[:limit]]

    def run(self, *, raw_document_id=None, payload=None, observed_at=None):
        if raw_document_id is not None:
            raw = RawDocument.objects.select_related("source").get(pk=raw_document_id)
            if raw.source_id != self.source.pk:
                raise ValueError(f"RAW {raw.pk}는 KREAM 소스가 아닙니다.")
            payload = payload if payload is not None else extract_payload(load_raw_json(raw))
            observed_at = observed_at or raw.collected_at
        if not isinstance(payload, dict):
            raise ValueError("KREAM payload(dict)가 필요합니다.")
        observed_at = _aware(observed_at or payload.get("collected_at"))
        discovery = _dict(payload.get("discovery"))
        stats = {"products": 0, "brand_sources": 0, "category_sources": 0,
                 "product_snapshots": {"created": 0, "updated": 0, "skipped": 0},
                 "resale_snapshots": {"created": 0, "updated": 0, "skipped": 0},
                 "missing_detail": 0,
                 "product_source_ids": []}
        for pid, feed, detail in self._records(payload):
            mapped = self._build(pid, feed, detail, discovery, observed_at)
            with transaction.atomic():
                brand_source = None
                category_source = None
                if mapped["brand_id"] is not None:
                    brand_source, _ = _source_upsert(
                        BrandSource,
                        {"source": self.source, "source_brand_id": str(mapped["brand_id"])},
                        mapped["brand_source"], observed_at,
                    )
                    stats["brand_sources"] += 1
                if mapped["category_id"] is not None:
                    category_source, _ = _source_upsert(
                        CategorySource,
                        {"source": self.source, "source_category_id": str(mapped["category_id"])},
                        mapped["category_source"], observed_at,
                    )
                    stats["category_sources"] += 1
                product_values = {**mapped["product_source"],
                                  "source_brand": brand_source,
                                  "source_category": category_source}
                ps, _ = _source_upsert(
                    ProductSource,
                    {
                        "source": self.source,
                        "source_product_id": pid,
                    },
                    product_values,
                    observed_at,
                )

                stats["products"] += 1

                stats["product_source_ids"].append(
                    ps.id
                )
                date = observed_at.astimezone(KST).date()
                if mapped["product_snapshot"] is not None:
                    scope = mapped["product_snapshot"]["ranking_scope"]
                    result = _daily_upsert(
                        ProductSourceSnapshot,
                        {"product_source": ps, "snapshot_date": date,
                         "ranking_scope": scope},
                        mapped["product_snapshot"], observed_at,
                    )
                    stats["product_snapshots"][result] += 1
                if mapped["resale_snapshot"] is not None:
                    result = _daily_upsert(
                        ResaleSnapshot,
                        {"product_source": ps, "snapshot_date": date},
                        mapped["resale_snapshot"], observed_at,
                    )
                    stats["resale_snapshots"][result] += 1
                else:
                    stats["missing_detail"] += 1
        return stats

    def _build(self, pid, feed, detail, discovery, observed_at):
        feed = _dict(feed)
        detail = _dict(detail)
        product = _dict(detail.get("product"))
        brand = _dict(product.get("brand"))
        category = _dict(product.get("category"))
        snap = _dict(detail.get("snapshot"))
        market = _dict(detail.get("market"))
        brand_id = brand.get("brand_id") if brand.get("brand_id") is not None else feed.get("brand_id")
        category_id = (category.get("source_category_id") if category.get("source_category_id") is not None
                       else feed.get("category_id"))
        brand_name = brand.get("name") or feed.get("brand_name")
        category_depth1 = category.get("depth1_name") or feed.get("category_depth1")
        category_depth2 = category.get("depth2_name") or feed.get("category_depth2")
        category_path = " > ".join(x for x in (category_depth1, category_depth2) if x)
        images = _list(product.get("image_urls"))
        gender = (product.get("product_gender") if product.get("product_gender") is not None
                  else feed.get("product_gender"))
        style_code = product.get("style_code") or feed.get("style_code")
        url = detail.get("source_url") or feed.get("product_url") or f"https://kream.co.kr/products/{pid}"
        name_ko = product.get("name_ko") or feed.get("name_ko")
        name_en = product.get("name_en") or feed.get("name_en")
        # ProductSource.attributes에는 다른 Source 테이블/정식 컬럼과
        # 중복되지 않는 상품 고유 속성만 저장한다.
        #
        # - brand/category -> BrandSource, CategorySource
        # - style_code     -> ProductSource.style_no
        # - 대표 이미지    -> ProductSource.thumbnail_url
        # - gender         -> ProductSource.source_genders
        options = []
        for option in _list(detail.get("options")):
            if isinstance(option, dict):
                value = option.get("value")
            else:
                value = option

            if value not in (None, "") and value not in options:
                options.append(value)

        attributes = {
            "color": product.get("color"),
            "product_type": product.get("product_type") or feed.get("product_type"),
            "currency": product.get("currency") or "KRW",
            "options": options,
        }

        # None / 빈 값은 attributes에 남기지 않는다.
        attributes = {
            key: value
            for key, value in attributes.items()
            if value not in (None, "", [], {})
        }
        # KREAM numeric gender codes must not be mapped to FEEDIT gender_scope
        # without a verified KREAM gender-code dictionary.
        product_values = {
            "source_name": name_ko or name_en,
            "source_name_en": name_en,
            "style_no": style_code,
            "thumbnail_url": images[0] if images else None,
            "product_url": url,
            "attributes": attributes,
            "source_genders": [gender] if gender is not None else [],
            # market_type: preserve model default until its TextChoices are verified.
        }
        tab_id = discovery.get("tab_id") if discovery.get("tab_id") is not None else feed.get("tab_id")
        # The product's own category is NOT the discovery ranking category.
        rank_category = discovery.get("category_id", "all")
        sort = discovery.get("sort") or feed.get("sort") or "popular_score"
        scope = (f"KREAM:{tab_id}:{rank_category}:{sort}"
                 if tab_id is not None else "KREAM:DETAIL")
        product_snapshot = {
            "list_price": _decimal(snap.get("original_price")),
            "sale_price": _decimal(snap.get("current_price") if snap.get("current_price") is not None else feed.get("price")),
            # KREAM feed discount_rate is not validated as ordinary retail discount.
            "discount_rate": None,
            "rank_position": _integer(feed.get("feed_rank")),
            "ranking_scope": scope,
            "ranking_context": {
                "tab_id": tab_id, "category_id": rank_category, "sort": sort,
                "feed_rank": feed.get("feed_rank"), "sort_type": feed.get("sort_type"),
                "ranking_signals": _list(detail.get("ranking_signals")),
            },
            "rating": _decimal(snap.get("review_rating")),
            "review_count": _integer(snap.get("review_count")),
            "like_count": _integer(snap.get("wish_count")),
            "view_count": _integer(snap.get("viewer_count")),
            "sales_count": None,
            "stock_status": ("AVAILABLE" if snap.get("availability") is True
                             else "UNAVAILABLE" if snap.get("availability") is False else None),
            "platform_metrics": {
                "currency": product.get("currency") or "KRW",
                "feed_original_price": feed.get("original_price"),
                "feed_discount_rate_unverified": feed.get("discount_rate"),
                "total_review_count": snap.get("total_review_count"),
                "max_benefit_price": snap.get("max_benefit_price"),
                "is_active": snap.get("is_active"),
                "has_immediate_delivery_item": snap.get("has_immediate_delivery_item"),
                "price_source": "detail" if snap.get("current_price") is not None else "feed",
            },
        } if (feed or detail) else None
        resale_snapshot = None
        if detail:
            listings = _list(market.get("listings"))
            asks = _list(market.get("asks"))
            bids = _list(market.get("bids"))
            sales = _list(market.get("sales"))
            def prices(rows):
                return [p for row in rows if isinstance(row, dict)
                        if (p := _decimal(row.get("price"))) is not None]
            lp, ap, bp = prices(listings), prices(asks), prices(bids)
            resale_snapshot = {
                "listing_count": None, "available_count": None,
                "min_price": min(lp) if lp else None,
                "max_price": max(lp) if lp else None,
                "avg_price": (sum(lp) / len(lp)) if lp else None,
                "median_price": median(lp) if lp else None,
                "sold_count": None,
                "lowest_ask": min(ap) if ap else None,
                "highest_bid": max(bp) if bp else None,
                "last_trade_price": _decimal(snap.get("last_sale_price")),
                "trade_volume": None,
                "resale_price_ratio": None, "resale_index": None,
                "market_metrics": {
                    "currency": product.get("currency") or "KRW",
                    "current_price": snap.get("current_price"),
                    "sample_statistics": {
                        "listing_sample_count": len(listings),
                        "listing_min_price": float(min(lp)) if lp else None,
                        "listing_max_price": float(max(lp)) if lp else None,
                        "listing_avg_price": float(sum(lp) / len(lp)) if lp else None,
                        "listing_median_price": float(median(lp)) if lp else None,
                        "asks_sample_count": len(asks),
                        "bids_sample_count": len(bids),
                        "sales_sample_count": len(sales),
                    },
                    "coverage": {"listings_complete": False,
                                 "asks_complete": False,
                                 "bids_complete": False,
                                 "sales_complete": False},
                    "sample_asks": asks,
                    "sample_bids": bids,
                    "sample_sales": sales,
                    "sample_listings": listings,
                },
            }
        return {
            "product_id": pid, "observed_at": observed_at,
            "snapshot_date": observed_at.astimezone(KST).date(),
            "brand_id": brand_id,
            "brand_source": {"name": brand_name},
            "category_id": category_id,
            "category_source": {"source_category_name": category_depth2 or category_depth1,
                                "source_category_path": category_path},
            "product_source": product_values,
            "product_snapshot": product_snapshot,
            "resale_snapshot": resale_snapshot,
        }
