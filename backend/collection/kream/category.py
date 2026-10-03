from __future__ import annotations

from uuid import uuid4
from .constants import KREAM_API_BASE_URL, KREAM_BASE_URL


class KreamCategoryCollector:
    def __init__(self, client):
        self.client = client

    def collect_depth1(self, tab_id: int) -> dict:
        return self.client.get(
            f"{KREAM_API_BASE_URL}/api/p/category-screen/tabs/depth-1/{tab_id}",
            params={"request_key": str(uuid4())},
            referer=f"{KREAM_BASE_URL}/categories/{tab_id}/all",
        )

    def collect_depth2(self, tab_id: int, category_id: int | str = "all") -> dict:
        return self.client.get(
            f"{KREAM_API_BASE_URL}/api/p/category-screen/tabs/depth-2/{tab_id}/{category_id}",
            params={"request_key": str(uuid4())},
            referer=f"{KREAM_BASE_URL}/categories/{tab_id}/{category_id}",
        )

    def collect_category_metadata(self, tab_id: int, category_id: int | str = "all") -> dict:
        return {
            "depth1": self.collect_depth1(tab_id),
            "depth2": self.collect_depth2(tab_id, category_id),
        }
