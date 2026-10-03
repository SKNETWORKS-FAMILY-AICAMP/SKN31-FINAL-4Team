"""알림 문구와 판정 규칙 — DB 를 건드리지 않는 순수 계산.

여기 있는 함수는 전부 값만 받아 값만 돌려준다.
DB 조회·생성은 notification_service.py 가 한다.
(금주의 리포트가 activity.py(계산) / activity_views.py(DB) 로 나뉜 것과 같은 결.)

돌리는 법:  cd backend && python -m unittest apps.api.test_notifications
"""
from __future__ import annotations

from datetime import timedelta, timezone

KST = timezone(timedelta(hours=9))

# ── 찜한 상품 가격 하락 ────────────────────────────────────────
# 몇 퍼센트부터 알릴 것인가. 1~2% 는 판매처의 일상적인 등락이라 알림이 소음이 된다.
PRICE_DROP_MIN_RATE = 0.05
# ★ 2026-09-27 (FAVORITE-002) — 찜 상품 '급등'. 오르는 쪽은 내릴 때보다 알림 가치가 낮아
#   (살 사람에게는 '이미 늦었다' 는 소식) 기준을 두 배로 둔다.
PRICE_RISE_MIN_RATE = 0.10
# '최저가' 는 이 기간 안에서 본다 — 요구사항 TREND-005 의 '최근 6개월 내 최저가' 와 같은 창
LOW_WINDOW_DAYS = 180
SOLD_OUT_STATUSES = ("SOLD_OUT", "OUT_OF_STOCK")

# ── 살!말? 투표 결과 ──────────────────────────────────────────
# 표가 이만큼 모이면 작성자에게 한 번 알린다. 뒤에 숫자를 더 넣으면 그때마다 또 알린다.
VOTE_RESULT_MILESTONES = (10,)

# 알림 종류 — core.Notification.Kind 와 같은 값을 쓴다.
# 여기서 다시 적어 두는 이유는 이 파일이 Django 없이도 돌아야 해서다.
PRICE_DROP = "PRICE_DROP"
VOTE_RESULT = "VOTE_RESULT"
WEEKLY_REPORT = "WEEKLY_REPORT"
BADGE = "BADGE"
TERM_ADDED = "TERM_ADDED"
JOB_REVIEW = "JOB_REVIEW"
VOTE_COMMENT = "VOTE_COMMENT"
OPS_ALERT = "OPS_ALERT"   # 운영 계정만 — 설정 칸이 없어 끌 수 없다(SETTING_FIELD 에 없음)
# 운영자가 관리자 화면에서 보내는 공지 (2026-10-02). 종류별 끄기 칸은 없고, '알림 전체 끄기'
# 를 한 사람에게는 가지 않는다(notification_service.allowed 가 전체 끄기를 먼저 본다).
ADMIN_NOTICE = "ADMIN_NOTICE"
# 성별이 비어 있는 회원에게 한 번 — 가상 피팅 모델 · 코디 추천이 성별을 쓴다 (2026-10-02)
PROFILE_GENDER = "PROFILE_GENDER"
PROFILE_GENDER_KEY = "PROFILE_GENDER"
# 요금제 신청 결과 · (운영 계정) 신청 대기 (2026-10-03, plan_views.py). 끌 수 없다 —
# 쓰고 있는 요금제가 바뀌었다는 소식이라 꺼 두면 왜 기능이 막혔는지 알 길이 없다.
PLAN_REVIEW = "PLAN_REVIEW"

# 종류 → NotificationSetting 의 칸 이름
SETTING_FIELD = {
    PRICE_DROP: "price_drop",
    VOTE_RESULT: "vote_result",
    WEEKLY_REPORT: "weekly_report",
    BADGE: "badge",
    TERM_ADDED: "term_added",
    JOB_REVIEW: "job_review",
    VOTE_COMMENT: "vote_comment",
}


# ── 조사 ───────────────────────────────────────────────────
# "찜한 발레 플랫이" / "찜한 로퍼가" — 앞말 받침에 따라 조사가 달라진다.
# 알림 문구는 상품명·용어처럼 우리가 고르지 않은 말을 그대로 받는다.
# 숫자로 끝나는 말(뱃지 '살말 백전 100')은 읽는 소리의 받침을 본다.
_DIGIT_FINAL = {"0": True, "1": True, "2": False, "3": True, "4": False,
                "5": False, "6": True, "7": True, "8": True, "9": False}


