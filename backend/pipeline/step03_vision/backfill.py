from __future__ import annotations

import argparse
import os
import time

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

import django

django.setup()

from django.db.models import Exists, OuterRef

from apps.core.models import (
    ProductSource,
    ProductTerm,
)

from pipeline.step03_vision.pipeline import (
    ProductVisionPipeline,
)


def format_score(value):
    if value is None:
        return "-"

    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes = seconds / 60

    if minutes < 60:
        return f"{minutes:.1f}m"

    hours = int(minutes // 60)
    remain_minutes = int(minutes % 60)

    return f"{hours}h {remain_minutes}m"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "FEEDIT STEP03 Vision Style Backfill"
        )
    )

    parser.add_argument(
        "--source",
        default=None,
        help=(
            "source code. "
            "예: musinsa, zigzag, ABLY, kream"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="실행할 최대 ProductSource 수",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "추론만 실행하고 "
            "ProductTerm은 저장하지 않음"
        ),
    )

    args = parser.parse_args()

    # =========================================================
    # STYLE ProductTerm 존재 여부
    # =========================================================

    style_terms = (
        ProductTerm.objects
        .filter(
            product_source_id=OuterRef("pk"),
            term__term_type="STYLE",
        )
    )

    # =========================================================
    # STEP03 대상
    #
    # 이미 STYLE이 하나라도 있는 상품은 처음부터 제외
    # =========================================================

    qs = (
        ProductSource.objects
        .annotate(
            has_style=Exists(style_terms)
        )
        .filter(
            has_style=False
        )
        .order_by("id")
    )

    if args.source:
        qs = qs.filter(
            source__code__iexact=args.source
        )

    if args.limit is not None:
        qs = qs[:args.limit]

    # ID + 상품명을 한 번에 가져옴.
    # 루프 안에서 상품명 때문에 DB를 다시 조회하지 않음.
    rows = list(
        qs.values(
            "id",
            "source_name",
        )
    )

    total = len(rows)

    # =========================================================
    # 시작 정보
    # =========================================================

    print()
    print("=" * 100)
    print("STEP03 VISION STYLE BACKFILL")
    print("=" * 100)

    print(
        "SOURCE     :",
        args.source or "ALL",
    )

    print(
        "MODE       :",
        "DRY-RUN"
        if args.dry_run
        else "SAVE",
    )

    print(
        "TOTAL      :",
        total,
    )

    print(
        "RULE       : "
        "STYLE ProductTerm이 없는 상품만 Vision 실행"
    )

    print(
        "SAVE       : "
        "Top1 STYLE만 HAS_STYLE ProductTerm으로 저장"
    )

    print("=" * 100)

    if total == 0:
        print()
        print("실행 대상이 없습니다.")
        return

    # =========================================================
    # Pipeline
    # =========================================================

    pipeline = ProductVisionPipeline()

    predicted = 0
    created = 0
    exists = 0
    skipped = 0
    failed = 0

    started = time.perf_counter()

    # =========================================================
    # Backfill
    # =========================================================

    for index, row in enumerate(
        rows,
        start=1,
    ):
        ps_id = row["id"]

        product_name = (
            row.get("source_name")
            or "-"
        )

        item_started = time.perf_counter()

        try:
            result = pipeline.run(
                ps_id,
                save=not args.dry_run,
            )

        except Exception as exc:
            result = {
                "status": "FAILED",
                "style": None,
                "score": None,
                "reason": (
                    f"{type(exc).__name__}: {exc}"
                ),
                "image_url": None,
            }

        status = (
            result.get("status")
            or "UNKNOWN"
        )

        style = (
            result.get("style")
            or "-"
        )

        score = result.get("score")

        reason = (
            result.get("reason")
            or "-"
        )

        image_url = (
            result.get("image_url")
            or "-"
        )

        # =====================================================
        # Counter
        # =====================================================

        if status == "PREDICTED":
            predicted += 1

        elif status == "CREATED":
            created += 1

        elif status == "EXISTS":
            exists += 1

        elif status == "FAILED":
            failed += 1

        else:
            skipped += 1

        # =====================================================
        # Time
        # =====================================================

        item_elapsed = (
            time.perf_counter()
            - item_started
        )

        elapsed = (
            time.perf_counter()
            - started
        )

        avg = elapsed / index

        remaining_seconds = (
            avg
            * (total - index)
        )

        percent = (
            index
            / total
            * 100
        )

        # =====================================================
        # Output
        # =====================================================

        print()
        print("-" * 100)

        print(
            f"[{index}/{total}] "
            f"{percent:6.2f}% "
            f"| PRODUCT_SOURCE={ps_id}"
        )

        print(
            f"NAME   : {product_name}"
        )

        print(
            f"STATUS : {status}"
        )

        print(
            f"STYLE  : {style}"
        )

        print(
            f"SCORE  : {format_score(score)}"
        )

        print(
            f"REASON : {reason}"
        )

        print(
            f"IMAGE  : {image_url}"
        )

        print(
            "TIME   : "
            f"{format_time(item_elapsed)} item "
            f"| {format_time(elapsed)} elapsed "
            f"| {format_time(remaining_seconds)} remaining"
        )

        print(
            "COUNT  : "
            f"PREDICTED={predicted} "
            f"| CREATED={created} "
            f"| EXISTS={exists} "
            f"| SKIPPED={skipped} "
            f"| FAILED={failed}"
        )

    # =========================================================
    # Final
    # =========================================================

    total_elapsed = (
        time.perf_counter()
        - started
    )

    print()
    print("=" * 100)
    print("STEP03 VISION BACKFILL COMPLETE")
    print("=" * 100)

    print(
        "SOURCE     :",
        args.source or "ALL",
    )

    print(
        "MODE       :",
        "DRY-RUN"
        if args.dry_run
        else "SAVE",
    )

    print(
        "TOTAL      :",
        total,
    )

    print(
        "PREDICTED  :",
        predicted,
    )

    print(
        "CREATED    :",
        created,
    )

    print(
        "EXISTS     :",
        exists,
    )

    print(
        "SKIPPED    :",
        skipped,
    )

    print(
        "FAILED     :",
        failed,
    )

    print(
        "ELAPSED    :",
        format_time(total_elapsed),
    )

    if total > 0:
        print(
            "AVG / ITEM :",
            format_time(
                total_elapsed / total
            ),
        )

    print("=" * 100)


if __name__ == "__main__":
    main()