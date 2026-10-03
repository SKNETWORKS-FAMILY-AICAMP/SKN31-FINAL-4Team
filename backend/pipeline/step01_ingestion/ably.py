from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from apps.core.models import (
    BrandSource, CategorySource, ProductSource,
    ProductSourceSnapshot, ProductReview, RawDocument,
)
from .common import base_cleaning, extract_payload, get_s3_client, load_raw_json
from collection.ably.store_profile_normalization import (
    build_brand_source_candidates, choose_brand_source_name, merge_brand_source_attributes,
)


def decimal_value(value):
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def integer_value(value):
    try:
        return int(Decimal(str(value))) if value not in (None, "") else None
    except (ValueError, InvalidOperation, OverflowError):
        return None


def non_negative_count(value):
    """Normalize a platform counter without turning invalid data into a real zero."""
    parsed = integer_value(value)
    return parsed if parsed is None or parsed >= 0 else None


def review_datetime(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = parse_datetime(value)
    else:
        return None
    if result and timezone.is_naive(result):
        from zoneinfo import ZoneInfo
        result = timezone.make_aware(result, ZoneInfo("Asia/Seoul"))
    return result


class AblyIngestion:
    SOURCE_CODE = "ABLY"

    def __init__(self):
        self.s3 = get_s3_client()

    def run(self, raw_document_id):
        raw = RawDocument.objects.select_related("source", "crawl_run").get(pk=raw_document_id)
        if raw.source.code.strip().upper() != self.SOURCE_CODE:
            raise ValueError("ABLY RawDocument source mismatch")
        payload = extract_payload(load_raw_json(raw, s3_client=self.s3))
        entity = str(payload.get("entity_type") or "").upper()
        result = {"raw_document_id": raw.id, "entity_type": entity, "products": 0,
                  "product_created": 0, "product_updated": 0, "snapshot_created": 0,
                  "review_created": 0, "review_updated": 0, "brand_created": 0,
                  "brand_updated": 0, "failed": 0, "errors": [], "product_source_ids": []}
        if entity == "STORE_PROFILE":
            # Brand department collects profiles; it must not generate product normalization jobs.
            for candidate in build_brand_source_candidates(payload):
                try:
                    with transaction.atomic():
                        _, created = self._brand(raw, candidate["source_brand_id"],
                                                 candidate["name"], candidate["attributes"])
                    result["brand_created" if created else "brand_updated"] += 1
                except Exception as exc:
                    result["failed"] += 1
                    result["errors"].append({"source_brand_id": candidate["source_brand_id"],
                                             "error_type": type(exc).__name__, "error_message": str(exc)})
            return result
        if entity != "RANKING":
            raise ValueError(f"Unsupported ABLY STEP01 entity_type: {entity}")
        for index, product in enumerate(payload.get("products") or []):
            result["products"] += 1
            try:
                one = self._product(raw, product, payload.get("ranking") or {})
                result["product_source_ids"].append(one.pop("product_source_id"))
                for key, value in one.items():
                    result[key] += value
            except Exception as exc:
                result["failed"] += 1
                result["errors"].append({"product_index": index,
                    "source_product_id": product.get("source_product_id") if isinstance(product, dict) else None,
                    "error_type": type(exc).__name__, "error_message": str(exc)})
        result["product_source_ids"] = list(dict.fromkeys(result["product_source_ids"]))
        return result

    def _brand(self, raw, brand_id, name, attributes):
        observed = raw.collected_at or timezone.now()
        brand, created = BrandSource.objects.get_or_create(
            source=raw.source, source_brand_id=str(brand_id),
            defaults={"name": base_cleaning(name), "attributes": attributes,
                      "first_seen_at": observed, "last_seen_at": observed})
        if not created:
            brand.name, _ = choose_brand_source_name(brand.name, base_cleaning(name))
            brand.attributes = merge_brand_source_attributes(brand.attributes, attributes)
            brand.last_seen_at = observed
            brand.save(update_fields=["name", "attributes", "last_seen_at", "updated_at"])
        return brand, created

    @transaction.atomic
    def _product(self, raw, row, ranking):
        source_id = base_cleaning(row.get("source_product_id"))
        name = base_cleaning(row.get("name"))
        if not source_id or not name:
            raise ValueError("Missing product id or empty source_name after STEP01 cleaning")
        observed = raw.collected_at or timezone.now()
        brand_data, market = row.get("brand") or {}, row.get("market") or {}
        brand_id = brand_data.get("source_brand_id")
        brand_name = brand_data.get("name")
        kind = "BRAND"
        if not brand_id and brand_name:
            brand_id = "NAME:" + (base_cleaning(brand_name) or "")
        if not brand_id and (market.get("source_market_id") or market.get("name")):
            brand_id = ("MARKET:" + str(market["source_market_id"])) if market.get("source_market_id") else "MARKET_NAME:" + (base_cleaning(market.get("name")) or "")
            brand_name, kind = market.get("name"), "MARKET_FALLBACK"
        brand, brand_created = (None, False)
        if brand_id:
            brand, brand_created = self._brand(raw, brand_id, brand_name,
                {"candidate_kind": kind, "markets": [{"market_sno": market.get("source_market_id"), "market_name": market.get("name")}] if market else []})
        category_data = row.get("category") or {}
        category_id = category_data.get("source_category_id")
        category_name = category_data.get("name")
        if not category_id and category_data.get("standard_category_id"):
            category_id = "STANDARD:" + str(category_data["standard_category_id"])
            category_name = category_data.get("standard_category_name")
        category = None
        if category_id:
            category, _ = CategorySource.objects.update_or_create(
                source=raw.source, source_category_id=str(category_id),
                defaults={"source_category_name": base_cleaning(category_name), "last_seen_at": observed})
        product, created = ProductSource.objects.get_or_create(
            source=raw.source, source_product_id=source_id,
            defaults={"source_name": name, "first_seen_at": observed})
        product.source_name = name
        # Preserve mapped Product, normalized_name, attributes and manual mapping status.
        if brand is not None:
            product.source_brand = brand
        if category is not None:
            product.source_category = category
        product.product_url = row.get("product_url")
        product.thumbnail_url = (row.get("images") or {}).get("image")
        product.style_no = base_cleaning(row.get("sku_code"))
        product.attributes = {
            **(product.attributes or {}),
            "ably": {"source_name_raw": row.get("name"), "market": market,
                     "category": category_data, "attributes": row.get("attributes") or {},
                     "review_summary": (row.get("reviews") or {}).get("summary") or {}},
        }
        product.last_seen_at = observed
        product.save(update_fields=["source_name", "source_brand", "source_category", "product_url",
                                   "thumbnail_url", "style_no", "attributes", "last_seen_at", "updated_at"])
        snapshot = row.get("snapshot") or {}
        raw_sales_count = snapshot.get("sales_count")
        sales_count = non_negative_count(raw_sales_count)
        platform_metrics = dict(snapshot)
        if raw_sales_count is not None and sales_count is None:
            platform_metrics["raw_sales_count"] = raw_sales_count
        import hashlib
        import json
        scope_keys = ("filter", "market_type_sno", "category_sno", "period", "age_tags")
        identity = json.dumps({key: ranking.get(key) for key in scope_keys}, sort_keys=True)
        scope = "ABLY:" + hashlib.sha256(identity.encode()).hexdigest()[:40]
        _, snapshot_created = ProductSourceSnapshot.objects.update_or_create(
            product_source=product, observed_at=observed, ranking_scope=scope,
            defaults={"list_price": decimal_value(snapshot.get("regular_price")),
                      "sale_price": decimal_value(snapshot.get("sale_price")),
                      "discount_rate": decimal_value(snapshot.get("discount_rate")),
                      "rank_position": (row.get("ranking") or {}).get("rank"),
                      "ranking_context": ranking, "review_count": snapshot.get("review_count"),
                      "sales_count": sales_count,
                      "stock_status": "SOLD_OUT" if snapshot.get("is_sold_out") else "AVAILABLE" if snapshot.get("is_buyable") else None,
                      "platform_metrics": platform_metrics})
        counts = {"product_source_id": product.id, "product_created": int(created),
                  "product_updated": int(not created), "snapshot_created": int(snapshot_created),
                  "brand_created": int(brand is not None and brand_created),
                  "brand_updated": int(brand is not None and not brand_created),
                  "review_created": 0, "review_updated": 0}
        for review in (row.get("reviews") or {}).get("items") or []:
            review_id = base_cleaning(review.get("source_review_id"))
            content = base_cleaning(review.get("content"))
            if not review_id or not content:
                continue
            reviewer = review.get("reviewer") or {}
            defaults = {"review_type": review.get("review_type") or "TEXT", "content": content,
                        "grade": None, "goods_option": ", ".join(map(str, review.get("goods_option") or []))[:200],
                        "like_count": review.get("like_count") or 0, "reviewer_sex": "",
                        "reviewer_height": integer_value(reviewer.get("height")), "reviewer_weight": integer_value(reviewer.get("weight")),
                        "survey": {**(review.get("survey") or {}), "evaluation": review.get("evaluation"),
                                   "delivery_evaluation": review.get("delivery_evaluation"),
                                   "reviewer": reviewer, "images": review.get("images") or [],
                                   "images_webp": review.get("images_webp") or []},
                        "source_created_at": review_datetime(review.get("created_at"))}
            saved, review_created = ProductReview.objects.get_or_create(
                product_source=product, source_review_id=review_id,
                defaults={**defaults, "created_at": timezone.now()})
            if not review_created:
                for key, value in defaults.items():
                    setattr(saved, key, value)
                saved.save(update_fields=list(defaults))
            counts["review_created" if review_created else "review_updated"] += 1
        return counts
