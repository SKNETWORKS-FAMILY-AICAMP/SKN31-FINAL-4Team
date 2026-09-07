from __future__ import annotations


class OCRTextMerger:

    def __init__(
        self,
        line_y_tolerance: float = 25,
        paragraph_gap: float = 80,
    ):
        self.line_y_tolerance = (
            line_y_tolerance
        )

        self.paragraph_gap = (
            paragraph_gap
        )

    def _group_lines(
        self,
        blocks: list[dict],
    ) -> list[list[dict]]:

        if not blocks:
            return []

        sorted_blocks = sorted(
            blocks,
            key=lambda item: (
                item["center"]["y"],
                item["center"]["x"],
            ),
        )

        lines = []

        for block in sorted_blocks:

            matched = None

            for line in lines[-5:]:

                average_y = sum(
                    item[
                        "center"
                    ][
                        "y"
                    ]
                    for item
                    in line
                ) / len(line)

                if (
                    abs(
                        block[
                            "center"
                        ][
                            "y"
                        ]
                        - average_y
                    )
                    <= self.line_y_tolerance
                ):
                    matched = line
                    break

            if matched is None:
                lines.append(
                    [block]
                )
            else:
                matched.append(
                    block
                )

        return lines

    def _merge_line(
        self,
        line: list[dict],
    ) -> dict:

        line = sorted(
            line,
            key=lambda item: (
                item[
                    "bbox"
                ][
                    "x_min"
                ]
            ),
        )

        text = " ".join(
            block["text"]
            for block in line
        )

        confidence = sum(
            block["confidence"]
            for block in line
        ) / len(line)

        return {
            "text": text,

            "confidence": round(
                confidence,
                4,
            ),

            "bbox": {
                "x_min": min(
                    block[
                        "bbox"
                    ][
                        "x_min"
                    ]
                    for block in line
                ),

                "x_max": max(
                    block[
                        "bbox"
                    ][
                        "x_max"
                    ]
                    for block in line
                ),

                "y_min": min(
                    block[
                        "bbox"
                    ][
                        "y_min"
                    ]
                    for block in line
                ),

                "y_max": max(
                    block[
                        "bbox"
                    ][
                        "y_max"
                    ]
                    for block in line
                ),
            },
        }

    def _merge_paragraphs(
        self,
        lines: list[dict],
    ) -> list[dict]:

        if not lines:
            return []

        lines = sorted(
            lines,
            key=lambda item: (
                item[
                    "bbox"
                ][
                    "y_min"
                ]
            ),
        )

        paragraphs = []

        current = [
            lines[0]
        ]

        for line in lines[1:]:

            previous = (
                current[-1]
            )

            gap = (
                line[
                    "bbox"
                ][
                    "y_min"
                ]
                - previous[
                    "bbox"
                ][
                    "y_max"
                ]
            )

            if (
                gap
                <= self.paragraph_gap
            ):
                current.append(
                    line
                )
            else:

                paragraphs.append(
                    self._make_paragraph(
                        current
                    )
                )

                current = [
                    line
                ]

        if current:

            paragraphs.append(
                self._make_paragraph(
                    current
                )
            )

        return paragraphs

    def _make_paragraph(
        self,
        lines: list[dict],
    ) -> dict:

        text = " ".join(
            line["text"]
            for line in lines
        )

        confidence = sum(
            line["confidence"]
            for line in lines
        ) / len(lines)

        return {
            "text": text,

            "confidence": round(
                confidence,
                4,
            ),

            "line_count": len(
                lines
            ),
        }

    def merge(
        self,
        blocks: list[dict],
    ) -> dict:

        grouped = self._group_lines(
            blocks
        )

        merged_lines = [
            self._merge_line(
                line
            )
            for line in grouped
        ]

        paragraphs = (
            self._merge_paragraphs(
                merged_lines
            )
        )

        text = "\n".join(
            paragraph["text"]
            for paragraph
            in paragraphs
        )

        return {
            "lines": merged_lines,
            "paragraphs": paragraphs,
            "text": text,
        }