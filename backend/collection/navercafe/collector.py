from __future__ import annotations

from .client import NaverCafeClient
from .constants import (
    CAFE_ID,
    TARGET_BOARDS,
)


class NaverCafeCollector:

    def __init__(
        self,
        client: NaverCafeClient,
    ):
        self.client = client

    def collect_menus(self) -> dict:
        return self.client.get_menus(
            cafe_id=CAFE_ID,
        )

    def collect_articles(
        self,
        board_type: str,
        *,
        page: int = 1,
        page_size: int = 15,
    ) -> dict:

        board = TARGET_BOARDS[board_type]

        return self.client.get_articles(
            cafe_id=CAFE_ID,
            menu_id=board["menu_id"],
            page=page,
            page_size=page_size,
        )