from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class ZigzagSnapshotStorage:

    def __init__(
        self,
        base_dir: str | Path = "data/zigzag_snapshots",
    ):
        self.base_dir = Path(base_dir)

    def save_group_snapshot(
        self,
        *,
        group: str,
        results: list[dict[str, Any]],
        observed_at: datetime | None = None,
    ) -> Path:

        observed_at = observed_at or datetime.now()

        date_str = observed_at.strftime("%Y-%m-%d")

        output_dir = self.base_dir / date_str
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = output_dir / f"{group}.json"

        payload = {
            "source": "zigzag",
            "group": group,
            "observed_at": observed_at.isoformat(),
            "snapshot_count": len(results),
            "snapshots": [],
        }

        for row in results:
            result_count = row.get("result_count")

            snapshot = {
                "category_id":
                    row.get("category_id"),

                "category_name":
                    row.get("category_name"),

                "tag_group":
                    row.get("tag_group"),

                "tag_attribute":
                    row.get("tag_attribute"),

                "tag_name":
                    row.get("tag_name"),

                "order":
                    row.get("order"),

                "result_count":
                    result_count,

                "is_capped":
                    (
                        result_count is not None
                        and result_count >= 10000
                    ),

                "collected_count":
                    row.get(
                        "collected_count",
                        0,
                    ),

                "products":
                    row.get(
                        "products",
                        [],
                    ),
            }

            payload["snapshots"].append(
                snapshot
            )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                payload,
                f,
                ensure_ascii=False,
                indent=2,
            )

        return output_path