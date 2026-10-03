"""어휘 게이트 — 사전에 있는 말만 통과시킨다.

설계서 3.3 의 3단 추출을 그대로 쓴다. 이미 실데이터로 검증했다.
    재현율   style 100% · material 100% · item 99.1% · brand 100%
    헛걸림   일상 문장 18개 중 1건 (tpo:운동 — 수식어 축이라 게이트를 통과 못 함)

`tools/question_extract.py` 를 import 해서 쓴다. 복사하지 않는다 —
복사하면 한쪽만 고쳐지고 두 곳이 다른 판정을 하게 된다.
"""
from __future__ import annotations

import sys
import re
import unicodedata

from .config import EXTRACTOR_DIR, LEXICON_PATH, SEARCH_FACETS

if str(EXTRACTOR_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTOR_DIR))

_CRAWLER_ADDED = False


def _norm(value):
    value = unicodedata.normalize("NFC", str(value or ""))
    return re.sub(r"[\s\-_·/&,\.\(\)\[\]]+", "", value).lower()


class _RDSLexicon:
    """RDS dictionary_term/term_alias/brand를 QuestionExtractor 계약으로 노출한다."""
    _risky = {"면", "마", "짐", "백", "폴", "캡", "운동", "여행", "출근", "데이트",
              "캠핑", "휴가", "하객", "골프", "학생", "기본", "러닝", "클래식", "모던"}

    def __init__(self, rows):
        self.surfaces = {}
        self.facet_of = {}
        self.trendable = {}
        for row in rows:
            canonical = str(row.get("canonical") or "").strip()
            facet = str(row.get("facet") or "").strip().lower()
            if not canonical or not facet:
                continue
            self.facet_of.setdefault(canonical, facet)
            self.trendable.setdefault(canonical, facet not in {"season", "body"})
            for surface in [canonical, *(row.get("aliases") or [])]:
                key = _norm(surface)
                if key: self.surfaces.setdefault(key, (canonical, facet))
        self._ordered = sorted(self.surfaces, key=len, reverse=True)
        self._free = [key for key in self._ordered
                      if len(key) >= 2 and key not in self._risky and self.surfaces[key][1] != "brand"]

    def exact(self, raw, facet=None):
        found = self.surfaces.get(_norm(raw))
        return found if found and (facet is None or found[1] == facet) else None

    def extract(self, text, mode="product"):
        hay, out, seen = _norm(text), [], set()
        for surface in (self._free if mode == "free" else self._ordered):
            index = hay.find(surface)
            if index < 0:
                continue
            canonical, facet = self.surfaces[surface]
            if canonical not in seen:
                seen.add(canonical); out.append((canonical, facet))
            hay = hay[:index] + "\0" * len(surface) + hay[index + len(surface):]
        return out


def _lexicon_cls():
    """crawler 의 Lexicon 을 import 한다. crawler 파일은 읽기만 하고 고치지 않는다."""
    global _CRAWLER_ADDED
    if not _CRAWLER_ADDED:
        from .config import CRAWLER
        sys.path.insert(0, str(CRAWLER))
        _CRAWLER_ADDED = True
    from feedit_crawler.lexicon import Lexicon
    return Lexicon


class LexiconGate:
    def __init__(self, store):
        from question_extract import QuestionExtractor
        if hasattr(store, "lexicon_entries"):
            self.lex = _RDSLexicon(store.lexicon_entries())
        else:
            Lexicon = _lexicon_cls()
            self.lex = Lexicon(str(LEXICON_PATH))
        # 접힘 되돌리기 — 지표에 자기 이름으로 있는 말은 접지 않는다
        self.prefer = store.metric_canonicals()
        self.qx = QuestionExtractor(self.lex, prefer_canonicals=self.prefer)

    def facet_of(self, canonical: str) -> str | None:
        return self.lex.facet_of.get(canonical)

    def term_key(self, canonical: str) -> str:
        return f"{self.facet_of(canonical)}:{canonical}"

    def parse(self, question: str) -> dict:
        """질문 → {search[], modifier[], other[]}

        search    스타일·소재·아이템·브랜드. 검색어로 쓴다
        modifier  핏·컬러·디테일·TPO. 수식어로만 읽는다
        other     계절·체형 등 비트렌드 축
        """
        hits = self.qx.extract(question)
        out = {"search": [], "modifier": [], "other": []}
        for h in hits:
            h = dict(h)
            h["term_key"] = f"{h['facet']}:{h['canonical']}"
            if h["role"] == "search" and h["trendable"]:
                out["search"].append(h)
            elif h["role"] == "modifier":
                out["modifier"].append(h)
            else:
                out["other"].append(h)
        return out

    # ── 사전에 없을 때 ────────────────────────────────────
    def near_candidates(self, question: str, limit: int = 3) -> list[dict]:
        """가까운 말을 골라 준다. 실패로 끝내지 않는다.

        ★ 돌려 보고 고쳤다. "우리 랩실에서 회의했어요" 에 `랩 · 리 · 우아` 가 나왔다.
          브랜드 사전에 1~2글자 항목이 410개 있어서(설계서 3.3) 그게 그대로 샜다.
          후보는 사용자가 눌러서 다시 물어볼 말이다. 쓰레기를 주면 안 누른다.

        규칙 셋.
          · 3글자 이상만 (1~2글자 브랜드가 노이즈의 전부였다)
          · 지표에 실제로 적재된 말만 (눌렀는데 "데이터 없음" 이 뜨면 두 번 실망한다)
          · 첫 글자만 같은 건 안 친다. 두 글자 이상 겹쳐야 한다

        지금은 문자열 겹침. 나중에 lexicon_embedding 이 생기면 의미 검색으로 바꾼다.
        """
        import re
        toks = [t for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", question)]
        if not toks:
            return []
        scored = []
        for canon, facet in self.lex.facet_of.items():
            if facet not in SEARCH_FACETS or len(canon) < 3:
                continue
            if canon not in self.prefer:      # 지표 없는 말은 후보로 주지 않는다
                continue
            best = 0
            for t in toks:
                if canon == t:
                    best = max(best, 100)
                elif t in canon or canon in t:
                    best = max(best, 60 + min(len(t), len(canon)))
                elif canon[:2] == t[:2]:
                    best = max(best, 30)
            if best:
                scored.append((best, canon, facet))
        scored.sort(key=lambda x: (-x[0], len(x[1])))
        return [{"canonical": c, "facet": f} for _, c, f in scored[:limit]]

    def popular(self, store, limit: int = 3) -> list[dict]:
        rows = store.top_terms(limit=limit)
        return [{"canonical": r["canonical"], "facet": r["facet"]} for r in rows]
