from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

_MODEL_BUNDLE_CACHE: dict[str, dict] = {}


def _load_model_bundle(model_path: Path) -> dict:
    key = str(model_path.resolve())
    if key not in _MODEL_BUNDLE_CACHE:
        _MODEL_BUNDLE_CACHE[key] = joblib.load(model_path)
    return _MODEL_BUNDLE_CACHE[key]


@dataclass(frozen=True)
class NoisePrediction:
    text: str
    label: str
    margin: float
    action: str
    protected: bool = False
    source: str = "classifier"

    @property
    def should_remove(self) -> bool:
        return self.action == "REMOVE"


@dataclass(frozen=True)
class NoiseDecision:
    text: str
    action: str
    reason: str
    source: str
    start: int | None = None
    end: int | None = None
    term_id: int | None = None
    term_type: str | None = None
    preserve_as_product_term: bool = False
    margin: float = 0.0

    @property
    def should_remove(self) -> bool:
        return self.action == "REMOVE"


class ProductNoiseClassifier:
    """Unknown residual 전용 fallback classifier."""

    PROTECTED_TERMS = {"made", "자체제작"}
    TECHNICAL_NOISE_TERMS = {"ver", "ver.", "version", "버전"}
    MARKETING_EXACT = {
        "실물핏극찬", "핏극찬", "예쁨보장", "핏보장", "퀄리티보장",
        "후기극찬", "후기검증", "문의폭주", "주문폭주", "인기폭주",
        "재구매폭주", "허얇골넓", "허얇골넓치트키", "가성비갑",
        "필수템", "소장각", "인생템", "교복템", "스판최고",
    }
    SALES_RE = re.compile(
        r"^(?:누적\s*)?\d+(?:\.\d+)?\s*(?:만|천)?\s*장(?:\s*(?:판매|돌파))?$",
        re.IGNORECASE,
    )
    STRONG_MARKETING_RE = re.compile(
        r"(?:실물핏?극찬|핏극찬|예쁨보장|핏보장|퀄리티보장|실물보장|"
        r"문의폭주|주문폭주|인기폭주|재구매폭주|허얇골넓(?:치트키)?|"
        r"가성비갑|후기(?:극찬|검증)|\d+(?:\.\d+)?\s*(?:만|천)?\s*장(?:판매|돌파)?|1등)",
        re.IGNORECASE,
    )

    def __init__(self, model_path: str | Path | None = None):
        if model_path is None:
            model_path = (
                Path(__file__).resolve().parents[1]
                / "noise_classifier" / "models" / "marketing_classifier_v1.joblib"
            )
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Noise classifier model이 없습니다: {self.model_path}")
        bundle = _load_model_bundle(self.model_path)
        self.version = int(bundle.get("version", 1))
        self.model = bundle["model"]
        self.auto_remove_margin = float(bundle.get("auto_remove_margin", 1.0))
        self.review_margin = float(bundle.get("review_margin", 0.25))
        bundle_protected = {
            str(v).strip().casefold() for v in bundle.get("protected_terms", [])
            if str(v or "").strip()
        }
        self.protected_terms = {v.casefold() for v in self.PROTECTED_TERMS} | bundle_protected

    def predict(self, text: str) -> NoisePrediction:
        result = self.predict_many([text])
        return result[0] if result else NoisePrediction("", "KEEP", 0.0, "KEEP", source="empty")

    def predict_many(self, values: list[str]) -> list[NoisePrediction]:
        if not values:
            return []
        results: list[NoisePrediction | None] = [None] * len(values)
        ml_indices: list[int] = []
        ml_values: list[str] = []
        technical = {v.casefold() for v in self.TECHNICAL_NOISE_TERMS}
        marketing = {v.casefold() for v in self.MARKETING_EXACT}

        for i, value in enumerate(values):
            raw = str(value or "").strip()
            key = raw.casefold()
            if not raw:
                results[i] = NoisePrediction(raw, "KEEP", 0.0, "KEEP", source="empty")
            elif key in self.protected_terms:
                results[i] = NoisePrediction(raw, "KEEP", 999.0, "KEEP", True, "protected")
            elif key in technical:
                results[i] = NoisePrediction(raw, "NOISE", 999.0, "REMOVE", source="technical_rule")
            elif key in marketing or self.SALES_RE.fullmatch(raw) or self.STRONG_MARKETING_RE.search(raw):
                results[i] = NoisePrediction(raw, "MARKETING", 999.0, "REMOVE", source="marketing_rule")
            else:
                ml_indices.append(i)
                ml_values.append(raw)

        if ml_values:
            labels = self.model.predict(ml_values)
            margins = self.model.decision_function(ml_values)
            if getattr(margins, "ndim", 1) > 1:
                margins = margins.max(axis=1)
            for i, raw, label, margin in zip(ml_indices, ml_values, labels, margins):
                label = str(label).upper()
                margin = float(margin)
                if label in {"MARKETING", "NOISE"} and margin >= self.auto_remove_margin:
                    action = "REMOVE"
                elif abs(margin) < self.review_margin:
                    action = "REVIEW"
                else:
                    action = "KEEP"
                results[i] = NoisePrediction(raw, label, margin, action, source="classifier")

        return [r for r in results if r is not None]