def has_final(word):
    """마지막 글자에 받침이 있으면 True. 한글도 숫자도 아니면 받침이 있는 쪽으로 본다."""
    text = str(word or "").strip()
    if not text:
        return True
    last = text[-1]
    if "가" <= last <= "힣":
        return (ord(last) - 0xAC00) % 28 != 0
    if last.isdigit():
        return _DIGIT_FINAL[last]
    return True


def josa(word, with_final, without_final):
    """josa("로퍼", "이", "가") → "가"."""
    return with_final if has_final(word) else without_final


def kst_day(at):
    """알림 하루의 기준은 한국시간이다 (배치가 UTC 로 돌아도 같은 날로 묶인다)."""
    return at.astimezone(KST).date()


def drop_rate(base, current):
    """기준가 대비 내린 비율(0~1). 올랐거나 값이 없으면 None."""
    try:
        base = float(base)
        current = float(current)
    except (TypeError, ValueError):
        return None
    if base <= 0 or current <= 0 or current >= base:
        return None
    return (base - current) / base


def price_drops(items, min_rate=PRICE_DROP_MIN_RATE):
    """내린 상품만 골라 비율을 붙인다. 많이 내린 것이 앞에 온다.

    items: [{"item_id", "name", "base", "current"}]
    """
    out = []
    for it in items:
        rate = drop_rate(it.get("base"), it.get("current"))
        if rate is None or rate < min_rate:
            continue
        row = dict(it)
        row["rate"] = rate
        row["percent"] = int(round(rate * 100))
        out.append(row)
    out.sort(key=lambda r: r["rate"], reverse=True)
    return out


def rise_rate(base, current):
    """기준가 대비 오른 비율(0~). 내렸거나 값이 없으면 None."""
    try:
        base = float(base)
        current = float(current)
    except (TypeError, ValueError):
        return None
    if base <= 0 or current <= base:
        return None
    return (current - base) / base


def price_rises(items, min_rate=PRICE_RISE_MIN_RATE):
    """크게 오른 상품만. 많이 오른 것이 앞에 온다. items 모양은 price_drops 와 같다."""
    out = []
    for it in items:
        rate = rise_rate(it.get("base"), it.get("current"))
        if rate is None or rate < min_rate:
            continue
        row = dict(it)
        row["rate"] = rate
        row["percent"] = int(round(rate * 100))
        out.append(row)
    out.sort(key=lambda r: r["rate"], reverse=True)
    return out


def is_sold_out(status):
    return str(status or "").upper() in SOLD_OUT_STATUSES


def saved_change_digest(drops, rises=(), sold_out=(), lows=()):
    """찜 상품 변동을 하루 한 건으로 (FAVORITE-002: 급락 · 최저가 · 급등 · 품절).

    drops · rises: price_drops · price_rises 결과. sold_out: [{"item_id","name"}].
    lows: 6개월 최저가를 새로 찍은 item_id 모음(급락 줄에 '최저가' 를 덧붙인다).
    내린 것만 있으면 예전 문구(price_digest)를 그대로 쓴다.
    """
    rises, sold_out, lows = list(rises), list(sold_out), set(lows)
    if not (drops or rises or sold_out):
        return None, None
    if drops and not rises and not sold_out and not (lows & {d["item_id"] for d in drops}):
        return price_digest(drops)
    lines = []
    for d in drops:
        low = " · 6개월 최저가" if d["item_id"] in lows else ""
        lines.append(f"{d.get('name') or '이름 없는 상품'} {d['percent']}% ↓{low}")
    for r in rises:
        lines.append(f"{r.get('name') or '이름 없는 상품'} {r['percent']}% ↑")
    for s in sold_out:
        lines.append(f"{s.get('name') or '이름 없는 상품'} 품절")
    n = len(lines)
    if n == 1:
        only = (drops or rises or sold_out)[0]
        name = only.get("name") or "찜한 상품"
        if sold_out:
            return f"찜한 {name}{josa(name, '이', '가')} 품절됐어요.", ""
        if rises:
            return f"찜한 {name}{josa(name, '이', '가')} {only['percent']}% 올랐어요.", ""
        return f"찜한 {name}{josa(name, '이', '가')} 6개월 최저가예요 ({only['percent']}% 내림).", ""
    body = "\n".join(lines[:5]) + (f"\n외 {n - 5}개" if n > 5 else "")
    return f"찜한 상품 {n}개에 변동이 있어요.", body


