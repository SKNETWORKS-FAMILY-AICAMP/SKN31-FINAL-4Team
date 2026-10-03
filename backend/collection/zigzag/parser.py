from __future__ import annotations

import html as html_lib
import json
import re
from urllib.parse import urlparse


class ZigzagParser:
    """Zigzag HTML/JSON parser. HTTP/ORM/S3 책임 없음."""

    @classmethod
    def parse_product_detail_html(
        cls,
        page_html: str,
        *,
        source_url: str | None = None,
        fallback_shop_id: str | None = None,
        fallback_shop_name: str | None = None,
    ) -> dict:
        """
        상품 상세 HTML에서 스토어 식별정보를 최대한 복구한다.
        가장 중요한 값은 main_domain이다.
        """
        page_html = page_html or ""
        info = cls._extract_json_object_after_key(page_html, "shop_information") or {}

        main_domain = cls.clean_text(
            info.get("main_domain")
            or info.get("shop_domain")
            or info.get("domain")
            or cls._regex_first(page_html, [
                r'"main_domain"\s*:\s*"([^"\\]+)"',
                r'\\"main_domain\\"\s*:\s*\\"([^"\\]+)\\"',
                r'"shop_domain"\s*:\s*"([^"\\]+)"',
                r'\\"shop_domain\\"\s*:\s*\\"([^"\\]+)\\"',
            ])
        )

        shop_id = cls.clean_text(
            info.get("id")
            or info.get("shop_id")
            or fallback_shop_id
        )
        name = cls.clean_text(
            info.get("name")
            or info.get("shop_name")
            or fallback_shop_name
        )

        profile_url = (
            f"https://zigzag.kr/{main_domain}"
            if main_domain
            else None
        )

        return {
            "source_url": source_url,
            "store": {
                "source_brand_id": shop_id,
                "name": name,
                "main_domain": main_domain,
                "source_profile_url": profile_url,
                "image_url": cls.clean_text(
                    info.get("typical_image_url")
                ),
                "description": cls.clean_text(
                    info.get("comment")
                ),
                "target_age": [
                    cls.clean_text(x.get("value") or x.get("name") or x.get("id"))
                    if isinstance(x, dict) else cls.clean_text(x)
                    for x in (info.get("age_list") or [])
                    if (cls.clean_text(x.get("value") or x.get("name") or x.get("id")) if isinstance(x, dict) else cls.clean_text(x))
                ] or None,
                "style_list": [
                    cls.clean_text(x.get("value")) if isinstance(x, dict) else cls.clean_text(x)
                    for x in (info.get("style_list") or [])
                    if (cls.clean_text(x.get("value")) if isinstance(x, dict) else cls.clean_text(x))
                ],
                "bookmark_count": cls.to_int(
                    info.get("bookmark_count")
                ),
            },
        }

    @classmethod
    def parse_store_html(cls, page_html: str, *, source_url: str) -> dict:
        info = cls._extract_json_object_after_key(page_html, "shop_information") or {}
        main_domain = cls.clean_text(info.get("main_domain"))
        styles = []
        for item in info.get("style_list") or []:
            value = cls.clean_text(item.get("value") if isinstance(item, dict) else item)
            if value and value not in styles:
                styles.append(value)
        ages = []
        for item in info.get("age_list") or []:
            if isinstance(item, dict):
                item = item.get("value") or item.get("name") or item.get("id")
            value = cls.clean_text(item)
            if value and value not in ages:
                ages.append(value)
        seller_badges = []
        for badge in info.get("seller_badge") or []:
            if not isinstance(badge, dict):
                continue
            obj = badge.get("text") or {}
            value = cls.clean_text(obj.get("text") if isinstance(obj, dict) else obj)
            if value:
                seller_badges.append(value)
        return {
            "source_brand_id": cls.clean_text(info.get("id") or info.get("shop_id")),
            "name": cls.clean_text(info.get("name")),
            "english_name": None,
            "main_domain": main_domain,
            "image_url": cls.clean_text(info.get("typical_image_url")),
            "description": cls.clean_text(info.get("comment")),
            "target_age": ages or None,
            "style_list": styles,
            "source_profile_url": f"https://zigzag.kr/{main_domain}" if main_domain else source_url,
            "bookmark_count": cls.to_int(info.get("bookmark_count")),
            "seller_badges": seller_badges,
        }

    @staticmethod
    def _regex_first(text: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.I | re.S)
            if m:
                return html_lib.unescape(m.group(1))
        return None

    @classmethod
    def _extract_json_object_after_key(cls, text: str, key: str) -> dict | None:
        if not text:
            return None
        patterns = [f'"{key}"', f'\\"{key}\\"']
        for marker in patterns:
            start = text.find(marker)
            if start < 0:
                continue
            colon = text.find(":", start + len(marker))
            if colon < 0:
                continue
            brace = text.find("{", colon)
            if brace < 0:
                continue
            # 먼저 일반 JSON decoder
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[brace:])
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
            # escaped JSON fallback
            chunk = text[brace:]
            try:
                unescaped = bytes(chunk, "utf-8").decode("unicode_escape")
                obj, _ = json.JSONDecoder().raw_decode(unescaped)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
        return None

    @staticmethod
    def clean_text(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def to_int(value) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def to_float(value) -> float | None:
        if value is None:
            return None
        try:
            return round(float(str(value).replace(",", "").replace("%", "").strip()), 4)
        except (TypeError, ValueError):
            return None
