"""
질문 전용 어휘 추출 — 3단.

왜 새로 만드나
  Lexicon.extract() 의 두 모드가 챗봇 질문에는 둘 다 안 맞는다.

    product  상품명·태그용. 부분 문자열을 다 믿는다.
             자유 글에 대면 '바람불면' 의 '면' 이 코튼이 된다.
             (lexicon.py:110~118 이 적어 둔 실제 사고. 댓글 2,000건 중 1,059건)

    free     자유 글용. 짧고 흔한 표기를 뺀다.
             그런데 lexicon.py:120~121 이 brand 를 통째로 뺀다.
             실측 — 전체 표기 6,573 중 free 는 1,058. brand 표기 5,472 전부 제외.
             RISKY 35개(클래식·면·백…)도 함께 빠진다.
             "무신사 스탠다드 어때?" 도 "클래식 요즘 어때?" 도 안 걸린다.

  챗봇 질문은 자유 글이 아니다. 사용자가 의도를 갖고 친 짧은 문장이다.
  그래서 잣대가 달라야 한다.

핵심 관찰
  free 가 막으려던 오탐은 **전부 부분 문자열 매칭**에서 나왔다.
      '바람불면' 안의 '면',  '마냥' 안의 '마',  '짐작' 안의 '짐'
  어절을 통째로 보면 이 경로가 통째로 없어진다.
      어절 '바람불면' ≠ 표기 '면'
  사용자가 질문에 '면' 이라는 어절을 그대로 쓰면 그건 코튼이 맞다.

그래서 3단
  1단  extract(q, "free")            안전한 1,058 표기로 기본 추출 (부분일치 허용)
  2단  어절 완전일치 → RISKY 복구      조사 떼고 exact() 로 조회
  3단  어절 n-gram → 브랜드           1~5어절 창을 exact(facet="brand") 로만

lexicon.py 를 고치지 않는다. 감싸서 쓴다.
크롤러 파이프라인(trend_chat·metrics)의 동작은 그대로 둔다.
"""
from __future__ import annotations

import re
import unicodedata

# 챗봇이 검색어(주어)로 인정하는 축
SEARCH_FACETS = ("style", "material", "item", "brand")
# 주어로는 못 쓰지만 수식어로 읽는 축
MODIFIER_FACETS = ("fit", "color", "detail", "tpo")

# 조사·어미. 어절 끝에서 떼어 낸다.
#   긴 것부터 떼야 한다. '에서는' 을 '는' 부터 떼면 '에서' 가 남는다.
_JOSA = sorted(
    ["으로는", "에서는", "이라는", "라는", "에서", "에게", "이랑", "하고", "으로", "부터", "까지",
     "이나", "나마", "조차", "마저", "밖에", "처럼", "보다", "같이", "대로", "만큼",
     "은", "는", "이", "가", "을", "를", "의", "에", "로", "과", "와", "도", "만", "야", "요"],
    key=len, reverse=True)

# 질문에서 떼어 낼 기호. 어절 경계로만 쓴다.
_PUNCT = re.compile(r"[?!.,~…·\"'“”‘’()\[\]{}<>/\\|:;`＋+*^%$#@&=_\-—–]+")

# 한 글자 표기는 어절이 통째로 같아도 방증이 있어야 채택한다.
#   "면 소재 어때?"        → '소재' 가 있으니 코튼      ○
#   "백 번 말해도 소용없다"  → 방증 없음                 ✕
#   실측에서 잡힌 유일한 헛걸림이 '백'(가방) 하나였다.
#   문맥어 두 갈래 — 패션어와, 질문임을 드러내는 말.
#   "백 사고싶어"          → '사고' 가 있으니 가방        ○  (실제로 가방을 묻는 말이다)
#   "백 번 말해도 소용없다"  → 둘 다 없음                  ✕
_CONTEXT = ("소재", "원단", "재질", "스타일", "코디", "아이템", "브랜드", "룩",
            "옷", "패션", "트렌드", "핏", "컬러", "색", "사이즈", "입", "신", "매치",
            # 질문 의도어
            "어때", "어떨", "살까", "사도", "사고", "살지", "말지", "추천", "유행",
            "괜찮", "어울", "온도", "지수", "알려")

