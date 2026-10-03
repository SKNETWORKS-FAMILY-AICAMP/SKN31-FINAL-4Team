"""코디 인계(Fit Handoff) — 스타일로 상품을 고르고, 연출을 검수한다.

왜 별도 모듈인가 (AGENTS.md §1) —
  슬롯별로 어떤 아이템을 찾을지 적은 표(SLOT_KINDS)가 답변 경로 안에 숨으면
  하드코딩이고, 도구가 읽는 자료로 바깥에 드러나 있으면 능력이다. season.py 가
  같은 자리에 있다 — 고치면 답이 바뀌고, 무엇을 기준으로 골랐는지 말할 수 있다.

이 모듈이 하지 않는 것 —
  · 옷의 구조(여밈·두께)를 상품명으로 판별하지 않는다. 그건 사진을 볼 수 있는
    쪽(vton.inspect)만 안다. 실제 반례: "[원단 선택 가능]카펜터 버뮤다 스웨트
    8부 팬츠" 는 '스웨트' 가 붙었지만 하의다.
  · 이미지를 생성하지 않는다. 생성은 사용자가 위젯에서 누를 때만 일어난다.
"""
from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor

from . import vton


# ── 슬롯마다 무엇을 찾나 ────────────────────────────────────
#   ★ 값은 /api/products 의 kind 파라미터로 그대로 간다. kind 는 ITEM 태그
#     (commerce.product_term · term_type='ITEM') 와 표준 카테고리명 양쪽을 본다
#     (backend/apps/api/views.py `_apply`). 그래서 태그가 비어 있어도 카테고리로
#     걸린다 — 한쪽만 채워져 있어도 상품이 나온다.
#   ★ 이름은 vton.SLOT_ORDER 와 같아야 한다. 한쪽만 늘리면 화면의 칸과 어긋난다.
SLOT_KINDS: dict[str, list[str]] = {
    "상의": ["티셔츠", "셔츠", "니트", "스웨트셔츠", "후드", "블라우스"],
    "하의": ["팬츠", "데님", "스커트", "반바지", "트레이닝팬츠"],
    "아우터": ["재킷", "코트", "점퍼", "가디건", "베스트"],
    "원피스(셋업)": ["원피스", "점프수트", "셋업"],
    "신발": ["스니커즈", "운동화", "부츠", "로퍼", "샌들"],
}
# 기본 코디 — 상의·하의·신발 한 벌. 아우터와 레이어드는 모델이 요청할 때만 늘린다.
DEFAULT_SLOTS = ["상의", "하의", "신발"]
# 한 코디에 담을 수 있는 칸 수. 화면(VF_MAX)·서버(vton.MAX_ITEMS)와 같은 상한이다.
MAX_SLOTS = vton.MAX_ITEMS


# ── 상대 경로 사진 (2026-09-22) ─────────────────────────────
#   DB 실측: commerce.product_source.thumbnail_url 중 27,424건이 호스트 없는
#   무신사 상대 경로다(`thumbnails/images/goods_img/...`). 가장 큰 덩어리라
#   이것을 버리면 상의·하의가 통째로 빈다.
#   ★ 기준은 수집기가 원본이다 — backend/collection/musinsa/constants.py
#     IMAGE_BASE_URL = "https://image.msscdn.net". 여기서 새로 정하지 않는다.
#   ★ 같은 규칙이 화면 쪽에도 있다. 고칠 때 셋을 같이 고친다:
#       backend/apps/api/images.py       (Django)
#       frontend/api/_lib/image.js       (Vercel 함수 — 배포된 화면이 쓰는 길)
#     공통 계약은 backend/apps/api/test_images.py 의 표다.
IMAGE_BASE = {"MUSINSA": "https://image.msscdn.net",
              "MUSINSA_USED": "https://image.msscdn.net"}
# 상대 경로로 인정할 모양. 모르는 모양은 주소로 만들지 않고 버린다 —
# 앞에 아무 호스트나 붙이면 엉뚱한 사진을 입히게 된다.
RELATIVE_HINTS = ("thumbnails/images/", "images/goods_img/", "goods_img/")


