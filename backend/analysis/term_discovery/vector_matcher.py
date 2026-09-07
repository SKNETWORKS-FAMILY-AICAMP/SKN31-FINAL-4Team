from __future__ import annotations

from django.utils import timezone
from pgvector.django import CosineDistance

from apps.core.models import (
    DictionaryTerm,
    TermCandidate,
)

from .embedding_service import (
    TermEmbeddingService,
)


class TermVectorMatcher:

    # ---------------------------------------------------------
    # 임시 threshold
    # 실제 후보 데이터 쌓인 뒤 튜닝할 것
    # ---------------------------------------------------------

    ALIAS_THRESHOLD = 0.90
    NEW_TERM_THRESHOLD = 0.65

    def __init__(self):
        self.embedding_service = (
            TermEmbeddingService()
        )

    # =========================================================
    # DictionaryTerm embedding
    # =========================================================

    def embed_dictionary_term(
        self,
        term: DictionaryTerm,
    ) -> list[float]:

        text = (
            self.embedding_service
            .build_dictionary_term_text(
                term
            )
        )

        vector = (
            self.embedding_service
            .embed(text)
        )

        term.embedding = vector
        term.embedding_updated_at = (
            timezone.now()
        )

        term.save(
            update_fields=[
                "embedding",
                "embedding_updated_at",
                "updated_at",
            ]
        )

        return vector

    # =========================================================
    # Candidate embedding
    # =========================================================

    def embed_candidate(
        self,
        candidate: TermCandidate,
    ) -> list[float]:

        text = (
            self.embedding_service
            .build_candidate_text(
                candidate
            )
        )

        vector = (
            self.embedding_service
            .embed(text)
        )

        candidate.embedding = vector
        candidate.embedding_updated_at = (
            timezone.now()
        )

        candidate.save(
            update_fields=[
                "embedding",
                "embedding_updated_at",
                "updated_at",
            ]
        )

        return vector

    # =========================================================
    # Similar term search
    # =========================================================

    def find_similar_terms(
        self,
        candidate: TermCandidate,
        limit: int = 5,
    ):

        # 후보 embedding이 없으면 생성
        if candidate.embedding is None:
            self.embed_candidate(
                candidate
            )

        queryset = (
            DictionaryTerm.objects
            .filter(
                embedding__isnull=False
            )
        )

        # -----------------------------------------------------
        # ACTIVE term만 검색
        # -----------------------------------------------------

        # DictionaryTerm에 status 필드가 있으면 유지
        if hasattr(
            DictionaryTerm,
            "Status",
        ):
            queryset = queryset.filter(
                status=(
                    DictionaryTerm
                    .Status
                    .ACTIVE
                )
            )

        # -----------------------------------------------------
        # 후보 타입이 분류되어 있으면
        # 같은 타입 안에서만 검색
        #
        # 예:
        # 커브드 -> DETAIL
        # 그러면 STYLE / COLOR / ITEM은 검색 제외
        # -----------------------------------------------------

        if candidate.suggested_type:

            queryset = queryset.filter(
                term_type=(
                    candidate
                    .suggested_type
                )
            )

        # -----------------------------------------------------
        # pgvector cosine distance
        # distance 작을수록 의미적으로 가까움
        # -----------------------------------------------------

        results = (
            queryset
            .annotate(
                distance=CosineDistance(
                    "embedding",
                    candidate.embedding,
                )
            )
            .order_by(
                "distance"
            )[:limit]
        )

        return results

    # =========================================================
    # Decision recommendation
    # =========================================================

    def recommend_decision(
        self,
        similarity: float,
    ) -> tuple[str, str]:

        # -----------------------------------------------------
        # 기존 용어와 거의 동일
        # -----------------------------------------------------

        if (
            similarity
            >= self.ALIAS_THRESHOLD
        ):

            return (
                TermCandidate
                .Decision
                .ALIAS,

                (
                    "기존 용어와 의미 유사도가 "
                    "매우 높아 동일 개념의 "
                    "별칭일 가능성이 높음 "
                    f"({similarity:.4f})"
                ),
            )

        # -----------------------------------------------------
        # 기존 용어와 충분히 다름
        # -----------------------------------------------------

        if (
            similarity
            <= self.NEW_TERM_THRESHOLD
        ):

            return (
                TermCandidate
                .Decision
                .NEW_TERM,

                (
                    "기존 용어와 의미적 차이가 "
                    "커 신규 표준 용어일 "
                    "가능성이 높음 "
                    f"({similarity:.4f})"
                ),
            )

        # -----------------------------------------------------
        # 애매한 구간
        # -----------------------------------------------------

        return (
            TermCandidate
            .Decision
            .PENDING,

            (
                "기존 용어와 관련성은 있으나 "
                "동일 개념으로 확정하기 어려움 "
                f"({similarity:.4f})"
            ),
        )

    # =========================================================
    # Candidate match
    # =========================================================

    def match_candidate(
        self,
        candidate: TermCandidate,
        limit: int = 5,
    ) -> list[dict]:

        # -----------------------------------------------------
        # 1. Top-K 검색
        # -----------------------------------------------------

        results = (
            self.find_similar_terms(
                candidate=candidate,
                limit=limit,
            )
        )

        matches = []

        # -----------------------------------------------------
        # 2. distance -> similarity 변환
        #
        # cosine distance:
        # 0에 가까울수록 유사
        #
        # similarity = 1 - distance
        # -----------------------------------------------------

        for term in results:

            distance = float(
                term.distance
            )

            similarity = (
                1.0 - distance
            )

            matches.append(
                {
                    "term": term,
                    "distance": distance,
                    "similarity": (
                        similarity
                    ),
                }
            )

        # 비교 가능한 기존 term 없음
        if not matches:

            candidate.nearest_term = None
            candidate.similarity_score = None

            candidate.decision = (
                TermCandidate
                .Decision
                .NEW_TERM
            )

            candidate.decision_reason = (
                "비교 가능한 기존 표준 용어가 "
                "없어 신규 용어 후보로 판단"
            )

            candidate.save(
                update_fields=[
                    "nearest_term",
                    "similarity_score",
                    "decision",
                    "decision_reason",
                    "updated_at",
                ]
            )

            return []

        # -----------------------------------------------------
        # 3. 가장 가까운 기존 term
        # -----------------------------------------------------

        best = matches[0]

        best_term = (
            best["term"]
        )

        best_similarity = (
            best["similarity"]
        )

        # -----------------------------------------------------
        # 4. Decision 추천
        # -----------------------------------------------------

        (
            decision,
            reason,
        ) = (
            self.recommend_decision(
                best_similarity
            )
        )

        # -----------------------------------------------------
        # 5. Candidate DB 저장
        # -----------------------------------------------------

        candidate.nearest_term = (
            best_term
        )

        candidate.similarity_score = (
            best_similarity
        )

        candidate.decision = (
            decision
        )

        candidate.decision_reason = (
            reason
        )

        candidate.save(
            update_fields=[
                "nearest_term",
                "similarity_score",
                "decision",
                "decision_reason",
                "updated_at",
            ]
        )

        return matches