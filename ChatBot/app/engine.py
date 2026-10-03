"""질문 하나를 받아 답 하나를 돌려준다. 서비스의 입구.

Luna(LLM)는 네 자리에만 쓴다. 넷 다 **없어도 돌아간다.**
    ① 의도 분류   규칙이 못 잡을 때만        nlu.py
    ② 어투 다듬기 값을 꽂은 뒤 문장만        polish.py    숫자는 자리표시자로 봉인
    ③ 웹 검색     지식 질문                websearch.py 출처 없으면 안 올린다
    ④ 맥락 해석   정규식으로도 못 이은 후속 질문 · 잡담만   context.py
                 마지막 수단으로만 부르고, 이미 사전을 통과했던 term 밖은
                 고를 수 없게 스키마로 막는다.

LLM 이 하지 않는 것
    · 지표 해석 — 온도 86점이 무슨 뜻인지는 설계서가 원본이다.
      LLM 에게 맡기면 화면과 챗봇이 다른 말을 한다.
    · 엔티티 결정 — 4종 축 게이트는 사전이 정한다.
    · 숫자 — 값은 서버가 DB 에서 직접 꽂는다.
"""
from __future__ import annotations

import re

from . import (agent_blocks, agent_path, context, fit, followup, history, llm, mdclean,
               plans, polish, product_link, report, report_skill, salmal_index,
               websearch)
from .followup import URL as _URL
from .lexicon_gate import LexiconGate
from .nlu import classify
from .intents import is_salmal_question, is_greeting, GENERAL_CODES, SALMAL_CODES
from .store import ReadOnlyStore, default_store

# 사진만으로는 답이 끝나지 않는 질문 — 상품 · 트렌드 값이 필요하다(_vision_ask).
_PHOTO_NEEDS_TOOLS = re.compile(
    r"추천|어울|코디|매치|매칭|같이\s*입|비슷|찾아|상품|요즘|트렌드|유행|인기|핫|뜨는|"
    r"가격|얼마|어디서|순위|지수|온도|대신|대체|살\s*만|브랜드")