def absolute_image(url: str, source: str = "") -> str:
    """상품 사진 주소를 받아 온전한 주소로 돌려준다. 못 만들면 빈 문자열."""
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("//"):
        return "https:" + text
    path = text.lstrip("/")
    if not path.startswith(RELATIVE_HINTS):
        return ""
    base = IMAGE_BASE.get(str(source or "").upper())
    if not base:
        # 소스를 모르면 모양으로 가른다 — goods_img 는 무신사 경로다.
        base = IMAGE_BASE["MUSINSA"] if "goods_img/" in path else ""
    return f"{base}/{path}" if base else ""


# ── 스타일 이름 → 상품 태그 이름 (2026-10-01) ──────────────────
#   /api/products 의 style 은 상품 태그(term_type='STYLE')의 **표준 이름과 정확히**
#   맞아야 걸린다(backend/apps/api/views.py `_apply`). 모델은 사용자의 말을 그대로
#   옮겨 적는다. 실측(2026-10-01, 운영 /api/products):
#       style=긱시크    → 상품 있음        style=긱시크룩 → 0건
#   "결혼식 하객" 은 아예 스타일이 아니다(사전 축 tpo). 그대로 찾으면 0건이고,
#   챗봇은 "태그된 상품이 없다" 고 답했다 — 상품이 없는 게 아니라 이름이 틀렸다.
#   그래서 찾기 전에 사전(LexiconGate)으로 스타일 표준 이름을 고른다.
_NOT_STYLE_REASON = {
    "tpo": "착용 상황(TPO)이라 상품 스타일 태그가 아닙니다",
    "item": "아이템 이름이라 스타일이 아닙니다 — kinds 에 적을 말입니다",
    "material": "소재 이름이라 스타일이 아닙니다",
    "color": "색 이름이라 스타일이 아닙니다",
    "brand": "브랜드 이름이라 스타일이 아닙니다",
}


def resolve_styles(names, gate) -> tuple[list[str], list[dict]]:
    """(찾을 스타일 표준 이름, 스타일이 아니어서 뺀 말) 을 돌려준다.

    ★ 사전을 못 읽으면 이름을 그대로 둔다 — 고칠 근거가 없는데 지우면, 맞게 적힌
      이름까지 사라진다. 그때는 예전처럼 찾아 보고 없으면 없다고 말한다.
    """
    styles: list[str] = []
    skipped: list[dict] = []
    for raw in names or []:
        name = str(raw or "").strip()
        if not name:
            continue
        try:
            parsed = gate.parse(name)
        except Exception:                       # noqa: BLE001
            parsed = None
        if not isinstance(parsed, dict):
            if name not in styles:
                styles.append(name)
            continue
        hits = [h for key in ("search", "modifier", "other")
                for h in (parsed.get(key) or []) if isinstance(h, dict)]
        found = [str(h.get("canonical") or "") for h in hits
                 if str(h.get("facet") or "").lower() == "style" and h.get("canonical")]
        if found:
            for canonical in found:
                if canonical not in styles:
                    styles.append(canonical)
            continue
        facet = next((str(h.get("facet") or "").lower() for h in hits if h.get("facet")), None)
        skipped.append({"name": name, "facet": facet,
                        "reason": _NOT_STYLE_REASON.get(facet or "",
                                                        "사전에 없는 스타일 이름입니다")})
    return styles, skipped


# ── 승인된 코디 (화면을 거쳐 돌아온 것) ─────────────────────────
#   ★ 2026-10-01 — 승인 카드 "이 코디로 입혀보기" 를 누르면 화면이 코디를 들고 와서
#     /v1/chat 의 fit_proposal 로 보낸다. 서버(server.py)는 받았는데 engine.ask 가
#     ctx 로 옮기는 목록에 이 키가 없어 **조용히 버렸다.** 그래서 살!말? 의 첫 턴에
#     build_fit 이 도구 목록에 한 번도 오르지 못했고, 모델은 "어떤 코디를 입혀볼까요?"
#     라고 되물었다(2026-10-01 실측, 아메카지 코디).
#   ★ 브라우저를 거쳐 온 값이다. 우리가 적은 칸만, 길이를 잘라 받는다. 사진 주소는
#     build_fit 이 허용 호스트로 한 번 더 거른다(vton.image_host_allowed).
_PROPOSAL_KEYS = ("name", "brand", "image", "url", "slot", "style", "kind", "price",
                  "product_source_id", "source", "source_label", "category")


