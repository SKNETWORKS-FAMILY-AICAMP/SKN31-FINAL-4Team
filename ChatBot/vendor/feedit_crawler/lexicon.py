"""
어휘 사전 — 태그와 상품명에서 스타일·핏·소재를 뽑아낸다.

이 파일이 하는 일은 하나다. **글자 뭉치를 우리 어휘로 바꾼다.**
    '오버핏셔츠'          → fit:오버핏 · item:셔츠
    '[MADE]릴카 언발 오프숄더 반팔 티셔츠'
                          → fit:언발 · fit:오프숄더 · fit:반팔 · item:티셔츠

왜 이게 중요한가:
  · 무신사에는 tags[] 가 있지만 지그재그·에이블리·크림에는 없다.
    사이트마다 다른 규칙을 짜면 다섯 벌을 만들고 다섯 벌을 고쳐야 한다.
    같은 사전을 '태그'에도 '상품명'에도 돌리면 한 벌로 끝난다.
  · 태그는 합성어라 통째로 사전에 넣으면 조합마다 항목이 필요하다.
    조각으로 넣고 부분 일치로 잡으면 조합은 저절로 풀린다.

★ 가장 긴 것부터 잡는다
  '오버핏' 을 먼저 잡아야 한다. '핏' 부터 잡으면 '오버핏' 이 영영 안 나온다.
  잡은 자리는 지워서 같은 글자가 두 번 세어지지 않게 한다.

★ 모르는 말은 버리지 않고 쌓아 둔다
  사전에 없는 태그는 '후보'로 모은다. 사람이 보고 승인하면 사전이 자란다.
  버리면 무엇을 놓치고 있는지 영영 알 수 없다.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable

import yaml

# 트렌드 지수에 안 쓰는 축 (계절·성별은 달력과 인구가 만드는 값이지
# 유행이 아니다. 섞으면 여름마다 '여름'이 1위가 된다.)
_HANGUL = re.compile(r'[가-힣]+')

NON_TREND_FACETS = {"season", "body"}


def _norm(s: str) -> str:
    """비교용 정규화 — 공백·기호를 없애고 소문자로.

    '오버 핏' 과 '오버핏', 'Y2K' 와 'y2k' 를 같게 본다.
    한글은 NFC 로 모아야 자모 분리된 파일에서도 맞는다.
    """
    s = unicodedata.normalize("NFC", str(s or ""))
    return re.sub(r"[\s\-_·/&,\.\(\)\[\]]+", "", s).lower()


class Lexicon:
    def __init__(self, path: str | Path = "config/lexicon.yaml"):
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        self.version = d.get("version", 0)

        blk = d.get("block") or {}
        self._block_exact = {_norm(x) for x in (blk.get("exact") or [])}
        self._block_pat = [re.compile(p) for p in (blk.get("pattern") or [])]

        # surface(표기) → (canonical, facet)
        self.surfaces: dict[str, tuple[str, str]] = {}
        self.facet_of: dict[str, str] = {}
        self.trendable: dict[str, bool] = {}

        for facet, spec in (d.get("terms") or {}).items():
            if isinstance(spec, dict):          # {trendable: false, words: [...]}
                groups = spec.get("words") or []
                trend = bool(spec.get("trendable", True))
            else:
                groups, trend = spec, True
            if facet in NON_TREND_FACETS:
                trend = False
            for grp in groups:
                canon = grp[0]
                self.facet_of[canon] = facet
                self.trendable[canon] = trend
                for sf in grp:
                    n = _norm(sf)
                    # 이미 있으면 덮지 않는다 — 먼저 등록된 축이 이긴다.
                    # 설계서의 '한 말은 한 축에만' 을 여기서 지킨다.
                    self.surfaces.setdefault(n, (canon, facet))

        # 엑셀 원본을 개발 시 한 번 정규화한 기준 사전. 관리자가 파일을 올리는
        # 구조가 아니라 프로젝트와 함께 배포되고 크롤러가 자동으로 읽는다.
        master = Path(path).with_name("lexicon_master.json")
        if master.exists():
            try:
                extra = json.loads(master.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                extra = {}
            for term in extra.get("terms") or []:
                canon = str(term.get("canonical") or "").strip()
                facet = str(term.get("facet") or "").strip()
                if not canon or not facet:
                    continue
                self.facet_of.setdefault(canon, facet)
                self.trendable.setdefault(canon, facet not in NON_TREND_FACETS)
                for sf in term.get("surfaces") or [canon]:
                    n = _norm(sf)
                    if n:
                        # YAML의 기존 수동 판정이 충돌 시 우선한다.
                        self.surfaces.setdefault(n, (canon, facet))

        # 긴 것부터. '오버핏' 이 '핏' 보다 먼저 걸려야 한다.
        self._ordered = sorted(self.surfaces, key=len, reverse=True)

        # ★★ 자유 글에서는 못 쓰는 표기 ★★
        #   상품명 안에서는 짧은 말도 안전하다 — 이미 옷 이야기이기 때문이다.
        #   '순면 티셔츠' 의 '면' 은 코튼이 맞다.
        #
        #   그런데 댓글·블로그 같은 **자유 글**에 같은 잣대를 대면 무너진다.
        #       '바람불면 날라갈거같아요'   → 면 → 코튼
        #       '뛰는 폼보고 마냥 웃을 수'  → 마 → 린넨
        #       '운동하는법을 찾아서'       → 운동 → tpo
        #   실제로 댓글 2,000건 중 1,059건이 이런 헛걸림 하나 때문에 담겼다.
        #   네이버 블로그도, 시어쉘 패딩이 '시스루' 가 된 것도 같은 뿌리다.
        #
        #   그래서 자유 글에서는 **짧거나 흔한 표기를 빼고** 본다.
        self._free = [sf for sf in self._ordered
                      if self._ok_free(sf) and self.surfaces[sf][1] != "brand"]

    #  ★ 길이로 자르면 안 된다
    #    처음엔 '세 글자 미만은 뺀다' 로 했더니 셔츠·니트·팬츠까지 날아갔다.
    #    문제는 길이가 아니라 **패션 밖에서 더 흔히 쓰는 말**인가다.
    #    아래는 그런 말만 손으로 골라 둔 것이다.
    RISKY = {
        # 한 글자 — 아무 낱말에나 박힌다
        "면",      # 바람불면 · 시작하면 · 측면
        "마",      # 마냥 · 마음 · 얼마
        "짐",      # 짐작 · 짐가방
        "백",      # 백만 · 백번
        "폴", "캡",
        # 패션 밖 뜻이 더 센 말
        "시어",    # 시어머니 · 시어쉘(경량 소재) ← 시스루로 오인됐다
        "골지",    # 골지라면
        "와플",    # 먹는 와플
        "운동", "여행", "출근", "데이트", "캠핑", "휴가", "하객",
        "골프", "학생", "기본",
        "러닝", "마라톤", "조깅", "등산", "클래식", "모던",
        # 옷 이름·검색어로는 쓰지만 자유 글에선 대개 딴 뜻이다
        #   '레이싱' → F1·게임 이야기가 훨씬 흔하다
        "레이싱",
        "회색", "흰색", "검정", "검은색", "빨강", "파랑",
        # 계절·성별 — 자유 글에선 대개 말 그대로의 뜻이다
        "봄", "여름", "가을", "겨울",
        "남성", "여성", "남자", "여자", "키즈", "아동",
    }

    @classmethod
    def _ok_free(cls, sf: str) -> bool:
        return sf not in cls.RISKY and len(sf) >= 2

    # ── 버릴 말인가 ──────────────────────────────────────────
    def is_blocked(self, raw: str) -> bool:
        s = unicodedata.normalize("NFC", str(raw or "")).strip()
        if _norm(s) in self._block_exact:
            return True
        return any(p.search(s) for p in self._block_pat)

    def exact(self, raw: str, facet: str | None = None) -> tuple[str, str] | None:
        """표기 전체가 사전 항목과 같을 때만 반환한다.

        브랜드처럼 짧은 이름이 많은 축은 상품명 부분 일치로 찾으면 `리`, `랩` 같은
        문자열이 대량 오탐된다. 별도 brand_name 필드에는 이 안전한 경로를 쓴다.
        """
        got = self.surfaces.get(_norm(raw))
        if not got or (facet is not None and got[1] != facet):
            return None
        return got

    # ── 글자 하나에서 어휘 뽑기 ──────────────────────────────
    def extract(self, text: str, mode: str = "product") -> list[tuple[str, str]]:
        """'오버핏셔츠' → [('오버핏','fit'), ('셔츠','item')]

        mode
          'product'  상품명·태그·카테고리. 이미 옷 이야기라 짧은 말도 믿는다.
          'free'     댓글·블로그 같은 자유 글. 짧고 흔한 표기는 뺀다.
                     안 그러면 '바람불면' 이 코튼이 된다.
        """
        hay = _norm(text)
        if not hay:
            return []
        out: list[tuple[str, str]] = []
        seen = set()
        for sf in (self._free if mode == "free" else self._ordered):
            i = hay.find(sf)
            if i < 0:
                continue
            canon, facet = self.surfaces[sf]
            if canon not in seen:
                seen.add(canon)
                out.append((canon, facet))
            # 잡은 자리를 지운다. 안 지우면 '반팔티' 가
            # 반팔·티셔츠·티 로 세 번 세어진다.
            hay = hay[:i] + "\x00" * len(sf) + hay[i + len(sf):]
        return out

    # ── 상품 하나에 태그 붙이기 ──────────────────────────────
    def tag(self, *, name: str = "", tags: Iterable[str] = (),
            category: str = "", free: str = "") -> dict:
        """상품 한 건의 태그를 뽑는다.

        어디서 나왔는지(field)를 같이 남긴다. 스키마의
        product_term_hit.field 가 그걸 받는다 — 태그에서 나온 '오버핏'과
        상품명에서 나온 '오버핏'은 신뢰도가 다르므로 가중치를 달리 준다.
        """
        hits: dict[str, dict] = {}
        unknown: list[str] = []

        def add(canon, facet, field, w):
            h = hits.setdefault(canon, {"term": canon, "facet": facet,
                                        "fields": {}, "weight": 0.0,
                                        "trendable": self.trendable.get(canon, True)})
            # 같은 말이 여러 곳에서 나오면 가장 센 자리의 가중치를 쓴다.
            h["fields"][field] = max(h["fields"].get(field, 0), w)
            h["weight"] = max(h["weight"], w)

        # ① 사이트가 붙여 준 태그 — 사람이 분류한 것이라 가장 믿을 만하다
        for t in tags or ():
            t = str(t or "").strip()
            if not t or self.is_blocked(t):
                continue
            got = self.extract(t)
            if not got:
                unknown.append(t)       # 모르는 말 → 후보로
                continue
            for canon, facet in got:
                add(canon, facet, "tag", 1.0)

        # ② 상품명 — 태그가 없는 사이트의 유일한 재료
        #    판매자가 검색 노출을 노리고 쓴 말이 섞이므로 가중치를 낮춘다.
        for canon, facet in self.extract(name):
            add(canon, facet, "name", 0.6)

        # ③ 카테고리 — 아이템 축은 여기가 가장 정확하다
        for canon, facet in self.extract(category):
            add(canon, facet, "category", 0.9 if facet == "item" else 0.5)

        # ④ 자유 글(후기·댓글·블로그) — 뜻이 겹치는 짧은 말은 빼고 본다
        for canon, facet in self.extract(free, "free"):
            add(canon, facet, "body", 0.5)

        return {"hits": sorted(hits.values(), key=lambda h: -h["weight"]),
                "unknown": unknown}

    # ── 사전에 없던 말 모으기 ────────────────────────────────
    def survey(self, rows: Iterable[dict]) -> dict:
        """여러 상품을 훑어 '사전이 못 잡은 말'을 세어 돌려준다.

        사전을 키우는 근거가 된다. 자주 나오는데 못 잡는 말이
        곧 다음에 넣어야 할 항목이다.
        """
        from collections import Counter
        miss, cover, total = Counter(), 0, 0
        facets = Counter()
        for r in rows:
            total += 1
            res = self.tag(name=r.get("name") or "",
                           tags=r.get("tags") or (),
                           category=r.get("category_path") or "")
            if res["hits"]:
                cover += 1
            for h in res["hits"]:
                facets[h["facet"]] += 1
            for u in res["unknown"]:
                miss[u] += 1
        return {"total": total, "tagged": cover,
                "rate": round(cover / total, 4) if total else 0,
                "facets": dict(facets),
                "candidates": miss.most_common(60)}
