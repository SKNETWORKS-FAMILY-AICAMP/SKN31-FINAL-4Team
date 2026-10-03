from __future__ import annotations

import csv
import json
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent

CSV_PATH = (
    THIS_DIR
    / "lora_pair_v11_en.csv"
)

OUTPUT_PATH = (
    THIS_DIR
    / "assets"
    / "style_prompts_en.json"
)


STYLE_LABELS = (
    "고프코어",
    "블록코어",
    "바이크코어",
    "놈코어",
    "애슬레저",
    "클래식",
    "아메카지",
    "그런지",
    "페미닌",
    "스트릿웨어",
)


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"CSV 파일 없음: {CSV_PATH}"
        )

    prompt_map = {}

    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError(
                "CSV header가 없습니다."
            )

        required = {
            "label",
            "text",
        }

        missing = (
            required
            - set(reader.fieldnames)
        )

        if missing:
            raise ValueError(
                "CSV column 누락: "
                + ", ".join(
                    sorted(missing)
                )
            )

        for row in reader:
            label = str(
                row.get("label")
                or ""
            ).strip()

            text = str(
                row.get("text")
                or ""
            ).strip()

            if (
                label in STYLE_LABELS
                and text
                and label not in prompt_map
            ):
                prompt_map[label] = text

    missing_labels = [
        label
        for label in STYLE_LABELS
        if label not in prompt_map
    ]

    if missing_labels:
        raise ValueError(
            "CSV에 없는 STYLE: "
            + ", ".join(
                missing_labels
            )
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            prompt_map,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 100)
    print("STYLE PROMPTS CREATED")
    print("=" * 100)
    print("CSV    :", CSV_PATH)
    print("OUTPUT :", OUTPUT_PATH)
    print("COUNT  :", len(prompt_map))
    print()

    for label in STYLE_LABELS:
        print(
            f"{label:<10} -> "
            f"{prompt_map[label]}"
        )


if __name__ == "__main__":
    main()