class ProductNameNoiseProcessor:
    """
    Core-name 제거 결정을 한 곳에서 만든다.

    플랫폼 정책
    ------------------------------------------------------------
    CONSERVATIVE
    - musinsa
    - kream

    AGGRESSIVE
    - zigzag
    - ably

    원칙
    ------------------------------------------------------------
    1. structural remove_from_core는 플랫폼과 관계없이 제거
    2. DiscoveryExclusion은 upstream structural/exclusion 결과를 존중
    3. CONSERVATIVE 플랫폼은 의미를 확신할 수 없는 front wrapper 보존
    4. AGGRESSIVE 플랫폼은 front metadata wrapper 적극 제거
    5. AGGRESSIVE 플랫폼은 ITEM → TPO/STYLE → ITEM 패턴을
       semantic tag tail로 판단
    6. DictionaryTerm 추출과 core-name 제거는 독립
    """

    CONSERVATIVE_SOURCES = {
        "musinsa",
        "kream",
    }

    AGGRESSIVE_SOURCES = {
        "zigzag",
        "ably",
    }

    SEO_TERM_TYPES = {
        "STYLE",
        "TPO",
    }

    SEMANTIC_TAG_TYPES = {
        "STYLE",
        "TPO",
    }

    FRONT_WRAPPER_PRESERVE_TYPES = {
        "MATERIAL",
        "COLOR",
    }

    FRONT_META_MAX_RATIO = 0.38

    DECORATIVE_WRAPPER_RE = re.compile(
        r"[\[\{<]([^\]\}>]{1,80})[\]\}>]"
    )

    PAREN_RE = re.compile(
        r"\(([^()]*)\)"
    )

    SEO_CHAIN_SPLIT_RE = re.compile(
        r"\s*(?:-|/|\||,|·|•|;)\s*"
    )

    def __init__(
        self,
        classifier: ProductNoiseClassifier | None = None,
        source_code: str = "",
    ):
        self.classifier = (
            classifier
            or ProductNoiseClassifier()
        )

        self.source_code = (
            str(source_code or "")
            .strip()
            .lower()
        )

    @property
    def conservative_mode(self) -> bool:
        return (
            self.source_code
            in self.CONSERVATIVE_SOURCES
        )

    @property
    def aggressive_mode(self) -> bool:
        return (
            self.source_code
            in self.AGGRESSIVE_SOURCES
        )

    def process(
        self,
        *,
        raw_name: str,
        structural_spans: list[dict[str, Any]] | None = None,
        semantic_result: dict[str, Any] | None = None,
        residual_candidates: list[str] | None = None,
    ) -> list[NoiseDecision]:
        raw = str(raw_name or "")
        semantic_result = semantic_result or {}

        decisions: list[NoiseDecision] = []
        occupied: list[tuple[int, int]] = []

        def add(
            decision: NoiseDecision,
        ) -> None:
            key = (
                decision.start,
                decision.end,
                decision.action,
                decision.reason,
                decision.text.casefold(),
            )

            if any(
                (
                    d.start,
                    d.end,
                    d.action,
                    d.reason,
                    d.text.casefold(),
                )
                == key
                for d in decisions
            ):
                return

            decisions.append(
                decision
            )

            if (
                decision.should_remove
                and decision.start is not None
                and decision.end is not None
            ):
                occupied.append(
                    (
                        decision.start,
                        decision.end,
                    )
                )

        # ========================================================
        # 1. Structural decisions
        # ========================================================

        for span in structural_spans or []:
            if (
                span.get("remove_from_core")
                is not True
            ):
                continue

            try:
                start = int(
                    span.get("start")
                )
                end = int(
                    span.get("end")
                )
            except (TypeError, ValueError):
                continue

            if not (
                0 <= start < end <= len(raw)
            ):
                continue

            add(
                NoiseDecision(
                    text=raw[start:end],
                    action="REMOVE",
                    reason=(
                        "STRUCTURAL_"
                        f"{str(span.get('category') or 'NOISE').upper()}"
                    ),
                    source="structural",
                    start=start,
                    end=end,
                )
            )

        # ========================================================
        # 2. Leading decorative wrappers
        # ========================================================
        #
        # CONSERVATIVE
        # musinsa / kream
        #
        #   [개구리 중사 케로로] 긴팔티
        #   → KEEP
        #
        # AGGRESSIVE
        # zigzag / ably
        #
        #   [여신실루엣][활용도UP] 원피스
        #   → REMOVE
        #
        # structural analyzer가 이미 제거 대상으로 잡은
        # wrapper는 1단계에서 처리되므로 여기서는 건드리지 않는다.
        # ========================================================

        leading_cursor = 0

        for match in (
            self.DECORATIVE_WRAPPER_RE.finditer(
                raw
            )
        ):
            front_limit = max(
                8,
                int(
                    len(raw)
                    * self.FRONT_META_MAX_RATIO
                ),
            )

            if match.start() > front_limit:
                break

            between = raw[
                leading_cursor:
                match.start()
            ]

            if between.strip():
                break

            leading_cursor = match.end()

            if self._inside_removed(
                match.start(),
                match.end(),
                occupied,
            ):
                continue

            # 무신사 / KREAM:
            # 알 수 없는 wrapper를 metadata라고
            # 단정하지 않고 상품 식별 정보로 보존한다.
            if self.conservative_mode:
                continue

            # 명확한 MATERIAL / COLOR wrapper는
            # aggressive source에서도 보존한다.
            if self._preserve_front_wrapper(
                match,
                semantic_result,
            ):
                continue

            add(
                NoiseDecision(
                    text=match.group(0),
                    action="REMOVE",
                    reason="FRONT_META_WRAPPER",
                    source="structural_context",
                    start=match.start(),
                    end=match.end(),
                )
            )

        # ========================================================
        # 3. Semantic tag tail
        # ========================================================
        #
        # AGGRESSIVE source 전용.
        #
        # 첫 ITEM 이후:
        #
        # ITEM
        # → TPO / STYLE
        # → ITEM
        #
        # 패턴이 확인되면 첫 TPO/STYLE부터 문자열 끝까지
        # 검색용 tag tail로 판단한다.
        #
        # 예:
        #
        # 가을니트      ITEM
        # 출근룩        TPO       <- CUT
        # 상견례룩      TPO
        # 슬림니트      ITEM
        # 긴팔니트 ...
        #
        # 결과:
        # ... 가을니트
        #
        # ITEM → ITEM만으로는 절대 발동하지 않는다.
        # ========================================================

        semantic_tag_tail = (
            self._find_semantic_tag_tail(
                raw=raw,
                semantic_result=semantic_result,
            )
        )

        if semantic_tag_tail is not None:
            tail_start, tail_end = (
                semantic_tag_tail
            )

            if not self._inside_removed(
                tail_start,
                tail_end,
                occupied,
            ):
                add(
                    NoiseDecision(
                        text=raw[
                            tail_start:
                            tail_end
                        ],
                        action="REMOVE",
                        reason="SEMANTIC_TAG_TAIL",
                        source="semantic_context",
                        start=tail_start,
                        end=tail_end,
                    )
                )

        # ========================================================
        # 4. Semantic evidence
        # ========================================================
        #
        # DictionaryTerm은 기본적으로 KEEP.
        #
        # 단,
        # - front metadata wrapper
        # - trailing SEO tag chain
        #
        # 같은 문맥이 명확한 경우에만 core에서 제거한다.
        #
        # ProductTerm evidence 자체는 유지된다.
        # ========================================================

        for evidence in (
            semantic_result.get(
                "known_evidence"
            )
            or []
        ):
            surface = str(
                evidence.get("surface")
                or ""
            ).strip()

            if not surface:
                continue

            for match in re.finditer(
                re.escape(surface),
                raw,
                flags=re.IGNORECASE,
            ):
                if self._inside_removed(
                    match.start(),
                    match.end(),
                    occupied,
                ):
                    continue

                if (
                    self._inside_preserved_front_wrapper(
                        raw,
                        match.start(),
                        match.end(),
                        semantic_result,
                    )
                ):
                    continue

                context = (
                    self._semantic_noise_context(
                        raw,
                        match.start(),
                        match.end(),
                        evidence,
                    )
                )

                if not context:
                    continue

                add(
                    NoiseDecision(
                        text=match.group(0),
                        action="REMOVE",
                        reason=context,
                        source="semantic_context",
                        start=match.start(),
                        end=match.end(),
                        term_id=evidence.get(
                            "term_id"
                        ),
                        term_type=evidence.get(
                            "term_type"
                        ),
                        preserve_as_product_term=True,
                    )
                )

        # ========================================================
        # 5. Unknown residual classifier
        # ========================================================
        #
        # Dictionary에서 이미 의미를 아는 term이 아니라
        # residual candidate만 classifier에 보낸다.
        #
        # classifier가 REMOVE라고 확신한 경우에만
        # 실제 core-name span을 제거한다.
        # ========================================================

        residuals = list(
            dict.fromkeys(
                str(v or "").strip()
                for v in (
                    residual_candidates
                    or []
                )
                if str(v or "").strip()
            )
        )

        predictions = (
            self.classifier.predict_many(
                residuals
            )
        )

        for surface, prediction in zip(
            residuals,
            predictions,
        ):
            if prediction.action == "REMOVE":
                for match in re.finditer(
                    re.escape(surface),
                    raw,
                    flags=re.IGNORECASE,
                ):
                    if self._inside_removed(
                        match.start(),
                        match.end(),
                        occupied,
                    ):
                        continue

                    add(
                        NoiseDecision(
                            text=match.group(0),
                            action="REMOVE",
                            reason=(
                                "CLASSIFIER_"
                                f"{prediction.label}"
                            ),
                            source=prediction.source,
                            start=match.start(),
                            end=match.end(),
                            margin=prediction.margin,
                        )
                    )

            else:
                occurrences = list(
                    re.finditer(
                        re.escape(surface),
                        raw,
                        flags=re.IGNORECASE,
                    )
                )

                if (
                    occurrences
                    and all(
                        self._inside_removed(
                            match.start(),
                            match.end(),
                            occupied,
                        )
                        for match in occurrences
                    )
                ):
                    continue

                add(
                    NoiseDecision(
                        text=surface,
                        action=prediction.action,
                        reason=(
                            "CLASSIFIER_"
                            f"{prediction.label}"
                        ),
                        source=prediction.source,
                        margin=prediction.margin,
                    )
                )

        return sorted(
            decisions,
            key=lambda d: (
                d.start is None,
                d.start or 0,
                d.end or 0,
                d.text,
            ),
        )

    def _find_semantic_tag_tail(
        self,
        *,
        raw: str,
        semantic_result: dict[str, Any],
    ) -> tuple[int, int] | None:
        """
        Zigzag / ABLY의 검색 태그형 상품명 tail을 찾는다.

        조건
        ------------------------------------------------------------
        1. AGGRESSIVE source일 것
        2. 첫 ITEM evidence가 존재할 것
        3. 첫 ITEM 이후 TPO/STYLE evidence가 존재할 것
        4. 그 뒤 ITEM evidence가 다시 등장할 것

        조건을 만족하면 첫 TPO/STYLE 위치부터
        문자열 끝까지 제거한다.

        ITEM → ITEM만 있는 정상 복합 상품명은 제거하지 않는다.
        """

        if not self.aggressive_mode:
            return None

        evidence_rows = (
            semantic_result.get(
                "known_evidence"
            )
            or []
        )

        candidates: list[
            dict[str, Any]
        ] = []

        for evidence in evidence_rows:
            if not isinstance(
                evidence,
                dict,
            ):
                continue

            term_type = str(
                evidence.get("term_type")
                or ""
            ).upper()

            if term_type not in {
                "ITEM",
                "TPO",
                "STYLE",
            }:
                continue

            surface = str(
                evidence.get("surface")
                or ""
            ).strip()

            if not surface:
                continue

            # semantic evidence에 직접 span이 있다면
            # 그것을 최우선으로 사용한다.
            start = evidence.get("start")
            end = evidence.get("end")

            if (
                isinstance(start, int)
                and isinstance(end, int)
                and 0 <= start < end <= len(raw)
            ):
                candidates.append(
                    {
                        "term_type": term_type,
                        "start": start,
                        "end": end,
                        "surface": surface,
                    }
                )
                continue

            # 현재 semantic evidence가 span을 직접
            # 제공하지 않는 경우도 있으므로 raw에서 찾는다.
            for match in re.finditer(
                re.escape(surface),
                raw,
                flags=re.IGNORECASE,
            ):
                candidates.append(
                    {
                        "term_type": term_type,
                        "start": match.start(),
                        "end": match.end(),
                        "surface": match.group(0),
                    }
                )

        if not candidates:
            return None

        # 동일 위치/타입 evidence 중복 제거
        unique: dict[
            tuple[str, int, int],
            dict[str, Any],
        ] = {}

        for row in candidates:
            key = (
                row["term_type"],
                row["start"],
                row["end"],
            )

            unique[key] = row

        candidates = sorted(
            unique.values(),
            key=lambda row: (
                row["start"],
                row["end"],
                row["term_type"],
            ),
        )

        # --------------------------------------------------------
        # 첫 번째 ITEM 찾기
        # --------------------------------------------------------

        first_item_index: int | None = None

        for index, evidence in enumerate(
            candidates
        ):
            if (
                evidence["term_type"]
                == "ITEM"
            ):
                continue

            # 괄호 내부 ITEM은 본체 anchor로 사용하지 않는다.
            if self._inside_parentheses(
                raw,
                evidence["start"],
                evidence["end"],
            ):
                continue

            first_item_index = index
            break

        if first_item_index is None:
            return None

        first_item = candidates[
            first_item_index
        ]

        # 첫 ITEM 내부/중첩 evidence는 건너뛰기 위해
        # ITEM의 끝 위치를 기준으로 시작한다.
        first_item_end = first_item["end"]

        tag_start: int | None = None
        tag_seen = False

        # --------------------------------------------------------
        # 첫 ITEM 뒤를 순회
        # --------------------------------------------------------

        for evidence in candidates:
            if (
                evidence["start"]
                < first_item_end
            ):
                continue

            term_type = evidence[
                "term_type"
            ]

            # 첫 ITEM 뒤에 등장한 TPO/STYLE.
            # 여기서부터 tag tail 후보.
            if (
                term_type
                in self.SEMANTIC_TAG_TYPES
            ):
                if tag_start is None:
                    tag_start = evidence[
                        "start"
                    ]

                tag_seen = True
                continue

            # TPO/STYLE을 하나 이상 본 뒤
            # ITEM이 다시 등장하면 tag tail 확정.
            if (
                term_type == "ITEM"
                and tag_seen
                and tag_start is not None
            ):
                return (
                    tag_start,
                    len(raw),
                )

        return None

    def _preserve_front_wrapper(
        self,
        match: re.Match[str],
        semantic_result: dict[str, Any],
    ) -> bool:
        """
        Leading wrapper가 순수 상품 정보인 경우 보존한다.

        예:
        [울100%]
        [캐시미어]
        [BLACK]

        AGGRESSIVE source에서도 MATERIAL/COLOR처럼
        명확한 상품 속성 wrapper는 core에 남긴다.
        """

        inside: list[
            dict[str, Any]
        ] = []

        body_start = match.start(1)
        body_end = match.end(1)

        for evidence in (
            semantic_result.get(
                "known_evidence"
            )
            or []
        ):
            surface = str(
                evidence.get("surface")
                or ""
            ).strip()

            if not surface:
                continue

            for found in re.finditer(
                re.escape(surface),
                match.group(1),
                flags=re.IGNORECASE,
            ):
                absolute_start = (
                    body_start
                    + found.start()
                )

                absolute_end = (
                    body_start
                    + found.end()
                )

                if (
                    body_start
                    <= absolute_start
                    < absolute_end
                    <= body_end
                ):
                    inside.append(
                        evidence
                    )
                    break

        if not inside:
            return False

        types = {
            str(
                row.get("term_type")
                or ""
            ).upper()
            for row in inside
        }

        return (
            bool(types)
            and types
            <= self.FRONT_WRAPPER_PRESERVE_TYPES
        )

    def _inside_preserved_front_wrapper(
        self,
        raw: str,
        start: int,
        end: int,
        semantic_result: dict[str, Any],
    ) -> bool:
        """
        현재 semantic evidence가 보존 대상 front wrapper
        내부에 있는지 확인한다.

        CONSERVATIVE source에서는 모든 알 수 없는
        leading wrapper를 보존하므로 내부 semantic evidence도
        wrapper라는 이유만으로 제거하지 않는다.
        """

        leading_cursor = 0

        for wrapper in (
            self.DECORATIVE_WRAPPER_RE.finditer(
                raw
            )
        ):
            front_limit = max(
                8,
                int(
                    len(raw)
                    * self.FRONT_META_MAX_RATIO
                ),
            )

            if (
                wrapper.start()
                > front_limit
            ):
                break

            if raw[
                leading_cursor:
                wrapper.start()
            ].strip():
                break

            leading_cursor = (
                wrapper.end()
            )

            if not (
                wrapper.start()
                <= start
                and end
                <= wrapper.end()
            ):
                continue

            # CONSERVATIVE source에서는
            # leading wrapper 자체를 보존한다.
            if self.conservative_mode:
                return True

            return (
                self._preserve_front_wrapper(
                    wrapper,
                    semantic_result,
                )
            )

        return False

    def _semantic_noise_context(
        self,
        raw: str,
        start: int,
        end: int,
        evidence: dict[str, Any],
    ) -> str | None:
        term_type = str(
            evidence.get("term_type")
            or ""
        ).upper()

        # ========================================================
        # Leading wrapper
        # ========================================================

        for match in (
            self.DECORATIVE_WRAPPER_RE.finditer(
                raw
            )
        ):
            if not (
                match.start()
                <= start
                and end
                <= match.end()
            ):
                continue

            front_limit = max(
                8,
                int(
                    len(raw)
                    * self.FRONT_META_MAX_RATIO
                ),
            )

            if (
                match.start()
                > front_limit
            ):
                continue

            # 무신사 / KREAM은 wrapper라는 이유만으로
            # semantic term을 제거하지 않는다.
            if self.conservative_mode:
                continue

            # Zigzag / ABLY는 기존 aggressive 정책.
            return "FRONT_META_WRAPPER"

        # ========================================================
        # Trailing parenthesized SEO tag chain
        # ========================================================

        for match in self.PAREN_RE.finditer(
            raw
        ):
            if not (
                match.start()
                <= start
                and end
                <= match.end()
            ):
                continue

            body = (
                match.group(1)
                .strip()
            )

            parts = [
                part.strip()
                for part
                in self.SEO_CHAIN_SPLIT_RE.split(
                    body
                )
                if part.strip()
            ]

            trailing = not raw[
                match.end():
            ].strip()

            if (
                trailing
                and len(parts) >= 4
                and term_type
                in self.SEO_TERM_TYPES
            ):
                return "SEO_TAG_CHAIN"

        return None

    @staticmethod
    def _inside_removed(
        start: int,
        end: int,
        occupied: list[
            tuple[int, int]
        ],
    ) -> bool:
        return any(
            start >= left
            and end <= right
            for left, right
            in occupied
        )
        
    @staticmethod
    def _inside_parentheses(
        raw: str,
        start: int,
        end: int,
    ) -> bool:
        for match in re.finditer(
            r"\([^()]*\)",
            raw,
        ):
            if (
                match.start()
                <= start
                and end
                <= match.end()
            ):
                return True

        return False