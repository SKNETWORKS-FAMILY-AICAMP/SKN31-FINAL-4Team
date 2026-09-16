from __future__ import annotations

import json
import logging
import re
from typing import Any


LOGGER = logging.getLogger("collection.normalization")

TABLE_BRAND_SOURCE = "dictionary.brand_source"
TABLE_CATEGORY_SOURCE = "dictionary.category_source"
TABLE_PRODUCT_SOURCE = "commerce.product_source"
TABLE_PRODUCT_SOURCE_SNAPSHOT = "snapshot.product_source_snapshot"
TABLE_RESALE_SNAPSHOT = "snapshot.resale_snapshot"


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def source_key_text(value: Any) -> str | None:
    """Normalize text only for a deterministic platform-source fallback key."""
    text = clean_text(value)
    return text.casefold() if text else None


def gender_scope(value: Any) -> str | None:
    values = value if isinstance(value, (list, tuple)) else [value]
    cleaned = [clean_text(item) for item in values]
    unique = list(dict.fromkeys(item for item in cleaned if item))
    return ",".join(unique) or None


def compact_preview(previews: list[dict], *, source: str | None = None) -> dict:
    related_count = sum(
        len(preview.get("related_listing_candidates") or []) for preview in previews
    )
    warnings = sum(len(preview.get("warnings") or []) for preview in previews)
    tables = sorted(
        {
            target.get("_table")
            for preview in previews
            for target in (preview.get("targets") or {}).values()
            if isinstance(target, dict) and target.get("_table")
        }
    )
    return {
        "source": previews[0]["source"] if previews else source,
        "db_write": False,
        "db_write_operations": 0,
        "normalized_product_count": len(previews),
        "related_listing_candidate_count": related_count,
        "warning_count": warnings,
        "target_tables": tables,
    }


def log_preview(preview: dict) -> None:
    source = preview.get("source")
    product = (preview.get("targets") or {}).get("product_source") or {}
    source_product_id = product.get("source_product_id")
    LOGGER.debug(
        "[NORMALIZE][DRY_RUN][%s] source_product_id=%s",
        source,
        source_product_id,
    )
    for name, target in (preview.get("targets") or {}).items():
        if not isinstance(target, dict):
            continue
        table = target.get("_table")
        operation = target.get("_operation")
        key = target.get("_key") or {}
        query_strategy = target.get("_query_strategy")
        references = target.get("_references") or {}
        fields = {key: value for key, value in target.items() if not key.startswith("_")}
        LOGGER.debug(
            "[DB_MAP][DRY_RUN] target=%s table=%s operation=%s "
            "source_product_id=%s key=%s query_strategy=%s references=%s fields=%s",
            name,
            table,
            operation,
            source_product_id,
            json.dumps(key, ensure_ascii=False, default=str),
            query_strategy,
            json.dumps(references, ensure_ascii=False, default=str),
            json.dumps(fields, ensure_ascii=False, default=str),
        )
    for related in preview.get("related_listing_candidates") or []:
        relation = related.get("relation") or {}
        candidate = related.get("product_source_payload") or {}
        related_snapshot = related.get("resale_snapshot_payload") or {}
        used = (candidate.get("attributes") or {}).get("used") or {}
        market_metrics = related_snapshot.get("market_metrics") or {}
        LOGGER.debug(
            "[NORMALIZE][RELATED] parent_goods_no=%s related_goods_no=%s "
            "condition=%s size=%s sale_price=%s sold_out=%s",
            relation.get("discovered_from"),
            candidate.get("source_product_id"),
            used.get("condition_grade"),
            used.get("size"),
            market_metrics.get("sale_price"),
            market_metrics.get("is_sold_out"),
        )
        LOGGER.debug(
            "[RELATED][NORMALIZED] parent=%s goods_no=%s "
            "target_product_table=%s target_snapshot_table=%s db_write=false",
            relation.get("discovered_from"),
            candidate.get("source_product_id"),
            TABLE_PRODUCT_SOURCE,
            TABLE_RESALE_SNAPSHOT,
        )
    LOGGER.debug(
        "normalization_preview=%s",
        json.dumps(preview, ensure_ascii=False, default=str),
    )


def log_run_summary(summary: dict) -> None:
    LOGGER.info(
        "[NORMALIZE][DRY_RUN][SUMMARY] source=%s products=%s related=%s "
        "warnings=%s target_tables=%s PREVIEW_DB_WRITE_EXECUTED=FALSE",
        summary.get("source"),
        summary.get("normalized_product_count"),
        summary.get("related_listing_candidate_count"),
        summary.get("warning_count"),
        ",".join(summary.get("target_tables") or []),
    )
    LOGGER.info(
        "[DB_WRITE][PREVIEW] executed=false migration=0 schema_change=0 insert=0 "
        "update=0 delete=0"
    )
