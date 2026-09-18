from __future__ import annotations

from typing import Any

from .collector import ZigzagCnvCollector
from .config import (
    DEFAULT_ACTION_ID,
    DEFAULT_GROUPS,
    DEFAULT_LAYOUT_ID,
    DEFAULT_LIMITS,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
    DEFAULT_MODULE_SLOT_ID,
    DEFAULT_ORDER,
    GROUP_CONFIG,
)


class ZigzagCnvService:
    def __init__(
        self,
        *,
        layout_id: str = DEFAULT_LAYOUT_ID,
        action_id: str = DEFAULT_ACTION_ID,
        module_slot_id: str = DEFAULT_MODULE_SLOT_ID,
        min_delay: float = DEFAULT_MIN_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
    ):
        self.layout_id = str(layout_id)
        self.action_id = str(action_id)
        self.module_slot_id = str(module_slot_id)

        self.collector = ZigzagCnvCollector(
            min_delay=min_delay,
            max_delay=max_delay,
        )

    def close(self) -> None:
        self.collector.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def collect_tag(
        self,
        *,
        category_id: str,
        tag_name: str,
        attribute: str,
        group_name: str,
        limit: int = 100,
        order: str = DEFAULT_ORDER,
    ) -> dict[str, Any]:
        tag_filter = self.collector.make_combined_tag(
            tag_name,
            attribute=attribute,
            name=group_name,
        )

        snapshot = self.collector.collect_snapshot(
            category_id=str(category_id),
            layout_id=self.layout_id,
            action_id=self.action_id,
            module_slot_id=self.module_slot_id,
            order=order,
            filters=[tag_filter],
            limit=int(limit),
        )

        return {
            "category_id": str(category_id),
            "tag_group": group_name,
            "tag_attribute": attribute,
            "tag_name": tag_name,
            "order": order,
            "result_count": snapshot["result_count"],
            "is_count_capped": snapshot[
                "is_count_capped"
            ],
            "collected_count": snapshot[
                "collected_count"
            ],
            "products": snapshot["products"],
        }

    def collect_group(
        self,
        *,
        category_id: str,
        group: str,
        limit: int | None = None,
        order: str = DEFAULT_ORDER,
    ) -> list[dict[str, Any]]:
        group = str(group).lower().strip()

        if group not in GROUP_CONFIG:
            raise ValueError(
                f"지원하지 않는 Zigzag group: {group}"
            )

        config = GROUP_CONFIG[group]

        resolved_limit = (
            int(limit)
            if limit is not None
            else int(config["default_limit"])
        )

        results: list[dict[str, Any]] = []

        for tag_name in config["tags"]:
            print()
            print("=" * 70)
            print(
                f"[ZIGZAG:{group.upper()}] "
                f"category={category_id} "
                f"tag={tag_name}"
            )
            print("=" * 70)

            row = self.collect_tag(
                category_id=str(category_id),
                tag_name=tag_name,
                attribute=config["attribute"],
                group_name=config["label"],
                limit=resolved_limit,
                order=order,
            )

            results.append(row)

            print(
                f"[DONE] {tag_name} "
                f"result={row['result_count']} "
                f"products={row['collected_count']}"
            )

        return results

    def collect_category(
        self,
        *,
        category_id: str,
        groups: list[str] | None = None,
        limits: dict[str, int] | None = None,
        order: str = DEFAULT_ORDER,
    ) -> dict[str, Any]:
        groups = [
            str(group).lower().strip()
            for group in (groups or DEFAULT_GROUPS)
        ]

        limits = {
            **DEFAULT_LIMITS,
            **(limits or {}),
        }

        group_results: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        for group in groups:
            if group not in GROUP_CONFIG:
                raise ValueError(
                    f"지원하지 않는 Zigzag group: {group}"
                )

            group_results[group] = self.collect_group(
                category_id=str(category_id),
                group=group,
                limit=int(limits[group]),
                order=order,
            )

        return {
            "category_id": str(category_id),
            "order": order,
            "groups": group_results,
        }
