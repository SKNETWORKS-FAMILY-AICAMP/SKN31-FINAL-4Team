from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from apps.core.models import DictionaryTerm


def normalize_dictionary_text(value: str | None) -> str:
    if not value:
        return ""

    text = str(value).lower().strip()
    text = text.replace("_", " ")
    text = text.replace("-", " ")
    text = re.sub(r"[^\w가-힣\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class ProductAttributeExtractor:
    """
    ProductSource 분석 소스:
    - PRODUCT_NAME
    - TAG
    - ZIGZAG_CNV_TREND
    - ZIGZAG_CNV_STYLE
    - ZIGZAG_CNV_TPO
    """

    CNV_SOURCE_MAP = {
        "trend": "ZIGZAG_CNV_TREND",
        "style": "ZIGZAG_CNV_STYLE",
        "styles": "ZIGZAG_CNV_STYLE",
        "tpo": "ZIGZAG_CNV_TPO",
    }

    CNV_SUGGESTED_TYPE = {
        "ZIGZAG_CNV_TREND": "STYLE",
        "ZIGZAG_CNV_STYLE": "STYLE",
        "ZIGZAG_CNV_TPO": "TPO",
    }

    def __init__(self):
        self._surface_index = {}
        self._surfaces_by_length = []
        self._load_dictionary()

    def _load_dictionary(self) -> None:
        terms = (
            DictionaryTerm.objects
            .filter(status=DictionaryTerm.Status.ACTIVE)
            .prefetch_related("aliases")
            .order_by("id")
        )

        index = {}

        for term in terms:
            self._register_surface(
                index=index,
                surface=term.canonical_name,
                term=term,
                match_type="CANONICAL",
            )

            for alias in term.aliases.all():
                self._register_surface(
                    index=index,
                    surface=getattr(alias, "alias", None),
                    term=term,
                    match_type="ALIAS",
                )

        self._surface_index = index
        self._surfaces_by_length = sorted(
            index.items(),
            key=lambda row: (len(row[0]), row[0]),
            reverse=True,
        )

    @staticmethod
    def _register_surface(
        *,
        index: dict,
        surface: str | None,
        term,
        match_type: str,
    ) -> None:
        normalized = normalize_dictionary_text(surface)
        if not normalized:
            return

        row = {
            "term_id": term.id,
            "term_code": getattr(term, "term_code", None),
            "term_type": getattr(term, "term_type", None),
            "canonical_name": getattr(term, "canonical_name", None),
            "attribute_type": getattr(term, "attribute_type", None),
            "match_type": match_type,
            "dictionary_surface": surface,
        }

        bucket = index.setdefault(normalized, [])
        if not any(
            existing.get("term_id") == row["term_id"]
            for existing in bucket
        ):
            bucket.append(row)

    def extract_text(
        self,
        text: str | None,
        *,
        source_field: str,
        source_index: int | None = None,
        source_meta: dict[str, Any] | None = None,
        exact_only: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:

        raw_text = str(text or "").strip()
        if not raw_text:
            return {"known": [], "unknown": []}

        normalized_text = normalize_dictionary_text(raw_text)
        if not normalized_text:
            return {"known": [], "unknown": []}

        known = []
        seen_term_ids = set()

        if exact_only:
            candidates = self._surface_index.get(normalized_text, [])

            for match in candidates:
                term_id = match.get("term_id")
                if term_id in seen_term_ids:
                    continue
                seen_term_ids.add(term_id)

                row = dict(match)
                row.update(
                    {
                        "surface": raw_text,
                        "source_field": source_field,
                        "source_index": source_index,
                        "source_text": raw_text,
                        "source_meta": source_meta or {},
                    }
                )
                known.append(row)

            if known:
                return {"known": known, "unknown": []}

            unknown = {
                "text": raw_text,
                "surface": raw_text,
                "source_field": source_field,
                "source_index": source_index,
                "source_text": raw_text,
                "candidate_source": "EXACT_UNMATCHED",
                "source_meta": source_meta or {},
            }

            suggested_type = self.CNV_SUGGESTED_TYPE.get(source_field)
            if suggested_type:
                unknown["suggested_type"] = suggested_type

            return {"known": [], "unknown": [unknown]}

        # PRODUCT_NAME phrase matching: longest surface first.
        occupied = []

        for normalized_surface, matches in self._surfaces_by_length:
            for hit in re.finditer(
                re.escape(normalized_surface),
                normalized_text,
                flags=re.IGNORECASE,
            ):
                start, end = hit.span()

                if any(
                    start >= left and end <= right
                    for left, right in occupied
                ):
                    continue

                for match in matches:
                    term_id = match.get("term_id")
                    if term_id in seen_term_ids:
                        continue

                    seen_term_ids.add(term_id)

                    row = dict(match)
                    row.update(
                        {
                            "surface": (
                                match.get("dictionary_surface")
                                or normalized_surface
                            ),
                            "source_field": source_field,
                            "source_index": source_index,
                            "source_text": raw_text,
                            "source_meta": source_meta or {},
                        }
                    )
                    known.append(row)

                occupied.append((start, end))

        # 상품명 UNKNOWN은 여기서 자동 candidate로 만들지 않는다.
        return {"known": known, "unknown": []}

    def extract_product(
        self,
        *,
        product_source,
        normalized_name: str,
        tags: list | tuple | None = None,
    ) -> dict[str, Any]:

        attributes = (
            product_source.attributes
            if isinstance(product_source.attributes, dict)
            else {}
        )

        tags = list(tags) if isinstance(tags, (list, tuple)) else []

        known_evidence = []
        unknown_evidence = []

        # 1) PRODUCT NAME
        name_result = self.extract_text(
            normalized_name,
            source_field="PRODUCT_NAME",
            exact_only=False,
        )
        known_evidence.extend(name_result["known"])
        unknown_evidence.extend(name_result["unknown"])

        # 2) SOURCE TAG
        for index, tag in enumerate(tags):
            if isinstance(tag, dict):
                tag_text = (
                    tag.get("term")
                    or tag.get("name")
                    or tag.get("value")
                    or tag.get("text")
                )
            else:
                tag_text = tag

            tag_text = str(tag_text or "").strip()
            if not tag_text:
                continue

            tag_result = self.extract_text(
                tag_text,
                source_field="TAG",
                source_index=index,
                exact_only=True,
            )
            known_evidence.extend(tag_result["known"])
            unknown_evidence.extend(tag_result["unknown"])

        # 3) ZIGZAG CNV
        observed_tags = (
            attributes.get("observed_tags")
            if isinstance(attributes.get("observed_tags"), list)
            else []
        )

        for index, observation in enumerate(observed_tags):
            if not isinstance(observation, dict):
                continue

            tag_text = str(
                observation.get("tag")
                or observation.get("name")
                or ""
            ).strip()

            if not tag_text:
                continue

            group = str(
                observation.get("group")
                or observation.get("attribute")
                or ""
            ).strip().lower()

            source_field = self.CNV_SOURCE_MAP.get(
                group,
                "ZIGZAG_CNV",
            )

            source_meta = {
                "group": group or None,
                "group_label": observation.get("group_label"),
                "rank": observation.get("rank"),
                "result_count": observation.get("result_count"),
                "order": observation.get("order"),
            }

            cnv_result = self.extract_text(
                tag_text,
                source_field=source_field,
                source_index=index,
                source_meta=source_meta,
                exact_only=True,
            )
            known_evidence.extend(cnv_result["known"])
            unknown_evidence.extend(cnv_result["unknown"])

        # aggregate known
        known_map = {}

        for item in known_evidence:
            term_id = item.get("term_id")
            key = (
                ("ID", term_id)
                if term_id is not None
                else (
                    "NAME",
                    item.get("term_type"),
                    item.get("canonical_name"),
                )
            )

            if key not in known_map:
                known_map[key] = {
                    "term_id": term_id,
                    "term_code": item.get("term_code"),
                    "term_type": item.get("term_type"),
                    "canonical_name": item.get("canonical_name"),
                    "attribute_type": item.get("attribute_type"),
                    "surfaces": [],
                    "source_fields": [],
                    "evidence_count": 0,
                    "evidence": [],
                }

            agg = known_map[key]

            surface = item.get("surface")
            if surface and surface not in agg["surfaces"]:
                agg["surfaces"].append(surface)

            sf = item.get("source_field")
            if sf and sf not in agg["source_fields"]:
                agg["source_fields"].append(sf)

            agg["evidence_count"] += 1

            evidence_row = {
                "source_field": sf,
                "surface": surface,
                "source_index": item.get("source_index"),
                "match_type": item.get("match_type"),
                "source_meta": item.get("source_meta") or {},
            }

            if evidence_row not in agg["evidence"]:
                agg["evidence"].append(evidence_row)

        known_terms = list(known_map.values())

        # aggregate unknown
        unknown_map = {}

        for item in unknown_evidence:
            text = str(item.get("text") or "").strip()
            if not text:
                continue

            key = text.casefold()

            if key not in unknown_map:
                unknown_map[key] = {
                    "text": text,
                    "source_fields": [],
                    "surfaces": [],
                    "evidence_count": 0,
                    "suggested_type": item.get("suggested_type"),
                    "evidence": [],
                }

            agg = unknown_map[key]

            sf = item.get("source_field")
            if sf and sf not in agg["source_fields"]:
                agg["source_fields"].append(sf)

            surface = item.get("surface")
            if surface and surface not in agg["surfaces"]:
                agg["surfaces"].append(surface)

            if not agg.get("suggested_type") and item.get("suggested_type"):
                agg["suggested_type"] = item.get("suggested_type")

            agg["evidence_count"] += 1

            evidence_row = {
                "source_field": sf,
                "source_index": item.get("source_index"),
                "surface": surface,
                "source_meta": item.get("source_meta") or {},
            }

            if evidence_row not in agg["evidence"]:
                agg["evidence"].append(evidence_row)

        unknown_terms = list(unknown_map.values())

        by_type = defaultdict(list)
        for item in known_terms:
            term_type = item.get("term_type") or "UNKNOWN_TYPE"
            canonical_name = item.get("canonical_name")
            if (
                canonical_name
                and canonical_name not in by_type[term_type]
            ):
                by_type[term_type].append(canonical_name)

        evidence_summary = defaultdict(int)
        for item in known_evidence + unknown_evidence:
            evidence_summary[
                item.get("source_field") or "UNKNOWN"
            ] += 1

        return {
            "product_source_id": product_source.id,
            "source": getattr(
                getattr(product_source, "source", None),
                "code",
                None,
            ),
            "normalized_name": normalized_name,
            "tags": list(tags),
            "known_terms": known_terms,
            "known_by_type": dict(by_type),
            "unknown_terms": unknown_terms,
            "known_evidence": known_evidence,
            "unknown_evidence": unknown_evidence,
            "evidence_summary": dict(evidence_summary),
            "summary": {
                "known_count": len(known_terms),
                "unknown_count": len(unknown_terms),
                "known_evidence_count": len(known_evidence),
                "unknown_evidence_count": len(unknown_evidence),
                "cnv_observation_count": len(observed_tags),
            },
        }
