from __future__ import annotations

import math
from dataclasses import dataclass

from .embedding_service import TermEmbeddingService


@dataclass
class SemanticClassificationResult:
    term_type: str
    attribute_type: str | None
    confidence: float
    reason: str


class SemanticCandidateClassifier:

    # =========================================================
    # 1. Semantic prototypes
    # =========================================================

    TYPE_PROTOTYPES = {
        "MATERIAL": (
            "패션 상품의 원단, 섬유, 소재, 재질, "
            "표면 질감, 가공 소재를 나타내는 표현. "
            "데님, 스웨이드, 트위드, 코듀로이, "
            "피치스킨, 울, 레더와 같은 개념."
        ),

        "DETAIL": (
            "개별 의류나 패션 상품 자체의 형태적 속성과 "
            "디자인 구조를 나타내는 표현. "
            "핏, 실루엣, 넥라인, 기장, 소매, 절개, "
            "셔링, 볼륨, 곡선 형태, 구조적 디테일 등을 포함."
        ),

        "COLOR": (
            "패션 상품의 색상, 색조, 색 계열을 나타내는 표현. "
            "블랙, 화이트, 버건디, 코발트블루, "
            "카키, 크림, 네이비 같은 컬러 개념."
        ),
    }

    DETAIL_PROTOTYPES = {
        "FIT": (
            "옷이 몸에 맞는 정도와 여유감, "
            "몸을 감싸는 방식과 관련된 핏 특성. "
            "슬림핏, 오버핏, 와이드핏, 배럴핏, "
            "루즈핏 같은 개념."
        ),

        "SILHOUETTE": (
            "의류 전체의 외곽선, 볼륨, 곡선, 형태를 "
            "나타내는 실루엣 특성. "
            "커브드, A라인, 벌룬, 플레어, "
            "볼륨형 같은 개념."
        ),

        "NECKLINE": (
            "의류의 목 부분과 어깨선 주변 형태를 나타내는 "
            "넥라인 특성. "
            "브이넥, 라운드넥, 보트넥, "
            "오프숄더, 스퀘어넥 같은 개념."
        ),

        "SLEEVE": (
            "의류 소매의 형태, 길이, 볼륨과 관련된 특성. "
            "퍼프 슬리브, 벌룬 슬리브, 캡 슬리브, "
            "롱 슬리브 같은 개념."
        ),

        "LENGTH": (
            "의류의 전체 길이와 기장을 나타내는 특성. "
            "크롭, 미니, 미디, 맥시, 롱 같은 개념."
        ),

        "DETAIL": (
            "절개, 셔링, 주름, 포켓, 지퍼, 스티치, "
            "레이어, 러플 등 의류의 세부 디자인 요소."
        ),
    }

    # =========================================================
    # 2. Gate rules
    # =========================================================

    ITEM_SUFFIXES = (
        "팬츠",
        "바지",
        "재킷",
        "자켓",
        "셔츠",
        "스커트",
        "드레스",
        "원피스",
        "코트",
        "니트",
        "후드",
        "후디",
        "티셔츠",
        "블라우스",
        "카디건",
        "가디건",
        "베스트",
        "조끼",
        "부츠",
        "슈즈",
        "스니커즈",
        "로퍼",
        "샌들",
        "백",
        "가방",
        "캡",
        "햇",
    )

    TPO_TERM_HINTS = (
        "출근",
        "오피스",
        "데이트",
        "하객",
        "웨딩",
        "결혼식",
        "공항",
        "여행",
        "휴양",
        "리조트",
        "운동",
        "등산",
        "캠핑",
        "페스티벌",
        "파티",
    )

    TPO_CONTEXT_HINTS = (
        "출근할 때",
        "회사에서",
        "오피스",
        "데이트할 때",
        "결혼식",
        "하객",
        "공항",
        "여행할 때",
        "휴양지",
        "리조트",
        "운동할 때",
        "등산",
        "캠핑",
        "페스티벌",
        "파티",
        "착용 상황",
        "입는 상황",
    )

    STYLE_SUFFIXES = (
        "코어",
        "core",
        "시크",
        "chic",
        "프레피",
        "preppy",
    )

    STYLE_CONTEXT_HINTS = (
        "스타일",
        "스타일링",
        "패션 스타일",
        "미학",
        "미적",
        "aesthetic",
        "코어",
        "core",
        "무드",
        "mood",
        "감성",
        "룩의 분위기",
        "패션 정체성",
        "스타일 정체성",
    )

    # =========================================================
    # 3. Init
    # =========================================================

    def __init__(self):
        self.embedding_service = TermEmbeddingService()

        self._type_vectors = None
        self._detail_vectors = None

    # =========================================================
    # 4. Utility
    # =========================================================

    @staticmethod
    def cosine_similarity(
        a: list[float],
        b: list[float],
    ) -> float:

        dot = sum(
            x * y
            for x, y in zip(a, b)
        )

        norm_a = math.sqrt(
            sum(x * x for x in a)
        )

        norm_b = math.sqrt(
            sum(y * y for y in b)
        )

        if not norm_a or not norm_b:
            return 0.0

        return dot / (
            norm_a * norm_b
        )

    def _get_contexts(
        self,
        candidate,
        limit: int = 5,
    ) -> list[str]:

        observations = (
            candidate.observations
            .order_by("-detected_at")[:limit]
        )

        return [
            obs.raw_text
            for obs in observations
        ]

    # =========================================================
    # 5. Gate: ITEM
    # =========================================================

    def _looks_like_item(
        self,
        term: str,
    ) -> bool:

        term_lower = term.lower().strip()

        return any(
            term_lower.endswith(suffix)
            for suffix in self.ITEM_SUFFIXES
        )

    # =========================================================
    # 6. Gate: TPO
    # =========================================================

    def _looks_like_tpo(
        self,
        candidate,
    ) -> bool:

        term = candidate.raw_term.lower().strip()
        contexts = " ".join(
            self._get_contexts(candidate)
        ).lower()

        if any(
            hint in term
            for hint in self.TPO_TERM_HINTS
        ):
            return True

        if any(
            hint in contexts
            for hint in self.TPO_CONTEXT_HINTS
        ):
            return True

        return False

    # =========================================================
    # 7. Gate: STYLE
    # =========================================================

    def _looks_like_style(
        self,
        candidate,
    ) -> bool:

        term = candidate.raw_term.lower().strip()

        contexts = " ".join(
            self._get_contexts(candidate)
        ).lower()

        # 고프코어 / 발레코어 / 긱시크 등
        if any(
            term.endswith(suffix)
            for suffix in self.STYLE_SUFFIXES
        ):
            return True

        # 실제 문맥에서 패션 정체성/미학으로 쓰이는지
        if any(
            hint in contexts
            for hint in self.STYLE_CONTEXT_HINTS
        ):
            return True

        return False

    # =========================================================
    # 8. Classification text
    # =========================================================

    def _build_classification_text(
        self,
        candidate,
    ) -> str:

        observations = (
            candidate.observations
            .order_by("-detected_at")[:5]
        )

        masked_contexts = []

        for obs in observations:
            text = obs.raw_text

            if candidate.raw_term:
                text = text.replace(
                    candidate.raw_term,
                    "[TARGET]",
                )

            masked_contexts.append(text)

        if masked_contexts:
            context_text = "\n".join(
                f"- {text}"
                for text in masked_contexts
            )
        else:
            context_text = "- 문맥 없음"

        return (
            f"분류 대상 패션 표현: "
            f"{candidate.raw_term}\n"
            f"[TARGET]이 패션 문맥에서 어떤 역할을 하는지 "
            f"판단하기 위한 데이터입니다.\n"
            f"{context_text}"
        )

    # =========================================================
    # 9. Prototype vectors
    # =========================================================

    def _get_type_vectors(self):

        if self._type_vectors is None:
            self._type_vectors = {}

            for type_name, text in (
                self.TYPE_PROTOTYPES.items()
            ):
                self._type_vectors[
                    type_name
                ] = (
                    self.embedding_service
                    .embed(text)
                )

        return self._type_vectors

    def _get_detail_vectors(self):

        if self._detail_vectors is None:
            self._detail_vectors = {}

            for attribute, text in (
                self.DETAIL_PROTOTYPES.items()
            ):
                self._detail_vectors[
                    attribute
                ] = (
                    self.embedding_service
                    .embed(text)
                )

        return self._detail_vectors

    # =========================================================
    # 10. DETAIL subtype
    # =========================================================

    def _classify_detail_attribute(
        self,
        classification_vector: list[float],
    ) -> tuple[str, float, dict]:

        detail_scores = {}

        for attribute, vector in (
            self._get_detail_vectors().items()
        ):
            detail_scores[attribute] = (
                self.cosine_similarity(
                    classification_vector,
                    vector,
                )
            )

        best_attribute = max(
            detail_scores,
            key=detail_scores.get,
        )

        best_score = (
            detail_scores[best_attribute]
        )

        return (
            best_attribute,
            best_score,
            detail_scores,
        )

    # =========================================================
    # 11. Main classification
    # =========================================================

    def classify_candidate(
        self,
        candidate,
    ) -> SemanticClassificationResult:

        classification_text = (
            self._build_classification_text(
                candidate
            )
        )

        classification_vector = (
            self.embedding_service
            .embed(classification_text)
        )

        # -----------------------------------------------------
        # STEP 1
        # ITEM gate
        # -----------------------------------------------------

        if self._looks_like_item(
            candidate.raw_term
        ):
            result = SemanticClassificationResult(
                term_type="ITEM",
                attribute_type=None,
                confidence=0.95,
                reason=(
                    "ITEM gate matched: "
                    "후보 자체가 패션 상품 종류 형태"
                ),
            )

            self._save_result(
                candidate,
                result,
            )

            return result

        # -----------------------------------------------------
        # STEP 2
        # TPO gate
        # STYLE보다 먼저 검사
        # -----------------------------------------------------

        if self._looks_like_tpo(
            candidate
        ):
            result = SemanticClassificationResult(
                term_type="TPO",
                attribute_type=None,
                confidence=0.90,
                reason=(
                    "TPO gate matched: "
                    "착용 상황/목적 관련 표현"
                ),
            )

            self._save_result(
                candidate,
                result,
            )

            return result

        # -----------------------------------------------------
        # STEP 3
        # STYLE gate
        # -----------------------------------------------------

        if self._looks_like_style(
            candidate
        ):
            result = SemanticClassificationResult(
                term_type="STYLE",
                attribute_type=None,
                confidence=0.90,
                reason=(
                    "STYLE gate matched: "
                    "패션 정체성/미학/코어 관련 표현"
                ),
            )

            self._save_result(
                candidate,
                result,
            )

            return result

        # -----------------------------------------------------
        # STEP 4
        # Semantic competition
        #
        # 여기서는 ITEM / STYLE / TPO 제외.
        # MATERIAL / DETAIL / COLOR만 비교.
        # -----------------------------------------------------

        type_scores = {}

        for type_name, vector in (
            self._get_type_vectors().items()
        ):
            type_scores[type_name] = (
                self.cosine_similarity(
                    classification_vector,
                    vector,
                )
            )

        best_type = max(
            type_scores,
            key=type_scores.get,
        )

        best_type_score = (
            type_scores[best_type]
        )

        attribute_type = None
        detail_reason = None

        # -----------------------------------------------------
        # STEP 5
        # DETAIL subtype
        # -----------------------------------------------------

        if best_type == "DETAIL":

            (
                attribute_type,
                attribute_score,
                detail_scores,
            ) = self._classify_detail_attribute(
                classification_vector
            )

            ranked_details = sorted(
                detail_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )

            detail_reason = (
                f"attribute={attribute_type} "
                f"score={attribute_score:.4f} "
                f"| detail_top="
                + ", ".join(
                    f"{name}:{score:.3f}"
                    for name, score
                    in ranked_details[:3]
                )
            )

        # -----------------------------------------------------
        # STEP 6
        # Debug / reason
        # -----------------------------------------------------

        ranked_types = sorted(
            type_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        reason_parts = [
            (
                f"semantic type={best_type} "
                f"score={best_type_score:.4f}"
            ),
            (
                "top_types="
                + ", ".join(
                    f"{name}:{score:.3f}"
                    for name, score
                    in ranked_types
                )
            ),
        ]

        if detail_reason:
            reason_parts.append(
                detail_reason
            )

        result = SemanticClassificationResult(
            term_type=best_type,
            attribute_type=attribute_type,
            confidence=best_type_score,
            reason=" | ".join(
                reason_parts
            ),
        )

        # -----------------------------------------------------
        # STEP 7
        # DB save
        # -----------------------------------------------------

        self._save_result(
            candidate,
            result,
        )

        return result

    # =========================================================
    # 12. Save
    # =========================================================

    def _save_result(
        self,
        candidate,
        result: SemanticClassificationResult,
    ) -> None:

        candidate.suggested_type = (
            result.term_type
        )

        candidate.suggested_attribute_type = (
            result.attribute_type
        )

        candidate.confidence = (
            result.confidence
        )

        candidate.note = (
            result.reason
        )

        candidate.save(
            update_fields=[
                "suggested_type",
                "suggested_attribute_type",
                "confidence",
                "note",
                "updated_at",
            ]
        )