def clean_proposal(raw) -> dict | None:
    """화면이 돌려준 코디를 서버가 쓸 모양으로. 입힐 것이 없으면 None."""
    if not isinstance(raw, dict):
        return None
    items = []
    for row in (raw.get("items") or [])[:MAX_SLOTS]:
        if not isinstance(row, dict):
            continue
        kept = {}
        for key in _PROPOSAL_KEYS:
            value = row.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                kept[key] = value
            elif isinstance(value, str) and value.strip():
                kept[key] = value.strip()[:500 if key in ("image", "url") else 80]
        if kept.get("slot") in SLOT_KINDS and kept.get("image"):
            items.append(kept)
    if not items:
        return None
    out = {"items": items,
           "options": [str(o) for o in (raw.get("options") or []) if str(o) in vton.OPTION_LINES],
           "styles": [str(s).strip()[:30] for s in (raw.get("styles") or [])
                      if str(s or "").strip()][:4]}
    if raw.get("gender") in ("FEMALE", "MALE"):
        out["gender"] = raw["gender"]
    occ = " ".join(str(raw.get("occasion") or "").split())[:40]
    if occ:
        out["occasion"] = occ
    ref = raw.get("ref") if isinstance(raw.get("ref"), dict) else None
    if ref and str(ref.get("url") or "").startswith(("http://", "https://")):
        out["ref"] = {k: str(ref.get(k) or "").strip()[:120 if k != "url" else 300]
                      for k in ("title", "who", "url", "domain")}
    why = str(raw.get("why") or "").strip()[:200]
    if why:
        out["why"] = why
    return out


def clean_memory(raw) -> dict:
    """화면이 보낸 '이 대화의 코디 기억'(fit_memory)을 걸러 ctx 에 넣을 모양으로.

    ★ 브라우저를 거쳐 온 값이다. 문자열만, 개수와 길이를 잘라 받는다. 이 값은 상품을
      **빼는 데만** 쓰고(seen), 출처(refs)는 모델에게 '피해서 고르라' 고 알려 주는 데만
      쓴다 — 화면에 출처로 다시 올리지 않는다(출처는 이번 턴 find_looks 결과에서만 온다).
    """
    if not isinstance(raw, dict):
        return {}
    def strs(v, n, size):
        return [str(x).strip()[:size] for x in (v if isinstance(v, list) else [])
                if isinstance(x, (str, int)) and str(x).strip()][:n]
    out = {}
    seen = strs(raw.get("seen"), 60, 300)
    if seen:
        out["fit_seen"] = seen
    refs = [u for u in strs(raw.get("refs"), 8, 300) if u.startswith(("http://", "https://"))]
    if refs:
        out["fit_refs"] = refs
    occ = " ".join(str(raw.get("occasion") or "").split())[:40]
    if occ:
        out["fit_occasion"] = occ
    return out


def _normalize_slots(slots) -> list[str]:
    """모르는 칸 이름은 버리고, 같은 칸이 두 번 와도 그대로 둔다.

    ★ 중복을 막지 않는다 — '아우터' 가 둘이어야 레이어드가 성립한다
      (chat_popup.cpFitItems 가 같은 이유로 중복을 허용한다).
    """
    rows = [str(s or "").strip() for s in (slots or [])]
    rows = [s for s in rows if s in SLOT_KINDS]
    return (rows or list(DEFAULT_SLOTS))[:MAX_SLOTS]


# ── 늘 같은 룩이 나오던 문제 (2026-10-02) ─────────────────────
#   예전엔 칸마다 추천순 **1위 한 점**(got[0])만 집었다. 같은 스타일 · 같은 아이템이면
#   몇 번을 물어도 같은 상품, 같은 룩이었다.
#   → 칸마다 후보를 POOL 만큼 받아, 이 대화에서 이미 보여 준 상품(seen)을 빼고, 위쪽
#     PICK_TOP 안에서 하나를 뽑는다. 추천순 위쪽에서만 뽑으니 엉뚱한 상품이 섞이지
#     않고, 같은 질문에도 다른 조합이 나온다.
POOL = 12
PICK_TOP = 6


