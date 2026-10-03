"""데이터 API 연동 — 비즈니스 요금제 (2026-10-03). DB 를 건드리지 않는 순수 계산.

비즈니스 회원이 자기 시스템(엑셀 · BI · 사내 대시보드)에서 FEEDiT 지표를 직접 받아 가는 길이다.
화면이 쓰는 것과 **같은 지표 계산(views.py)** 을 그대로 내준다 — 숫자를 새로 만들지 않는다.

★ 베타 동안에는 열리지 않는다.
  요금제(plan_policy.enforced)가 꺼져 있으면 키를 만들 수도, 지표를 받을 수도 없다.
  베타가 끝나면(FEEDIT_PUBLIC_BETA=0) 비즈니스 · 운영 계정이 키를 만들어 바로 쓴다.

부르는 법 (밖에서)
  GET https://<서비스 주소>/api/data                 쓸 수 있는 지표 목록
  GET https://<서비스 주소>/api/data/<지표>?term=…    지표 하나
  머리글  Authorization: Bearer fdk_…   (또는 X-API-Key: fdk_…)

키
  'fdk_<회원 번호>_<키 번호>_<비밀>' — 회원 번호로 행 하나만 찾아 비교한다(전체를 뒤지지 않는다).
  저장하는 것은 SHA-256 해시뿐이다. 원문은 만든 순간 한 번만 보여 주고 다시 보여 줄 수 없다.
  app_user.profile_metadata["data_api_keys"] 에 둔다 — 새 표가 없다(마이그레이션 없음).

한도 (환경변수로 바꿀 수 있다)
  FEEDIT_DATA_API_PER_DAY  계정당 하루 요청 수, 기본 10000
  FEEDIT_DATA_API_PER_MIN  키당 분당 요청 수, 기본 60

돌리는 법:  cd backend && python -m unittest apps.api.test_data_api
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets

KEY_PREFIX = "fdk"
KEY_RE = re.compile(r"^fdk_(\d{1,12})_([0-9a-f]{8})_([A-Za-z0-9_-]{20,64})$")
MAX_KEYS = 5                 # 계정당 살아 있는 키 수
NAME_MAX = 40

# 내주는 지표 — 이름 → (views.py 함수 이름, 설명, 받는 값)
# ★ 상품 목록 · 사전 통째 받기는 넣지 않는다. 긁어 가기 좋은 원본이고, 요금제 표의 '지표 연동' 과 다르다.
METRICS = {
    "trend": ("trend", "언급량 · 트렌드 온도 추이", "term (필수) · source"),
    "search": ("search", "검색량 · 검색 추이 · 지역", "term (필수)"),
    "assoc": ("assoc", "연관어", "term (필수) · sort=pmi|lift|count"),
    "sentiment": ("sentiment", "긍부정(구매 의향)", "term (필수) · subject"),
    "lifecycle": ("lifecycle", "수명주기", "term 또는 style · kind · brand · item"),
    "discount": ("discount", "할인률 변화", "style · kind · brand · item 또는 source_id"),
    "resale": ("resale", "리세일 지수", "style · kind · brand · item 또는 product_id · source_id · days"),
    "terms": ("terms", "지표가 있는 용어 목록", "rank=hot (선택)"),
}


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(max(value, low), high)


def per_day() -> int:
    return _env_int("FEEDIT_DATA_API_PER_DAY", 10000, 1, 10_000_000)


def per_min() -> int:
    return _env_int("FEEDIT_DATA_API_PER_MIN", 60, 1, 100_000)


# ── 키 ────────────────────────────────────────────────────────

def digest(raw_key: str) -> str:
    return hashlib.sha256(str(raw_key).encode("utf-8")).hexdigest()


def new_key(profile_id: int) -> tuple[str, dict]:
    """(원문 키, 저장할 행). 원문은 저장하지 않는다."""
    key_id = secrets.token_hex(4)
    raw = f"{KEY_PREFIX}_{int(profile_id)}_{key_id}_{secrets.token_urlsafe(24)}"
    return raw, {"id": key_id, "hash": digest(raw), "tail": raw[-4:]}


def parse_key(raw) -> tuple[int, str] | None:
    """'fdk_12_ab12cd34_…' → (12, 'ab12cd34'). 모양이 아니면 None."""
    m = KEY_RE.fullmatch(str(raw or "").strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def key_from_headers(meta: dict) -> str:
    """Authorization: Bearer … 또는 X-API-Key. request.META 를 받는다."""
    auth = str(meta.get("HTTP_AUTHORIZATION") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return str(meta.get("HTTP_X_API_KEY") or "").strip()


def active_keys(meta) -> list[dict]:
    rows = (meta or {}).get("data_api_keys")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("id") and not r.get("revoked_at")]


def match(meta, key_id: str, raw: str) -> dict | None:
    """살아 있는 키 중 번호와 해시가 맞는 것."""
    want = digest(raw)
    for row in active_keys(meta):
        if row.get("id") == key_id and hmac.compare_digest(str(row.get("hash") or ""), want):
            return row
    return None


def clean_name(value) -> str:
    return " ".join(str(value or "").split())[:NAME_MAX] or "이름 없는 키"


def public_key(row: dict) -> dict:
    """화면에 보여 줄 것 — 해시는 내보내지 않는다."""
    return {
        "id": row.get("id"), "name": row.get("name") or "",
        "hint": f"{KEY_PREFIX}_…{row.get('tail') or ''}",
        "created_at": row.get("created_at"), "last_used_at": row.get("last_used_at"),
    }


# ── 하루 사용량 ───────────────────────────────────────────────

def used_today(meta, today: str) -> int:
    row = (meta or {}).get("data_api_usage")
    if not isinstance(row, dict) or row.get("day") != today:
        return 0
    try:
        return max(0, int(row.get("count") or 0))
    except (TypeError, ValueError):
        return 0


def consume(meta, today: str, limit: int | None = None) -> tuple[bool, dict]:
    """한 번 쓴다. (통과했나, 새 data_api_usage 값)."""
    limit = per_day() if limit is None else limit
    used = used_today(meta, today)
    if used >= limit:
        return False, {"day": today, "count": used}
    return True, {"day": today, "count": used + 1}


def catalogue() -> list[dict]:
    return [{"metric": k, "path": f"/api/data/{k}", "about": v[1], "params": v[2]}
            for k, v in METRICS.items()]
