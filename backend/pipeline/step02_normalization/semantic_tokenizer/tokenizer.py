from __future__ import annotations



import logging

import re

import time

import unicodedata

from pathlib import Path

from typing import Any



from django.db.models import Prefetch

from apps.core.models import Brand, DictionaryTerm, DiscoveryExclusion





# ============================================================

# OPTIONAL NLP DEPENDENCIES

# ============================================================



try:

    from kiwipiepy import Kiwi

except Exception:

    Kiwi = None



try:

    import sentencepiece as spm

except Exception:

    spm = None





# ============================================================

# PATHS

# ============================================================



THIS_DIR = Path(__file__).resolve().parent

SPM_DIR = THIS_DIR / "data" / "sentencepiece"

logger = logging.getLogger(__name__)





# ============================================================

# NORMALIZATION

# ============================================================



MULTISPACE_RE = re.compile(r"\s+")



# FEEDIT tokenizer 내부 의미 경계.

# 하이픈(-)은 A-라인 / MA-1 / XS-XL 등의 의미 보존 때문에 제외한다.

TOKEN_SEPARATOR_RE = re.compile(

    r"[\s+&/|,·•ㆍ_]+"

)



# 상품 옵션 개수: 3color / 2 colors / 4컬러

COLOR_COUNT_RE = re.compile(

    r"^\d+\s*(?:color|colors|컬러)$",

    re.IGNORECASE,

)



# 괄호형/독립형 상품 코드.

# 너무 짧은 일반 영문은 제외하고 숫자를 포함하는 코드형 문자열만 처리.
PRODUCT_CODE_RE = re.compile(
    r"^\(?(?=[-a-z0-9._/]*\d)[-a-z0-9._/]{6,}\)?$",
    re.IGNORECASE,
)

def normalize_match_text(text: str | None) -> str:

    """

    Dictionary matching 전용 정규화.

    과도한 전처리는 하지 않고:

    - NFKC

    - trim
fv
    - lowercase

    - 다중 공백 축소

    """

    if not text:

        return ""



    text = unicodedata.normalize(

        "NFKC",

        str(text),

    )



    text = MULTISPACE_RE.sub(

        " ",

        text,

    ).strip()



    return text.lower()





# ============================================================

# TOKENIZER

# ============================================================



