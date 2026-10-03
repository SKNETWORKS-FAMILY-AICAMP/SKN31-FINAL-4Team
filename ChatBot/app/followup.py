"""이어지는 질문을 앞 턴에 이어 붙인다.

두 가지만 이어받는다.
  ① 물음   "그러면 고프코어는?"  → 앞 턴이 '지금 유행이야?' 였으면 그 물음 그대로
  ② 대상   "그건 어때?"          → 앞 턴에서 말하던 것

이어받지 않는 것
  · 값. 앞 턴의 숫자를 다음 답에 옮겨 쓰지 않는다. 매번 DB 에서 새로 읽는다.
  · 사전 게이트. 앞 턴에 있었다고 없는 말이 통과되지 않는다 —
    ②는 '앞 턴에서 게이트를 통과한 term' 만 되살린다.

왜 규칙인가
  이어짐의 신호는 한국어에서 정형적이다 — 앞머리 접속어, 조사만 남은 짧은 꼬리말,
  지시대명사. LLM 을 부르면 느리고, 무엇보다 '왜 이어받았는지' 를 사용자에게
  설명할 수 없다. 이어받은 사실은 화면에 note 로 남는다.
"""
from __future__ import annotations

import re

# 주소가 섞인 질문 — 이어받지 않는다.
#   ★ 2026-09-13. "https://www.musinsa.com/products/7160737 이거 지금 사도 될까?" 가
#     앞 턴의 '트랙탑' 으로 읽혔다. 링크는 사전에 걸리지 않으니 search 가 비고,
#     "이거" 가 지시대명사로 잡혀 ② 대상 이어받기가 그대로 발동한 것이다.
#     **링크를 붙였다는 것은 그 링크의 물건을 묻는다는 뜻이다** — 앞에서 말하던
#     것으로 읽으면 전혀 다른 상품을 답하게 된다. 무엇인지는 링크를 확인해서
#     정한다(engine.py 의 상품 링크 확인). 여기서는 이어받지 않는 것으로 끝낸다.
URL = re.compile(r"https?://\S+|\bwww\.[^\s]+", re.I)

# 앞머리 접속어 — "그러면", "그럼", "그러니까", "그래서", "그리고", "반대로", "그다음"
LEAD = re.compile(r"^\s*(그러면|그럼|그러믄|그러니까|그래서|그리고|반대로|그\s*다음|다음은|then)\s*[,·]?\s*",
                  re.I)
# 지시대명사 — 앞에서 말하던 그것
ANAPHORA = re.compile(r"(그건|그것|그거|이건|이것|이거|저건|저것|걔|얘|"
                      r"그\s*(스타일|브랜드|아이템|소재|말|키워드)|"
                      r"이\s*(스타일|브랜드|아이템|소재|말|키워드)|"
                      r"방금|아까|위에\s*것|앞에\s*말한)")
# 꼬리 조사만 남은 짧은 물음 — "고프코어는?", "나일론도?", "아디다스는요"
TAIL_ONLY = re.compile(r"^\s*(은|는|이|가|도|만|요|은요|는요|이요|말고|는\s*어|은\s*어)?\s*[?？]?\s*$")

# 이어받으면 안 되는 물음 — 그 자체로 완결된 질문이다.
#   context.py 도 이 목록을 그대로 가져다 쓴다(후속 질문의 결과로 나올 수 없는 의도들) —
#   두 곳에 따로 적으면 한쪽만 고쳐질 수 있어서다.
NEVER_INHERIT = {"meta.capability", "meta.greeting", "meta.smalltalk", "out_of_scope"}

# 비교 신호 — "둘 중에 더 뜨거운 건요?", "뭐가 더 핫해?", "어느 쪽이 더 잘 나가?"
#   이번 질문엔 대상이 없으니 최근 턴들에서 서로 다른 term 을 모아 온다.
COMPARE = re.compile(r"(둘\s*(중|다)|어느\s*(게|것|쪽)|누가\s*더|뭐가\s*더|무엇이\s*더|"
                     r"더\s*(뜨거운|핫한|인기\s*있는|잘\s*나가는))")