# ── 브랜드 사전에 일반어가 섞여 있다 ──
#  실측 (2026-09-02) — 브랜드 표기 5,472개 중
#      2글자 이하   410개   '킨' '싹' '고목' '골라' '기준' '나우' '기호' …
#      숫자만         3개   '222' '225' '2365'  ← 신발 사이즈가 브랜드로 잡힌다
#  문서 6,000건에 돌려 보니 '기준'(29회) '정도'(38) '시그니처'(23) '피그먼트'(23)
#  같은 일반어가 브랜드로 걸렸다.
#
#  이건 추출 로직이 아니라 **사전 데이터의 문제**다. 근본 수정은 사전 쪽에서 해야 한다.
#  여기서는 질문이 오염되지 않게 막기만 한다.
_BRAND_MIN_LEN = 2
_BRAND_BLOCK = {
    # 실측으로 확인된 일반어. 관리자가 늘려 간다 — search_query_log 가 근거가 된다.
    "기준", "정도", "시그니처", "피그먼트", "페이지", "고목", "골라", "나우", "기호",
    "그루", "나체", "구보", "고저", "슬릭", "알리스", "몽돌", "싹", "킨",
}


def _brand_ok(surface: str) -> bool:
    if len(surface) < _BRAND_MIN_LEN:
        return False
    if surface.isdigit():
        return False
    return surface not in _BRAND_BLOCK


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", str(s or ""))


def tokenize(question: str) -> list[str]:
    """질문 → 어절 목록. 기호는 경계로 보고 버린다."""
    q = _PUNCT.sub(" ", _nfc(question))
    return [t for t in q.split() if t]


def strip_josa(token: str) -> list[str]:
    """어절에서 조사를 뗀 후보들. 원형도 같이 돌려준다.

    '발레코어는' → ['발레코어는', '발레코어']
    '면'         → ['면']            (한 글자는 떼지 않는다. 떼면 빈 문자열이 된다)
    """
    out = [token]
    for j in _JOSA:
        if len(token) > len(j) and token.endswith(j):
            stem = token[: -len(j)]
            if len(stem) >= 1:
                out.append(stem)
            break          # 하나만 뗀다. 두 번 떼면 '스커트' → '스커' 가 된다
    return out


