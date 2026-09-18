from __future__ import annotations

from datetime import datetime
from typing import Any

from .service import ZigzagCnvService
from .storage import ZigzagSnapshotStorage


LAYOUT_ID = "301"

ACTION_ID = (
    "a061b462-576a-4991-9146-62b2166c132a"
)

MODULE_SLOT_ID = "s6C9txhfmfIi"

COLLECTION_POLICY = {
    "trend": 100,
    "style": 50,
    "tpo": 50,
}

def run_daily_light_snapshot() -> dict[str, Any]:
    started_at = datetime.now()

    service = ZigzagCnvService(
        layout_id=LAYOUT_ID,
        action_id=ACTION_ID,
        module_slot_id=MODULE_SLOT_ID,
    )

    storage = ZigzagSnapshotStorage()

    results: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "groups": {},
    }

    for group in [
        "trend",
        "style",
        "tpo",
    ]:
        print()
        print("#" * 80)
        print(f"[DAILY LIGHT] START GROUP={group}")
        print("#" * 80)

        group_results = service.collect_all_categories(
            group=group,
            mode="LIGHT",
        )

        output_path = storage.save_group_snapshot(
            group=group,
            results=group_results,
            observed_at=started_at,
        )

        results["groups"][group] = {
            "snapshot_count": len(group_results),
            "output_path": str(
                output_path.resolve()
            ),
        }

        print()
        print(
            f"[DAILY LIGHT] DONE "
            f"group={group} "
            f"snapshots={len(group_results)}"
        )

        print(
            f"[DAILY LIGHT] SAVED "
            f"{output_path.resolve()}"
        )

    finished_at = datetime.now()

    results["finished_at"] = (
        finished_at.isoformat()
    )

    results["duration_seconds"] = (
        finished_at - started_at
    ).total_seconds()

    print()
    print("=" * 80)
    print("DAILY LIGHT SNAPSHOT COMPLETE")
    print("=" * 80)

    for group, info in results["groups"].items():
        print(
            f"{group:10} "
            f"snapshots={info['snapshot_count']} "
            f"path={info['output_path']}"
        )

    print(
        "duration_seconds:",
        results["duration_seconds"],
    )

    return results


def run_daily_full_snapshot():

    service = ZigzagCnvService(
        layout_id=LAYOUT_ID,
        action_id=ACTION_ID,
        module_slot_id=MODULE_SLOT_ID,
    )

    storage = ZigzagSnapshotStorage()

    for group, limit in COLLECTION_POLICY.items():

        results = service.collect_all_categories(
            group=group,
            mode="FULL",
            limit=limit,
        )

        storage.save_group_snapshot(
            group=group,
            results=results,
        )




if __name__ == "__main__":
    run_daily_full_snapshot()