from __future__ import annotations

import re
import unicodedata
from typing import Any


class ProductCoreNameRefiner:
    """STEP02 final core-name refinement.

    Former STEP03 behavior, folded into STEP02 without DB access.

    Policy
    - Remove decorative leading wrappers by default.
    - Keep a leading wrapper when it contains an ITEM or MATERIAL term
      found by the current STEP02 semantic analysis.
    - Remove conservative slash-separated SEO tails only when at least
      one tail value is already explained by normalized attributes.
    - Never write to DB.
    """

    PROTECTED_TERM_TYPES = {"ITEM", "MATERIAL"}

    LEADING_WRAPPER_RE = re.compile(
        r"""^\s*(?P<wrapper>
            \((?P<paren>[^()]*)\)
            |
            \[(?P<bracket>[^\[\]]*)\]
            |
            \{(?P<brace>[^{}]*)\}
        )""",
        re.VERBOSE,
    )

    def refine(
        self,
        *,
        value: str,
        known_evidence: list[dict[str, Any]] | None = None,
        normalized_attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        before = str(value or "").strip()

        if not before:
            return {
                "before": "",
                "after": "",
                "changed": False,
                "removed": [],
                "protected": [],
            }

        protected_terms = self._get_protected_terms(known_evidence or [])
        normalized_values = self._get_normalized_values(
            normalized_attributes or {}
        )

        after, removed, protected = self._refine_leading_wrappers(
            before,
            protected_terms,
        )

        after, suffix_removed = self._remove_suffix_seo_tail(
            after,
            normalized_values,
        )
        removed.extend(suffix_removed)

        after = self._cleanup(after)

        if not after:
            after = before
            removed = []

        return {
            "before": before,
            "after": after,
            "changed": before != after,
            "removed": removed,
            "protected": protected,
        }

    def _refine_leading_wrappers(
        self,
        value: str,
        protected_terms: list[str],
    ) -> tuple[str, list[str], list[str]]:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        removed: list[str] = []
        protected: list[str] = []

        while True:
            match = self.LEADING_WRAPPER_RE.match(text)
            if not match:
                break

            wrapper = match.group("wrapper")
            body = (
                match.group("paren")
                or match.group("bracket")
                or match.group("brace")
                or ""
            )
            body = self._normalize_text(body)

            if self._is_residue(body):
                removed.append(wrapper)
                text = text[match.end():].lstrip()
                continue

            matched_terms = self._find_protected_terms(
                wrapper_body=body,
                protected_terms=protected_terms,
            )

            if matched_terms:
                protected.append(wrapper)
                break

            removed.append(wrapper)
            text = text[match.end():].lstrip()

        return self._cleanup(text), removed, protected

    def _remove_suffix_seo_tail(
        self,
        value: str,
        normalized_values: list[str],
    ) -> tuple[str, list[str]]:
        text = str(value or "").strip()

        if "/" not in text:
            return text, []

        parts = [part.strip() for part in text.split("/")]

        if len(parts) < 3:
            return text, []

        first = parts[0].strip()
        tail = [part for part in parts[1:] if part]

        if not first or len(tail) < 2:
            return text, []

        short_count = sum(1 for part in tail if len(part) <= 20)
        if short_count / len(tail) < 0.8:
            return text, []

        normalized_known = []
        for item in normalized_values:
            normalized = self._normalize_compare(item)
            if normalized:
                normalized_known.append(normalized)

        known_count = 0
        for part in tail:
            normalized_part = self._normalize_compare(part)
            if not normalized_part:
                continue

            for known in normalized_known:
                if known in normalized_part or normalized_part in known:
                    known_count += 1
                    break

        if known_count == 0:
            return text, []

        removed_surface = "/" + "/".join(tail)
        return first, [removed_surface]

    def _get_protected_terms(
        self,
        known_evidence: list[dict[str, Any]],
    ) -> list[str]:
        values: list[str] = []

        for row in known_evidence:
            if not isinstance(row, dict):
                continue

            term_type = str(row.get("term_type") or "").upper()
            if term_type not in self.PROTECTED_TERM_TYPES:
                continue

            value = str(
                row.get("canonical_name")
                or row.get("surface")
                or ""
            ).strip()

            if value:
                values.append(value)

        return list(dict.fromkeys(values))

    @staticmethod
    def _get_normalized_values(
        normalized_attributes: dict[str, Any],
    ) -> list[str]:
        values: list[str] = []

        for items in normalized_attributes.values():
            if not isinstance(items, list):
                continue

            for value in items:
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
                elif isinstance(value, dict):
                    for key in ("canonical_name", "value", "name"):
                        nested = value.get(key)
                        if isinstance(nested, str) and nested.strip():
                            values.append(nested.strip())
                            break

        return list(dict.fromkeys(values))

    def _find_protected_terms(
        self,
        *,
        wrapper_body: str,
        protected_terms: list[str],
    ) -> list[str]:
        body = self._normalize_compare(wrapper_body)
        if not body:
            return []

        found: list[str] = []
        for term in protected_terms:
            normalized_term = self._normalize_compare(term)
            if normalized_term and normalized_term in body:
                found.append(term)

        return list(dict.fromkeys(found))

    @staticmethod
    def _is_residue(value: str) -> bool:
        text = re.sub(r"(?:까지|부터)", "", str(value or ""))
        text = re.sub(
            r'''[\s\d!！?？*＊~～\-–—_/|,+·•:;.'"`]+''',
            "",
            text,
        )
        return not bool(text.strip())

    @staticmethod
    def _normalize_text(value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_compare(value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        return re.sub(
            r'''[\s!！?？*＊~～\-–—_/|,+·•:;.'"`]+''',
            "",
            text,
        )

    @staticmethod
    def _cleanup(value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        text = "".join(
            char
            for char in text
            if unicodedata.category(char)[0] != "C" or char in "\t\n"
        )

        previous = None
        while previous != text:
            previous = text
            text = re.sub(r"\(\s*\)", " ", text)
            text = re.sub(r"\[\s*\]", " ", text)
            text = re.sub(r"\{\s*\}", " ", text)

        text = re.sub(
            r'''[(\[{]\s*[~～\-–—_/|.,·:;!*]*\s*
                (?:까지|부터)?\s*
                [~～\-–—_/|.,·:;!*]*\s*[)\]}]''',
            " ",
            text,
            flags=re.VERBOSE,
        )
        text = re.sub(r"([\(\[\{])\s*[/|,+·;:]+\s*", r"\1", text)
        text = re.sub(r"\s*[/|,+·;:]+\s*([\)\]\}])", r"\1", text)
        text = re.sub(r"\(\s*\)", " ", text)
        text = re.sub(r"\[\s*\]", " ", text)
        text = re.sub(r"\{\s*\}", " ", text)
        text = re.sub(r"\s*_{2,}\s*", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(
            r'''^\s*[!！?？\.,，:;|·•~～*＊_/+]+\s*''',
            "",
            text,
            flags=re.VERBOSE,
        )
        text = re.sub(
            r'''\s*[!！?？\.,，:;|·•~～*＊_/+]+\s*$''',
            "",
            text,
            flags=re.VERBOSE,
        )
        return re.sub(r"\s+", " ", text).strip()