def _residue(question: str, parsed: dict) -> str:
    """질문에서 사전에 걸린 말과 접속어를 걷어내고 남은 부분."""
    q = URL.sub(" ", str(question or ""))
    q = LEAD.sub("", q).strip()
    for bucket in ("search", "modifier", "other"):
        for h in parsed.get(bucket) or []:
            for w in {h.get("surface"), h.get("canonical")}:
                if w:
                    q = q.replace(str(w), " ")
    return re.sub(r"\s+", " ", q).strip()


def _last(history: list[dict], mode: str) -> dict | None:
    for t in reversed(history or []):
        if t.get("intent") and t["intent"] not in NEVER_INHERIT:
            return t
    return None


def _recent_terms(history: list[dict], limit: int = 2) -> list[dict]:
    """최근 턴들에서 사전 term 을 최신순 · 중복 없이 모은다.

    "둘 중에 더 뜨거운 건요?" 처럼 비교 대상이 바로 앞 턴 하나가 아니라
    최근 몇 턴에 걸쳐 나왔을 때 쓴다. _last() 는 한 턴만 보므로 이걸로 보강한다.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for t in reversed(history or []):
        if t.get("intent") in NEVER_INHERIT:
            continue
        for term in (t.get("terms") or []):
            c = term.get("canonical")
            if not c or c in seen:
                continue
            seen.add(c)
            out.append(term)
            if len(out) >= limit:
                return out
    return out


def resolve(question: str, parsed: dict, nlu: dict, history: list[dict],
            mode: str = "general") -> dict:
    """{intent, carried_terms, why} — 아무것도 안 이어받으면 빈 dict.

    intent 를 이어받는 조건 (둘 다여야 한다)
      · 규칙이 확신하지 못했다 — 확신했다면 이번 질문이 스스로 물음을 밝힌 것이다
      · 이어짐의 형태다 — 앞머리 접속어가 있거나, 사전 말을 빼면 조사만 남는다
    """
    out: dict = {}
    if URL.search(str(question or "")):
        # 링크 질문. 대상은 링크가 정한다 — 앞 턴에서 가져오지 않는다.
        return out
    prev = _last(history, mode)
    if not prev:
        return out

    q = str(question or "")
    sure = bool(nlu.get("source") == "rule" and nlu.get("confidence", 0) >= 1.0)
    has_lead = bool(LEAD.match(q))
    residue = _residue(q, parsed)
    tailish = bool(TAIL_ONLY.match(residue))

    # ① 물음 이어받기
    if not sure and (has_lead or tailish) and parsed.get("search"):
        out["intent"] = prev["intent"]
        out["why"] = f"앞 질문 '{prev['q']}' 의 물음을 이어받았습니다."

    # ② 대상 이어받기 — 이번 질문에 사전에 걸린 말이 하나도 없을 때만
    if not parsed.get("search"):
        is_compare = bool(COMPARE.search(q))
        if (has_lead or ANAPHORA.search(q) or is_compare) and prev.get("terms"):
            terms = _recent_terms(history, limit=2) if is_compare else prev["terms"]
            out["carried_terms"] = [t for t in terms if t.get("canonical")]
            if not out["carried_terms"]:
                return out
            if is_compare:
                names = " · ".join(t["canonical"] for t in out["carried_terms"])
                out["why"] = f"앞에서 말하던 '{names}' 를 나란히 비교했습니다."
            else:
                out["why"] = (f"앞 질문에서 말하던 "
                              f"'{out['carried_terms'][0]['canonical']}' 로 읽었습니다.")
            if is_compare:
                out["intent"] = "metric.compare"
            elif sure:
                out.pop("intent", None)      # 이번 질문이 물음을 밝혔으면 그건 그대로
            else:
                out["intent"] = prev["intent"]
    return out
