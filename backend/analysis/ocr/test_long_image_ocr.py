from pprint import pprint

from analysis.ocr.long_image_ocr import (
    LongImageOCR,
)


IMAGE_URL = (
    "https://untapped.diskn.com/"
    "Untapped%20Studio/Musinsa/MUN123/"
    "16)%EB%94%94%ED%85%8C%EC%9D%BC.jpg"
)


def main():

    ocr = LongImageOCR(
        slice_height=4000,
        overlap=50,
        max_slices=4,
        min_text_density=0.004,
    )

    result = ocr.extract(
        image_url=IMAGE_URL,
        min_confidence=0.25,
    )

    print(
        "\n=============================="
    )
    print("SUMMARY")
    print(
        "=============================="
    )

    pprint(
        {
            "image_size": result[
                "image_size"
            ],
            "slice_count": result[
                "slice_count"
            ],
            "processed": result[
                "processed_slice_count"
            ],
            "skipped": result[
                "skipped_slice_count"
            ],
            "block_count": result[
                "block_count"
            ],
            "timing": result[
                "timing"
            ],
        }
    )

    print(
        "\n=============================="
    )
    print("RAW OCR")
    print(
        "=============================="
    )

    print(
        result["raw_text"]
    )


if __name__ == "__main__":
    main()