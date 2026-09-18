from __future__ import annotations

from apps.core.models import CrawlTarget, Source

from .config import (
    CATEGORY_MAP,
    DEFAULT_ACTION_ID,
    DEFAULT_GROUPS,
    DEFAULT_LAYOUT_ID,
    DEFAULT_LIMITS,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
    DEFAULT_MODULE_SLOT_ID,
    DEFAULT_ORDER,
)


def upsert_zigzag_targets() -> list[CrawlTarget]:

    source = Source.objects.get(
        code__iexact="zigzag"
    )

    targets: list[CrawlTarget] = []

    for category_name, category_id in CATEGORY_MAP.items():

        target_url = (
            "https://zigzag.kr/pages/"
            "srp-clp-category"
            f"?category_id={category_id}"
        )

        target, created = (
            CrawlTarget.objects.update_or_create(
                source=source,

                # 이름 + source 조합으로 찾음
                name=f"zigzag [CNV>{category_name}]",

                defaults={
                    "target_type":
                        CrawlTarget.TargetType.RANKING,

                    "target_url":
                        target_url,

                    "collection_mode":
                        CrawlTarget.CollectionMode.LIVE,

                    "params": {
                        "category_id":
                            str(category_id),

                        "groups":
                            list(DEFAULT_GROUPS),

                        "limits":
                            dict(DEFAULT_LIMITS),

                        "order":
                            DEFAULT_ORDER,

                        "layout_id":
                            DEFAULT_LAYOUT_ID,

                        "action_id":
                            DEFAULT_ACTION_ID,

                        "module_slot_id":
                            DEFAULT_MODULE_SLOT_ID,

                        "min_delay":
                            DEFAULT_MIN_DELAY,

                        "max_delay":
                            DEFAULT_MAX_DELAY,
                    },

                    # 24시간
                    "interval_minutes": 1440,

                    "priority": 5,

                    "is_active": True,
                },
            )
        )

        targets.append(target)

        print(
            "CREATED" if created else "UPDATED",
            target.id,
            target.name,
            target.target_url,
        )

    return targets