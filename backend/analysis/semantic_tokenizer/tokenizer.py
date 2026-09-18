from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from apps.core.models import DictionaryTerm


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


# ============================================================
# NORMALIZATION
# ============================================================

MULTISPACE_RE = re.compile(r"\s+")

# FEEDIT tokenizer 내부 의미 경계.
# 하이픈(-)은 A-라인 / MA-1 / XS-XL 등의 의미 보존 때문에 제외한다.
TOKEN_SEPARATOR_RE = re.compile(
    r"[\s+&/|,·•ㆍ]+"
)


def normalize_match_text(text: str | None) -> str:
    """
    Dictionary matching 전용 정규화.
    과도한 전처리는 하지 않고:
    - NFKC
    - trim
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
        data/sentencepiece 안에서 8k 모델을 우선 탐색.
        파일명이 달라도 .model 하나만 있으면 자동 사용.
        """

        if not SPM_DIR.exists():
            return None

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
        """
        DB DictionaryTerm / TermAlias를 다시 읽는다.

        Alias를 DB에 추가한 뒤에는:
            reload_tokenizer_dictionary()
        또는
            tokenizer.reload_dictionary()
        실행.
        """

        active_terms = (
            DictionaryTerm.objects
            .filter(
                status=DictionaryTerm.Status.ACTIVE
            )
            .prefetch_related("aliases")
            .order_by("id")
        )

        entries: list[dict] = []

        for term in active_terms:
            canonical = normalize_match_text(
                term.canonical_name
            )

            if canonical:
                entries.append(
                    self._build_entry(
                        term=term,
                        match_surface=canonical,
                        match_type="CANONICAL",
                    )
                )

            for alias_obj in term.aliases.all():
                alias = normalize_match_text(
                    alias_obj.alias
                )

                if not alias:
                    continue

                entries.append(
                    self._build_entry(
                        term=term,
                        match_surface=alias,
                        match_type="ALIAS",
                    )
                )

        # 긴 표현 우선
        entries.sort(
            key=lambda x: x["length"],
            reverse=True,
        )

        self.match_entries = entries

        # ----------------------------------------------------
        # Compound component authority:
        # DictionaryTerm / TermAlias 자체를 그대로 사용한다.
        # 문자열 suffix(기장/허리/핏/소매/넥...)를 잘라서
        # 가짜 component를 만들지 않는다.
        #
        # prefix 쪽은 term_type에 상관없이 기존 dictionary entry라면
        # MATERIAL / COLOR / STYLE / DETAIL / ITEM 모두 조합 가능하다.
        #
        # right-head 여부만 term_type metadata로 제한한다.
        self.component_entries = list(entries)

        self.multiword_entries = [
            entry
            for entry in entries
            if " " in entry["match_surface"]
        ]

        self.multiword_entries.sort(
            key=lambda x: x["length"],
            reverse=True,
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

        for entry in self.match_entries:
            if (
                entry["match_surface"]
                == normalized
            ):
                return entry

        return None

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
        '일반 기장' 안에서 '반 기장'이 잘못 잡히는 문제 방지.
        """

        return (
            (
                start == 0
                or text[
                    start - 1
                ].isspace()
            )
            and (
                end == len(text)
                or text[end].isspace()
            )
        )

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

        # 1) exact dictionary always wins
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

        # 2) partial dictionary coverage
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
        1. ITEM 바로 앞이 UNKNOWN이면:
           연속 UNKNOWN만 묶는다.
           -> 워크 + 자켓
           -> 미니 + 스커트

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

        # A. UNKNOWN이 ITEM에 직접 붙은 경우
        if self._is_unknown_modifier(prev):
            start = item_index - 1

            while start - 1 >= 0:
                before = tokens[start - 1]

                if not self._is_unknown_modifier(
                    before
                ):
                    break

                start -= 1

            return start

        # B. 의미가 명확한 DETAIL이 ITEM에 직접 붙은 경우
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

        composed = (
            self.compose_semantic_phrases(
                tokens
            )
        )

        return {
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,

            # 기존 코드 호환용 atomic 분석.
            "tokens": tokens,

            # 서비스/트렌드 분석용 상위 의미 단위.
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
            +  &  /  |  ,  ·  •  ㆍ  whitespace

        split 하지 않음:
            -

        이유:
            A-라인, MA-1, XS-XL 같은 표현 보존.
        """

        output = []

        chunks = [
            chunk.strip()
            for chunk in TOKEN_SEPARATOR_RE.split(
                str(text or "")
            )
            if chunk.strip()
        ]

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