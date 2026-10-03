"""Load collected commerce reviews from a RawDocument into ProductReview."""

from __future__ import annotations

import json
from datetime import datetime, time, timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.core.models import ProductReview, ProductSource, RawDocument, TextDocument

from .common import extract_payload, get_s3_client, load_raw_json


REVIEW_DOCUMENT_TYPES = {
    "MUSINSA": {"RANKING", "PRODUCT"},
    "ABLY": {"RANKING"},
    "ZIGZAG": {"CNV_CATEGORY", "RANKING"},
}


def _products(payload: dict, source_code: str):
    if source_code == "ZIGZAG":
        groups = payload.get("groups") or {}
        for snapshots in groups.values():
            if not isinstance(snapshots, list):
                continue
            for snapshot in snapshots:
                if isinstance(snapshot, dict):
                    yield from (p for p in snapshot.get("products") or [] if isinstance(p, dict))
        return

    products = payload.get("products")
    if isinstance(products, list):
        yield from (p for p in products if isinstance(p, dict))
    elif source_code == "MUSINSA" and isinstance(payload.get("product"), dict):
        yield payload


def _product_id(product: dict, source_code: str) -> str | None:
    if source_code == "MUSINSA":
        value = (product.get("product") or {}).get("goods_no")
    elif source_code == "ZIGZAG":
        value = product.get("product_id")
    else:
        value = product.get("source_product_id")
    return str(value) if value not in (None, "") else None