def item_key(row: dict) -> str:
    """상품을 가리키는 열쇠 — 판매처 상품 id, 없으면 상품 주소, 없으면 사진 주소."""
    for k in ("product_source_id", "url", "image"):
        v = str((row or {}).get(k) or "").strip()
        if v:
            return v[:300]
    return ""


def _keys(row: dict) -> set[str]:
    """상품의 열쇠 전부 — 화면은 주소로, 서버는 id 로 기억할 수 있어 어느 쪽이든 맞춘다."""
    return {str((row or {}).get(k) or "").strip()[:300]
            for k in ("product_source_id", "url", "image")} - {""}


def propose(market, styles, slots=None, kinds=None, limit: int = POOL,
            gender: str | None = None, seen=None, rng: random.Random | None = None) -> dict:
    """스타일 태그로 슬롯별 상품을 한 점씩 고른다. 생성하지 않는다.

    ★ 슬롯 조회는 서로 독립이다 — 차례로 물으면 한 바퀴가 어댑터 timeout×칸 수가
      된다(8초×3=24초). 예산의 절반을 조회가 먹던 자리라 병렬로 부른다.
    ★ 사진 없는 상품은 코디에 담지 않는다. 입힐 수 없는 것을 승인 카드에 올리면
      사용자는 눌러 보고 나서야 안다.
    """
    names = [str(s or "").strip() for s in (styles or []) if str(s or "").strip()]
    gender = gender if gender in ("FEMALE", "MALE") else None
    if not names:
        return {"unavailable": "어떤 스타일로 고를지 정해지지 않았습니다."}
    picks = _normalize_slots(slots)
    # ★ 방금 추천한 아이템 말을 그대로 쓴다 (2026-09-22). "블록코어의 트랙 재킷" 을
    #   추천했으면 '재킷' 이 아니라 **트랙 재킷** 으로 찾는 편이 맞다. 칸 순서와
    #   짝을 맞춰 오고, 빈 자리는 기준표(SLOT_KINDS)로 떨어진다.
    asked = [str(k or "").strip() for k in (kinds or [])]
    asked += [""] * max(0, len(picks) - len(asked))
    shown = {str(x)[:300] for x in (seen or []) if str(x or "").strip()}
    rng = rng or random.Random()

    def one(index: int, slot: str) -> list[dict]:
        # 찾을 말: 모델이 준 아이템 → 기준표. 스타일도 하나씩 건다 — 여러 개를 한
        # 번에 걸면 어느 태그로 걸린 상품인지 알 수 없어 "왜 골랐나" 를 못 말한다.
        words = [w for w in [asked[index]] if w] + SLOT_KINDS[slot][:2]
        for style in names[:2]:
          for word in words[:2]:
            sel = {"style": style, "kind": word}
            if gender:
                sel["gender"] = gender
            rows = market.products(sel, limit=limit)
            got = []
            for row in (rows or []):
                # 사진을 온전한 주소로 만든다. 못 만들면 담지 않는다 —
                # 입힐 수 없는 것을 승인 카드에 올리면 눌러 보고 나서야 안다.
                image = absolute_image(row.get("image"), row.get("source"))
                if image and vton.image_host_allowed(image):
                    got.append({**row, "image": image})
            # 이미 보여 준 상품은 뺀다. 다 본 것뿐이면 다음 말로 넘어간다 — 같은 상품을
            # "다른 룩" 이라며 다시 내밀지 않는다.
            fresh = [r for r in got if not (_keys(r) & shown)]
            if fresh:
                pick = rng.choice(fresh[:PICK_TOP])
                return [{**pick, "slot": slot, "style": style, "kind": word}]
        return []

    with ThreadPoolExecutor(max_workers=min(4, len(picks))) as pool:
        found = list(pool.map(one, range(len(picks)), picks))

    # 같은 상품이 두 칸에 걸리면(아우터 둘 등) 뒤쪽 칸을 비운다.
    used, items = set(), []
    for rows in found:
        for row in rows:
            k = item_key(row)
            if k and k in used:
                continue
            used.add(k)
            items.append(row)
    if not items:
        empty = " · ".join(sorted(set(picks)))
        return {"unavailable": f"'{names[0]}' 태그가 붙은 상품 중 사진이 있는 것을 "
                               f"{empty} 칸에서 찾지 못했습니다."}
    missed = [s for s, rows in zip(picks, found) if not rows]
    out = {"items": items, "styles": names, "slots": picks}
    if shown:
        out["excluded_seen"] = len(shown)
    if gender:
        out["gender"] = gender
    if missed:
        # 없는 칸을 조용히 빼지 않는다 — 결측을 숨기지 않는 리포트 원칙과 같은 자리.
        out["missing_slots"] = sorted(set(missed))
    return out


