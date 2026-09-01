from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from .client import MusinsaClient
from .constants import ARCHIVE_CATEGORIES_API_URL, ARCHIVE_GOODS_API_URL, PRODUCT_BASE_URL, RANKING_API_URL
from .exceptions import MusinsaCollectError


class MusinsaRankingCollector:
    def __init__(self, client: MusinsaClient):
        self.client = client

    @staticmethod
    def _require_endpoint(value: str, name: str) -> str:
        if not value:
            raise MusinsaCollectError(f"{name} 값이 비어 있습니다. 기존 검증된 constants.py endpoint를 넣어주세요.")
        return value

    def discover_current(self, target_url: str) -> list[dict]:
        endpoint = self._require_endpoint(RANKING_API_URL, "RANKING_API_URL")
        query = parse_qs(urlparse(target_url).query)
        period = query.get("period", ["DAILY"])[0]
        gender = query.get("gf", ["A"])[0]
        category_code = query.get("categoryCode", [""])[0]
        age_band = query.get("ageBand", ["AGE_BAND_ALL"])[0]
        params = {
            "storeCode": query.get("storeCode", ["musinsa"])[0], "subPan": query.get("subPan", ["product"])[0],
            "sectionId": query.get("sectionId", ["200"])[0], "gf": gender,
            "contentsId": query.get("contentsId", [""])[0], "categoryCode": category_code,
            "ageBand": age_band, "period": period,
        }
        body = self.client.get_json(endpoint, params=params, headers={"Referer": target_url})
        modules = ((body.get("data") or {}).get("modules") or [])
        result, seen, fallback = [], set(), 1
        for module in modules:
            if not isinstance(module, dict) or module.get("type") != "MULTICOLUMN": continue
            for item in module.get("items") or []:
                if not isinstance(item, dict): continue
                onclick = item.get("onClick") if isinstance(item.get("onClick"), dict) else {}
                url = onclick.get("url")
                goods_no = self._extract_goods_no(url)
                if goods_no is None or goods_no in seen: continue
                seen.add(goods_no)
                rank = self._to_int(item.get("rank")) or fallback
                result.append({
                    "rank": rank, "goods_no": goods_no, "product_url": PRODUCT_BASE_URL.format(goods_no=goods_no),
                    "ranking_period": period, "ranking_gender": gender,
                    "ranking_category_depth1_code": category_code or None, "ranking_age_band": age_band,
                })
                fallback += 1
        return result

    def collect_archive_categories(self, *, year_month: str, gender_code: str) -> list[dict]:
        endpoint = self._require_endpoint(ARCHIVE_CATEGORIES_API_URL, "ARCHIVE_CATEGORIES_API_URL")
        body = self.client.get_json(endpoint, params={"yearMonth": year_month, "gf": gender_code})
        items = (body.get("data") or {}).get("list") or []
        return items if isinstance(items, list) else []

    def collect_archive(self, *, year_month: str, gender_code: str, category_code: str) -> list[dict]:
        endpoint = self._require_endpoint(ARCHIVE_GOODS_API_URL, "ARCHIVE_GOODS_API_URL")
        body = self.client.get_json(endpoint, params={"yearMonth": year_month, "gf": gender_code, "category": category_code})
        items = (body.get("data") or {}).get("list") or []
        result = []
        for item in items:
            if not isinstance(item, dict): continue
            goods_no, rank = self._to_int(item.get("goodsNo")), self._to_int(item.get("rank"))
            if goods_no is None or rank is None: continue
            result.append({
                "rank": rank, "goods_no": goods_no, "goods_name": item.get("goodsName"),
                "brand": item.get("brand"), "brand_name": item.get("brandName"), "image_url": item.get("imageUrl"),
                "is_permanent_stopped": bool(item.get("isPermanentStopped")),
                "product_url": PRODUCT_BASE_URL.format(goods_no=goods_no),
                "ranking_year_month": year_month, "ranking_gender": gender_code, "ranking_category_code": category_code,
            })
        return result

    @staticmethod
    def _extract_goods_no(url):
        if not url: return None
        import re
        m = re.search(r"/products/(\d+)", str(url))
        return int(m.group(1)) if m else None

    @staticmethod
    def _to_int(value):
        try: return int(float(value))
        except (TypeError, ValueError): return None
