from __future__ import annotations

import time

from analysis.ocr.aggregator import (
    AttributeEvidenceAggregator,
)
from analysis.ocr.block_classifier import (
    FashionInfoBlockClassifier,
)
from analysis.ocr.cleaner import (
    clean_ocr_text,
)
from analysis.ocr.section_ocr import (
    SectionOCR,
)
from analysis.ocr.text_merger import (
    OCRTextMerger,
)


class ProductDetailInfoPipeline:

    def __init__(
        self,
    ):
        self.ocr = SectionOCR()

        self.text_merger = (
            OCRTextMerger()
        )

        self.block_classifier = (
            FashionInfoBlockClassifier()
        )

        self.aggregator = (
            AttributeEvidenceAggregator()
        )

    def run(
        self,
        images: list[dict],
        min_ocr_confidence: float = 0.25,
    ) -> dict:

        total_start = (
            time.perf_counter()
        )

        image_results = []
        all_evidences = []

        for index, image_info in enumerate(
            images
        ):

            image_url = (
                image_info[
                    "image_url"
                ]
            )

            section_type = (
                image_info[
                    "section_type"
                ]
            )

            print(
                "\n"
                "========================================"
            )

            print(
                f"[Pipeline] "
                f"{index + 1}/{len(images)} "
                f"{section_type}"
            )

            print(
                "========================================"
            )

            ocr_result = (
                self.ocr.extract(
                    image_url=image_url,
                    section_type=(
                        section_type
                    ),
                    min_confidence=(
                        min_ocr_confidence
                    ),
                )
            )

            merged_result = (
                self.text_merger.merge(
                    ocr_result[
                        "blocks"
                    ]
                )
            )

            cleaned_text = (
                clean_ocr_text(
                    merged_result[
                        "text"
                    ]
                )
            )

            image_evidences = []

            for paragraph in (
                merged_result[
                    "paragraphs"
                ]
            ):

                text = (
                    paragraph.get(
                        "text",
                        "",
                    )
                    .strip()
                )

                if not text:
                    continue

                evidences = (
                    self.block_classifier.classify(
                        text=text,

                        ocr_confidence=(
                            paragraph.get(
                                "confidence",
                                1.0,
                            )
                        ),

                        source_image_index=(
                            index
                        ),
                    )
                )

                for evidence in evidences:

                    evidence_dict = (
                        evidence.to_dict()
                    )

                    image_evidences.append(
                        evidence_dict
                    )

                    all_evidences.append(
                        evidence_dict
                    )

            image_results.append(
                {
                    "image_index": index,

                    "image_url": (
                        image_url
                    ),

                    "section_type": (
                        section_type
                    ),

                    "raw_ocr_text": (
                        ocr_result[
                            "raw_text"
                        ]
                    ),

                    "merged_text": (
                        merged_result[
                            "text"
                        ]
                    ),

                    "cleaned_text": (
                        cleaned_text
                    ),

                    "paragraphs": (
                        merged_result[
                            "paragraphs"
                        ]
                    ),

                    "evidences": (
                        image_evidences
                    ),

                    "timing": (
                        ocr_result[
                            "timing"
                        ]
                    ),
                }
            )

        aggregated = (
            self.aggregator.aggregate(
                all_evidences
            )
        )

        total_elapsed = (
            time.perf_counter()
            - total_start
        )

        return {
            "image_count": len(
                images
            ),

            "evidence_count": sum(
                len(values)
                for values
                in aggregated.values()
            ),

            "images": (
                image_results
            ),

            "evidence": (
                aggregated
            ),

            "timing": {
                "total_ms": round(
                    total_elapsed
                    * 1000,
                    2,
                ),
            },
        }