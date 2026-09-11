from __future__ import annotations

from typing import Any

from .collector import ZigzagCollector


class ZigzagStoreEnricher:
    """
    RANKING item의 store 정보를 완성한다.

    우선순위:
    1. 같은 run 내부 cache
    2. 기존 BrandSource DB
    3. 대표 상품 상세 HTML에서 main_domain 복구
    4. /{main_domain} STORE 페이지를 1회 조회해 profile 보강

    STORE는 CrawlTarget으로 등록하지 않는다.
    """

    def __init__(self, *, collector: ZigzagCollector):
        self.collector = collector
        self.cache: dict[str, dict[str, Any]] = {}

        self.cache_hit_count = 0
        self.db_hit_count = 0
        self.fetched_count = 0
        self.failure_count = 0

    def enrich(self, item: dict[str, Any]) -> dict[str, Any]:
        result = dict(item)
        store = dict(result.get("store") or {})

        shop_id = self._clean(
            store.get("source_brand_id")
            or result.get("store_id")
            or result.get("shop_id")
        )

        if not shop_id:
            result["store"] = store
            return result

        # 1) current-run cache
        cached = self.cache.get(shop_id)
        if cached:
            self.cache_hit_count += 1
            return self._merge(result, cached, source="RUN_CACHE")

        # 2) persisted BrandSource cache
        persisted = self._load_brand_source(shop_id)
        if persisted and self._is_complete(persisted):
            self.db_hit_count += 1
            self.cache[shop_id] = persisted
            return self._merge(result, persisted, source="BRAND_SOURCE")

        # persisted partial values are still useful as fallback
        resolved = dict(persisted or {})
        if store.get("name") and not resolved.get("name"):
            resolved["name"] = store.get("name")
        resolved["source_brand_id"] = shop_id

        try:
            # 3) representative product detail -> main_domain
            detail = self.collector.collect_product_detail(result)
            detail_store = (detail or {}).get("store") or {}
            resolved = self._merge_store_dict(resolved, detail_store)

            # 4) full store profile once
            main_domain = self._clean(resolved.get("main_domain"))
            if main_domain:
                profile = self.collector.collect_shop(
                    f"https://zigzag.kr/{main_domain}",
                    collect_products=False,
                )
                resolved = self._merge_store_dict(
                    resolved,
                    profile.get("shop") or {},
                )

            self.fetched_count += 1

        except Exception as exc:
            self.failure_count += 1
            resolved["enrichment_error"] = {
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }

        self.cache[shop_id] = resolved
        return self._merge(result, resolved, source="FETCHED")

    @property
    def unique_store_count(self) -> int:
        return len(self.cache)

    @staticmethod
    def _clean(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _is_complete(cls, store: dict[str, Any]) -> bool:
        return bool(
            cls._clean(store.get("source_brand_id"))
            and cls._clean(store.get("main_domain"))
            and cls._clean(store.get("source_profile_url"))
        )

    @classmethod
    def _merge_store_dict(
        cls,
        base: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(base or {})
        for key, value in (incoming or {}).items():
            if value not in (None, "", [], {}):
                result[key] = value

        main_domain = cls._clean(
            result.get("main_domain")
            or result.get("shop_domain")
            or result.get("domain")
        )
        if main_domain:
            result["main_domain"] = main_domain
            if not result.get("source_profile_url"):
                result["source_profile_url"] = (
                    f"https://zigzag.kr/{main_domain}"
                )
        return result

    @classmethod
    def _merge(
        cls,
        item: dict[str, Any],
        resolved_store: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        result = dict(item)
        store = cls._merge_store_dict(
            dict(result.get("store") or {}),
            resolved_store,
        )
        store["enrichment_source"] = source
        result["store"] = store
        result["store_id"] = store.get("source_brand_id")
        result["store_name"] = store.get("name")
        return result

    @staticmethod
    def _load_brand_source(shop_id: str) -> dict[str, Any] | None:
        """
        collection 계층의 import-time Django 의존을 피하기 위해 lazy import.
        DB 연결이 불가능하면 그냥 None -> HTTP enrichment로 간다.
        """
        try:
            from apps.core.models import BrandSource

            obj = (
                BrandSource.objects
                .filter(
                    source__code__iexact="ZIGZAG",
                    source_brand_id=str(shop_id),
                )
                .first()
            )
        except Exception:
            return None

        if obj is None:
            return None

        attrs = obj.attributes if isinstance(obj.attributes, dict) else {}

        return {
            "source_brand_id": str(obj.source_brand_id),
            "name": obj.name,
            "english_name": obj.english_name,
            "main_domain": attrs.get("main_domain"),
            "source_profile_url": obj.source_profile_url,
            "image_url": obj.image_url,
            "description": obj.description,
            "target_age": obj.target_age,
            "style_list": attrs.get("style_list"),
            "bookmark_count": attrs.get("bookmark_count"),
            "seller_badges": attrs.get("seller_badges"),
            "total_product_count": attrs.get("total_product_count"),
        }
