import re


class CandidateNormalizer:

    @staticmethod
    def normalize(
        text: str,
    ) -> str:

        text = text.lower().strip()

        text = text.replace(
            "_",
            " ",
        )

        text = text.replace(
            "-",
            " ",
        )

        text = re.sub(
            r"[^\w가-힣\s]",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()