def prune_options(options, items, seen) -> tuple[dict, list[str]]:
    """아이템과 맞지 않는 연출을 떼어내고, 무엇을 왜 뗐는지 함께 돌려준다.

    seen 은 vton.inspect() 결과이고 items 와 같은 순서다. 사진을 못 본 경우
    (seen 이 비었을 때)는 아무것도 떼지 않는다 — 확인하지 못한 것을 근거로
    지시를 지우면, 사용자가 켠 연출이 이유 없이 사라진다.
    """
    on = {k: bool(v) for k, v in (options or {}).items() if k in vton.OPTION_LINES}
    dropped: list[str] = []
    rows = list(items or [])
    looks = list(seen or [])

    def looked(slot: str) -> list[dict]:
        return [s for s, i in zip(looks, rows) if i.get("slot") == slot]

    # ① 레이어드는 아우터가 둘 이상일 때만 성립한다. 사진 판단이 아니라 산수다.
    outers = [i for i in rows if i.get("slot") == "아우터"]
    if on.get("outer_layered") and len(outers) < 2:
        on["outer_layered"] = False
        dropped.append("아우터가 한 벌이라 레이어드는 빼고 그립니다.")

    # ② 그 칸이 아예 없으면 그 칸의 여밈 지시도 없다.
    for key, slot in (("outer_open", "아우터"), ("outer_closed", "아우터"),
                      ("top_open", "상의"), ("top_closed", "상의")):
        if on.get(key) and not any(i.get("slot") == slot for i in rows):
            on[key] = False
            dropped.append(f"{slot} 가 없어 {slot} 열기/닫기는 뺐습니다.")

    # ③ 여밈이 없는 옷은 열 수 없다. 판단은 사진이 한다(vton.inspect).
    for slot, keys in (("상의", ("top_open", "top_closed")),
                       ("아우터", ("outer_open", "outer_closed"))):
        rows_seen = looked(slot)
        if not rows_seen or not any(on.get(k) for k in keys):
            continue
        if any(s.get("openable") == "yes" for s in rows_seen):
            continue
        if any(s.get("openable") == "no" for s in rows_seen):
            for k in keys:
                on[k] = False
            dropped.append(f"사진을 보니 {slot}에 여밈이 없어 열기/닫기는 뺐습니다.")
        else:
            # ★ 모르면 빼지도 넣지도 않는다. 켜진 채 두고 확인하지 못했다고 밝힌다.
            dropped.append(f"{slot} 사진에서 여밈을 확인하지 못했습니다.")

    # ④ 짝 충돌 — vton.option_lines 도 둘 다 버리지만 조용하다. 여기서 사유를 남긴다.
    for a, b in vton.OPTION_CONFLICTS:
        if on.get(a) and on.get(b):
            on[a] = on[b] = False
            dropped.append("열기와 닫기를 같이 켜서 둘 다 뺐습니다.")
    return on, dropped


def layer_order(items, seen) -> list[dict]:
    """아우터가 둘이면 얇은 것을 앞 칸에 둔다.

    생성 프롬프트는 "얇고 짧은 것을 안쪽" 이라고만 적혀 있어, 어느 쪽이 얇은지는
    사진을 본 쪽이 정해 줘야 한다(vton.inspect 의 layer). 모르면 순서를 바꾸지
    않는다.
    """
    weight = {"얇음": 0, "보통": 1, "두꺼움": 2}
    order = {id(i): weight.get((s or {}).get("layer"), 1)
             for i, s in zip(items or [], seen or [])}
    if not order:
        return list(items or [])
    return sorted(items, key=lambda i: (i.get("slot") != "아우터", order.get(id(i), 1)))