class ChatEngine:
    def __init__(self, store: ReadOnlyStore | None = None, *, use_llm: bool = True,
                 salmal=None, taste=None):
        self.store = store or default_store()
        self.gate = LexiconGate(self.store)
        self.use_llm = use_llm
        self.salmal = salmal
        self.taste = taste
        self.memory = history.Memory()

    # ── 진단 ──────────────────────────────────────────
    def llm_state(self) -> dict:
        return {"enabled": self.use_llm, "key": llm.key_hint(),
                "model": llm.MODEL, "last_error": llm.LAST_ERROR,
                "orchestrator": agent_path.enabled(),
                "roles": {r: llm.role(r) for r in llm.ROLES}}

    # ── 본체 ──────────────────────────────────────────
    def ask(self, question: str, mode: str = "general", plan: str = plans.FREE,
            *, conversation_id: str | None = None,
            history_in: list | None = None,
            extra: dict | None = None,
            on_progress=None,
            images: list[str] | None = None,
            cancel_check=None) -> dict:
        q = " ".join(str(question or "").split())
        imgs = [u for u in (images or []) if isinstance(u, str) and u.strip()][:6]
        if not q and not imgs:
            return {"ok": False, "reason": "EMPTY", "message": "질문을 입력해 주세요."}
        if len(q) > 500:
            return {"ok": False, "reason": "TOO_LONG",
                    "message": "질문은 500자 이하로 입력해 주세요."}

        # ── 이미지 첨부 (2026-09-10) ─────────────────────────
        #   사진이 오면 먼저 비전 모델이 본다. 사진 속 옷이 어떤 스타일인지는 우리 DB 값이
        #   아니라 모델이 보고 설명하는 것이다. 질문이 상품 · 트렌드를 더 묻는다면
        #   (2026-10-02) 본 것을 앞 턴으로 붙여 도구 루프로 넘긴다 — _vision_ask 참고.
        if imgs:
            return self._vision_ask(q, mode, imgs, conversation_id, extra, on_progress,
                                    history_in=history_in, cancel_check=cancel_check)

        # ── 새 경로 (2026-09-09) ────────────────────────────
        #   FEEDIT_CHAT_ORCHESTRATOR=1 이면 도구 루프로 간다.
        #   의도를 정규식으로 확정하지 않고, 도구를 고르고 결과를 보고 다시 고른다.
        #
        #   ★ 아래 기존 경로를 **지우지 않았다.**
        #     지금 돌고 있는 챗봇을 세우지 않고 갈아 끼우기 위해서다.
        #     두 경로를 같은 질문으로 돌려 비교한 뒤 기본값을 바꾸면 된다.
        #     끄면(변수 없음) 예전과 완전히 같은 길로 간다.
        if agent_path.enabled() and self.use_llm:
            return self._agent_ask(q, mode, conversation_id, history_in, extra,
                                   on_progress, cancel_check)

        # 앞 턴. 클라이언트가 보낸 것이 있으면 그쪽을 믿는다 —
        # 사용자의 세션 목록이 원본이고, 서버 메모리는 프로세스가 죽으면 사라진다.
        past = history.sanitize(history_in) if history_in else self.memory.recent(conversation_id)

        # ★ 사전 게이트를 먼저 본다. 사전 단어가 하나도 없고 이어받을 대화까지 있으면
        #   맨 아래 ④ 맥락 해석(context.py)이 마지막에 LLM 을 부를 것이다. 그 경우
        #   의도 분류(nlu)에서도 LLM 을 부르면 같은 메시지 하나에 LLM 이 두 번 불려
        #   느려지고 비용도 두 배가 된다 — 그때는 여기서 규칙만으로 조용히 넘어간다.
        #   (사전 단어가 있거나, 대화 기록이 없어 ④가 어차피 안 불릴 때는 그대로 쓴다.)
        parsed = self.gate.parse(q)
        skip_nlu_llm = not parsed["search"] and bool(past)
        nlu = classify(q, mode, use_llm=self.use_llm and not skip_nlu_llm)
        intent = nlu["intent"]

        if intent == "meta.capability":
            return self._capability(plan, nlu)
        if intent == "meta.greeting":
            return self._greeting(nlu, mode)

        carried = followup.resolve(q, parsed, nlu, past, mode)

        # ★ 링크 질문 — 무엇을 묻는지는 **링크가 정한다**.
        #   사전에 걸린 말이 없는 링크 질문은 앞 대화(④)로 넘기지 않는다.
        #   넘기면 "https://…/7160737 이거 사도 될까?" 가 앞 턴의 다른 상품으로
        #   읽힌다(2026-09-13 트랙탑 오독). 대신 링크를 열어 상품명·브랜드를
        #   확인하고, 확인한 말만 사전 게이트에 다시 태운다.
        is_link = bool(_URL.search(q))
        seen = None
        if is_link and not parsed["search"] and self.use_llm and llm.available():
            seen = product_link.inspect(q, timeout=12)
            if seen.get("found"):
                for text in (seen.get("item_name"), seen.get("brand")):
                    again = self.gate.parse(str(text or ""))
                    if again["search"]:
                        parsed["search"].extend(again["search"])
                if parsed["search"]:
                    label = " ".join(x for x in (seen.get("brand"),
                                                 seen.get("item_name")) if x)
                    carried = {"why": f"링크에서 확인한 '{label}' 로 읽었습니다."}

        # ④ 규칙(정규식)으로도 못 이었다 — 잡담인지, 놓친 후속 질문인지 LLM에게 맥락을 묻는다.
        #    마지막 수단으로, 딱 한 번만 부른다. candidate_terms 는 이미 게이트를 통과했던
        #    값뿐이라 사전 밖 단어를 새로 지어낼 수 없다 (context.py 참고).
        if not parsed["search"] and not carried and not is_link and self.use_llm and past:
            codes = GENERAL_CODES if mode == "general" else SALMAL_CODES
            ctx = context.resolve(q, past, codes, mode=mode)
            if ctx and ctx["kind"] == "smalltalk":
                return self._smalltalk(nlu, ctx["reply"])
            if ctx and ctx["kind"] == "followup":
                names = " · ".join(ctx["refer_terms"])
                carried = {"carried_terms": [{"canonical": c} for c in ctx["refer_terms"]],
                           "intent": ctx["intent"],
                           "why": f"앞 대화 맥락으로 '{names}' 로 읽었습니다."}

        if carried.get("carried_terms"):
            # ★ 되살릴 때도 게이트를 다시 통과시킨다. 앞 턴에 있었다는 이유만으로
            #   사전 밖의 말이 들어오면 안 된다.
            for t in carried["carried_terms"]:
                again = self.gate.parse(t["canonical"])
                if again["search"]:
                    parsed["search"].extend(again["search"])
            if not parsed["search"]:
                carried.pop("carried_terms", None)
                carried.pop("intent", None)
        if carried.get("intent"):
            intent = carried["intent"]
            nlu = dict(nlu, intent=intent, source="followup",
                       followup=carried.get("why"))

        # 사전에 걸린 말이 없으면 여기서 끝난다.
        # ★ 지식 질문이어도 검색으로 우회시키지 않는다 (설계서 3.4).
        if not parsed["search"]:
            out = (report.link_not_identified(q, seen) if is_link
                   else report.not_in_lexicon(self.gate, self.store, q))
            out["intent"] = intent
            out["question"] = q
            out["nlu"] = nlu
            self._remember(conversation_id, q, intent, mode, [])
            return out

        if intent == "out_of_scope":
            # 사전에는 걸렸는데 모델이 패션 밖이라고 봤다. 사전을 믿는다.
            intent = "metric.level"
            nlu = dict(nlu, intent=intent, overridden="out_of_scope→사전에 걸려 metric.level 로")

        rep = report.compose(self.store, self.gate, q, intent, parsed, plan, mode)
        rep["nlu"] = nlu
        if carried.get("why"):
            # 이어받았다는 사실을 숨기지 않는다. 잘못 이어받았으면 사용자가 바로 안다.
            rep.setdefault("notes", []).insert(
                0, {"code": "FOLLOW_UP", "term": None, "message": carried["why"]})
        self._remember(conversation_id, q, intent, mode, parsed["search"])

        if mode == "general" and is_salmal_question(q):
            rep["hint"] = {
                "code": "MODE_MISMATCH",
                "message": "살지 말지는 살!말? 모드가 더 정확합니다.\n"
                           "가격 · 재고 · 수명주기까지 같이 봅니다.",
                "action": {"type": "switch_mode", "to": "salmal", "label": "살!말? 모드로"},
            }

        # ③ 지식 질문 — 웹에서 찾아 붙인다
        if intent == "knowledge.origin" and self.use_llm:
            self._attach_web(rep, parsed, q, plan, past)

        # ② 어투 다듬기 — 값이 다 꽂힌 뒤에만
        if self.use_llm:
            self._polish(rep)
        return rep

    def _remember(self, conv_id, q, intent, mode, terms, visual=None, follow=None):
        if conv_id:
            self.memory.add(conv_id, history.make_turn(q, intent, mode, terms, visual,
                                                       follow=follow))

    def _vision_terms(self, visual: dict | None) -> list[dict]:
        """사진 관찰값 중 사전에 실제로 있는 용어만 지표용 term으로 승격한다."""
        if not isinstance(visual, dict):
            return []
        words = [visual.get("item")]
        for key in ("tags", "materials", "styles", "details"):
            words.extend(visual.get(key) or [])
        out, seen = [], set()
        for word in words:
            parsed = self.gate.parse(str(word or ""))
            for term in parsed.get("search") or []:
                key = term.get("term_key") or term.get("canonical")
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(term)
                if len(out) >= 4:
                    return out
        return out


    # ── 새 경로 본체 (도구 루프) ──────────────────────
    def _agent_ask(self, q: str, mode: str, conversation_id: str | None,
                   history_in: list | None, extra: dict | None, on_progress=None,
                   cancel_check=None, extra_turns: list | None = None,
                   visual: dict | None = None) -> dict:
        """도구 루프로 답한다. extra_turns 는 history 끝에 덧붙일 턴 —
        사진 질문이 '방금 본 사진' 을 앞 턴처럼 넘길 때 쓴다(_vision_ask)."""
        past_a = (history.sanitize(history_in) if history_in
                  else self.memory.recent(conversation_id))
        if extra_turns:
            past_a = list(past_a) + list(extra_turns)
        ctx = {"mode": mode}
        # ★ 되묻기 예산 (15번). **서버 기억**에서도 센다.
        #   클라이언트가 보내는 history 에는 되묻기 턴이 빠진다 —
        #   chat_popup 은 report 이벤트가 올 때만 turn 을 남기는데,
        #   되묻기는 kind="meta" 라 report 를 보내지 않기 때문이다.
        #   그쪽만 보면 예산이 영원히 0 이라 상한이 걸리지 않는다.
        #   둘 중 큰 쪽을 쓴다 — 서버가 재시작하면 기억이 비지만,
        #   그때 한 번 더 되묻는 것은 감당할 수 있는 실패다.
        ctx["asked_before"] = max(history.count_asks(past_a),
                                  history.count_asks(self.memory.recent(conversation_id)))
        # 화면에서 넘어온 것들. 없으면 없는 대로 — 도구 목록만 줄어든다.
        for k in ("screen_term", "salmal_card_id", "user_id", "region", "taste_context", "gender"):
            v = extra.get(k) if extra else None
            if v:
                ctx[k] = v
        # ★ 승인된 코디 (2026-10-01). server.py 는 받아서 넘겼는데 여기 목록에 없어
        #   버려졌다 — "이 코디로 입혀보기" 를 눌러도 build_fit 이 목록에 오르지 못하고
        #   모델이 "어떤 코디를 입혀볼까요?" 를 되물었다. 걸러서 넣는다(fit.clean_proposal).
        proposal = fit.clean_proposal(extra.get("fit_proposal")) if extra else None
        if proposal:
            ctx["fit_proposal"] = proposal
        # ★ 이 대화에서 이미 보여 준 코디 (2026-10-02) — 상품(seen) · 근거 기사(refs) ·
        #   상황(occasion). '다른 룩' 이 같은 룩이 되지 않게 도구와 모델이 본다.
        ctx.update(fit.clean_memory(extra.get("fit_memory")) if extra else {})
        out = agent_path.ask(q, store=self.store, gate=self.gate, mode=mode,
                             history=past_a, ctx=ctx, salmal=self.salmal,
                             taste=self.taste, on_progress=on_progress,
                             cancel_check=cancel_check)
        self._remember(conversation_id, q, out.get("intent") or "agent", mode,
                       out.get("terms") or [], visual=visual, follow=out.get("followup"))
        return out

    # ── 이미지 첨부 ───────────────────────────────────
    def _vision_ask(self, q: str, mode: str, images: list[str],
                     conversation_id: str | None, extra: dict | None = None,
                     on_progress=None, *, history_in: list | None = None,
                     cancel_check=None) -> dict:
        """사진을 보고 답한다. 값은 도구에서만 나온다는 원칙(AGENTS.md §2)이
        지표·가격 같은 우리 DB 값 얘기라, 사진 속 옷을 설명하는 이 자리에는
        해당하지 않는다 — greeting·smalltalk처럼 LLM이 그대로 답을 만드는
        자리로 취급한다. LLM이 없거나 실패하면 실패라고 말한다(꾸미지 않는다)."""
        if not self.use_llm or not llm.available():
            return {"ok": False, "reason": "IMAGE_UNAVAILABLE",
                    "message": "지금은 사진을 분석할 수 없습니다. 잠시 후 다시 시도해 주세요."}
        if on_progress:
            on_progress("사진을 보는 중")
        if mode == "salmal":
            visual = llm.vision_salmal(q, images)
            if not visual:
                return {"ok": False, "reason": "IMAGE_FAILED",
                        "message": "사진을 분석하지 못했습니다. 다시 시도해 주세요."}
            visual_context = history.sanitize_visual(visual) or {}
            visual_terms = self._vision_terms(visual_context)
            result = salmal_index.calculate(
                term=str(visual.get("item") or ""),
                product_tags=visual.get("tags") or [],
                taste_context=(extra or {}).get("taste_context"),
            )
            result.update({"term": visual.get("item") or "사진 속 아이템", "as_of": "사진 분석 기준"})
            catalog = []
            for i, block in enumerate(agent_blocks.salmal_blocks(result)):
                catalog.append({"id": f"salmal:visual:{i}", "kind": "salmal",
                                "term": result["term"], "block": block})
            canvas = report_skill.build(catalog, trace=None)
            self._remember(conversation_id, q or "[사진]", "vision.salmal", mode,
                           visual_terms, visual_context)
            return {"ok": True, "kind": "agent", "intent": "vision.salmal",
                    "headline": mdclean.to_html(str(visual.get("summary") or "사진을 확인했습니다.")),
                    "followup": "", "terms": visual_terms, "as_of": {},
                    "blocks": [canvas] if canvas else [], "notes": [], "sources": [],
                    "partial": not result.get("recommendation_allowed"),
                    # 사진에서는 이름만 안다 — 브랜드·가격은 비워 두고 사용자가 채운다.
                    "item_draft": {"title": result["term"], "brand": "", "price": None,
                                   "source": "사진 분석"},
                    "visual_item": {"name": result["term"], "tags": visual.get("tags") or []},
                    "visual_context": visual_context}
        visual = llm.vision(q, images, mode=mode)
        if not visual:
            return {"ok": False, "reason": "IMAGE_FAILED",
                    "message": "사진을 분석하지 못했습니다. 다시 시도해 주세요."}
        # 전환 중인 테스트·오래된 어댑터가 문자열을 돌려도 답은 유지한다.
        if isinstance(visual, str):
            visual = {"summary": visual}
        visual_context = history.sanitize_visual(visual) or {}
        visual_terms = self._vision_terms(visual_context)
        answer = str(visual_context.get("summary") or "사진을 확인했습니다.")
        # ★ 사진 + 데이터가 필요한 질문 (2026-10-02).
        #   "이거랑 어울리는 바지 추천해줘" · "이 스타일 요즘 유행이야?" 는 사진 설명만으로
        #   답이 끝나지 않는다. 본 것을 '방금 본 사진' 턴으로 앞에 붙여 도구 루프에 넘긴다 —
        #   [최근 이미지 분석] 줄로 아이템·색·소재가 모델에게 가고(orchestrator._ctx_block),
        #   상품 · 트렌드 값은 지금처럼 도구에서만 나온다. 도구 루프가 실패하면 사진 설명만
        #   돌려준다(아래 원래 답).
        if q and _PHOTO_NEEDS_TOOLS.search(q) and agent_path.enabled() and self.use_llm \
                and not (cancel_check and cancel_check()):
            seen_turn = history.make_turn("[사진]", "vision.image", mode, visual_terms,
                                          visual_context)
            if on_progress:
                on_progress("사진 속 아이템으로 찾아보는 중")
            try:
                out = self._agent_ask(q, mode, conversation_id, history_in, extra,
                                      on_progress, cancel_check, extra_turns=[seen_turn],
                                      visual=visual_context)
            except Exception:                          # noqa: BLE001 — 사진 설명은 이미 있다
                out = None
            if out and out.get("ok") and out.get("kind") != "meta":
                out["headline"] = mdclean.to_html(answer) + (out.get("headline") or "")
                out["visual_context"] = visual_context
                known = {t.get("canonical") for t in out.get("terms") or []}
                out["terms"] = list(out.get("terms") or []) + [
                    t for t in visual_terms if t.get("canonical") not in known]
                return out
        self._remember(conversation_id, q or "[사진]", "vision.image", mode,
                       visual_terms, visual_context)
        # report 이벤트가 와야 프런트가 이 턴의 history를 저장한다. 블록은 비어 있어
        # 화면에는 예전처럼 답변 문장만 보인다(reportHTML의 빈 블록 처리 규칙).
        return {"ok": True, "kind": "agent", "intent": "vision.image",
                "headline": mdclean.to_html(answer), "followup": "",
                "terms": visual_terms, "as_of": {}, "blocks": [], "notes": [],
                "sources": [], "partial": False, "visual_context": visual_context}

    # ── ③ ────────────────────────────────────────────
    def _attach_web(self, rep: dict, parsed: dict, q: str, plan: str, past: list[dict]):
        head = parsed["search"][0]
        # ★ 이 term 을 이미 이전 턴에서 knowledge.origin 으로 설명한 적이 있어야만
        #   "출처는요?" 를 "뜻을 반복하지 말고 출처만" 으로 읽는다. 처음 묻는 term 인데도
        #   그렇게 읽으면 "이미 답한 내용" 이라는 전제 자체가 틀려서 답이 어색해진다.
        prior_discussed = any(
            head["canonical"] in [t.get("canonical") for t in (h.get("terms") or [])]
            and h.get("intent") == "knowledge.origin"
            for h in (past or []))
        got = websearch.ask(head["canonical"], head["facet"], q,
                            prior_discussed=prior_discussed)
        if not got:
            rep["notes"].insert(0, {"code": "WEB_UNAVAILABLE", "term": head["canonical"],
                                    "message": "웹에서 확인하지 못했습니다. 지표만 보여드립니다."})
            return
        if not got.get("answer"):
            rep["notes"].insert(0, {"code": "WEB_NO_SOURCE", "term": head["canonical"],
                                    "message": got.get("note") or "확인된 출처가 없습니다."})
            return
        rep["web"] = {"answer": got["answer"], "sources": got["sources"]}
        rep["headline"] = mdclean.first_sentence(got["answer"])
        if got.get("injection_seen"):
            # 읽어 온 글에 지시문이 있었다. 따르지 않았고, 사용자에게 알린다.
            rep["notes"].insert(0, {
                "code": "WEB_INJECTION", "term": head["canonical"],
                "message": "검색된 문서에 지시문이 섞여 있었습니다. 따르지 않았습니다."})

    # ── ② ────────────────────────────────────────────
    def _polish(self, rep: dict):
        head = rep.get("headline")
        if not head:
            return
        ctx = {"intent": rep.get("intent"), "mode": rep.get("kind"),
               "as_of": (rep.get("as_of") or {}).get("metric")}
        new, src = polish.polish(head, context=ctx)
        rep["headline"] = new
        rep["tone"] = src                    # 'llm' 이면 다듬어졌다, 'rule' 이면 원문 그대로

    # ── 인사 ──────────────────────────────────────────
    def _greeting(self, nlu: dict, mode: str = "general") -> dict:
        example = ('"이 자켓 사도 될까?", "지금 안 사면 후회할까?"' if mode == "salmal"
                   else '"카고팬츠 요즘 어때?", "고프코어 얼마나 뜨거워?"')
        return {"ok": True, "kind": "meta", "intent": "meta.greeting", "nlu": nlu,
                "message": ("안녕하세요! FEEDiT입니다.\n\n"
                            "무엇이 궁금하신가요?\n"
                            f"예) {example}")}

    # ── 잡담 (LLM 이 맥락을 보고 판단했다) ──────────────
    def _smalltalk(self, nlu: dict, reply: str) -> dict:
        return {"ok": True, "kind": "meta", "intent": "meta.smalltalk",
                "nlu": dict(nlu, intent="meta.smalltalk", source="llm_context"),
                "message": reply}

    # ── 능력 안내 ─────────────────────────────────────
    def _capability(self, plan: str, nlu: dict) -> dict:
        p = plans.normalize(plan)
        can = ["지금 얼마나 뜨거운지 (트렌드 온도 · 언급량)",
               "어떤 플랫폼에서 많이 나오는지",
               "그 말이 어떻게 시작됐는지 (웹에서 찾아 출처와 함께)"]
        if p != plans.FREE:
            can += ["오르는 중인지 내리는 중인지", "무엇과 같이 언급되는지 (연관어)",
                    "사려는 사람이 많은지 (구매의향)"]
        return {"ok": True, "kind": "meta", "intent": "meta.capability", "nlu": nlu,
                "message": ("스타일 · 소재 · 아이템 · 브랜드 네 가지 키워드로 트렌드를 답합니다.\n\n"
                            "물어볼 수 있는 것\n" + "\n".join("· " + x for x in can) +
                            "\n\n패션과 무관한 질문은 답하지 않습니다."),
                "plan": p}