class QuestionExtractor:
    """Lexicon 을 감싸서 질문 전용 추출을 한다. Lexicon 자체는 건드리지 않는다."""

    def __init__(self, lexicon, max_ngram: int = 5, prefer_canonicals=None):
        """
        prefer_canonicals
            지표에 자기 이름으로 적재돼 있는 canonical 집합.
            사전이 '코트' 를 '아우터' 로 접어 버리는데 지표에는 '코트' 가 따로 있다.
            (실측 24건 충돌 · 그중 22건이 양쪽 다 적재 — 아래 fold_conflicts 참조)
            이 집합을 주면 **사용자가 쓴 말이 지표에 있으면 접지 않는다.**
            안 주면 지금처럼 사전이 접는 대로 간다.
        """
        self.lex = lexicon
        self.max_ngram = max_ngram
        self.prefer = set(prefer_canonicals or ())

    # ── 1단 ────────────────────────────────────────────
    def _pass1_free(self, question: str) -> list[tuple[str, str, str]]:
        return [(c, f, "free") for c, f in self.lex.extract(question, "free")]

    # ── 2단 ────────────────────────────────────────────
    def _pass2_exact_token(self, tokens: list[str],
                           question: str) -> list[tuple[str, str, str]]:
        """어절 완전일치. RISKY 여도 채택한다 — 부분 문자열이 아니기 때문이다.

        예외 하나. **한 글자 표기는 방증을 요구한다.**
        '백 번 말해도 소용없다' 의 '백' 은 어절 전체가 같지만 가방이 아니다.
        질문에 패션 문맥어가 있거나 다른 검색축 용어가 이미 잡혔을 때만 채택한다.
        """
        has_context = any(w in question for w in _CONTEXT)
        multi = []
        single = []
        for tok in tokens:
            for cand in strip_josa(tok):
                got = self.lex.exact(cand)
                if not got or got[1] == "brand":   # 브랜드는 3단에서 따로 본다
                    continue
                (single if len(cand) == 1 else multi).append((got[0], got[1], f"token:{cand}"))
                break
        if single and not (has_context or any(f in SEARCH_FACETS for _, f, _ in multi)):
            single = []
        return multi + single

    # ── 3단 ────────────────────────────────────────────
    def _pass3_brand_ngram(self, tokens: list[str]) -> list[tuple[str, str, str]]:
        """1~5어절 창을 붙여 brand 로만 완전일치 조회.

        긴 창부터 본다 — '무신사 스탠다드' 가 '무신사' 보다 먼저 잡혀야 한다.
        잡힌 자리는 소비해서 같은 어절이 두 번 세어지지 않게 한다.
        """
        out, used = [], set()
        n = len(tokens)
        for size in range(min(self.max_ngram, n), 0, -1):
            for i in range(n - size + 1):
                if any(k in used for k in range(i, i + size)):
                    continue
                window = tokens[i:i + size]
                # 마지막 어절의 조사만 떼어 본다 ('나이키는' → '나이키')
                tails = strip_josa(window[-1])
                for tail in tails:
                    phrase = " ".join(window[:-1] + [tail])
                    if not _brand_ok(phrase.replace(" ", "")):
                        continue
                    got = self.lex.exact(phrase, facet="brand")
                    if got:
                        out.append((got[0], got[1], f"brand:{phrase}"))
                        used.update(range(i, i + size))
                        break
        return out

    # ── 합치기 ─────────────────────────────────────────
    def extract(self, question: str) -> list[dict]:
        """질문 → [{canonical, facet, role, via}]

        role  'search'   4종 축. 검색어로 쓴다
              'modifier' fit·color·detail·tpo. 수식어로만 쓴다
              'other'    season·body 등. 참고만
        """
        tokens = tokenize(question)
        hits: list[tuple[str, str, str]] = []
        hits += self._pass1_free(question)
        hits += self._pass2_exact_token(tokens, question)
        hits += self._pass3_brand_ngram(tokens)

        # ── 접힘 되돌리기 ──
        #  사용자가 쓴 말 자체가 지표에 있으면 그 말로 답한다.
        #  "코트 어때?" 에 아우터 수치를 주면 사용자가 물은 것에 답한 게 아니다.
        if self.prefer:
            unfolded, dropped = [], set()
            for canon, facet, via in hits:
                raw = via.split(":", 1)[1] if ":" in via else None
                if raw and raw != canon and raw in self.prefer:
                    unfolded.append((raw, self.lex.facet_of.get(raw, facet),
                                     f"{via}|unfold"))
                    dropped.add(canon)      # 접혔던 상위어는 버린다
                else:
                    unfolded.append((canon, facet, via))
            # "코트 사도 될까?" 에 아우터와 코트를 둘 다 주면 무엇을 물었는지 흐려진다.
            # 되돌린 말이 있으면 그 말로만 답한다.
            hits = [h for h in unfolded if not (h[0] in dropped and "|unfold" not in h[2])]

        seen, out = set(), []
        for canon, facet, via in hits:
            if canon in seen:
                continue
            seen.add(canon)
            role = ("search" if facet in SEARCH_FACETS
                    else "modifier" if facet in MODIFIER_FACETS else "other")
            out.append({"canonical": canon, "facet": facet, "role": role, "via": via,
                        "trendable": bool(self.lex.trendable.get(canon, True))})
        return out

    def search_terms(self, question: str) -> list[dict]:
        """검색어로 쓸 수 있는 것만. 챗봇 게이트는 이걸 본다."""
        return [x for x in self.extract(question) if x["role"] == "search" and x["trendable"]]
