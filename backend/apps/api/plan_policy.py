"""요금제 — 프리 · 프로 · 비즈니스 (2026-10-03). DB 를 건드리지 않는 순수 계산.

★ 베타 동안에는 아무것도 막지 않는다.
  FEEDIT_PUBLIC_BETA 가 켜져 있으면 이 파일의 제한은 전부 꺼진다.
  변수가 **없어도 켜진 것**으로 본다 — 지금 운영 중인 서버의 .env 를 건드리지 않아도
  베타가 그대로 유지된다.

  챗봇 서버(ChatBot/app/plans.py)와 **같은 변수**를 본다.
  두 컨테이너가 루트 .env 하나를 같이 읽으므로, 베타를 끝낼 때는
  그 한 줄만 0 으로 바꾸고 둘을 다시 띄우면 된다.

요금제 표 — 화면(frontend/pricing/static/js/pricing.js 의 COMPARE)과 같은 내용이다.

                    프리                       프로          비즈니스
  살!말? 참여       무제한                     무제한        무제한
  AI 챗             하루 20회                  무제한        무제한
  트렌드 분석       FEED 전체 + EDIT 언급량·온도  FEED · EDIT 전체
  리포트 내보내기   미지원                     지원          지원
  데이터 API 연동   미지원                     미지원        지원

결제는 붙어 있지 않다(사업자 등록 전).
  · 프로 · 비즈니스는 **신청 → 운영 계정 승인**으로 바뀐다.
  · 해지(프리로 돌아가기)는 승인 없이 바로 된다.
  · 저장 위치는 app_user.profile_metadata — 새 표가 없다(마이그레이션 없음).
      plan          지금 요금제 ("PRO" · "BUSINESS". 없거나 모르는 값은 FREE)
      plan_request  마지막 신청 한 건 (직업 인증의 job_request 와 같은 모양)
      plan_history  바뀐 기록 (최근 HISTORY_MAX 건)
      plan_chat     오늘 챗봇을 몇 번 썼나 {"day": "2026-10-03", "used": 3}

돌리는 법:  cd backend && python -m unittest apps.api.test_plan_policy
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

FREE, PRO, BUSINESS = "FREE", "PRO", "BUSINESS"
ADMIN = "ADMIN"
VALID = (FREE, PRO, BUSINESS)
PAID = (PRO, BUSINESS)
RANK = {FREE: 0, PRO: 1, BUSINESS: 2, ADMIN: 3}

LABEL = {FREE: "프리", PRO: "프로", BUSINESS: "비즈니스", ADMIN: "운영"}

# 트렌드 분석 EDIT 여섯 탭 — frontend/trend/static/js/nav_meta.js 의 S_EDIT id 와 같다
EDIT_TABS = ("temp", "assoc", "sentiment", "life", "stock", "resale")

# 프리의 하루 챗봇 횟수. 챗봇 서버의 plans.QUOTA[FREE]["turns"] 와 같은 값이어야 한다
# (챗봇 서버가 같은 숫자로 한 번 더 센다 — 둘이 다르면 먼저 닿는 쪽이 막는다).
FREE_CHAT_DAILY = 20

FEATURES = {
    FREE: {
        "salmal": True,
        "chat_daily": FREE_CHAT_DAILY,
        "trend_feed": True,
        "trend_edit": ["temp"],
        "report_export": False,
        "data_api": False,
    },
    PRO: {
        "salmal": True,
        "chat_daily": None,          # None = 하루 횟수를 세지 않는다
        "trend_feed": True,
        "trend_edit": list(EDIT_TABS),
        "report_export": True,
        "data_api": False,
    },
    BUSINESS: {
        "salmal": True,
        "chat_daily": None,
        "trend_feed": True,
        "trend_edit": list(EDIT_TABS),
        "report_export": True,
        "data_api": True,
    },
}

NOTE_MAX = 300
COMPANY_MAX = 60
CONTACT_MAX = 80
REASON_MAX = 200
HISTORY_MAX = 20

# 챗봇에 넘기는 요금제 표 — 몇 초짜리 확인증이면 충분하다. 길면 남에게 넘겨 쓸 틈이 생긴다.
TICKET_TTL = 600
TICKET_VERSION = "v1"


# ── 베타 스위치 ───────────────────────────────────────────────

def public_beta() -> bool:
    """베타인가. 매번 환경변수를 읽는다 — 시험에서 바꿔 끼울 수 있게."""
    return str(os.getenv("FEEDIT_PUBLIC_BETA", "1")).strip().lower() not in {
        "0", "false", "off", "no",
    }


def enforced() -> bool:
    """요금제 제한을 실제로 거는가 (= 베타가 끝났는가)."""
    return not public_beta()


# ── 요금제 판정 ───────────────────────────────────────────────

def normalize(plan) -> str:
    """모르는 값은 FREE 로 떨어뜨린다.

    알파 계정의 "TEST", 운영 계정 표시용 "ADMIN", 빈 값 — 전부 FREE 다.
    모르는 값을 위로 올리면 사고가 조용히 지나간다. 반대여야 한다.
    """
    plan = str(plan or "").strip().upper()
    return plan if plan in VALID else FREE


def stored_plan(meta, is_admin=False) -> str:
    """저장된 요금제. 운영 계정(슈퍼유저 · 스태프)은 ADMIN — 모든 기능을 쓴다."""
    if is_admin:
        return ADMIN
    return normalize((meta or {}).get("plan"))


def features_of(plan) -> dict:
    """그 요금제가 쓸 수 있는 것. ADMIN 은 가장 넓은 비즈니스와 같다."""
    key = BUSINESS if plan == ADMIN else normalize(plan)
    row = FEATURES[key]
    return {k: (list(v) if isinstance(v, list) else v) for k, v in row.items()}


def open_features() -> dict:
    """베타 — 아무것도 막지 않는다."""
    return features_of(BUSINESS)


def chat_plan(plan) -> str:
    """챗봇 서버가 아는 이름으로. 챗봇은 ADMIN 을 모른다 — 가장 넓은 BUSINESS 로 보낸다."""
    return BUSINESS if plan == ADMIN else normalize(plan)


# ── 하루 챗봇 횟수 ─────────────────────────────────────────────

def chat_used(meta, today: str) -> int:
    row = (meta or {}).get("plan_chat")
    if not isinstance(row, dict) or row.get("day") != today:
        return 0
    try:
        return max(0, int(row.get("used") or 0))
    except (TypeError, ValueError):
        return 0


def chat_usage(meta, plan, today: str) -> dict:
    """오늘 몇 번 썼고 몇 번 남았나. 한도가 없으면 limit · remaining 이 None."""
    limit = features_of(plan)["chat_daily"]
    used = chat_used(meta, today)
    if limit is None:
        return {"limit": None, "used": used, "remaining": None, "day": today}
    return {"limit": limit, "used": min(used, limit),
            "remaining": max(limit - used, 0), "day": today}


def chat_consume(meta, plan, today: str) -> tuple[bool, dict]:
    """한 번 쓴다. (통과했나, 새 plan_chat 값).

    한도가 있는 요금제만 막는다. 한도가 없어도 센다 — 운영자가 사용량을 볼 수 있게.
    """
    limit = features_of(plan)["chat_daily"]
    used = chat_used(meta, today)
    if limit is not None and used >= limit:
        return False, {"day": today, "used": used}
    return True, {"day": today, "used": used + 1}


# ── 신청 ──────────────────────────────────────────────────────

def _clean(value, limit) -> str:
    return " ".join(str(value or "").split())[:limit]


def request_public(meta):
    """로그인 응답에 싣는 내 신청 상태. 처리한 사람 아이디는 빼고 보낸다."""
    req = (meta or {}).get("plan_request")
    if not isinstance(req, dict):
        return None
    return {k: req.get(k) for k in ("plan", "status", "requested_at", "decided_at", "reason")}


def pending_of(meta):
    req = (meta or {}).get("plan_request")
    return req if isinstance(req, dict) and req.get("status") == "PENDING" else None


def parse_request(data) -> dict:
    """화면이 보낸 신청을 검사한다. 틀리면 ValueError(사람이 읽을 문구).

    비즈니스는 팀 단위라 팀(회사) 이름을 받는다. 연락처는 비워 두면
    계정 이메일로 연락한다(관리자 목록에 같이 보인다).
    """
    if not isinstance(data, dict):
        raise ValueError("요청 형식이 올바르지 않습니다.")
    plan = str(data.get("plan") or "").strip().upper()
    if plan not in VALID:
        raise ValueError("알 수 없는 요금제입니다.")
    out = {
        "plan": plan,
        "note": _clean(data.get("note"), NOTE_MAX),
        "company": _clean(data.get("company"), COMPANY_MAX),
        "contact": _clean(data.get("contact"), CONTACT_MAX),
    }
    if plan == BUSINESS and not out["company"]:
        raise ValueError("비즈니스 요금제는 팀(회사) 이름을 적어 주세요.")
    if plan != BUSINESS:
        out["company"] = ""
    return out


def new_request(parsed: dict, current: str, now_iso: str) -> dict:
    return {
        "plan": parsed["plan"], "from_plan": current,
        "note": parsed.get("note") or "", "company": parsed.get("company") or "",
        "contact": parsed.get("contact") or "",
        "status": "PENDING", "requested_at": now_iso,
        "decided_at": None, "decided_by": None, "reason": "",
    }


def add_history(meta: dict, kind: str, plan: str, from_plan: str, at: str, by: str = "") -> None:
    """요금제가 바뀐 기록을 한 줄 붙인다. 최근 HISTORY_MAX 건만 남긴다."""
    rows = meta.get("plan_history") if isinstance(meta.get("plan_history"), list) else []
    rows = list(rows) + [{"kind": kind, "plan": plan, "from": from_plan, "at": at, "by": by}]
    meta["plan_history"] = rows[-HISTORY_MAX:]


# ── 화면에 보내는 값 ──────────────────────────────────────────

def state(meta, is_admin=False, signed_in=True, today: str = "") -> dict:
    """로그인 응답(user.billing)과 /api/auth/plan 이 같이 쓰는 모양.

    enforced  베타가 끝났나. false 면 화면은 **지금과 똑같이** 동작해야 한다.
    plan      저장된 요금제 (FREE · PRO · BUSINESS · ADMIN)
    features  지금 실제로 쓸 수 있는 것 — 베타면 전부 열려 있다
    plans     요금제별 기능 (로그아웃할 때 화면이 프리 기준으로 돌아가는 데 쓴다)
    """
    on = enforced()
    plan = stored_plan(meta, is_admin) if signed_in else FREE
    return {
        "enforced": on,
        "signed_in": bool(signed_in),
        "plan": plan,
        "label": LABEL.get(plan, plan),
        "features": features_of(plan) if on else open_features(),
        "plans": {p: features_of(p) for p in VALID},
        "request": request_public(meta) if signed_in else None,
        "chat": chat_usage(meta, plan, today) if (signed_in and today and on) else None,
    }


def guest_state() -> dict:
    """로그인 전. 요금제 화면이 베타인지 아닌지만 알면 된다."""
    return state({}, is_admin=False, signed_in=False)


# ── 챗봇에 넘기는 확인증 ──────────────────────────────────────
#   챗봇 서버는 Django 세션을 모른다. 그래서 요청이 "나는 PRO" 라고 우기면 믿을 수밖에
#   없었다(ChatBot/server.py 머리말). 베타가 끝나면 Django 가 서명한 짧은 확인증만 믿는다.
#   서명 키는 두 서버가 같이 읽는 루트 .env 의 FEEDIT_PLAN_SECRET(없으면 FEEDIT_CHAT_TOKEN).
#   검사 코드는 ChatBot/app/plans.py 의 verify_ticket — 모양을 바꾸면 거기도 같이 바꾼다.

def ticket_secret() -> str:
    return (os.getenv("FEEDIT_PLAN_SECRET") or os.getenv("FEEDIT_CHAT_TOKEN") or "").strip()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def sign_ticket(user_id, plan, now=None, ttl=TICKET_TTL, secret=None):
    """'v1.<내용>.<서명>'. 서명 키가 없으면 None — 챗봇은 그때 모두를 FREE 로 본다."""
    secret = ticket_secret() if secret is None else secret
    if not secret:
        return None
    now = int(time.time() if now is None else now)
    body = json.dumps({"u": str(user_id), "p": chat_plan(plan), "e": now + int(ttl)},
                      separators=(",", ":"), sort_keys=True).encode("utf-8")
    head = f"{TICKET_VERSION}.{_b64(body)}"
    sig = hmac.new(secret.encode("utf-8"), head.encode("ascii"), hashlib.sha256).digest()
    return f"{head}.{_b64(sig)}"
