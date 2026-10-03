from __future__ import annotations

import re
from dataclasses import dataclass, field

from kiwipiepy import Kiwi


@dataclass
class TextSegment:
    index: int
    text: str
    source_text: str
    segment_type: str = "TEXT"


@dataclass
class TextPreprocessResult:
    raw_text: str
    clean_text: str
    segments: list[TextSegment] = field(
        default_factory=list
    )
    removed_noise: list[str] = field(
        default_factory=list
    )


class KiwiTextPreprocessor:
    """
    FEEDIT Text STEP02 전처리기.

    목적:
    - 원본 TextDocument.body는 변경하지 않는다.
    - 분석에 불필요한 웹/메타 노이즈를 제거한다.
    - 패션 의미를 가진 텍스트는 최대한 보존한다.
    - Kiwi를 이용해 한국어 문장 경계를 보조한다.

    제거 대상:
    - URL
    - 이메일
    - 독립적인 timestamp
    - 가격/할인 정보만 있는 line
    - YouTube description boilerplate
    - 장식 문자만 있는 line

    보존 대상:
    - 상품명
    - 패션 설명
    - 해시태그 내용
    - 브랜드명
    - 스타일/아이템/소재/색상 표현
    """

    URL_RE = re.compile(
        r"(?:https?://|www\.)\S+",
        re.IGNORECASE,
    )

    EMAIL_RE = re.compile(
        r"\b[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+"
        r"\.[A-Za-z]{2,}\b"
    )

    TIMESTAMP_PREFIX_RE = re.compile(
        r"^\s*"
        r"(?:"
        r"\d{1,2}:"
        r"(?:\d{1,2}:)?"
        r"\d{2}"
        r")"
        r"\s*"
    )

    PRICE_ONLY_RE = re.compile(
        r"^\s*"
        r"[\d,.]+\s*원"
        r"(?:"
        r"\s*(?:→|->|-)\s*"
        r"[\d,.]+\s*원"
        r")?"
        r"(?:\s*\(\s*\d+\s*%\s*할인\s*\))?"
        r"\s*$",
        re.IGNORECASE,
    )

    STRUCTURE_ONLY_RE = re.compile(
        r"^\s*"
        r"(?:"
        r"category\s*\d+"
        r"|day\s*\d+"
        r"|intro"
        r"|event"
        r")"
        r"\s*[!★☆✦✨._\-]*"
        r"\s*$",
        re.IGNORECASE,
    )

    DECORATION_ONLY_RE = re.compile(
        r"^[\s\-_=+*★☆✦✨♡♥❤"
        r"●○■□▪▫◆◇▶▷"
        r"▬─━└┗┏┓┃│"
        r"]+$"
    )

    WHITESPACE_RE = re.compile(
        r"[ \t]+"
    )

    MULTI_NEWLINE_RE = re.compile(
        r"\n{3,}"
    )
    CONTACT_ONLY_RE = re.compile(
    r"^[✔✓☑\s]*"
    r"(?:contact|insta|instagram|business|business\s*mail)"
    r"\s*[:：]?\s*$",
    re.IGNORECASE,
    )

    SIZE_META_RE = re.compile(
        r"^[✔✓☑\s]*"
        r"(?:size|신체정보)"
        r"\b.*$",
        re.IGNORECASE,
    )

    STRUCTURE_ONLY_RE = re.compile(
        r"^\s*"
        r"[★☆✦✨🎁📖\s]*"
        r"(?:"
        r"category\s*\d+"
        r"|day\s*\d+"
        r"|intro"
        r"|event"
        r"|timeline"
        r"|타임라인"
        r")"
        r"[!★☆✦✨🎁📖._\-\s]*"
        r"$",
        re.IGNORECASE,
    )

    EVENT_META_RE = re.compile(
        r"(?:"
        r"참여\s*기간"
        r"|당첨자\s*발표"
        r"|당첨\s*발표"
        r"|고정댓글"
        r"|무효처리"
        r"|추첨을\s*통해"
        r"|선물로\s*드립니다"
        r")",
        re.IGNORECASE,
    )

    EMOJI_ONLY_RE = re.compile(
        r"^[^\w가-힣A-Za-z0-9]+$"
    )

    BOILERPLATE_PATTERNS = (
        re.compile(
            r"비즈니스\s*(?:문의|메일)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:광고|협찬|제휴)\s*문의",
            re.IGNORECASE,
        ),
        re.compile(
            r"유료\s*광고를?\s*"
            r"(?:포함|포함하고)",
            re.IGNORECASE,
        ),
        re.compile(
            r"큐레이션\s*활동으로\s*"
            r"수수료",
            re.IGNORECASE,
        ),
        re.compile(
            r"contact\s*[:：]?",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        kiwi: Kiwi | None = None,
    ):
        self.kiwi = (
            kiwi
            if kiwi is not None
            else Kiwi()
        )

    def process(
        self,
        text: str | None,
        *,
        document_type: str | None = None,
    ) -> TextPreprocessResult:
        raw_text = str(text or "")

        if not raw_text.strip():
            return TextPreprocessResult(
                raw_text=raw_text,
                clean_text="",
            )

        document_type = str(
            document_type or ""
        ).upper()

        if document_type == "DESCRIPTION":
            return self._process_description(
                raw_text
            )

        return self._process_natural_text(
            raw_text
        )

    def _process_description(
        self,
        raw_text: str,
    ) -> TextPreprocessResult:
        removed_noise: list[str] = []
        cleaned_lines: list[str] = []

        normalized = raw_text.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        ).replace(
            "¶",
            "\n",
        )

        for raw_line in normalized.split("\n"):
            line = raw_line.strip()

            if not line:
                continue

            cleaned = self._clean_line(
                line,
                removed_noise=removed_noise,
            )

            if not cleaned:
                continue

            cleaned_lines.append(cleaned)

        clean_text = "\n".join(
            cleaned_lines
        )

        segments = self._build_description_segments(
            cleaned_lines
        )

        return TextPreprocessResult(
            raw_text=raw_text,
            clean_text=clean_text,
            segments=segments,
            removed_noise=removed_noise,
        )

    def _process_natural_text(
        self,
        raw_text: str,
    ) -> TextPreprocessResult:
        removed_noise: list[str] = []

        text = raw_text.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        ).replace(
            "¶",
            "\n",
        )

        text = self._remove_web_noise(
            text,
            removed_noise=removed_noise,
        )

        text = self.WHITESPACE_RE.sub(
            " ",
            text,
        )

        text = self.MULTI_NEWLINE_RE.sub(
            "\n\n",
            text,
        )

        text = text.strip()

        segments = self._split_sentences(
            text
        )

        return TextPreprocessResult(
            raw_text=raw_text,
            clean_text=text,
            segments=segments,
            removed_noise=removed_noise,
        )
        
    def _clean_line(
        self,
        line: str,
        *,
        removed_noise: list[str],
    ) -> str | None:
        original = line

        if self.DECORATION_ONLY_RE.fullmatch(line):
            removed_noise.append(original)
            return None

        if self.CONTACT_ONLY_RE.fullmatch(line):
            removed_noise.append(original)
            return None

        if self.SIZE_META_RE.fullmatch(line):
            removed_noise.append(original)
            return None

        if self.STRUCTURE_ONLY_RE.fullmatch(line):
            removed_noise.append(original)
            return None

        if self.EVENT_META_RE.search(line):
            removed_noise.append(original)
            return None

        if self.PRICE_ONLY_RE.fullmatch(line):
            removed_noise.append(original)
            return None

        if self._is_boilerplate(line):
            removed_noise.append(original)
            return None

        line = self._remove_web_noise(
            line,
            removed_noise=removed_noise,
        )

        line = self.TIMESTAMP_PREFIX_RE.sub(
            "",
            line,
        )

        line = self.WHITESPACE_RE.sub(
            " ",
            line,
        ).strip()

        if not line:
            if original not in removed_noise:
                removed_noise.append(original)

            return None

        return line

    def _remove_web_noise(
        self,
        text: str,
        *,
        removed_noise: list[str],
    ) -> str:
        def remove_url(
            match: re.Match,
        ) -> str:
            value = match.group(0)
            removed_noise.append(value)
            return " "

        def remove_email(
            match: re.Match,
        ) -> str:
            value = match.group(0)
            removed_noise.append(value)
            return " "

        text = self.URL_RE.sub(
            remove_url,
            text,
        )

        text = self.EMAIL_RE.sub(
            remove_email,
            text,
        )

        return text

    def _build_description_segments(
        self,
        lines: list[str],
    ) -> list[TextSegment]:
        segments: list[TextSegment] = []

        index = 0

        for line in lines:
            sentence_segments = (
                self._split_sentences(
                    line,
                    start_index=index,
                )
            )

            segments.extend(
                sentence_segments
            )

            index += len(
                sentence_segments
            )

        return segments

    def _split_sentences(
        self,
        text: str,
        *,
        start_index: int = 0,
    ) -> list[TextSegment]:
        if not text.strip():
            return []

        try:
            sentences = (
                self.kiwi.split_into_sents(
                    text
                )
            )
        except Exception:
            sentences = []

        segments: list[TextSegment] = []

        if not sentences:
            return [
                TextSegment(
                    index=start_index,
                    text=text.strip(),
                    source_text=text.strip(),
                )
            ]

        for sentence in sentences:
            sentence_text = str(
                sentence.text
            ).strip()

            if not sentence_text:
                continue

            if self.EMOJI_ONLY_RE.fullmatch(
                sentence_text
            ):
                continue


            segments.append(
                TextSegment(
                    index=(
                        start_index
                        + len(segments)
                    ),
                    text=sentence_text,
                    source_text=sentence_text,
                )
            )

        return segments

    def _is_boilerplate(
        self,
        text: str,
    ) -> bool:
        return any(
            pattern.search(text)
            for pattern
            in self.BOILERPLATE_PATTERNS
        )