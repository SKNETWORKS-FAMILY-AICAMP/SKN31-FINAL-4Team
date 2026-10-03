"""실데이터 스모크 — 진짜 DB 로 돌려 본다. 지어낸 예시로 확인하지 않는다."""
from __future__ import annotations

import json
import sys

from app.engine import ChatEngine
from app import plans

CASES = [
    ("발레코어 요즘 어때?",            "general", plans.FREE),
    ("발레코어 요즘 어때?",            "general", plans.PRO),
    ("티셔츠 꺾였어?",                 "general", plans.PRO),
    ("나이키 지금 어때?",              "general", plans.PRO),
    ("데님이랑 같이 뜨는 거 뭐야?",     "general", plans.PRO),
    ("청바지 사람들 반응 어때?",        "general", plans.PRO),
    ("코트 지금 사도 될까?",           "general", plans.PRO),
    ("코케트 어때?",                   "general", plans.PRO),
    ("우리 랩실에서 회의했어요",        "general", plans.PRO),
    ("너 뭐 할 수 있어?",              "general", plans.FREE),
]


def line(s=""):
    print(s)


def main():
    eng = ChatEngine()
    line(f"DB      {eng.store.path}")
    line(f"기준일  {eng.store.latest_day()}   metric_version={eng.store.version}")
    line(f"사전    canonical {len(eng.gate.lex.facet_of):,} · 지표 적재 {len(eng.gate.prefer):,}")
    line("=" * 78)
    for q, mode, plan in CASES:
        r = eng.ask(q, mode=mode, plan=plan)
        line(f"\n[{plan}] {q}")
        line(f"  intent={r.get('intent')}  ok={r.get('ok')}")
        if not r.get("ok"):
            line(f"  reason={r.get('reason')}")
            msg = (r.get("message") or "").replace("\n\n", " / ").replace("\n", " ")
            line(f"  {msg[:110]}")
            if r.get("near"):
                line("  near=" + ", ".join(x["canonical"] for x in r["near"]))
            continue
        if r.get("kind") == "meta":
            line("  " + r["message"].split("\n")[0])
            continue
        line("  " + r["headline"].replace("<b>", "").replace("</b>", ""))
        for t in r["terms"]:
            if not t.get("available"):
                line(f"    - {t['canonical']}({t['facet']}) 지표 없음")
                continue
            d = t.get("direction")
            line(f"    - {t['canonical']}({t['facet']}) temp={t.get('temp')} "
                 f"raw={t.get('raw_count')} dir={d['label'] if d else '—'} "
                 f"src={len(t.get('sources') or [])} assoc={len(t.get('associations') or [])} "
                 f"sent={'○' if t.get('sentiment') else '—'}")
        if r.get("locked"):
            line(f"    locked={r['locked']}")
        for n in r["notes"][:3]:
            line(f"    ! {n['code']}: {n['message']}")
    line("\n" + "=" * 78)
    if "--json" in sys.argv:
        print(json.dumps(eng.ask("발레코어 요즘 어때?", plan=plans.PRO),
                         ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    main()
