"""Luna 연결과 세 기능을 실제로 한 번씩 불러 본다.

★ 이 스크립트는 **네트워크가 되는 곳에서** 돌려야 한다.
  Claude 작업 환경은 api.openai.com 이 막혀 있어 여기서는 확인할 수 없었다.

    cd feedit/ChatBot
    python3 tools_llm_check.py

키는 환경변수 OPENAI_API_KEY, 없으면 크롤러 data/keys.json 에서 읽는다.
**키 값을 출력하지 않는다.**
"""
from __future__ import annotations

import sys

from app import llm, polish, websearch
from app.nlu import classify


def main() -> int:
    print("모델   :", llm.MODEL)
    print("키     :", llm.key_hint())
    if not llm.available():
        print("키가 없습니다. 크롤러 관리자 화면 [API] 탭에서 넣거나 OPENAI_API_KEY 를 설정하세요.")
        return 2

    print("\n[0] 연결")
    got = llm.respond("한 단어로만 답한다.", {"q": "ping"},
                      llm.strict_schema("ping", {"pong": {"type": "string"}}, ["pong"]),
                      timeout=20)
    print("   ", "OK" if got else f"실패 — {llm.LAST_ERROR}")
    if not got:
        return 1

    print("\n[1] 의도 분류 — 규칙이 못 잡는 문장으로")
    for q in ["그냥 니트 관련해서 알고싶은데",
              "요즘 사람들이 많이 찾는 소재가 뭔지",
              "내일 서울 날씨 알려줘"]:
        r = classify(q, "general")
        print(f"    {q:28s} → {r['intent']:18s} src={r['source']} conf={r.get('confidence')}")

    print("\n[2] 어투 다듬기 — 숫자가 그대로인지")
    src = "<b>발레코어</b>의 트렌드 온도는 <b>86점 · 과열</b>입니다. 언급 333건 기준입니다."
    out, how = polish.polish(src)
    print("    원문:", src)
    print("    결과:", out)
    print("    출처:", how, "" if how == "llm" else f"({llm.LAST_ERROR})")
    import re
    a = re.findall(r"\d[\d,]*", src)
    b = re.findall(r"\d[\d,]*", out)
    print("    숫자:", a, "→", b, "★ 같아야 한다:", "OK" if a == b else "★★ 다르다 ★★")

    print("\n[3] 웹 검색")
    r = websearch.ask("고프코어", "style", "고프코어는 어떻게 시작됐어?")
    if not r:
        print("    실패 —", llm.LAST_ERROR)
    elif not r.get("answer"):
        print("    출처 없음 —", r.get("note"))
    else:
        print("    답:", r["answer"][:160].replace("\n", " "))
        for s in r["sources"]:
            print("      ·", s.get("title", "")[:50], "—", s.get("url"))
        print("    지시문 감지:", r.get("injection_seen"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
