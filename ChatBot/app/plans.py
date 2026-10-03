"""플랜 게이팅 — 서버에서만 자른다.

잠긴 지표는 응답에 **아예 담기지 않는다.** 프론트가 가릴 것도 없다.
프론트 마스킹은 개발자도구로 다 보인다.

플랜 값 세 개는 pricing.js 의 세 카드(프리·프로·비즈니스)와 1:1 로 맞춘다.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time

FREE, PRO, BUSINESS = "FREE", "PRO", "BUSINESS"
VALID = (FREE, PRO, BUSINESS)

# 지표 → 이 플랜 이상이어야 보인다
GATE = {
    "raw_count":   FREE,
    "temp":        FREE,
    "pct_rank":    FREE,
    "evidence":    FREE,     # 건수는 아래에서 따로 자른다
    "direction":   PRO,
    "momentum":    PRO,
    "level":       PRO,
    "share_pct":   PRO,
    "sources":     PRO,      # FREE 는 상위 3개까지
    "associations": PRO,
    "sentiment":   PRO,
    "lifecycle":   PRO,
    "price":       PRO,
    "resale":      PRO,
    "salmal_axes": PRO,      # 살!말?지수 총점은 FREE 도 본다. 4축 분해만 PRO
    "render":      PRO,
}

# 잠긴 지표를 사람 말로 — 업셀 문구에 그대로 쓴다
LABEL = {
    "direction": "오르는지 내리는지",
    "momentum": "모멘텀",
    "level": "수준 분해",
    "share_pct": "점유율",
    "sources": "플랫폼별 분해",
    "associations": "연관어",
    "sentiment": "구매의향",
    "lifecycle": "수명주기",
    "price": "할인·최저가",
    "resale": "리세일 시세",
    "salmal_axes": "살!말?지수 4축 분해",
    "render": "착장 이미지",
}

RANK = {FREE: 0, PRO: 1, BUSINESS: 2}

# 공개 베타 동안은 새로 clone/pull 한 환경도 별도 플랜 설정 없이 모든 챗봇 기능을
# 쓴다. 환경변수가 **없는 것이 베타 ON** 이다. 이전 .env 에 FREE나 공유 토큰이
# 남아 있어 팀원마다 동작이 달라지는 문제를 막는다. 베타 종료 때만 0으로 끈다.
PUBLIC_BETA = str(os.getenv("FEEDIT_PUBLIC_BETA", "1")).strip().lower() not in {
    "0", "false", "off", "no",
}

# 하루 한도. pricing.js 는 PRO 를 "무제한"이라 적어 뒀지만 무제한은 구현할 수 없다.
# 300회는 실질 무제한이되 원가 폭주를 막는다. 문구 수정은 설계서 15장 #6.
QUOTA = {
    FREE:     {"turns": 20,  "images": 0,  "searches": 1},
    PRO:      {"turns": 300, "images": 10, "searches": 3},
    BUSINESS: {"turns": 300, "images": 30, "searches": 3},
}

FREE_SOURCE_LIMIT = 3
EVIDENCE_LIMIT = {FREE: 1, PRO: 5, BUSINESS: 5}


def normalize(plan) -> str:
    """모르는 값은 FREE 로 떨어뜨린다.

    모르는 값을 PRO 로 올리면 사고가 조용히 지나간다. 반대여야 한다.
    """
    return plan if plan in VALID else FREE


def effective(plan) -> str:
    """HTTP 사용자에게 실제 적용할 플랜. 공개 베타에서는 전 기능을 연다."""
    return BUSINESS if PUBLIC_BETA else normalize(plan)


def allows(plan: str, key: str) -> bool:
    need = GATE.get(key, PRO)
    return RANK[normalize(plan)] >= RANK[need]


def apply(plan: str, payload: dict) -> tuple[dict, list[str]]:
    """리포트에서 잠긴 것을 빼고, 무엇이 잠겼는지 목록을 돌려준다."""
    plan = normalize(plan)
    locked = []
    out = dict(payload)
    for key in list(out.keys()):
        if key in GATE and not allows(plan, key):
            out.pop(key, None)
            locked.append(key)
    # FREE 는 소스 상위 3개까지만
    if plan == FREE and isinstance(out.get("sources"), list):
        out["sources"] = out["sources"][:FREE_SOURCE_LIMIT]
    if isinstance(out.get("evidence"), list):
        out["evidence"] = out["evidence"][:EVIDENCE_LIMIT[plan]]
    return out, locked


# 업셀에 먼저 보여 줄 순서. "모멘텀"·"수준 분해" 같은 내부 용어가 앞에 오면
# 사용자에게 아무 뜻도 전달되지 않는다. 와닿는 것부터 세운다.
UPSELL_ORDER = ["direction", "sentiment", "associations", "sources",
                "lifecycle", "price", "resale", "salmal_axes", "render",
                "share_pct", "level", "momentum"]


def upsell(locked: list[str], plan: str) -> dict | None:
    """재촉하지 않는다. 무엇이 잠겼는지 이름으로 말하고 끝낸다."""
    ordered = [k for k in UPSELL_ORDER if k in locked]
    names = [LABEL[k] for k in ordered if k in LABEL]
    if not names or normalize(plan) != FREE:
        return None
    head = " · ".join(names[:3])
    # 받침에 맞는 조사. 돌려 보고 잡았다 — "플랫폼별 분해 이 필요합니다" 로 나왔다.
    last = head[-1]
    batchim = 0xAC00 <= ord(last) <= 0xD7A3 and (ord(last) - 0xAC00) % 28 != 0
    return {"type": "upsell", "plan": PRO, "locked": locked,
            "why": f"이 질문에 더 답하려면 {head}{'이' if batchim else '가'} 필요합니다.",
            "unlocks": names}


# ── 요금제 확인증 (2026-10-03) ──────────────────────────────
#   이 서버는 Django 로그인 세션을 모른다. 그래서 예전에는 요청이 스스로 적은 plan 을
#   그대로 믿었다(server.py 머리말 — "PRO 라고 우기면 못 막는다").
#   베타가 끝나면(PUBLIC_BETA=False) Django 가 서명해 준 확인증만 믿는다.
#     만드는 곳  backend/apps/api/plan_policy.py 의 sign_ticket
#     모양       "v1.<base64url JSON {u, p, e}>.<base64url HMAC-SHA256>"
#     서명 키    FEEDIT_PLAN_SECRET (없으면 FEEDIT_CHAT_TOKEN) — 두 서버가 같은 루트 .env 를 읽는다
#   확인증이 없거나 틀리거나 시간이 지났으면 None — 부르는 쪽이 FREE 로 본다.
#   베타 동안에는 effective() 가 어차피 BUSINESS 를 돌려주므로 이 함수를 부르지 않는다.

def ticket_secret() -> str:
    return (os.getenv("FEEDIT_PLAN_SECRET") or os.getenv("FEEDIT_CHAT_TOKEN") or "").strip()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def verify_ticket(ticket, now=None, secret=None) -> dict | None:
    """맞으면 {"user": "12", "plan": "PRO"}, 아니면 None."""
    secret = ticket_secret() if secret is None else secret
    if not secret or not isinstance(ticket, str) or len(ticket) > 600:
        return None
    parts = ticket.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        return None
    head = f"{parts[0]}.{parts[1]}"
    want = hmac.new(secret.encode("utf-8"), head.encode("ascii", "replace"), hashlib.sha256).digest()
    try:
        got = _unb64(parts[2])
        body = json.loads(_unb64(parts[1]).decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(want, got) or not isinstance(body, dict):
        return None
    try:
        if int(body.get("e") or 0) < int(time.time() if now is None else now):
            return None
    except (TypeError, ValueError):
        return None
    user = str(body.get("u") or "")[:40]
    if not user:
        return None
    return {"user": user, "plan": normalize(body.get("p"))}
