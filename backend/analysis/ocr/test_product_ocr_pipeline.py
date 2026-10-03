from pprint import pprint

from collection.musinsa.detail_image_collector import (
    MusinsaDetailImageCollector,
)
from analysis.ocr.pipeline import (
    ProductDetailInfoPipeline,
)


PRODUCT_URL = (
    "https://www.musinsa.com/products/7011611"
)


def main():

    print(
        "\n"
        "========================================"
    )
    print("1. DETAIL IMAGE COLLECT")
    print(
        "========================================"
    )

    collector = (
        MusinsaDetailImageCollector(
            headless=True
        )
    )

    collector_result = (
        collector.collect(
            PRODUCT_URL
        )
    )

    print(
        "detail_image_count:",
        collector_result[
            "detail_image_count"
        ],
    )

    print(
        "ocr_image_count:",
        collector_result[
            "ocr_image_count"
        ],
    )

    print(
        "\n"
        "========================================"
    )
    print("OCR TARGETS")
    print(
        "========================================"
    )

    for image in collector_result[
        "ocr_images"
    ]:

        print(
            f"- [{image['section_type']}] "
            f"{image['decoded_url']}"
        )

    ocr_images = (
        collector_result[
            "ocr_images"
        ]
    )

    if not ocr_images:

        print(
            "\nOCR 대상 이미지가 없습니다."
        )

        return

    # --------------------------------------------------
    # OCR pipeline
    # --------------------------------------------------

    print(
        "\n"
        "========================================"
    )
    print("2. OCR PIPELINE")
    print(
        "========================================"
    )

    pipeline = (
        ProductDetailInfoPipeline()
    )

    result = pipeline.run(
        images=ocr_images,
        min_ocr_confidence=0.25,
    )

    # --------------------------------------------------
    # image별 OCR 결과
    # --------------------------------------------------

    print(
        "\n"
        "========================================"
    )
    print("3. IMAGE RESULTS")
    print(
        "========================================"
    )

    for image_result in result[
        "images"
    ]:

        print(
            "\n"
            "----------------------------------------"
        )

        print(
            "SECTION:",
            image_result[
                "section_type"
            ],
        )

        print(
            "URL:",
            image_result[
                "image_url"
            ],
        )

        print(
            "\n[RAW OCR]"
        )

        print(
            image_result[
                "raw_ocr_text"
            ]
        )

        print(
            "\n[MERGED TEXT]"
        )

        print(
            image_result[
                "merged_text"
            ]
        )

        print(
            "\n[CLEANED TEXT]"
        )

        print(
            image_result[
                "cleaned_text"
            ]
        )

        print(
            "\n[EVIDENCE]"
        )

        pprint(
            image_result[
                "evidences"
            ]
        )

        print(
            "\n[TIMING]"
        )

        pprint(
            image_result[
                "timing"
            ]
        )

    # --------------------------------------------------
    # 최종 aggregation
    # --------------------------------------------------

    print(
        "\n"
        "========================================"
    )
    print("4. FINAL ATTRIBUTE EVIDENCE")
    print(
        "========================================"
    )

    evidence = result[
        "evidence"
    ]

    if not evidence:

        print(
            "NO EVIDENCE"
        )

    else:

        for attribute, items in (
            evidence.items()
        ):

            print(
                f"\n[{attribute}]"
            )

            for item in items:

                print(
                    f"- text: "
                    f"{item['text']}"
                )

                print(
                    f"  matched_keywords: "
                    f"{item['matched_keywords']}"
                )

                print(
                    f"  score: "
                    f"{item['score']}"
                )

                print(
                    f"  image_index: "
                    f"{item['source_image_index']}"
                )

    # --------------------------------------------------
    # summary
    # --------------------------------------------------

    print(
        "\n"
        "========================================"
    )
    print("5. SUMMARY")
    print(
        "========================================"
    )

    print(
        "image_count:",
        result[
            "image_count"
        ],
    )

    print(
        "evidence_count:",
        result[
            "evidence_count"
        ],
    )

    print(
        "total_ms:",
        result[
            "timing"
        ][
            "total_ms"
        ],
    )

    print(
        "total_sec:",
        round(
            result[
                "timing"
            ][
                "total_ms"
            ]
            / 1000,
            2,
        ),
    )


if __name__ == "__main__":
    main()