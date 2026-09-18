from __future__ import annotations

from typing import Any

from apps.core.models import ProductSource

from .analysis_repository import (
    ProductAnalysisRepository,
)
from .attribute_extractor import (
    ProductAttributeExtractor,
)
from .name_processor import (
    ProductNameProcessor,
)


class ProductEnrichmentPipeline:
    """
    STEP 3: 분석 JSON
    STEP 4: known -> ProductTerm
    STEP 5: CNV unknown -> TermCandidateObservation
    """

    def __init__(
        self,
        *,
        source_code: str,
    ):
        self.source_code = str(
            source_code or ""
        ).strip().upper()

        if not self.source_code:
            raise ValueError(
                "source_code가 필요합니다."
            )

        self.name_processor = (
            ProductNameProcessor()
        )
        self.extractor = (
            ProductAttributeExtractor()
        )
        self.repository = (
            ProductAnalysisRepository()
        )

    def analyze_one(
        self,
        product_source: ProductSource,
        *,
        save_json: bool = True,
    ) -> dict[str, Any]:

        attributes = (
            product_source.attributes
            if isinstance(
                product_source.attributes,
                dict,
            )
            else {}
        )

        name_result = (
            self.name_processor.process(
                source_name=product_source.source_name,
                source_code=product_source.source.code,
                existing_tags=(
                    attributes.get("tags")
                    or []
                ),
            )
        )

        result = (
            self.extractor.extract_product(
                product_source=product_source,
                normalized_name=(
                    name_result["normalized_name"]
                ),
                tags=name_result["tags"],
            )
        )

        result["source_name_meta"] = (
            name_result.get("source_name_meta")
            or {}
        )

        if save_json:
            self.repository.save_analysis_json(
                product_source,
                result,
            )
            # repository가 DB instance를 갱신했으므로
            # 이후 STEP 4/5가 최신 JSON을 보게 refresh.
            product_source.refresh_from_db(
                fields=[
                    "normalized_name",
                    "attributes",
                ]
            )

        return result

    def run_one(
        self,
        product_source: ProductSource,
        *,
        save_json: bool = True,
        persist_known: bool = True,
        persist_unknown: bool = True,
        cnv_candidates_only: bool = True,
    ) -> dict[str, Any]:

        analysis = self.analyze_one(
            product_source,
            save_json=save_json,
        )

        output = {
            "product_source_id":
                product_source.id,
            "analysis": analysis,
            "product_terms": None,
            "candidates": None,
        }

        if persist_known:
            output["product_terms"] = (
                self.repository
                .persist_known_terms(
                    product_source
                )
            )

        if persist_unknown:
            output["candidates"] = (
                self.repository
                .persist_unknown_candidates(
                    product_source,
                    cnv_only=(
                        cnv_candidates_only
                    ),
                )
            )

        return output

    def run(
        self,
        *,
        limit: int | None = 10,
        force: bool = False,
        persist_known: bool = True,
        persist_unknown: bool = False,
        cnv_candidates_only: bool = True,
        create_candidates: bool | None = None,
    ) -> dict[str, Any]:
        """
        안전한 기본:
          persist_known=True
          persist_unknown=False

        candidate까지 만들려면:
          persist_unknown=True

        create_candidates는 이전 호출 호환 alias.
        """
        if create_candidates is not None:
            persist_unknown = bool(
                create_candidates
            )

        queryset = (
            ProductSource.objects
            .select_related(
                "source",
                "source_brand",
                "source_category",
            )
            .filter(
                source__code__iexact=(
                    self.source_code
                )
            )
            .order_by("id")
        )

        result = {
            "source": self.source_code,
            "requested_limit": limit,
            "selected": 0,
            "processed": 0,
            "skipped": 0,
            "failed": 0,

            "product_term_created": 0,
            "product_term_existing": 0,

            "candidate_created": 0,
            "candidate_observation_created": 0,
            "candidate_observation_existing": 0,

            "cnv_observations": 0,
            "errors": [],
            "items": [],
        }

        selected = 0

        for product_source in queryset.iterator(
            chunk_size=200
        ):
            attributes = (
                product_source.attributes
                if isinstance(
                    product_source.attributes,
                    dict,
                )
                else {}
            )

            existing_analysis = (
                attributes.get(
                    "feedit_analysis"
                )
            )

            if (
                not force
                and isinstance(
                    existing_analysis,
                    dict,
                )
                and (
                    existing_analysis.get(
                        "version"
                    )
                    or 0
                ) >= 3
            ):
                result["skipped"] += 1
                continue

            if (
                limit is not None
                and selected >= limit
            ):
                break

            selected += 1
            result["selected"] += 1

            try:
                row = self.run_one(
                    product_source,
                    save_json=True,
                    persist_known=persist_known,
                    persist_unknown=persist_unknown,
                    cnv_candidates_only=(
                        cnv_candidates_only
                    ),
                )

                analysis = (
                    row.get("analysis")
                    or {}
                )
                summary = (
                    analysis.get("summary")
                    or {}
                )

                result["processed"] += 1
                result["cnv_observations"] += (
                    summary.get(
                        "cnv_observation_count",
                        0,
                    )
                    or 0
                )

                product_terms = (
                    row.get("product_terms")
                    or {}
                )

                result[
                    "product_term_created"
                ] += (
                    product_terms.get(
                        "created",
                        0,
                    )
                    or 0
                )

                result[
                    "product_term_existing"
                ] += (
                    product_terms.get(
                        "existing",
                        0,
                    )
                    or 0
                )

                candidates = (
                    row.get("candidates")
                    or {}
                )

                result[
                    "candidate_created"
                ] += (
                    candidates.get(
                        "candidate_created",
                        0,
                    )
                    or 0
                )

                result[
                    "candidate_observation_created"
                ] += (
                    candidates.get(
                        "observation_created",
                        0,
                    )
                    or 0
                )

                result[
                    "candidate_observation_existing"
                ] += (
                    candidates.get(
                        "observation_existing",
                        0,
                    )
                    or 0
                )

                result["items"].append(
                    {
                        "product_source_id":
                            product_source.id,
                        "source_product_id":
                            product_source
                            .source_product_id,
                        "normalized_name":
                            analysis.get(
                                "normalized_name"
                            ),
                        "evidence_summary":
                            analysis.get(
                                "evidence_summary"
                            ),
                        "product_terms":
                            product_terms,
                        "candidates":
                            candidates,
                    }
                )

            except Exception as exc:
                result["failed"] += 1
                result["errors"].append(
                    {
                        "product_source_id":
                            product_source.id,
                        "source_product_id":
                            product_source
                            .source_product_id,
                        "error_type":
                            type(exc).__name__,
                        "error":
                            str(exc),
                    }
                )

        return result