class FEEDITSemanticTokenizer:

    """

    FEEDIT 상품/태그용 semantic tokenizer.



    흐름

    ----

    1. DictionaryTerm canonical + TermAlias exact match

    2. multi-word dictionary match

    3. Dictionary metadata 기반 partial coverage segmentation

    4. UNKNOWN residual 생성

    5. UNKNOWN에 대해 Kiwi / whitespace / SentencePiece 보조 후보 생성

    6. ITEM head 기반 semantic phrase composition



    중요

    ----

    - SentencePiece는 의미 판정 authority가 아님.

    - Dictionary exact match가 항상 우선.

    - compound head는 DictionaryTerm.term_type metadata로 판정.

    - 문자열 suffix 하드코딩으로 component를 생성하지 않음.

    - 일부만 매칭돼도 KNOWN은 살리고 residual만 UNKNOWN으로 남김.

    - 1글자 alias는 ITEM일 때만 compound head로 허용.

    """



    # Compound right-head 허용 정책.

    # 문자열 suffix가 아니라 DictionaryTerm.term_type metadata를 사용한다.

    COMPOUND_HEAD_TERM_TYPES = {

        "ITEM",

        "DETAIL",

    }



    KIWI_POS = {

        "NNG",

        "NNP",

        "SL",

        "SH",

    }



    SIZE_SURFACES = {

        "xs",

        "s",

        "m",

        "l",

        "xl",

        "xxl",

        "xxxl",

        "2xl",

        "3xl",

        "4xl",

        "f",

        "free",

        "free size",

        "onesize",

        "one size",

    }



    # ITEM_PHRASE로 ITEM과 결합해도 되는 DETAIL metadata.

    #

    # ex)

    #   커브드 + 팬츠 -> 커브드팬츠

    #   부츠컷 + 팬츠 -> 부츠컷팬츠

    #   맥시 + 원피스 -> 맥시원피스

    #

    # ETC / DECORATION / NECKLINE 등은 기본적으로

    # 상품 속성으로 별도 보존한다.

    ITEM_PHRASE_DETAIL_TYPES = {

        "SILHOUETTE",

        "FIT",

        "LENGTH",

    }



    def __init__(

        self,

        *,

        sentencepiece_model_path: str | Path | None = None,

    ):

        self.kiwi = (

            Kiwi()

            if Kiwi is not None

            else None

        )



        self.sp = None



        model_path = (

            Path(sentencepiece_model_path)

            if sentencepiece_model_path

            else self._discover_sentencepiece_model()

        )



        if (

            spm is not None

            and model_path is not None

            and model_path.exists()

        ):

            self.sp = (

                spm.SentencePieceProcessor()

            )



            self.sp.load(

                str(model_path)

            )



        self.match_entries: list[dict] = []

        self.component_entries: list[dict] = []

        self.multiword_entries: list[dict] = []



        self.reload_dictionary()



    # ========================================================

    # SENTENCEPIECE

    # ========================================================



    @staticmethod

    def _discover_sentencepiece_model() -> Path | None:

        """

        FEEDIT production SentencePiece model 탐색.



        우선순위:

        1. feedit_spm_8k_v3.model

        2. 이름에 8k / 8000이 포함된 model

        3. 첫 번째 .model

        """



        if not SPM_DIR.exists():

            return None



        # retrain_feedit.py가 최신 학습 모델을 이 이름으로 승격한다.

        current_model = SPM_DIR / "feedit_spm_current.model"

        if current_model.exists():

            return current_model



        production_model = SPM_DIR / "feedit_spm_8k_v3.model"

        if production_model.exists():

            return production_model



        models = sorted(

            SPM_DIR.glob("*.model")

        )



        if not models:

            return None



        preferred = [

            p

            for p in models

            if "8k" in p.name.lower()

            or "8000" in p.name.lower()

        ]



        if preferred:

            return preferred[0]



        return models[0]



    # ========================================================

    # DICTIONARY LOAD

    # ========================================================



    def reload_dictionary(self) -> None:
        """DB 사전을 bulk load하여 tokenizer index를 재구성한다.

        핵심 원칙:
        - DictionaryTerm.detail N+1 제거
        - TermAlias prefetch 1회
        - Brand -> BrandSource N+1 제거
        - Brand -> DictionaryTerm forward relation이 있으면 select_related
        - 이후 entry/index 구성 중 DB query 없음
        """
        total_started = time.perf_counter()
        checkpoint = total_started

        def log_stage(label: str, **extra) -> None:
            nonlocal checkpoint
            now = time.perf_counter()
            suffix = " ".join(f"{k}={v}" for k, v in extra.items())
            logger.info(
                "[TOKENIZER INIT] %-28s stage=%7.3fs total=%7.3fs %s",
                label, now - checkpoint, now - total_started, suffix,
            )
            checkpoint = now

        logger.info("[TOKENIZER INIT] START")

        active_terms = list(
            DictionaryTerm.objects
            .filter(status=DictionaryTerm.Status.ACTIVE)
            .select_related("detail")
            .prefetch_related("aliases")
            .order_by("id")
        )
        log_stage("dictionary loaded", terms=len(active_terms))

        exclusion_rows = list(
            DiscoveryExclusion.objects
            .filter(is_active=True)
            .order_by("id")
        )
        self.exclusion_map = {}
        for exclusion in exclusion_rows:
            normalized = normalize_match_text(
                exclusion.normalized_term or exclusion.term
            )
            if not normalized:
                continue
            self.exclusion_map.setdefault(
                normalized,
                {
                    "reason": exclusion.reason,
                    "term": exclusion.term,
                    "source_id": exclusion.source_id,
                },
            )
        log_stage("exclusions built", exclusions=len(self.exclusion_map))

        entries: list[dict] = []
        for term in active_terms:
            canonical = normalize_match_text(term.canonical_name)
            if canonical:
                entries.append(
                    self._build_entry(
                        term=term,
                        match_surface=canonical,
                        match_type="CANONICAL",
                    )
                )

            # prefetch cache 사용. 여기서는 추가 query가 발생하지 않는다.
            seen_aliases: set[str] = set()
            for alias_obj in term.aliases.all():
                alias = normalize_match_text(alias_obj.alias)
                if not alias or alias == canonical or alias in seen_aliases:
                    continue
                seen_aliases.add(alias)
                entries.append(
                    self._build_entry(
                        term=term,
                        match_surface=alias,
                        match_type="ALIAS",
                    )
                )
        log_stage("term entries built", entries=len(entries))

        # BrandSource reverse accessor는 클래스 metadata에서 한 번만 찾는다.
        brand_source_accessors: list[str] = []
        for rel in Brand._meta.related_objects:
            related_model = getattr(rel, "related_model", None)
            if related_model is not None and related_model.__name__ == "BrandSource":
                accessor = rel.get_accessor_name()
                if accessor and accessor not in brand_source_accessors:
                    brand_source_accessors.append(accessor)

        # Brand -> DictionaryTerm forward relation이 실제로 존재하는 경우만
        # select_related 한다. property/역참조를 억지로 조회하지 않는다.
        brand_term_relations: list[str] = []
        for field in Brand._meta.fields:
            if field.name not in {"term", "dictionary_term"}:
                continue
            remote_model = getattr(getattr(field, "remote_field", None), "model", None)
            if remote_model is DictionaryTerm:
                brand_term_relations.append(field.name)

        active_brands = Brand.objects.all().order_by("id")
        brand_field_names = {f.name for f in Brand._meta.fields}
        if "status" in brand_field_names:
            active_value = getattr(
                getattr(Brand, "Status", object),
                "ACTIVE",
                "ACTIVE",
            )
            active_brands = active_brands.filter(status=active_value)

        if brand_term_relations:
            active_brands = active_brands.select_related(*brand_term_relations)
        if brand_source_accessors:
            active_brands = active_brands.prefetch_related(*brand_source_accessors)

        active_brands = list(active_brands)
        log_stage(
            "brands loaded",
            brands=len(active_brands),
            source_relations=len(brand_source_accessors),
        )

        for brand in active_brands:
            linked_term = None
            for attr_name in brand_term_relations:
                candidate = getattr(brand, attr_name, None)
                if (
                    candidate is not None
                    and getattr(candidate, "status", None) == DictionaryTerm.Status.ACTIVE
                    and getattr(candidate, "term_type", None) == "BRAND"
                ):
                    linked_term = candidate
                    break

            brand_surfaces: list[tuple[str, str]] = []
            for attr_name, match_type in (
                ("name", "BRAND_CANONICAL"),
                ("english_name", "BRAND_ENGLISH"),
            ):
                value = getattr(brand, attr_name, None)
                if value:
                    brand_surfaces.append((value, match_type))

            for accessor in brand_source_accessors:
                manager = getattr(brand, accessor, None)
                if manager is None:
                    continue
                # prefetch cache를 사용하므로 brand별 SELECT가 발생하지 않는다.
                for source_brand in manager.all():
                    if getattr(source_brand, "mapping_status", None) == "EXCLUDED":
                        continue
                    for attr_name, match_type in (
                        ("name", "BRAND_SOURCE"),
                        ("english_name", "BRAND_SOURCE_ENGLISH"),
                    ):
                        value = getattr(source_brand, attr_name, None)
                        if value:
                            brand_surfaces.append((value, match_type))

            seen_brand_surfaces: set[str] = set()
            for raw_surface, match_type in brand_surfaces:
                surface = normalize_match_text(raw_surface)
                if not surface or surface in seen_brand_surfaces:
                    continue
                seen_brand_surfaces.add(surface)
                entries.append(
                    self._build_brand_entry(
                        brand=brand,
                        linked_term=linked_term,
                        match_surface=surface,
                        match_type=match_type,
                    )
                )
        log_stage("brand entries built", entries=len(entries))

        # 동일 term_type + normalized surface 중복 제거.
        # Brand direct entry가 DictionaryTerm BRAND entry보다 우선한다.
        deduped_entries: dict[tuple[str | None, str | None], dict] = {}
        for entry in entries:
            key = (entry.get("term_type"), entry.get("match_surface"))
            current = deduped_entries.get(key)
            if current is None:
                deduped_entries[key] = entry
                continue
            if entry.get("brand_id") is not None and current.get("brand_id") is None:
                deduped_entries[key] = entry

        entries = list(deduped_entries.values())
        entries.sort(key=lambda x: x["length"], reverse=True)
        self.match_entries = entries

        # O(1) exact lookup. 기존 list scan은 entry 증가에 따라 매 호출이 느려졌다.
        self.exact_match_index: dict[str, dict] = {}
        for entry in entries:
            surface = entry["match_surface"]
            self.exact_match_index.setdefault(surface, entry)

        # BRAND는 partial compound segmentation에서 제외한다.
        self.component_entries = [
            entry for entry in entries
            if entry.get("term_type") != "BRAND"
        ]

        self.multiword_entries = [
            entry for entry in entries
            if " " in entry["match_surface"]
        ]
        self.multiword_entries.sort(key=lambda x: x["length"], reverse=True)

        # MATERIAL 동형어 해소도 전체 match_entries scan 대신 index 사용.
        self.material_match_index: dict[str, list[dict]] = {}
        for entry in entries:
            if entry.get("term_type") != "MATERIAL":
                continue
            for key in {
                entry.get("match_surface"),
                normalize_match_text(entry.get("canonical")),
            }:
                if key:
                    self.material_match_index.setdefault(key, []).append(entry)

        log_stage(
            "indexes built",
            match_entries=len(self.match_entries),
            components=len(self.component_entries),
            multiword=len(self.multiword_entries),
        )
        logger.info(
            "[TOKENIZER INIT] COMPLETE total=%.3fs",
            time.perf_counter() - total_started,
        )

    @staticmethod

    def _build_entry(

        *,

        term,

        match_surface: str,

        match_type: str,

    ) -> dict:

        """

        tokenizer output에 필요한 Dictionary 정보 보존.

        """



        attribute_type = None



        try:

            detail = term.detail

        except Exception:

            detail = None



        if detail is not None:

            attribute_type = getattr(

                detail,

                "attribute_type",

                None,

            )



        return {

            "term_id": term.id,

            "term_code": (

                term.term_code

            ),

            "term_type": (

                term.term_type

            ),

            "canonical": (

                term.canonical_name

            ),

            "normalized_name": (

                term.normalized_name

            ),

            "match_surface": (

                match_surface

            ),

            "match_type": (

                match_type

            ),

            "attribute_type": (

                attribute_type

            ),

            "component_type": None,

            "length": len(

                match_surface

            ),

        }



    @staticmethod

    def _build_brand_entry(

        *,

        brand,

        linked_term,

        match_surface: str,

        match_type: str,

    ) -> dict:

        """

        Brand / BrandSource를 tokenizer dictionary entry 형태로 변환.



        Brand가 DictionaryTerm(BRAND)와 연결되어 있으면

        term_id / term_code도 함께 보존한다.

        """



        canonical = (

            brand.name

            or brand.english_name

            or getattr(brand, "brand_code", None)

            or f"BRAND_{brand.id}"

        )



        return {

            "term_id": (

                linked_term.id

                if linked_term is not None

                else None

            ),

            "term_code": (

                linked_term.term_code

                if linked_term is not None

                else None

            ),

            "term_type": "BRAND",

            "canonical": canonical,

            "normalized_name": (

                normalize_match_text(

                    canonical

                )

            ),

            "match_surface": match_surface,

            "match_type": match_type,

            "attribute_type": None,

            "component_type": None,

            "length": len(match_surface),



            # Brand-specific metadata

            "brand_id": brand.id,

            "brand_code": getattr(brand, "brand_code", None),

            "brand_name": brand.name,

            "brand_english_name": (

                brand.english_name

            ),

        }



    # ========================================================

    # KNOWN TOKEN BUILD

    # ========================================================



    @staticmethod

    def _known_token(

        *,

        surface: str,

        entry: dict,

    ) -> dict:

        return {

            "kind": "KNOWN",

            "surface": surface,

            "term_id": entry.get(

                "term_id"

            ),

            "term_code": entry.get(

                "term_code"

            ),

            "term_type": entry.get(

                "term_type"

            ),

            "canonical": entry.get(

                "canonical"

            ),

            "canonical_name": entry.get(

                "canonical"

            ),

            "match_type": entry.get(

                "match_type"

            ),

            "attribute_type": entry.get(

                "attribute_type"

            ),

            "component_type": entry.get(

                "component_type"

            ),



            # BRAND token metadata

            "brand_id": entry.get(

                "brand_id"

            ),

            "brand_code": entry.get(

                "brand_code"

            ),

            "brand_name": entry.get(

                "brand_name"

            ),

            "brand_english_name": entry.get(

                "brand_english_name"

            ),

        }



    # ========================================================

    # EXACT

    # ========================================================



    def exact_dictionary_match(

        self,

        text: str,

    ) -> dict | None:

        normalized = normalize_match_text(

            text

        )



        if not normalized:

            return None



        return self.exact_match_index.get(normalized)



    # ========================================================

    # MULTI-WORD

    # ========================================================



    @staticmethod

    def is_phrase_boundary(

        text: str,

        start: int,

        end: int,

    ) -> bool:

        """

        Multi-word dictionary phrase의 좌우 경계 판정.



        FEEDIT 상품명에서는 whitespace뿐 아니라

        괄호/슬래시/언더스코어 등의 구분자도

        phrase boundary로 인정한다.



        예:

            "레더 워크 자켓_FS3WJ35U"

                ^^^^^^^^^

            -> "워크 자켓" 매칭 허용



            "[HIGH NECK]"

            ^^^^^^^^^

            -> "HIGH NECK" 매칭 허용



        단, 일반 문자 내부의 부분 문자열 매칭은 차단한다.

        """



        def is_boundary_char(

            char: str,

        ) -> bool:

            if char.isspace():

                return True



            return char in {

                "_",

                "/",

                "|",

                "+",

                "&",

                ",",

                "·",

                "•",

                "ㆍ",

                ";",

                ":",

                "(",

                ")",

                "[",

                "]",

                "{",

                "}",

                "<",

                ">",

            }



        left_ok = (

            start == 0

            or is_boundary_char(

                text[start - 1]

            )

        )



        right_ok = (

            end == len(text)

            or is_boundary_char(

                text[end]

            )

        )



        return left_ok and right_ok



    def match_multiword_dictionary(

        self,

        text: str,

    ) -> list[dict]:

        """

        전체 문장에서 multi-word DictionaryTerm을 먼저 lock.

        """



        normalized = normalize_match_text(

            text

        )



        if not normalized:

            return []



        occupied = [

            False

            for _ in normalized

        ]



        matches = []



        for entry in self.multiword_entries:

            target = entry[

                "match_surface"

            ]



            start = 0



            while True:

                idx = normalized.find(

                    target,

                    start,

                )



                if idx < 0:

                    break



                end = idx + len(target)



                if not self.is_phrase_boundary(

                    normalized,

                    idx,

                    end,

                ):

                    start = idx + 1

                    continue



                if any(

                    occupied[idx:end]

                ):

                    start = idx + 1

                    continue



                for i in range(

                    idx,

                    end,

                ):

                    occupied[i] = True



                matches.append({

                    "start": idx,

                    "end": end,

                    "surface": normalized[

                        idx:end

                    ],

                    "entry": entry,

                })



                start = end



        matches.sort(

            key=lambda x: x["start"]

        )



        return matches



    # ========================================================

    # COMPOUND

    # ========================================================



    @classmethod

    def is_compound_head_entry(

        cls,

        entry: dict,

    ) -> bool:

        """

        오른쪽 compound head 가능 여부를

        DictionaryTerm.term_type metadata로 판정한다.

        """

        return (

            entry.get("term_type")

            in cls.COMPOUND_HEAD_TERM_TYPES

        )



    def find_right_head(

        self,

        text: str,

    ) -> dict | None:

        normalized = normalize_match_text(

            text

        )



        candidates = []



        for entry in self.component_entries:

            target = entry[

                "match_surface"

            ]



            # 위험한 1글자 alias 차단.

            # 단, ITEM alias는 '티 -> 티셔츠'처럼 compound에 유용.

            if (

                len(target) == 1

                and entry["match_type"]

                == "ALIAS"

                and entry["term_type"]

                != "ITEM"

            ):

                continue



            if not self.is_compound_head_entry(

                entry

            ):

                continue



            if not normalized.endswith(

                target

            ):

                continue



            start = (

                len(normalized)

                - len(target)

            )



            candidates.append({

                "start": start,

                "end": len(

                    normalized

                ),

                "entry": entry,

            })



        if not candidates:

            return None



        candidates.sort(

            key=lambda x: x["entry"][

                "length"

            ],

            reverse=True,

        )



        return candidates[0]



    def _candidate_matches_at(

        self,

        text: str,

        pos: int,

    ) -> list[dict]:

        """

        현재 위치에서 시작하는 dictionary 후보를 모두 반환.



        우선순위는 여기서 확정하지 않고,

        coverage segmentation 단계에서 전체 경로를 비교한다.

        """

        candidates = []



        for entry in self.component_entries:

            target = entry["match_surface"]



            if not target:

                continue



            # 위험한 1글자 alias는 compound 내부에서 제한.

            if (

                len(target) == 1

                and entry["match_type"] == "ALIAS"

                and entry["term_type"] != "ITEM"

            ):

                continue



            # 짧은 ITEM alias(특히 "티")가 다른 단어 내부에

            # 끼어드는 false positive를 막는다.

            #

            # 예:

            #   니티드   -> 니 + 티 + 드      (금지)

            #   뷔스티에 -> 뷔스 + 티 + 에    (금지)

            #   티       -> 티셔츠            (허용)

            #

            # 한 글자 surface는 독립 token 경계에서만 허용한다.

            if len(target) == 1:

                end = pos + len(target)



                left_ok = (

                    pos == 0

                    or not text[pos - 1].isalnum()

                )

                right_ok = (

                    end == len(text)

                    or not text[end].isalnum()

                )



                if not (left_ok and right_ok):

                    continue



            if text.startswith(target, pos):

                candidates.append({

                    "start": pos,

                    "end": pos + len(target),

                    "entry": entry,

                })



        return candidates



    @staticmethod

    def _match_score(

        entry: dict,

    ) -> tuple:

        """

        동일 coverage일 때의 tie-breaker.



        CANONICAL > ALIAS > COMPONENT

        긴 표현 우선.

        """

        match_type_rank = {

            "CANONICAL": 3,

            "ALIAS": 2,

            "COMPONENT": 1,

        }



        return (

            match_type_rank.get(

                entry.get("match_type"),

                0,

            ),

            entry.get("length", 0),

        )



    def segment_by_dictionary_coverage(

        self,

        text: str,

    ) -> list[dict]:

        """

        문자열 전체를 dictionary coverage 최대화 기준으로 분해.



        목표

        ----

        1. KNOWN으로 설명되는 문자 수 최대화

        2. UNKNOWN span 수 최소화

        3. 같은 coverage면 canonical / 긴 term 우선



        중요한 점

        ---------

        전체 prefix가 100% dictionary로 설명되지 않아도

        KNOWN 부분은 살리고, 정말 못 설명한 부분만 UNKNOWN으로 남긴다.

        """

        normalized = normalize_match_text(text)



        if not normalized:

            return []



        n = len(normalized)



        # dp[i] = i 위치부터 끝까지의 최적 결과

        # value = (known_coverage, -unknown_chars, -segments, score, tokens)

        dp: list[tuple | None] = [None] * (n + 1)

        dp[n] = (0, 0, 0, (), [])



        for i in range(n - 1, -1, -1):

            best = None



            # 1) dictionary match 후보

            for match in self._candidate_matches_at(

                normalized,

                i,

            ):

                j = match["end"]

                tail = dp[j]



                if tail is None:

                    continue



                entry = match["entry"]

                surface = normalized[i:j]



                token = self._known_token(

                    surface=surface,

                    entry=entry,

                )



                score = (

                    len(surface) + tail[0],

                    tail[1],

                    tail[2] - 1,

                    (

                        self._match_score(entry),

                        *tail[3],

                    ),

                    [token, *tail[4]],

                )



                if (

                    best is None

                    or score[:4] > best[:4]

                ):

                    best = score



            # 2) 현재 문자 하나를 UNKNOWN으로 넘기는 후보

            tail = dp[i + 1]



            if tail is not None:

                unknown_score = (

                    tail[0],

                    tail[1] - 1,

                    tail[2] - 1,

                    ((0, 0), *tail[3]),

                    [

                        {

                            "kind": "_UNKNOWN_CHAR",

                            "surface": normalized[i],

                        },

                        *tail[4],

                    ],

                )



                if (

                    best is None

                    or unknown_score[:4] > best[:4]

                ):

                    best = unknown_score



            dp[i] = best



        raw_tokens = dp[0][4] if dp[0] else []



        # 연속 UNKNOWN char를 하나의 span으로 합친다.

        merged: list[dict] = []

        unknown_buffer = []



        def flush_unknown() -> None:

            nonlocal unknown_buffer



            if not unknown_buffer:

                return



            surface = "".join(unknown_buffer)



            merged.append(

                self._unknown_token(surface)

            )



            unknown_buffer = []



        for token in raw_tokens:

            if token.get("kind") == "_UNKNOWN_CHAR":

                unknown_buffer.append(

                    token["surface"]

                )

                continue



            flush_unknown()

            merged.append(token)



        flush_unknown()



        return merged



    @staticmethod

    def _excluded_token(

        *,

        surface: str,

        reason: str,

        match_type: str = "DISCOVERY_EXCLUSION",

    ) -> dict:

        return {

            "kind": "EXCLUDED",

            "surface": surface,

            "normalized": surface,

            "term_id": None,

            "term_code": None,

            "term_type": None,

            "canonical": None,

            "canonical_name": None,

            "match_type": match_type,

            "attribute_type": None,

            "component_type": None,

            "semantic_role": None,

            "exclusion_reason": reason,

        }



    def _match_exclusion(

        self,

        text: str,

    ) -> dict | None:

        normalized = normalize_match_text(

            text

        )



        if not normalized:

            return None



        info = getattr(

            self,

            "exclusion_map",

            {},

        ).get(normalized)



        if info is not None:

            return self._excluded_token(

                surface=normalized,

                reason=info.get("reason") or "OTHER",

            )



        # 옵션 개수: 3color, 2 colors, 4컬러

        if COLOR_COUNT_RE.fullmatch(

            normalized

        ):

            return self._excluded_token(

                surface=normalized,

                reason="PRODUCT_META",

                match_type="PRODUCT_META_RULE",

            )



        # 상품 코드: KYOR1RLR02W / ABC-12345 등.

        # 숫자가 반드시 포함되어야 일반 영단어 오탐을 줄인다.

        code_candidate = normalized.strip(

            "()[]{}"

        )



        if (

            any(ch.isdigit() for ch in code_candidate)

            and PRODUCT_CODE_RE.fullmatch(normalized)

        ):

            return self._excluded_token(

                surface=normalized,

                reason="PRODUCT_META",

                match_type="PRODUCT_CODE_RULE",

            )



        return None



    @staticmethod

    def _split_fashion_chunks(

        text: str,

    ) -> list[str]:

        """

        FEEDIT 상품명 gap splitter.



        일반 separator:

            whitespace, +, &, /, |, comma, ·, _, 괄호



        hyphen:

            쇼핑몰 SEO tag-chain에서는 separator로 사용하되

            A-라인 / MA-1 / XS-XL 같은 의미 있는 표현은 보존한다.

        """



        text = str(text or "").strip()



        if not text:

            return []



        # 괄호 자체는 의미 토큰이 아니므로 경계로 취급.

        text = re.sub(

            r"[()\[\]{}]",

            " ",

            text,

        )



        protected: dict[str, str] = {}



        def protect(match):

            key = f"zzprotectedhyphen{len(protected)}zz"

            protected[key] = match.group(0)

            return key



        # A-라인

        text = re.sub(

            r"\b[aA]-라인\b",

            protect,

            text,

        )



        # MA-1 / M-65 같은 패션 코드

        text = re.sub(

            r"\b[A-Za-z]{1,4}-\d{1,4}\b",

            protect,

            text,

        )



        # XS-XL / S-L 등의 size range

        text = re.sub(

            r"\b(?:XXS|XS|S|M|L|XL|XXL|XXXL)"

            r"-(?:XXS|XS|S|M|L|XL|XXL|XXXL)\b",

            protect,

            text,

            flags=re.IGNORECASE,

        )

        chunks = [
            chunk.strip()
            for chunk in TOKEN_SEPARATOR_RE.split(text)
            if chunk.strip()
        ]

        result = []


        for chunk in chunks:

            for key, original in protected.items():

                chunk = chunk.replace(

                    key,

                    original,

                )



            if chunk:

                result.append(chunk)



        return result



    def parse_fashion_chunk(

        self,

        text: str,

    ) -> list[dict]:

        """

        한 whitespace/separator chunk 처리.



        우선순위

        --------

        1. exact dictionary

        2. dictionary coverage segmentation

        3. 못 설명한 부분만 UNKNOWN



        과거처럼 prefix 전체가 100% match되어야만

        KNOWN을 살리는 all-or-nothing 방식은 사용하지 않는다.

        """

        normalized = normalize_match_text(

            text

        )



        if not normalized:

            return []



        # 0) 단순 사이즈 표기.

        if normalized in self.SIZE_SURFACES:

            return [{

                "kind": "SIZE",

                "surface": normalized,

                "normalized": normalized,

                "term_id": None,

                "term_code": None,

                "term_type": None,

                "canonical": normalized.upper(),

                "canonical_name": normalized.upper(),

                "match_type": "SIZE_RULE",

                "attribute_type": None,

                "component_type": None,

            }]



        # 1) exact dictionary always wins.

        # 같은 surface가 exclusion에도 있어도 정식 사전이 우선한다.

        exact = self.exact_dictionary_match(

            normalized

        )



        if exact is not None:

            return [

                self._known_token(

                    surface=normalized,

                    entry=exact,

                )

            ]



        # 2) exclusion / product meta.

        excluded = self._match_exclusion(

            normalized

        )



        if excluded is not None:

            return [excluded]



        # 3) partial dictionary coverage.

        return self.segment_by_dictionary_coverage(

            normalized

        )



    # ========================================================

    # UNKNOWN CANDIDATES

    # ========================================================



    @staticmethod

    def termhood_filter(

        text: str,

    ) -> bool:

        """

        최소한의 후보 필터.

        너무 공격적으로 제거하지 않음.

        """



        text = str(

            text or ""

        ).strip()



        if not text:

            return False



        if len(text) == 1:

            return False



        if text.isdigit():

            return False



        if re.fullmatch(

            r"[\W_]+",

            text,

            flags=re.UNICODE,

        ):

            return False



        if re.fullmatch(

            r"\d+(?:\.\d+)?%",

            text,

        ):

            return False



        return True



    def extract_unknown_candidates(

        self,

        surface: str,

    ) -> list[dict]:

        """

        UNKNOWN span 하나에서 후보 생성.



        우선:

        - ORIGINAL

        - WHITESPACE

        - KIWI

        - SentencePiece는 AUX evidence

        """



        surface = str(

            surface or ""

        ).strip()



        if not surface:

            return []



        rows: list[dict] = []



        # original

        rows.append({

            "text": surface,

            "source": "ORIGINAL",

            "reason": (

                "dictionary 미매칭 원문"

            ),

        })



        # whitespace

        for piece in surface.split():

            rows.append({

                "text": piece,

                "source": "WHITESPACE",

                "reason": (

                    "공백 단위 후보"

                ),

            })



        # Kiwi

        if self.kiwi is not None:

            try:

                for token in self.kiwi.tokenize(

                    surface

                ):

                    if (

                        token.tag

                        not in self.KIWI_POS

                    ):

                        continue



                    rows.append({

                        "text": token.form,

                        "source": "KIWI",

                        "tags": [

                            token.tag

                        ],

                        "reason": (

                            "Kiwi 명사/외국어 후보"

                        ),

                    })



            except Exception:

                pass



        # SentencePiece auxiliary

        if self.sp is not None:

            try:

                pieces = (

                    self.sp.encode(

                        surface,

                        out_type=str,

                    )

                )



                for piece in pieces:

                    clean_piece = (

                        piece

                        .replace("▁", "")

                        .strip()

                    )



                    if not clean_piece:

                        continue



                    rows.append({

                        "text": clean_piece,

                        "source": "SPM_AUX",

                        "reason": (

                            "SentencePiece 보조 분절"

                        ),

                    })



            except Exception:

                pass



        # normalize / filter / dedupe

        output = []

        seen = set()



        for row in rows:

            text = str(

                row.get("text")

                or ""

            ).strip()



            if not self.termhood_filter(

                text

            ):

                continue



            key = text.casefold()



            if key in seen:

                continue



            seen.add(key)



            row["text"] = text

            output.append(row)



        return output



    def _unknown_token(

        self,

        surface: str,

    ) -> dict:

        return {

            "kind": "UNKNOWN",

            "surface": surface,

            "candidates": (

                self.extract_unknown_candidates(

                    surface

                )

            ),

        }



    # ========================================================

    # SEMANTIC PHRASE COMPOSITION

    # ========================================================



    def _is_item_phrase_detail(

        self,

        token: dict,

    ) -> bool:

        """

        ITEM 바로 앞에서 ITEM_PHRASE modifier로 결합 가능한

        DETAIL인지 metadata로 판정한다.

        """

        return (

            token.get("kind") == "KNOWN"

            and token.get("term_type") == "DETAIL"

            and token.get("attribute_type")

            in self.ITEM_PHRASE_DETAIL_TYPES

        )



    @staticmethod

    def _is_unknown_modifier(

        token: dict,

    ) -> bool:

        """

        아직 사전에 없지만 ITEM 바로 앞에 붙은 residual 표현.



        ex)

            워크 + 자켓

            미니 + 스커트

        """

        return (

            token.get("kind") == "UNKNOWN"

            and bool(

                str(

                    token.get("surface")

                    or ""

                ).strip()

            )

        )



    def _item_phrase_start(

        self,

        tokens: list[dict],

        item_index: int,

    ) -> int:

        """

        ITEM head 앞에서 phrase 시작점을 결정한다.



        핵심 정책

        ---------

        1. UNKNOWN은 ITEM phrase modifier로 사용하지 않는다.

           UNKNOWN은 candidate/discovery 단계에서 별도 처리한다.



        2. ITEM 바로 앞이 DETAIL이고

           attribute_type이 SILHOUETTE/FIT/LENGTH이면:

           연속된 같은 계열의 의미 modifier를 묶는다.

           -> 커브드 + 팬츠

           -> 맥시 + 원피스



        3. STYLE / MATERIAL / ETC / DECORATION 등은

           phrase boundary로 보고 별도 속성으로 보존한다.



        이렇게 해야:

            하이웨스트 + 미니 + 스커트

        에서

            하이웨스트 / 미니스커트

        로 남는다.

        """

        if item_index <= 0:

            return item_index



        prev = tokens[item_index - 1]



        # UNKNOWN은 semantic ITEM phrase의 modifier로 사용하지 않는다.

        #

        # UNKNOWN + ITEM을 자동 합성하면 아래 같은 false positive가 생긴다.

        #   케찹 + 수트       -> 케찹수트

        #   니 + 티           -> 니티

        #   홀터탑 + ( + 브라 -> 홀터탑(브라

        #   넘버 + 트레이닝팬츠 -> 넘버트레이닝팬츠

        #

        # UNKNOWN은 candidate/discovery 단계에서 따로 다루고,

        # semantic phrase는 사전으로 의미가 확정된 modifier만 사용한다.

        if self._is_unknown_modifier(prev):

            return item_index



        # 의미가 명확한 DETAIL이 ITEM에 직접 붙은 경우

        if self._is_item_phrase_detail(prev):

            start = item_index - 1



            while start - 1 >= 0:

                before = tokens[start - 1]



                if not self._is_item_phrase_detail(

                    before

                ):

                    break



                start -= 1



            return start



        return item_index



    @staticmethod

    def _build_item_phrase(

        parts: list[dict],

    ) -> dict:

        """

        atomic token을 잃지 않고 상위 ITEM_PHRASE를 생성한다.

        """

        head = parts[-1]

        modifiers = parts[:-1]



        surface = "".join(

            str(

                token.get("surface")

                or ""

            )

            for token in parts

        )



        return {

            "kind": "COMPOSED",

            "phrase_type": "ITEM_PHRASE",

            "surface": surface,

            "head": {

                "surface": head.get("surface"),

                "term_id": head.get("term_id"),

                "term_code": head.get("term_code"),

                "canonical_name": head.get(

                    "canonical_name"

                ),

                "term_type": head.get(

                    "term_type"

                ),

                "match_type": head.get(

                    "match_type"

                ),

            },

            "modifiers": [

                {

                    "surface": token.get(

                        "surface"

                    ),

                    "kind": token.get(

                        "kind"

                    ),

                    "term_id": token.get(

                        "term_id"

                    ),

                    "canonical_name": (

                        token.get(

                            "canonical_name"

                        )

                    ),

                    "term_type": token.get(

                        "term_type"

                    ),

                    "attribute_type": (

                        token.get(

                            "attribute_type"

                        )

                    ),

                }

                for token in modifiers

            ],

            # 원자 분석 결과를 그대로 남겨 추적 가능하게 함.

            "atomic_tokens": parts,

            "composition_rule": (

                "ITEM_HEAD_NEAREST_MODIFIER"

            ),

        }



    def _resolve_item_material_homonyms(

        self,

        tokens: list[dict],

    ) -> list[dict]:

        """

        ITEM / MATERIAL 동형어를 문맥으로 해소한다.



        가능하면 실제 MATERIAL DictionaryTerm entry로 교체하여

        term_id / term_code / term_type 정합성을 유지한다.

        """



        MATERIAL_CAPABLE_ITEMS = {

            "니트",

            "저지",

        }



        resolved = [

            dict(token)

            for token in tokens

        ]



        def find_material_entry(

            token: dict,

        ) -> dict | None:

            surface = normalize_match_text(

                token.get("surface")

            )

            canonical = normalize_match_text(

                token.get("canonical_name")

            )



            candidates = list(
                self.material_match_index.get(surface, [])
            )

            if canonical and canonical != surface:
                for entry in self.material_match_index.get(canonical, []):
                    if entry not in candidates:
                        candidates.append(entry)

            if not candidates:

                return None



            candidates.sort(

                key=lambda entry: (

                    entry.get("match_type")

                    == "CANONICAL",

                    entry.get("length", 0),

                ),

                reverse=True,

            )



            return candidates[0]



        for i, token in enumerate(

            resolved

        ):

            if (

                token.get("kind") != "KNOWN"

                or token.get("term_type") != "ITEM"

            ):

                continue



            canonical = token.get(

                "canonical_name"

            )



            if (

                canonical

                not in MATERIAL_CAPABLE_ITEMS

            ):

                continue



            if i + 1 >= len(resolved):

                continue



            next_token = resolved[i + 1]



            if not (

                next_token.get("kind")

                == "KNOWN"

                and next_token.get("term_type")

                == "ITEM"

            ):

                continue



            material_entry = (

                find_material_entry(token)

            )



            if material_entry is not None:

                replacement = self._known_token(

                    surface=token.get("surface") or "",

                    entry=material_entry,

                )

                replacement[

                    "semantic_role"

                ] = "MATERIAL"

                replacement[

                    "resolved_from_term_type"

                ] = "ITEM"



                resolved[i] = replacement

                continue



            token["semantic_role"] = "MATERIAL"

            token[

                "resolved_from_term_type"

            ] = "ITEM"



        return resolved



    def compose_semantic_phrases(

        self,

        tokens: list[dict],

    ) -> dict:

        """

        atomic tokens -> semantic tokens + phrases.



        `tokens` 자체는 기존 Product Enrichment 호환을 위해

        절대 변경하지 않는다.

        """

        semantic_tokens = []

        phrases = []



        i = 0



        while i < len(tokens):

            token = tokens[i]



            # ITEM을 만났을 때 뒤에서 modifier를 찾기보다는,

            # 현재 위치부터 다음 ITEM까지 작은 window를 확인한다.

            if (

                token.get("kind") == "KNOWN"

                and token.get("term_type") == "ITEM"

            ):

                # 앞의 modifier는 이미 semantic_tokens에 들어갔으므로

                # 현 구조에서는 단독 ITEM 유지.

                semantic_tokens.append(token)

                i += 1

                continue



            # 현재 위치 이후 첫 ITEM을 찾는다.

            item_index = None



            for j in range(

                i,

                len(tokens),

            ):

                current = tokens[j]



                if (

                    current.get("kind") == "KNOWN"

                    and current.get("term_type")

                    == "ITEM"

                ):

                    item_index = j

                    break



                # STYLE / MATERIAL / 일반 DETAIL 등 강한 boundary가 나오면

                # 현재 modifier window를 너무 멀리 확장하지 않는다.

                if j > i:

                    prev = tokens[j - 1]



                    if (

                        prev.get("kind") == "KNOWN"

                        and prev.get("term_type")

                        in {"STYLE", "MATERIAL", "COLOR", "TPO"}

                    ):

                        break



            if item_index is None:

                semantic_tokens.append(token)

                i += 1

                continue



            start = self._item_phrase_start(

                tokens,

                item_index,

            )



            # 현재 위치가 phrase 시작점보다 앞이면

            # 현재 token은 별도 semantic token.

            if i < start:

                semantic_tokens.append(token)

                i += 1

                continue



            if start == item_index:

                semantic_tokens.append(

                    tokens[item_index]

                )

                i = item_index + 1

                continue



            parts = tokens[

                start:item_index + 1

            ]



            phrase = self._build_item_phrase(

                parts

            )



            semantic_tokens.append(phrase)

            phrases.append(phrase)



            i = item_index + 1



        return {

            "semantic_tokens": semantic_tokens,

            "phrases": phrases,

        }



    # ========================================================

    # FULL TEXT

    # ========================================================



    def tokenize(

        self,

        text: str | None,

    ) -> dict:

        """

        Public tokenizer.

        """



        raw_text = str(

            text or ""

        )



        cleaned_text = (

            normalize_match_text(

                raw_text

            )

        )



        if not cleaned_text:

            return {

                "raw_text": raw_text,

                "cleaned_text": "",

                "tokens": [],

                "semantic_tokens": [],

                "phrases": [],

            }



        multiword_matches = (

            self.match_multiword_dictionary(

                cleaned_text

            )

        )



        tokens = []



        cursor = 0



        for match in multiword_matches:

            # 앞쪽 gap

            if cursor < match["start"]:

                gap = cleaned_text[

                    cursor:

                    match["start"]

                ]



                tokens.extend(

                    self._tokenize_gap(

                        gap

                    )

                )



            # multi-word known

            tokens.append(

                self._known_token(

                    surface=match["surface"],

                    entry=match["entry"],

                )

            )



            cursor = match["end"]



        # 마지막 gap

        if cursor < len(cleaned_text):

            tokens.extend(

                self._tokenize_gap(

                    cleaned_text[cursor:]

                )

            )



        resolved_tokens = (

            self._resolve_item_material_homonyms(

                tokens

            )

        )



        composable_tokens = [

            token

            for token in resolved_tokens

            if token.get("kind") != "EXCLUDED"

        ]



        composed = (

            self.compose_semantic_phrases(

                composable_tokens

            )

        )



        return {

            "raw_text": raw_text,

            "cleaned_text": cleaned_text,



            "tokens": resolved_tokens,



            "semantic_tokens": (

                composed["semantic_tokens"]

            ),

            "phrases": composed["phrases"],

        }



    def _tokenize_gap(

        self,

        text: str,

    ) -> list[dict]:

        """

        Dictionary multi-word match 이후 남은 gap 처리.



        공백뿐 아니라 상품명/태그에서 자주 쓰이는 의미 구분자도

        독립 chunk 경계로 본다.



        split:

            +  &  /  |  ,  ·  •  ㆍ  _  whitespace

            쇼핑몰 SEO tag-chain의 hyphen



        보호:

            A-라인, MA-1, XS-XL 같은 의미 있는 hyphen 표현.

        """



        output = []



        chunks = self._split_fashion_chunks(

            text

        )



        for chunk in chunks:

            output.extend(

                self.parse_fashion_chunk(

                    chunk

                )

            )



        return output





# ============================================================

# LAZY SINGLETON

# ============================================================



_TOKENIZER: FEEDITSemanticTokenizer | None = None





def get_feedit_tokenizer(

    *,

    force_reload: bool = False,

) -> FEEDITSemanticTokenizer:

    global _TOKENIZER



    if (

        _TOKENIZER is None

        or force_reload

    ):

        _TOKENIZER = (

            FEEDITSemanticTokenizer()

        )



    return _TOKENIZER





def reload_tokenizer_dictionary() -> None:

    """

    DB DictionaryTerm / TermAlias 수정 후 실행.

    """

    tokenizer = get_feedit_tokenizer()



    tokenizer.reload_dictionary()





def feedit_semantic_tokenize_v2(

    text: str | None,

) -> dict:

    """

    기존 notebook에서 사용하던 public 함수명 유지.

    """

    tokenizer = get_feedit_tokenizer()



    return tokenizer.tokenize(text)





def tokenize(

    text: str | None,

) -> dict:

    """

    FEEDIT tokenizer 공용 진입점.



    팀원 사용:

        from analysis.tokenizer import tokenize

    """

    tokenizer = get_feedit_tokenizer()



    return tokenizer.tokenize(text)