def price_digest(drops):
    """하루치를 한 건으로 묶은 (제목, 본문). 내린 것이 없으면 (None, None).

    상품마다 한 건씩 보내지 않는다 — 찜이 많은 사람은 알림창이 가격표가 된다.
    """
    if not drops:
        return None, None
    if len(drops) == 1:
        d = drops[0]
        name = d.get("name") or "찜한 상품"
        return f"찜한 {name}{josa(name, '이', '가')} {d['percent']}% 내려갔어요.", ""
    title = f"찜한 상품 {len(drops)}개가 내려갔어요."
    body = " · ".join(
        f"{d.get('name') or '이름 없는 상품'} {d['percent']}%" for d in drops[:5]
    )
    if len(drops) > 5:
        body += f"\n외 {len(drops) - 5}개"
    return title, body


def vote_milestone(total, milestones=VOTE_RESULT_MILESTONES):
    """지금 표 수가 넘어선 가장 큰 기준점. 아직이면 None."""
    reached = [m for m in milestones if total >= m]
    return max(reached) if reached else None


def vote_result_text(total, buys, card_title=""):
    """(제목, 본문). '살!'이 몇 명인지 그대로 적는다 — 결론을 대신 내지 않는다."""
    if total <= 0:
        return None, None
    title = f"{total}명 중 {buys}명이 '살!'이라고 했어요."
    return title, (card_title or "")


def badge_text(label):
    return f"뱃지 '{label}'{josa(label, '을', '를')} 달성했어요.", ""


def vote_comment_text(nickname, card_title, content, choice=None):
    """(제목, 본문). 누가 · 어느 카드에 · 살/말 중 어느 쪽으로 · 무슨 말을 했는지."""
    who = str(nickname or "누군가").strip() or "누군가"
    side = {"BUY": " '살!' 쪽에서", "PASS": " '말!' 쪽에서"}.get(choice or "", "")
    title = f"{who}님이{side} 댓글을 남겼어요."
    text = " ".join(str(content or "").split())
    if len(text) > 60:
        text = text[:59] + "…"
    card = str(card_title or "").strip()
    # ★ 2026-09-20 — 카드 제목과 댓글을 줄을 나눠 적는다 (알림 창이 \n 을 줄바꿈으로 보여 준다)
    body = "\n".join(x for x in ((f"'{card[:30]}'" if card else ""), (f"“{text}”" if text else "")) if x)
    return title, body


def job_review_text(job_label, approved, reason=""):
    """직업 인증 결과 — 승인이면 배지가 달렸다고, 반려면 사유와 다시 신청하는 길을 적는다."""
    label = str(job_label or "직업")
    if approved:
        return (f"{label} 인증이 승인됐어요.",
                f"이제 닉네임 옆에 {label} 배지가 달려요.")
    body = f"사유: {reason}\n" if reason else ""
    return (f"{label} 인증이 반려됐어요.",
            body + "회원정보 수정에서 서류를 다시 올려 신청할 수 있어요.")


PLAN_LABEL = {"FREE": "프리", "PRO": "프로", "BUSINESS": "비즈니스"}


def plan_review_text(plan, status, reason=""):
    """요금제 신청 결과 — 승인 · 반려 · 운영자가 프리로 되돌림."""
    label = PLAN_LABEL.get(str(plan or "").upper(), "요금제")
    why = f"사유: {reason}\n" if reason else ""
    if status == "APPROVED":
        return (f"{label} 요금제 신청이 승인됐어요.",
                f"지금부터 {label} 요금제의 기능을 쓰실 수 있어요.")
    if status == "REVOKED":
        return ("요금제가 프리로 바뀌었어요.",
                why + "궁금한 점은 고객센터로 문의해 주세요.")
    return (f"{label} 요금제 신청이 반려됐어요.",
            why + "요금제 화면에서 다시 신청할 수 있어요.")


