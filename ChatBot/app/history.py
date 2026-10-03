"""대화 기억 — 바로 앞 몇 턴만.

왜 필요한가
  "발레코어는 지금 유행이야?" 다음에 "그러면 고프코어는?" 이 오면
  사람은 같은 질문을 다른 말에 대해 다시 묻는 것으로 읽는다.
  앞 턴이 없으면 규칙도 LLM 도 "고프코어가 뭐냐" 로 읽는다. 실제로 그렇게 답했다.

무엇을 기억하나 — 다섯 가지뿐이다.
  · 무엇을 물었나 (intent)
  · 무엇에 대해 물었나 (사전에 걸린 term)
  · 원문 (사용자에게 "앞 질문을 이어받았다" 고 보여 주려고)
  · 사진에서 직접 확인한 구조화 관찰값 (아이템·색·소재·실루엣 등)
  · 챗봇이 끝에 되물은 이어 갈 질문 (`next` — 답변의 [다음] 줄)
답변 본문은 기억하지 않는다. 다음 답을 만들 때 쓰이지 않는데 들고 있으면
언젠가 그걸 근거 삼아 말하게 된다.

★ `next` 를 기억하는 이유 (2026-10-01 실측)
  챗봇이 "더비슈즈의 출처별 반응이나, 실제 언급 근거를 더 볼까요?" 라고 묻고
  사용자가 "응 두개 다 알려줘" 라고 답했는데, 다음 턴의 모델은 그 질문을 몰랐다.
  기억에는 사용자 질문만 있었기 때문이다. 모델은 앞선 질문들에서 '두 개' 를
  짐작해 아이템 순위와 소재 순위를 다시 보여 줬다.
  짧은 대답(응 · 둘 다 · 그거)은 **챗봇이 물은 것**에 대한 대답이다. 그 질문이
  없으면 어떤 모델도 풀 수 없다. 질문은 주장이 아니라서 근거로 쓰일 위험도 없다.

수명
  대화당 8턴, 2시간, 전체 500대화. 개발 서버는 프로세스 메모리다.
  ★ 여기가 진실의 원본이 되면 안 된다. 서버가 죽으면 사라지는 것이 맞다.
    클라이언트도 최근 턴을 같이 보내므로(engine.ask(history=…)) 그때는 그쪽을 쓴다.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque

MAX_TURNS = 8
TTL_SEC = 2 * 60 * 60
MAX_CONV = 500
NEXT_MAX = 200     # 이어 갈 질문 한 줄의 상한


def clean_next(value) -> str | None:
    """이어 갈 질문 한 줄 — 태그를 걷고 한 줄로 줄인다. 밖에서 온 값일 수 있다."""
    import re
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = " ".join(text.split())[:NEXT_MAX]
    return text or None


# 되묻기로 끝난 턴의 intent. agent_path.ask() 가 이 값을 돌려주고,
# engine 이 그대로 기억에 넣는다. 예산(orchestrator.ASK_BUDGET)이 이걸 센다.
ASK_INTENT = "agent.ask"


def count_asks(turns) -> int:
    """이 대화에서 되물은 횟수.

    ★ 답변 본문이 아니라 intent 로 센다. 기억이 들고 있는 세 가지 중 하나라,
      새로 저장할 것이 없다.
    """
    return sum(1 for t in (turns or [])
               if isinstance(t, dict) and str(t.get("intent") or "") == ASK_INTENT)


_VISUAL_LISTS = ("tags", "colors", "materials", "silhouette", "details", "styles",
                 "uncertainties")


def sanitize_visual(raw) -> dict | None:
    """Vision Agent가 확인한 **관찰값만** 대화 기억에 남긴다.

    브라우저가 다음 요청에 다시 보내는 값이므로 길이와 모양을 제한한다. 이 값은
    사진 설명을 이어 갈 때만 쓰고 브랜드·가격·트렌드의 근거로 승격하지 않는다.
    """
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    item = " ".join(str(raw.get("item") or raw.get("name") or "").split())[:80]
    if item:
        out["item"] = item
    for key in _VISUAL_LISTS:
        value = raw.get(key)
        if not isinstance(value, (list, tuple)):
            continue
        rows = []
        for x in value[:8]:
            word = " ".join(str(x or "").split())[:60]
            if word and word not in rows:
                rows.append(word)
        if rows:
            out[key] = rows
    summary = " ".join(str(raw.get("summary") or "").split())[:500]
    if summary:
        out["summary"] = summary
    return out or None


def make_turn(question: str, intent: str, mode: str, terms: list[dict],
              visual: dict | None = None, follow: str | None = None) -> dict:
    turn = {
        "q": " ".join(str(question or "").split())[:200],
        "intent": intent,
        "mode": mode,
        "terms": [{"canonical": t.get("canonical"), "facet": t.get("facet"),
                   "term_key": t.get("term_key")} for t in (terms or [])][:4],
        "at": time.time(),
    }
    nxt = clean_next(follow)
    if nxt:
        turn["next"] = nxt
    seen = sanitize_visual(visual)
    if seen:
        turn["visual"] = seen
    return turn


class Memory:
    def __init__(self, max_turns: int = MAX_TURNS, ttl: int = TTL_SEC,
                 max_conv: int = MAX_CONV):
        self.max_turns, self.ttl, self.max_conv = max_turns, ttl, max_conv
        self._c: OrderedDict[str, deque] = OrderedDict()
        self._lock = threading.Lock()

    def recent(self, conv_id: str | None) -> list[dict]:
        if not conv_id:
            return []
        with self._lock:
            d = self._c.get(conv_id)
            if not d:
                return []
            self._c.move_to_end(conv_id)
            now = time.time()
            return [t for t in d if now - t["at"] <= self.ttl]

    def add(self, conv_id: str | None, turn: dict) -> None:
        if not conv_id:
            return
        with self._lock:
            d = self._c.get(conv_id)
            if d is None:
                d = self._c[conv_id] = deque(maxlen=self.max_turns)
            d.append(turn)
            self._c.move_to_end(conv_id)
            while len(self._c) > self.max_conv:
                self._c.popitem(last=False)

    def forget(self, conv_id: str | None) -> None:
        with self._lock:
            self._c.pop(conv_id, None)


def sanitize(raw) -> list[dict]:
    """클라이언트가 보낸 history 를 걸러 받는다.

    ★ 밖에서 온 값이다. intent 를 그대로 믿으면 사용자가 게이트를 우회할 수 있다.
      term 도 canonical 문자열만 받고, 실제로 지표에 있는지는 부르는 쪽이 확인한다.
    """
    out = []
    if not isinstance(raw, list):
        return out
    for t in raw[-MAX_TURNS:]:
        if not isinstance(t, dict):
            continue
        q = " ".join(str(t.get("q") or t.get("question") or "").split())[:200]
        if not q:
            continue
        terms = []
        for x in (t.get("terms") or [])[:4]:
            if isinstance(x, dict) and x.get("canonical"):
                terms.append({"canonical": str(x["canonical"])[:40],
                              "facet": str(x.get("facet") or "")[:16] or None,
                              "term_key": str(x.get("term_key") or "")[:60] or None})
            elif isinstance(x, str):
                terms.append({"canonical": x[:40], "facet": None, "term_key": None})
        turn = {"q": q, "intent": str(t.get("intent") or "")[:32] or None,
                "mode": "salmal" if t.get("mode") == "salmal" else "general",
                "terms": terms, "at": time.time()}
        visual = sanitize_visual(t.get("visual") or t.get("visual_context"))
        if visual:
            turn["visual"] = visual
        nxt = clean_next(t.get("next") or t.get("followup"))
        if nxt:
            turn["next"] = nxt
        out.append(turn)
    return out
