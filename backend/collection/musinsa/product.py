from __future__ import annotations

from .client import MusinsaClient
from .constants import (
    LIKE_API_URL, LIKE_BATCH_SIZE, MUSINSA_BASE_URL, OPTIONS_API_URL, PRODUCT_BASE_URL,
    STAT_API_URL, TAG_API_URL,
)
from .exceptions import MusinsaCollectError
from .parser import MusinsaParser


class MusinsaProductCollector:
    def __init__(self, client: MusinsaClient):
        self.client = client

    def collect_detail(self, product_url: str) -> dict:
        response = self.client.get_html(product_url)
        parsed = MusinsaParser.parse_product(response.text)
        parsed.setdefault("meta", {}).update({
            "request_url": product_url,
            "final_url": response.url,
            "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type"),
        })
        return parsed

    def collect_tags(self, goods_no: int) -> list[str] | None:
        body = self.client.get_json(TAG_API_URL.format(goods_no=goods_no), headers={"Referer": PRODUCT_BASE_URL.format(goods_no=goods_no)})
        tags = (body.get("data") or {}).get("tags")
        if not isinstance(tags, list): return None
        result = [str(v).strip() for v in tags if v is not None and str(v).strip()]
        return list(dict.fromkeys(result)) or None

    def collect_stat(self, goods_no: int) -> dict:
        body = self.client.get_json(STAT_API_URL.format(goods_no=goods_no), headers={"Referer": PRODUCT_BASE_URL.format(goods_no=goods_no)})
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        return {"view_count": self._to_int(data.get("pageViewTotal")), "sales_count": self._to_int(data.get("purchaseTotal"))}

    def collect_options(self, goods_no: int, *, goods_sale_type: str = "SALE", opt_kind_cd: str = "CLOTHES") -> dict:
        body = self.client.get_json(OPTIONS_API_URL.format(goods_no=goods_no), params={"goodsSaleType": goods_sale_type, "optKindCd": opt_kind_cd}, headers={"Referer": PRODUCT_BASE_URL.format(goods_no=goods_no)})
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        groups = []
        for group in data.get("basic") or []:
            if not isinstance(group, dict): continue
            values = []
            for value in group.get("optionValues") or []:
                if not isinstance(value, dict) or value.get("isDeleted"): continue
                values.append({
                    "value_no": value.get("no"), "name": value.get("name"), "code": value.get("code"),
                    "sequence": value.get("sequence"), "standard_option_value_no": value.get("standardOptionValueNo"),
                    "color": value.get("color"), "image_url": value.get("imageUrl") or None,
                })
            groups.append({
                "option_no": group.get("no"), "name": group.get("name"), "display_type": group.get("displayType"),
                "standard_option_no": group.get("standardOptionNo"), "sequence": group.get("sequence"), "values": values,
            })
        items = []
        for item in data.get("optionItems") or []:
            if not isinstance(item, dict) or item.get("isDeleted"): continue
            items.append({
                "option_item_no": item.get("no"), "managed_code": item.get("managedCode"),
                "price_delta": self._to_int(item.get("price")) or 0, "activated": bool(item.get("activated")),
                "option_value_nos": item.get("optionValueNos") or [],
            })
        return {"groups": groups, "items": items}

    def collect_like_counts(self, goods_nos: list[int]) -> dict[int, int | None]:
        goods_nos = list(dict.fromkeys(v for v in (self._to_int(x) for x in goods_nos) if v is not None))
        result = {}
        for start in range(0, len(goods_nos), LIKE_BATCH_SIZE):
            batch = goods_nos[start:start + LIKE_BATCH_SIZE]
            body = self.client.post_json(LIKE_API_URL, json={"relationIds": batch}, headers={"Origin": MUSINSA_BASE_URL, "Referer": f"{MUSINSA_BASE_URL}/"})
            items = ((body.get("data") or {}).get("contents") or {}).get("items") or []
            for item in items:
                if not isinstance(item, dict): continue
                relation_id = self._to_int(item.get("relationId"))
                if relation_id is not None: result[relation_id] = self._to_int(item.get("count"))
        return result

    @staticmethod
    def _to_int(value):
        if value is None or isinstance(value, bool): return None
        try: return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError): return None
