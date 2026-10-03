from __future__ import annotations



from typing import Any



from apps.core.models import ProductSource



from .processors import (

    ProductAttributeBuilder,

    ProductCoreNameBuilder,

    ProductCoreNameRefiner,

    ProductNoiseClassifier,

    ProductNameNoiseProcessor,

    ProductResidualBuilder,

    ProductStructuralAnalyzer,

    SemanticAttributeExtractor,

)





class ProductNormalizationPipeline:

    """

    FEEDIT STEP02 normalization v1.



    지원 플랫폼

    - zigzag

    - ably

    - musinsa

    - musinsa_used

    - kream



    정책

    - DB write 없음

    - 플랫폼별 Adapter에서 source_name을 표준 입력으로 변환

    - Structural Analyzer는 구조 정보 추출

    - Semantic Tokenizer는 RAW source_name 전체를 분석

    - Structural + Semantic evidence를 attribute로 통합

    - 이미 해석된 structural / semantic surface는 residual에서 제외

    - 남은 residual은 Noise Classifier에서 batch 판정

    - 확실한 MARKETING만 core name에서 제거

    - REVIEW / KEEP residual은 core name에 보존

    """



    VERSION = 2



    def __init__(

        self,

        *,

        source_code: str,

    ):

        self.source_code = (

            str(source_code or "")

            .strip()

            .lower()

        )



        if not self.source_code:

            raise ValueError(

                "source_code가 필요합니다."

            )



        # -----------------------------------------------------

        # Pipeline component는 생성 시 한 번만 준비한다.

        #

        # 특히 SemanticAttributeExtractor 내부 tokenizer는

        # get_feedit_tokenizer() singleton을 사용해야 한다.

        # -----------------------------------------------------



        self.adapter = self._build_adapter()



        self.structural_analyzer = (

            ProductStructuralAnalyzer()

        )



        self.semantic_extractor = (

            SemanticAttributeExtractor()

        )



        self.attribute_builder = (

            ProductAttributeBuilder()

        )



        self.core_name_builder = (

            ProductCoreNameBuilder()

        )



        self.core_name_refiner = (

            ProductCoreNameRefiner()

        )



        self.residual_builder = (

            ProductResidualBuilder()

        )



        self.noise_classifier = ProductNoiseClassifier()

        self.name_noise_processor = (

            ProductNameNoiseProcessor(

                classifier=self.noise_classifier,

                source_code=self.source_code,

            )

        )



    # =========================================================

    # Adapter

    # =========================================================



    def _build_adapter(self):

        if self.source_code == "zigzag":

            from .adapters.zigzag import (

                ZigzagNormalizationAdapter,

            )



            return ZigzagNormalizationAdapter()



        if self.source_code == "ably":

            from .adapters.ably import (

                AblyNormalizationAdapter,

            )



            return AblyNormalizationAdapter()



        if self.source_code == "musinsa":

            from .adapters.musinsa import (

                MusinsaNormalizationAdapter,

            )



            return MusinsaNormalizationAdapter()



        if self.source_code == "musinsa_used":

            from .adapters.musinsa_used import (

                MusinsaUsedNormalizationAdapter,

            )



            return MusinsaUsedNormalizationAdapter()



        if self.source_code == "kream":

            from .adapters.kream import (

                KreamNormalizationAdapter,

            )



            return KreamNormalizationAdapter()



        raise ValueError(

            "지원하지 않는 source_code: "

            f"{self.source_code}"

        )

    # =========================================================

    # Dictionary reload

    # =========================================================



    def reload_dictionary(self) -> None:

        """

        DictionaryTerm / TermAlias 등을 수정한 뒤

        semantic tokenizer dictionary만 다시 로드한다.



        Kiwi / SentencePiece tokenizer 자체를

        새로 생성하지 않는다.

        """



        self.semantic_extractor.reload_dictionary()



    # =========================================================

    # Run by ID

    # =========================================================



    def run_by_id(

        self,

        product_source_id: int,

    ) -> dict[str, Any]:

        product_source = (

            ProductSource.objects

            .select_related("source")

            .get(id=product_source_id)

        )



        return self.run(

            product_source

        )



    # =========================================================

    # Source evidence helpers

    # =========================================================



    @staticmethod

    def _merge_semantic_results(

        primary: dict[str, Any],

        extras: list[dict[str, Any]],

    ) -> dict[str, Any]:

        """상품명 semantic과 플랫폼 positive evidence semantic을 하나로 합친다.



        extras row 형식:

        {

            "source_field": "SOURCE_TAG" | "SOURCE_ATTRIBUTE",

            "semantic": SemanticAttributeExtractor 결과,

        }

        """

        merged = dict(primary or {})

        known_evidence = list((primary or {}).get("known_evidence") or [])

        known_by_type = {

            str(key): list(values or [])

            for key, values in ((primary or {}).get("known_by_type") or {}).items()

        }



        seen: set[tuple[Any, ...]] = {

            (

                row.get("term_id"),

                str(row.get("canonical_name") or "").casefold(),

                str(row.get("term_type") or "").upper(),

                str(row.get("attribute_type") or "").upper(),

            )

            for row in known_evidence

        }



        for extra_row in extras:

            semantic_result = extra_row.get("semantic") or {}

            source_field = str(

                extra_row.get("source_field") or "SOURCE_EVIDENCE"

            ).strip().upper()

            source_key = str(extra_row.get("source_key") or "").strip()

            source_value = str(extra_row.get("raw") or "").strip()



            for row in semantic_result.get("known_evidence") or []:

                key = (

                    row.get("term_id"),

                    str(row.get("canonical_name") or "").casefold(),

                    str(row.get("term_type") or "").upper(),

                    str(row.get("attribute_type") or "").upper(),

                )

                if key in seen:

                    continue



                seen.add(key)

                copied = dict(row)

                copied["source_field"] = source_field

                if source_key:

                    copied["source_key"] = source_key

                if source_value:

                    copied["source_value"] = source_value

                known_evidence.append(copied)



                term_type = str(copied.get("term_type") or "").upper()

                attribute_type = str(copied.get("attribute_type") or "").upper()

                bucket = (

                    attribute_type

                    if term_type == "DETAIL" and attribute_type

                    else term_type

                )

                canonical = str(

                    copied.get("canonical_name")

                    or copied.get("surface")

                    or ""

                ).strip()

                if bucket and canonical:

                    values = known_by_type.setdefault(bucket, [])

                    if canonical not in values:

                        values.append(canonical)



        merged["known_evidence"] = known_evidence

        merged["known_by_type"] = known_by_type

        return merged



    @classmethod

    def _merge_source_options(

        cls,

        attributes: dict[str, Any],

        source_options: dict[str, Any],

    ) -> dict[str, Any]:

        """명시적인 플랫폼 색상/사이즈 옵션을 서비스 attributes에 병합한다."""



        result = {

            str(key): cls._copy_attribute_value(value)

            for key, value in (attributes or {}).items()

        }



        for raw_key, raw_values in (source_options or {}).items():

            option_key = str(raw_key or "").strip().casefold()

            values = cls._normalize_option_values(raw_values)



            if not values:

                continue



            if option_key in {"색상", "컬러", "color", "colour"}:

                cls._merge_attribute_values(

                    result,

                    "color",

                    values,

                )

            elif option_key in {"사이즈", "size"}:

                cls._merge_attribute_values(

                    result,

                    "size",

                    values,

                )



        return result



    @classmethod

    def _merge_source_attributes(

        cls,

        attributes: dict[str, Any],

        source_attributes: dict[str, Any],

    ) -> dict[str, Any]:

        """플랫폼에서 이미 구조화된 source attribute를 서비스 slot에 병합한다."""



        result = {

            str(key): cls._copy_attribute_value(value)

            for key, value in (attributes or {}).items()

        }



        key_map = {

            "패턴/무늬": "pattern",

            "패턴": "pattern",

            "무늬": "pattern",

            "pattern": "pattern",

            "핏": "fit",

            "fit": "fit",

            "실루엣": "silhouette",

            "silhouette": "silhouette",

            "소재": "material",

            "재질": "material",

            "material": "material",

            "색상": "color",

            "컬러": "color",

            "color": "color",

            "colour": "color",

            "기장": "length",

            "length": "length",

            "소매기장": "sleeve",

            "소매": "sleeve",

            "sleeve": "sleeve",

            "넥라인": "neckline",

            "neckline": "neckline",

            "디테일": "detail",

            "detail": "detail",

        }



        for raw_key, raw_values in (source_attributes or {}).items():

            source_key = str(raw_key or "").strip()

            target = key_map.get(source_key) or key_map.get(source_key.casefold())



            if not target:

                continue



            values = cls._normalize_option_values(raw_values)

            if not values:

                continue



            cls._merge_attribute_values(result, target, values)



        return result



    @classmethod

    def _merge_source_genders(

        cls,

        attributes: dict[str, Any],

        source_genders: list[str],

    ) -> dict[str, Any]:

        """ProductSource의 명시적 성별 값을 서비스 gender에 병합한다."""



        result = {

            str(key): cls._copy_attribute_value(value)

            for key, value in (attributes or {}).items()

        }



        gender_map = {

            "M": "MEN",

            "MEN": "MEN",

            "MALE": "MEN",

            "W": "WOMEN",

            "F": "WOMEN",

            "WOMEN": "WOMEN",

            "FEMALE": "WOMEN",

            "U": "UNISEX",

            "UNISEX": "UNISEX",

        }



        values: list[str] = []

        for raw_value in source_genders or []:

            value = gender_map.get(str(raw_value or "").strip().upper())

            if value and value not in values:

                values.append(value)



        if values:

            cls._merge_attribute_values(result, "gender", values)



        return result



    @staticmethod

    def _copy_attribute_value(value: Any) -> Any:

        if isinstance(value, list):

            return [

                dict(item) if isinstance(item, dict) else item

                for item in value

            ]

        if isinstance(value, dict):

            return dict(value)

        return value



    @staticmethod

    def _normalize_option_values(value: Any) -> list[Any]:

        if isinstance(value, (list, tuple, set)):

            raw_values = list(value)

        elif value in (None, ""):

            raw_values = []

        else:

            raw_values = [value]



        result: list[Any] = []



        for item in raw_values:

            normalized = (

                dict(item)

                if isinstance(item, dict)

                else str(item or "").strip()

            )



            if normalized in (None, "", {}):

                continue



            if normalized not in result:

                result.append(normalized)



        return result



    @staticmethod

    def _merge_attribute_values(

        attributes: dict[str, Any],

        key: str,

        values: list[Any],

    ) -> None:

        current = attributes.get(key)



        if isinstance(current, list):

            merged = list(current)

        elif current in (None, ""):

            merged = []

        else:

            merged = [current]



        for value in values:

            if value not in merged:

                merged.append(value)



        if merged:

            attributes[key] = merged



    def _extract_semantic_cached(
        self,
        text: str,
        cache: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """한 상품 처리 중 동일 semantic text의 중복 tokenize를 제거한다."""
        key = str(text or "").strip()
        if not key:
            return {}
        cached = cache.get(key)
        if cached is not None:
            return cached
        result = self.semantic_extractor.extract(key)
        cache[key] = result
        return result


    # =========================================================

    # Main

    # =========================================================



    def run(

        self,

        product_source: ProductSource,

    ) -> dict[str, Any]:



        # -----------------------------------------------------

        # 0. Source validation

        # -----------------------------------------------------



        actual_source = (

            str(

                product_source.source.code

                or ""

            )

            .strip()

            .lower()

        )



        if actual_source != self.source_code:

            raise ValueError(

                "Pipeline source 불일치: "

                f"pipeline={self.source_code!r}, "

                f"product={actual_source!r}"

            )



        # -----------------------------------------------------

        # 1. Platform Adapter

        # -----------------------------------------------------



        source_input = self.adapter.build(

            product_source

        )



        raw_name = str(

            source_input.get(

                "source_name"

            )

            or ""

        ).strip()



        if not raw_name:

            raise ValueError(

                "source_name이 비어 있습니다. "

                f"ProductSource ID={product_source.id}"

            )



        # -----------------------------------------------------

        # 2. Structural Analysis

        # -----------------------------------------------------



        structural = (

            self.structural_analyzer.analyze(

                raw_name,

                source=product_source.source,

                allow_bare_numeric_size=False,

            )

        )



        structural_spans = [

            span.to_dict()

            for span in structural.spans

        ]



        semantic_input = raw_name

        # 동일 상품의 source tag/attribute에 같은 값이 반복되는 경우
        # tokenizer를 다시 돌리지 않는다.
        semantic_cache: dict[str, dict[str, Any]] = {}
        semantic = self._extract_semantic_cached(
            semantic_input,
            semantic_cache,
        )



        # Platform source evidence

        source_tags = [

            str(value or "").strip()

            for value in (

                source_input.get("source_tags")

                or []

            )

            if str(value or "").strip()

        ]



        source_options = (

            source_input.get("source_options")

            if isinstance(

                source_input.get("source_options"),

                dict,

            )

            else {}

        )



        source_attributes = (

            source_input.get("source_attributes")

            if isinstance(

                source_input.get("source_attributes"),

                dict,

            )

            else {}

        )



        # musinsa_used의 필터 수집 positive evidence는

        # ProductSource.attributes["attributes"]에 저장되어 있다.

        # Adapter가 아직 이를 넘기지 않는 경우에도 안전하게 복구한다.

        if actual_source == "musinsa_used" and not source_attributes:

            raw_payload = (

                product_source.attributes

                if isinstance(product_source.attributes, dict)

                else {}

            )

            nested_attributes = raw_payload.get("attributes")

            if isinstance(nested_attributes, dict):

                source_attributes = nested_attributes



        raw_source_genders = source_input.get("source_genders")

        if not isinstance(raw_source_genders, (list, tuple, set)):

            raw_source_genders = getattr(product_source, "source_genders", None) or []



        source_genders = [

            str(value or "").strip().upper()

            for value in raw_source_genders

            if str(value or "").strip()

        ]



        gender_scope = str(

            getattr(product_source, "gender_scope", None) or ""

        ).strip().upper()



        if gender_scope and gender_scope not in source_genders:

            source_genders.append(gender_scope)



        # -----------------------------------------------------

        # Platform positive evidence -> Dictionary semantic

        #

        # source tag / source attribute 값은 그대로 ProductTerm으로

        # 넣지 않는다. 반드시 FEEDIT SemanticAttributeExtractor를

        # 통과시켜 DictionaryTerm / Alias / Exclusion 정책을 적용한다.

        # -----------------------------------------------------

        source_evidence_semantics: list[dict[str, Any]] = []



        for source_tag in source_tags:

            tag_result = self._extract_semantic_cached(source_tag, semantic_cache)

            if tag_result.get("known_evidence"):

                source_evidence_semantics.append(

                    {

                        "source_field": "SOURCE_TAG",

                        "raw": source_tag,

                        "semantic": tag_result,

                    }

                )



        for source_key, raw_values in source_attributes.items():

            values = self._normalize_option_values(raw_values)

            for raw_value in values:

                # dict 자체는 semantic text가 아니므로 label/value 계열만 사용한다.

                if isinstance(raw_value, dict):

                    candidate = (

                        raw_value.get("tag")

                        or raw_value.get("name")

                        or raw_value.get("label")

                        or raw_value.get("value")

                        or ""

                    )

                else:

                    candidate = raw_value



                source_value = str(candidate or "").strip()

                if not source_value:

                    continue



                attribute_result = self._extract_semantic_cached(source_value, semantic_cache)

                if attribute_result.get("known_evidence"):

                    source_evidence_semantics.append(

                        {

                            "source_field": "SOURCE_ATTRIBUTE",

                            "source_key": source_key,

                            "raw": source_value,

                            "semantic": attribute_result,

                        }

                    )



        source_semantic = self._merge_semantic_results(

            semantic,

            source_evidence_semantics,

        )



        # -----------------------------------------------------

        # 4. Attribute Build

        #

        # Structural evidence

        # +

        # Semantic Dictionary evidence

        # -----------------------------------------------------



        product_attributes = (

            self.attribute_builder.build(

                structural_attributes=(

                    structural.attributes

                ),

                semantic_result=source_semantic,

            )

        )



        product_attributes = (

            self._merge_source_options(

                product_attributes,

                source_options,

            )

        )



        product_attributes = (

            self._merge_source_attributes(

                product_attributes,

                source_attributes,

            )

        )



        product_attributes = (

            self._merge_source_genders(

                product_attributes,

                source_genders,

            )

        )



        # -----------------------------------------------------

        # 5. Consumed semantic surfaces

        # -----------------------------------------------------



        semantic_surfaces = [

            str(

                row.get("surface")

                or ""

            ).strip()

            for row

            in (

                semantic.get(

                    "known_evidence"

                )

                or []

            )

            if str(

                row.get("surface")

                or ""

            ).strip()

        ]



        # -----------------------------------------------------

        # 6. Consumed structural surfaces

        #

        # remove_from_core=False인 span도

        # Structural Analyzer가 이미 해석한 표현이다.

        #

        # 따라서 residual 후보에는 다시 등장시키지 않는다.

        # -----------------------------------------------------



        structural_surfaces = [

            str(

                row.get("raw")

                or ""

            ).strip()

            for row in structural_spans

            if str(

                row.get("raw")

                or ""

            ).strip()

        ]



        # -----------------------------------------------------

        # 7. Structural marketing

        #

        # Structural MarketingDetector가 이미 확정한 표현은

        # classifier로 다시 판정하지 않는다.

        # -----------------------------------------------------



        structural_marketing_surfaces = [

            str(

                row.get("raw")

                or ""

            ).strip()

            for row in structural_spans

            if (

                row.get("category")

                == "MARKETING"

                and str(

                    row.get("raw")

                    or ""

                ).strip()

            )

        ]



        # 중복 제거 + 순서 유지



        semantic_surfaces = list(

            dict.fromkeys(

                semantic_surfaces

            )

        )



        structural_surfaces = list(

            dict.fromkeys(

                structural_surfaces

            )

        )



        structural_marketing_surfaces = list(

            dict.fromkeys(

                structural_marketing_surfaces

            )

        )



        # -----------------------------------------------------

        # 8. Residual Candidate

        #

        # Semantic / Structural에서 이미 설명된 표현을 제외하고

        # 정말 남은 표현만 Noise Classifier로 보낸다.

        # -----------------------------------------------------



        residual_candidates = (

            self.residual_builder.build(

                raw_name=raw_name,

                used_surfaces=semantic_surfaces,

                structural_surfaces=(

                    structural_surfaces

                ),

                structural_tags=[],

            )

        )



        # -----------------------------------------------------

        # 9. Unified core-name noise decisions

        # -----------------------------------------------------



        noise_decisions = self.name_noise_processor.process(

            raw_name=raw_name,

            structural_spans=structural_spans,

            semantic_result=semantic,

            residual_candidates=residual_candidates,

        )



        remove_decisions = [

            {

                "text": d.text,

                "action": d.action,

                "reason": d.reason,

                "source": d.source,

                "start": d.start,

                "end": d.end,

                "term_id": d.term_id,

                "term_type": d.term_type,

                "preserve_as_product_term": d.preserve_as_product_term,

                "margin": d.margin,

            }

            for d in noise_decisions

        ]



        # Compatibility outputs for existing callers.

        noise_predictions = [

            row for row in remove_decisions

            if row["source"] in {"classifier", "marketing_rule", "technical_rule", "protected", "empty"}

        ]

        marketing_surfaces = list(dict.fromkeys(

            row["text"] for row in remove_decisions

            if row["action"] == "REMOVE"

        ))

        noise_review_surfaces = list(dict.fromkeys(

            row["text"] for row in remove_decisions

            if row["action"] == "REVIEW"

        ))

        kept_residual_tags = list(dict.fromkeys(

            row["text"] for row in remove_decisions

            if row["action"] in {"KEEP", "REVIEW"}

        ))



        # -----------------------------------------------------

        # 10. Core Name Builder

        # 의미 판단은 하지 않고 REMOVE span 적용 + punctuation cleanup만 한다.

        # -----------------------------------------------------



        core = self.core_name_builder.build(

            raw_name=raw_name,

            known_terms=semantic.get("known_evidence") or [],

            structural_spans=[],

            noise_surfaces=[],

            remove_spans=remove_decisions,

        )



        pre_refined_name = core.get("normalized_name") or raw_name

        final_normalized_name = pre_refined_name

        core_refinement = {

            "before": pre_refined_name,

            "after": final_normalized_name,

            "changed": False,

            "version": 2,

            "reason": "CoreNameBuilder is the final naming stage in v2.",

        }



        # -----------------------------------------------------

        # 13. Result

        # -----------------------------------------------------



        return {

            "version": self.VERSION,



            "product_source_id": (

                product_source.id

            ),



            "source_code": actual_source,



            "raw_name": raw_name,



            "semantic_input": (

                semantic_input

            ),



            "core_name": final_normalized_name,



            "normalized_name": final_normalized_name,



            "pre_refined_core_name": pre_refined_name,



            "core_refinement": core_refinement,



            # Structural

            "structural_spans": (

                structural_spans

            ),



            "structural_attributes": (

                structural.attributes

            ),



            # Semantic

            "semantic_tokens": (

                semantic.get(

                    "semantic_tokens"

                )

                or []

            ),



            "semantic_phrases": (

                semantic.get("phrases")

                or []

            ),



            "known_evidence": (

                source_semantic.get(

                    "known_evidence"

                )

                or []

            ),



            "known_by_type": (

                source_semantic.get(

                    "known_by_type"

                )

                or {}

            ),



            "unknown_terms": (

                semantic.get(

                    "unknown_terms"

                )

                or []

            ),



            "excluded_terms": (

                semantic.get(

                    "excluded_terms"

                )

                or []

            ),



            # Platform source evidence

            "source_tags": source_tags,



            "source_options": source_options,



            "source_attributes": source_attributes,



            "source_genders": source_genders,



            "source_tag_known_evidence": [

                evidence

                for row in source_evidence_semantics

                if row.get("source_field") == "SOURCE_TAG"

                for evidence in (row["semantic"].get("known_evidence") or [])

            ],



            "source_attribute_known_evidence": [

                evidence

                for row in source_evidence_semantics

                if row.get("source_field") == "SOURCE_ATTRIBUTE"

                for evidence in (row["semantic"].get("known_evidence") or [])

            ],



            # Final service attributes

            "product_attributes": (

                product_attributes

            ),



            # Residual / Noise

            "residual_tags": (

                kept_residual_tags

            ),



            "noise_decisions": remove_decisions,



            "noise_predictions": (

                noise_predictions

            ),



            "marketing_surfaces": (

                marketing_surfaces

            ),



            "noise_review_surfaces": (

                noise_review_surfaces

            ),



            # Core removal audit

            "removed_surfaces": (

                core.get(

                    "removed_surfaces"

                )

                or []

            ),

        }