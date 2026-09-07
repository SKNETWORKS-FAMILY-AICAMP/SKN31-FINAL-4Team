import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

import django

django.setup()


from apps.core.models import (
    TermCandidate,
    DictionaryTerm,
    TermAlias,
)

from analysis.term_discovery.candidate_classifier import (
    CandidateClassifier,
)

from analysis.term_discovery.vector_matcher import (
    TermVectorMatcher,
)

from analysis.term_discovery.promotion_service import (
    TermPromotionService,
)


TARGET_TERM = "커브드"


def main():
    print("=" * 70)
    print("FEEDIT TERM DISCOVERY E2E TEST")
    print("=" * 70)

    # 1. 후보 조회
    candidate = (
        TermCandidate.objects
        .filter(raw_term=TARGET_TERM)
        .first()
    )

    if candidate is None:
        print(f"[FAIL] 후보 없음: {TARGET_TERM}")
        return

    print("\n[1] CANDIDATE")
    print("term           :", candidate.raw_term)
    print("detected_count :", candidate.detected_count)
    print("source_count   :", candidate.source_count)

    # 2. LLM 타입 분류
    print("\n[2] LLM CLASSIFICATION")

    classifier = CandidateClassifier()

    classification = (
        classifier.classify_candidate(
            candidate
        )
    )

    candidate.refresh_from_db()

    print(
        "term_type      :",
        classification.term_type,
    )
    print(
        "attribute_type :",
        classification.attribute_type,
    )
    print(
        "confidence     :",
        classification.confidence,
    )
    print(
        "reason         :",
        classification.reason,
    )

    # 3. pgvector 검색
    print("\n[3] PGVECTOR MATCH")

    matcher = TermVectorMatcher()

    matches = matcher.match_candidate(
        candidate=candidate,
        limit=5,
    )

    candidate.refresh_from_db()

    if matches:
        for i, item in enumerate(
            matches,
            start=1,
        ):
            term = item["term"]

            print(
                f"{i}. "
                f"{term.canonical_name}"
                f" | {term.term_type}"
                f" | similarity="
                f"{item['similarity']:.4f}"
            )
    else:
        print("기존 비교 대상 없음")

    # 4. 판정 결과
    print("\n[4] DECISION")

    print(
        "nearest         :",
        candidate.nearest_term,
    )
    print(
        "similarity      :",
        candidate.similarity_score,
    )
    print(
        "decision        :",
        candidate.decision,
    )
    print(
        "decision_reason :",
        candidate.decision_reason,
    )

    # 5. PENDING이면 여기서 종료
    if (
        candidate.decision
        == TermCandidate.Decision.PENDING
    ):
        print("\n[5] PROMOTION")
        print(
            "PENDING 상태이므로 자동 승격하지 않습니다."
        )
        print(
            "관리자 검토 후 NEW_TERM / ALIAS / REJECT "
            "결정이 필요합니다."
        )

        print("\n" + "=" * 70)
        print("E2E TEST SUCCESS")
        print("=" * 70)
        return

    # 6. 실제 승격
    print("\n[5] PROMOTION")

    promoter = TermPromotionService()

    promotion = promoter.promote(
        candidate
    )

    print(
        "success :",
        promotion.success,
    )
    print(
        "action  :",
        promotion.action,
    )
    print(
        "message :",
        promotion.message,
    )

    # 7. 최종 DB 검증
    print("\n[6] DB VERIFY")

    candidate.refresh_from_db()

    print(
        "candidate_status:",
        candidate.status,
    )

    if promotion.action == "NEW_TERM":
        exists = (
            DictionaryTerm.objects
            .filter(
                canonical_name=candidate.raw_term,
                term_type=candidate.suggested_type,
            )
            .exists()
        )

        print(
            "DictionaryTerm created:",
            exists,
        )

    elif promotion.action == "ALIAS":

        exists = (
            TermAlias.objects
            .filter(
                alias=candidate.raw_term,
                term=candidate.nearest_term,
            )
            .exists()
        )

        print(
            "TermAlias created:",
            exists,
        )

    print("\n" + "=" * 70)
    print("E2E TEST SUCCESS")
    print("=" * 70)


if __name__ == "__main__":
    main()