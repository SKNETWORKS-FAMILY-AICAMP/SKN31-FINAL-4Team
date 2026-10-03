from __future__ import annotations

import argparse
import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

import django

django.setup()

from apps.core.models import ProductSource
from pipeline.step03_vision.pipeline import (
    ProductVisionPipeline,
)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "product_source_id",
        type=int,
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help=(
            "지정하지 않으면 predict-only. "
            "지정하면 HAS_STYLE 저장."
        ),
    )

    args = parser.parse_args()

    ps = ProductSource.objects.get(
        id=args.product_source_id
    )

    print("=" * 100)
    print("PRODUCT SOURCE")
    print("=" * 100)
    print("ID   :", ps.id)
    print(
        "NAME :",
        getattr(ps, "source_name", None),
    )
    print()

    pipeline = ProductVisionPipeline()

    result = pipeline.run(
        ps,
        save=args.save,
    )

    print("=" * 100)
    print("VISION RESULT")
    print("=" * 100)

    for key, value in result.items():
        print(
            f"{key.upper():20s}:",
            value,
        )


if __name__ == "__main__":
    main()