def term_added_text(raw_term, canonical_name=""):
    """요청한 말과 사전에 오른 표준명이 다르면 둘 다 보여 준다."""
    body = ""
    if canonical_name and canonical_name != raw_term:
        body = (f"사전에는 '{canonical_name}'"
                f"{josa(canonical_name, '으로', '로')} 올라갔어요.")
    return f"요청한 '{raw_term}'{josa(raw_term, '이', '가')} 사전에 올라갔어요.", body


def weekly_report_text(week_start):
    """week_start: 이번 주 월요일 date."""
    return (
        "일요일이 왔어요.",
        "금주의 리포트를 확인해 보세요.",
    )


# ── 성별 요청 (2026-10-02) ──────────────────────────────────
def gender_prompt_text():
    """가입할 때 성별을 받기 전(2026-10-02 이전)에 가입한 회원에게 한 번 보낸다."""
    return ("성별을 알려 주세요.",
            "코디 입혀보기 모델과 추천 코디를 성별에 맞춰 드려요.\n"
            "눌러서 바로 고를 수 있어요.")


# ── 운영 공지 (관리자 화면에서 보내는 알림 · 상단 띠 공지) ─────────
NOTICE_TITLE_MAX = 60     # 알림 목록 한 줄 · 토스트에 들어가는 길이
NOTICE_BODY_MAX = 300
TICKER_MAX = 140
# 눌렀을 때 갈 수 있는 화면 — 프런트 goView 가 아는 이름만 (없는 화면이면 공백 페이지가 된다)
NOTICE_LINKS = {
    "": "이동 없음",
    "home": "홈",
    "trend": "트렌드 분석",
    "salmal": "살!말?",
    "style": "스타일",
    "price": "가격",
    "mypage": "마이페이지",
}


def _one_line(value):
    return " ".join(str(value or "").split())


def clean_notice(title, body="", link=""):
    """관리자가 쓴 알림 → (title, body, link). 틀리면 ValueError(사람이 읽을 문장).

    본문은 줄바꿈을 살린다 — 알림 목록이 \n 을 줄로 그린다(notify.js bodyHTML).
    """
    t = _one_line(title)
    if not t:
        raise ValueError("제목을 입력해 주세요.")
    if len(t) > NOTICE_TITLE_MAX:
        raise ValueError(f"제목은 {NOTICE_TITLE_MAX}자 이하로 입력해 주세요.")
    lines = [_one_line(x) for x in str(body or "").replace("\r", "").split("\n")]
    b = "\n".join(lines).strip("\n")
    while "\n\n\n" in b:
        b = b.replace("\n\n\n", "\n\n")
    if len(b) > NOTICE_BODY_MAX:
        raise ValueError(f"본문은 {NOTICE_BODY_MAX}자 이하로 입력해 주세요.")
    l = str(link or "").strip()
    if l not in NOTICE_LINKS:
        raise ValueError("이동 화면이 올바르지 않습니다.")
    return t, b, l


def clean_ticker(message, link=""):
    """상단 띠 공지 → (message, link). 한 줄로 흐르니 줄바꿈은 걷는다."""
    m = _one_line(message)
    if not m:
        raise ValueError("공지 문구를 입력해 주세요.")
    if len(m) > TICKER_MAX:
        raise ValueError(f"공지 문구는 {TICKER_MAX}자 이하로 입력해 주세요.")
    l = str(link or "").strip()
    if l not in NOTICE_LINKS:
        raise ValueError("이동 화면이 올바르지 않습니다.")
    return m, l


def parse_recipients(text):
    """'12, 진, @민지\n34' → (ids, nicknames). 숫자는 회원 번호, 나머지는 닉네임으로 본다."""
    ids, names = [], []
    for raw in str(text or "").replace(",", "\n").replace(";", "\n").split("\n"):
        word = raw.strip().lstrip("@#").strip()
        if not word:
            continue
        if word.isdigit():
            n = int(word)
            if n not in ids:
                ids.append(n)
        elif word not in names:
            names.append(word[:40])
    return ids, names