def _review_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        # Zigzag sends Unix milliseconds; parsing the digits as an ISO date
        # can yield either NULL or a plausible-looking year centuries ago.
        if text.isascii() and text.isdigit():
            if len(text) not in (10, 13):
                return None
            try:
                timestamp = int(text) / (1000 if len(text) == 13 else 1)
                return datetime.fromtimestamp(timestamp, tz=datetime_timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        try:
            parsed = parse_datetime(text)
            if parsed is None:
                date = parse_date(text)
                parsed = datetime.combine(date, time.min) if date else None
        except ValueError:
            parsed = None
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _integer(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", ""))
        return int(number) if number.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def _text(value, *, max_length=None):
    if value is None:
        result = ""
    elif isinstance(value, (dict, list)):
        result = json.dumps(value, ensure_ascii=False)
    else:
        result = str(value)
    return result[:max_length] if max_length else result


def _defaults(review: dict, source_code: str, *, collected_for_product_id=None) -> dict:
    reviewer = review.get("reviewer") or {}
    reviewer = reviewer if isinstance(reviewer, dict) else {}
    survey = review.get("survey") or {}
    # Keep platform fields for which ProductReview has no dedicated column.
    extra = {
        "survey": survey,
        "images": review.get("images") or [],
    }
    if source_code == "ABLY":
        extra.update(
            evaluation=review.get("evaluation"),
            delivery_evaluation=review.get("delivery_evaluation"),
            images_webp=review.get("images_webp") or [],
        )
    elif source_code == "ZIGZAG":
        extra.update(
            source_grade=review.get("grade"),
            videos=review.get("videos") or [],
            additional_description=review.get("additional_description"),
            updated_at=review.get("updated_at"),
        )
    if reviewer:
        extra["reviewer"] = reviewer
    if collected_for_product_id is not None:
        extra["collected_for_product_id"] = collected_for_product_id
    option = review.get("goods_option")
    if isinstance(option, (dict, list)):
        extra["goods_option_raw"] = option
    return {
        "review_type": _text(review.get("review_type"), max_length=30),
        "content": _text(review.get("content")),
        "grade": _integer(review.get("grade")),
        "goods_option": _text(option, max_length=200),
        "like_count": _integer(review.get("like_count")) or 0,
        "reviewer_sex": _text(reviewer.get("sex"), max_length=20),
        "reviewer_height": _integer(reviewer.get("height")),
        "reviewer_weight": _integer(reviewer.get("weight")),
        "survey": extra,
        "source_created_at": _review_date(review.get("created_at")),
    }


def ingest_raw_document_reviews(
    *, raw_document_id: int, raw_data: dict | None = None,
    create_missing_products: bool = False,
) -> dict:
    """Upsert every review in one saved RAW document; safe to rerun."""
    raw_document = RawDocument.objects.select_related("source").get(pk=raw_document_id)
    source_code = raw_document.source.code.upper()
    document_type = raw_document.document_type.upper()
    if document_type not in REVIEW_DOCUMENT_TYPES.get(source_code, set()):
        raise ValueError(f"Unsupported review RAW: {source_code}/{document_type}")

    if raw_data is None:
        raw_data = load_raw_json(raw_document, s3_client=get_s3_client())
    payload = extract_payload(raw_data)
    result = {
        "raw_document_id": raw_document.id,
        "source": source_code,
        "created": 0,
        "updated": 0,
        "skipped_missing_product": 0,
        "skipped_invalid_review": 0,
        "created_missing_products": 0,
    }
    product_cache = {}
    pending = {}
    with transaction.atomic():
        for product in _products(payload, source_code):
            product_id = _product_id(product, source_code)
            bundle = product.get("reviews") or {}
            items = bundle.get("items") if isinstance(bundle, dict) else None
            if not isinstance(items, list) or not items:
                continue
            for review in items:
                if not isinstance(review, dict):
                    result["skipped_invalid_review"] += 1
                    continue
                review_id = review.get("source_review_id")
                if review_id in (None, ""):
                    review_id = review.get("review_id")
                if review_id in (None, ""):
                    result["skipped_invalid_review"] += 1
                    continue
                nested_id = review.get("source_product_id")
                review_product_id = (
                    str(nested_id) if nested_id not in (None, "") else product_id
                )
                if review_product_id is None:
                    result["skipped_missing_product"] += 1
                    continue
                if review_product_id not in product_cache:
                    product_source = ProductSource.objects.filter(
                        source_id=raw_document.source_id,
                        source_product_id=review_product_id,
                    ).first()
                    if product_source is None and create_missing_products:
                        if review_product_id != product_id:
                            name = None
                        elif source_code == "MUSINSA":
                            name = (product.get("product") or {}).get("name")
                        else:
                            name = product.get("product_name") or product.get("name")
                        product_source, created = ProductSource.objects.get_or_create(
                            source_id=raw_document.source_id,
                            source_product_id=review_product_id,
                            defaults={
                                "source_name": _text(name, max_length=500) or None,
                                "first_seen_at": raw_document.collected_at,
                                "last_seen_at": raw_document.collected_at,
                            },
                        )
                        result["created_missing_products"] += int(created)
                    product_cache[review_product_id] = product_source
                product_source = product_cache[review_product_id]
                if product_source is None:
                    result["skipped_missing_product"] += 1
                    continue
                key = (product_source.id, str(review_id))
                pending[key] = ProductReview(
                    product_source_id=product_source.id,
                    source_review_id=str(review_id),
                    **_defaults(
                        review, source_code,
                        collected_for_product_id=(
                            product_id if review_product_id != product_id else None
                        ),
                    ),
                )

        if pending:
            existing = set(
                ProductReview.objects.filter(
                    product_source_id__in={key[0] for key in pending},
                    source_review_id__in={key[1] for key in pending},
                ).values_list("product_source_id", "source_review_id")
            )
            result["updated"] = len(existing & pending.keys())
            result["created"] = len(pending) - result["updated"]
            ProductReview.objects.bulk_create(
                list(pending.values()),
                batch_size=500,
                update_conflicts=True,
                unique_fields=["product_source", "source_review_id"],
                update_fields=[
                    "review_type", "content", "grade", "goods_option",
                    "like_count", "reviewer_sex", "reviewer_height",
                    "reviewer_weight", "survey", "source_created_at",
                ],
            )
    return result


def require_complete_review_ingestion(result: dict) -> dict:
    """Fail automatic ingestion when a saved RAW review was left out."""
    if result["skipped_missing_product"] or result["skipped_invalid_review"]:
        raise RuntimeError(f"Commerce review ingestion incomplete: {result}")
    return result



def sync_review_text_documents(*, product_review_ids: list[int]) -> dict:
    """Current ProductReview rows -> TextDocument(REVIEW), without legacy analysis code."""
    ids = list(dict.fromkeys(int(v) for v in product_review_ids if v not in (None, "")))
    if not ids:
        return {"created": 0, "updated": 0, "text_document_ids": []}

    reviews = list(
        ProductReview.objects
        .filter(id__in=ids)
        .select_related("product_source__source")
        .order_by("id")
    )

    created_count = 0
    updated_count = 0
    document_ids: list[int] = []

    with transaction.atomic():
        for review in reviews:
            body = str(review.content or "").strip()
            if not body:
                continue

            source = review.product_source.source
            external_id = str(review.source_review_id)[:255]
            metadata = {
                "origin": "commerce.product_review",
                "review_id": review.id,
                "product_source_id": review.product_source_id,
                "review_type": review.review_type,
                "grade": review.grade,
                "goods_option": review.goods_option,
                "like_count": review.like_count,
                "reviewer_sex": review.reviewer_sex,
                "reviewer_height": review.reviewer_height,
                "reviewer_weight": review.reviewer_weight,
                "survey": review.survey if isinstance(review.survey, dict) else {},
            }

            document = (
                TextDocument.objects
                .filter(
                    source=source,
                    document_type=TextDocument.DocumentType.REVIEW,
                    external_id=external_id,
                )
                .first()
            )

            if document is None:
                document = TextDocument.objects.create(
                    source=source,
                    document_type=TextDocument.DocumentType.REVIEW,
                    external_id=external_id,
                    body=body,
                    language="ko",
                    analysis_metadata=metadata,
                    analysis_status=TextDocument.AnalysisStatus.PENDING,
                )
                created_count += 1
            else:
                old_meta = document.analysis_metadata if isinstance(document.analysis_metadata, dict) else {}
                merged_meta = {**old_meta, **metadata}
                changed = document.body != body or merged_meta != old_meta
                if changed:
                    document.body = body
                    document.analysis_metadata = merged_meta
                    document.save(update_fields=["body", "analysis_metadata", "updated_at"])
                    updated_count += 1

            document_ids.append(document.id)

    return {
        "created": created_count,
        "updated": updated_count,
        "text_document_ids": list(dict.fromkeys(document_ids)),
    }


def ingest_and_sync_raw_document_reviews(*, raw_document_id: int) -> dict:
    """LIVE review bridge: RAW -> ProductReview -> TextDocument(REVIEW)."""
    raw = RawDocument.objects.select_related("source").get(pk=raw_document_id)
    source_code = str(raw.source.code or "").strip().upper()
    document_type = str(raw.document_type or "").strip().upper()

    if document_type not in REVIEW_DOCUMENT_TYPES.get(source_code, set()):
        return {
            "status": "SKIPPED",
            "reason": "UNSUPPORTED_REVIEW_DOCUMENT",
            "product_review_ids": [],
            "text_document_ids": [],
        }

    review_result = ingest_raw_document_reviews(raw_document_id=raw_document_id)

    # Resolve only reviews represented by this RAW by matching source/product ids
    # from the RAW parser. This is bounded to products touched in the document.
    raw_data = load_raw_json(raw, s3_client=get_s3_client())
    payload = extract_payload(raw_data)
    source_product_ids = [
        pid for pid in (_product_id(product, source_code) for product in _products(payload, source_code))
        if pid is not None
    ]
    product_source_ids = list(
        ProductSource.objects.filter(
            source_id=raw.source_id,
            source_product_id__in=source_product_ids,
        ).values_list("id", flat=True)
    )
    product_review_ids = list(
        ProductReview.objects.filter(
            product_source_id__in=product_source_ids,
        ).values_list("id", flat=True)
    )

    text_result = sync_review_text_documents(product_review_ids=product_review_ids)
    return {
        "status": "SUCCESS",
        **review_result,
        "product_review_ids": product_review_ids,
        "text_document_ids": text_result["text_document_ids"],
        "text_document_created": text_result["created"],
        "text_document_updated": text_result["updated"],
    }
