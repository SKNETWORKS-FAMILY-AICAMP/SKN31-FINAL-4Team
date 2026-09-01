# backend/collection/musinsa/test_detail_image_collector.py

from collection.musinsa.detail_image_collector import (
    MusinsaDetailImageCollector,
)


PRODUCT_URL = (
    "https://www.musinsa.com/products/6213122"
)


def main():

    collector = (
        MusinsaDetailImageCollector(
            headless=True
        )
    )

    result = collector.collect(
        PRODUCT_URL
    )

    print(
        "\n============================"
    )
    print("SUMMARY")
    print(
        "============================"
    )

    print(
        "DETAIL:",
        result["detail_image_count"],
    )

    print(
        "OCR:",
        result["ocr_image_count"],
    )

    print(
        "\n============================"
    )
    print("DETAIL IMAGES")
    print(
        "============================"
    )

    for image in result[
        "detail_images"
    ]:

        print()

        print(
            "PRIORITY:",
            image["ocr_priority"]
        )

        print(
            "OCR:",
            image["ocr_required"]
        )

        print(
            "SIZE:",
            image["width"],
            "x",
            image["height"],
        )

        print(
            "URL:",
            image["decoded_url"]
        )


if __name__ == "__main__":
    main()