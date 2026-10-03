"""사용자 활동 기록 API — 검색 · 살!말? 투표 · 찜 · 챗봇 사용 + 금주의 리포트.

모두 로그인 세션(Django 세션 쿠키)이 있어야 한다. 브라우저는 /api/auth/<action> 으로
부르고, 버셀 함수(frontend/api/auth/[action].js)가 쿠키·CSRF 를 그대로 중계한다.

★ 왜 살!말? 투표를 vote_ballot 이 아니라 user_event 에 적나
  vote_ballot 은 app.vote_card 의 id(FK)가 반드시 있어야 한다. 그런데 지금 살!말? 화면의
  카드는 아직 DB 카드가 아니라 프론트 목업(vote_app.js 의 VOTES)이다. 그래서
  카드 식별값(card_key)과 선택을 user_event(VOTE).metadata 에 남긴다.
  card_key 가 실제 vote_card id(숫자)이면 vote_ballot 에도 같이 반영한다.

★ 찜도 같은 이유
  user_saved_item 은 product FK 가 필요하다. 실데이터 상품 카드(id 'db-<product_source_id>')만
  user_saved_item 에 넣고, 모든 찜/해제는 user_event(SAVE) 에도 남긴다.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.api.images import absolute_image_url
from apps.core.models import (
    AppUser,
    ChatSession,
    DictionaryTerm,
    ProductSource,
    ProductSourceSnapshot,
    UserEvent,
    UserSavedItem,
    VoteBallot,
    VoteCard,
    VoteComment,
    VoteReport,
)

from .activity import build_weekly_report, latest_state, week_bounds
from . import notification_service

TEXT_MAX = 120
DB_ITEM_RE = re.compile(r"^db-(\d+)$")
VISIBLE_VOTE_CARD = Q(seed_key__startswith="youtube:") | Q(seed_key__startswith="user:")


# ── 공용 도우미 ─────────────────────────────────────────────

def _error(reason, status=400):
    return JsonResponse({"status": "error", "reason": reason, "data": None}, status=status)


def _body(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _text(value, limit=TEXT_MAX):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _login_profile(request):
    """로그인하지 않았으면 None — 비로그인 사용자의 활동은 기록하지 않는다."""
    if not request.user.is_authenticated:
        return None
    profile, _ = AppUser.objects.get_or_create(
        user=request.user, defaults={"nickname": request.user.first_name or request.user.username[:12]},
    )
    return profile


def _card_is_closed(card, now=None):
    """마감 시각이 지난 카드는 즉시 종료 상태로 동기화한다."""
    now = now or timezone.now()
    if card.status == VoteCard.Status.CLOSED:
        return True
    if card.closes_at is not None and card.closes_at <= now:
        card.status = VoteCard.Status.CLOSED
        card.save(update_fields=["status", "updated_at"])
        return True
    return False


def _style_term(name):
    """스타일 이름이 사전(STYLE)에 있으면 그 용어를 돌려준다."""
    name = _text(name)
    if not name:
        return None
    return DictionaryTerm.objects.filter(
        status=DictionaryTerm.Status.ACTIVE, term_type="STYLE", canonical_name=name,
    ).first()


def active_vote_count(profile):
    """지금 투표가 살아 있는 카드 수 (같은 카드를 다시 눌러 취소한 것은 뺀다)."""
    rows = _event_rows(profile, types=("VOTE",))
    return len(latest_state(rows, "VOTE", "card_key", lambda m: m.get("choice") in ("BUY", "PASS")))


def active_saved_count(profile):
    """지금 찜이 살아 있는 항목 수 (목업 상품 포함)."""
    rows = _event_rows(profile, types=("SAVE",))
    n = len(latest_state(rows, "SAVE", "item_id", lambda m: bool(m.get("liked"))))
    # 기록 API 이전에 user_saved_item 에 직접 들어간 행이 있으면 그쪽 수를 따른다.
    return max(n, UserSavedItem.objects.filter(user=profile).count())


def _event_rows(profile, types=None, since=None):
    qs = UserEvent.objects.filter(user=profile).select_related("term")
    if types:
        qs = qs.filter(event_type__in=types)
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    rows = []
    for e in qs.order_by("created_at"):
        meta = e.metadata if isinstance(e.metadata, dict) else {}
        style = _text(meta.get("style")) or None
        if not style and e.term_id and e.term.term_type == "STYLE":
            style = e.term.canonical_name
        rows.append({"type": e.event_type, "at": e.created_at, "meta": meta, "style": style})
    return rows


# ── ① 검색 · 챗봇 사용 기록 ─────────────────────────────────

@require_POST
def event(request):
    """POST /api/auth/event

    {"type": "SEARCH", "q": "발레코어", "facet": "스타일", "style": "발레코어"}
    {"type": "CHAT", "conversation_id": "c_123"}
    """
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    kind = _text(data.get("type")).upper()

    if kind == "SEARCH":
        q = _text(data.get("q"))
        if not q:
            return _error("검색어(q)가 비어 있습니다.")
        facet = _text(data.get("facet"), 20)
        term = DictionaryTerm.objects.filter(status=DictionaryTerm.Status.ACTIVE, canonical_name=q).first()
        style_term = _style_term(data.get("style")) or (term if term and term.term_type == "STYLE" else None)
        UserEvent.objects.create(
            user=profile, event_type=UserEvent.EventType.SEARCH, term=term,
            metadata={"q": q, "facet": facet, "style": style_term.canonical_name if style_term else ""},
        )
        notification_service.check_badges(profile)
        return JsonResponse({"status": "ok", "data": {"recorded": "SEARCH"}})

    if kind == "CHAT":
        conv = _text(data.get("conversation_id"), 80)
        if not conv:
            return _error("conversation_id 가 비어 있습니다.")
        with transaction.atomic():
            session = (ChatSession.objects.select_for_update()
                       .filter(user=profile, context__conversation_id=conv).first())
            if session is None:
                session = ChatSession.objects.create(
                    user=profile, title=_text(data.get("title"), 300) or None,
                    context={"conversation_id": conv},
                )
            else:
                session.save(update_fields=["updated_at"])   # 최근 대화 시각만 앞으로 민다
            UserEvent.objects.create(
                user=profile, event_type=UserEvent.EventType.CHAT,
                metadata={"conversation_id": conv, "chat_session_id": session.id},
            )
        notification_service.check_badges(profile)
        return JsonResponse({"status": "ok", "data": {"recorded": "CHAT", "chat_session_id": session.id}})

    return _error("type 은 SEARCH 또는 CHAT 이어야 합니다.")


# ── ② 살!말? 투표 ───────────────────────────────────────────

@require_POST
def vote(request):
    """POST /api/auth/vote

    {"card_key": "mock:3", "title": "스퀘어 토 로퍼", "brand": "...", "style": "", "choice": "BUY"|"PASS"|null}
    choice 가 null 이면 투표 취소.
    """
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    card_key = _text(data.get("card_key"), 80)
    if not card_key:
        return _error("card_key 가 비어 있습니다.")
    choice = data.get("choice")
    choice = _text(choice).upper() if choice else None
    if choice not in (None, "BUY", "PASS"):
        return _error("choice 는 BUY · PASS · null 중 하나여야 합니다.")
    style_term = _style_term(data.get("style"))
    card = None
    if card_key.isdigit():
        card = VoteCard.objects.filter(VISIBLE_VOTE_CARD, id=int(card_key)).first()
        if card is None:
            return _error("카드를 찾지 못했습니다.", status=404)
        if _card_is_closed(card):
            return _error("마감된 투표에는 참여할 수 없습니다.", status=409)

    with transaction.atomic():
        UserEvent.objects.create(
            user=profile, event_type=UserEvent.EventType.VOTE, term=style_term,
            metadata={"card_key": card_key, "title": _text(data.get("title")),
                      "brand": _text(data.get("brand")), "choice": choice,
                      "style": style_term.canonical_name if style_term else ""},
        )
        # 실제 DB 카드면 vote_ballot 에도 반영한다.
        if card is not None:
            if choice is None:
                VoteBallot.objects.filter(card=card, user=profile).delete()
            else:
                VoteBallot.objects.update_or_create(
                    card=card, user=profile, defaults={"choice": choice})
    # 알림 — 카드 작성자에게 투표 결과(기준 표 수를 넘었을 때 한 번), 투표한 사람에게 뱃지.
    # 실패해도 투표는 이미 저장됐다. notification_service 가 예외를 삼키고 로그만 남긴다.
    if card is not None and choice is not None:
        notification_service.check_vote_result(card)
    notification_service.check_badges(profile)
    return JsonResponse({"status": "ok", "data": {"card_key": card_key, "choice": choice,
                                                   "vote_count": active_vote_count(profile)}})


@require_http_methods(["POST", "DELETE"])
def vote_comment(request):
    """실제 DB 살!말? 댓글을 저장하거나 작성자 본인이 삭제한다."""
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    if request.method == "DELETE":
        try:
            comment_id = int(data.get("comment_id"))
        except (TypeError, ValueError):
            return _error("comment_id가 올바르지 않습니다.")
        comment = VoteComment.objects.filter(id=comment_id, is_deleted=False).first()
        if comment is None:
            return _error("댓글을 찾지 못했습니다.", status=404)
        # 운영 계정(슈퍼유저·스태프)은 누구의 댓글이든 지울 수 있다 — 신고 처리용.
        is_admin = request.user.is_superuser or request.user.is_staff
        if comment.user_id != profile.id and not is_admin:
            return _error("본인이 작성한 댓글만 삭제할 수 있습니다.", status=403)
        comment.is_deleted = True
        comment.save(update_fields=["is_deleted", "updated_at"])
        return JsonResponse({"status": "ok", "data": {"id": comment.id, "deleted": True}})

    try:
        card_id = int(data.get("card_id"))
    except (TypeError, ValueError):
        return _error("card_id가 올바르지 않습니다.")
    card = VoteCard.objects.filter(VISIBLE_VOTE_CARD, id=card_id).first()
    if card is None:
        return _error("카드를 찾지 못했습니다.", status=404)
    if _card_is_closed(card):
        return _error("마감된 투표에는 댓글을 작성할 수 없습니다.", status=409)
    content = _text(data.get("content"), 1000)
    if not content:
        return _error("댓글 내용을 입력해 주세요.")
    ballot = VoteBallot.objects.filter(card=card, user=profile).first()
    comment = VoteComment.objects.create(
        card=card,
        user=profile,
        choice=ballot.choice if ballot else "NEUTRAL",
        content=content,
        source_metadata={"source": "USER"},
    )
    # 카드 작성자에게 새 댓글 알림 (내 카드에 내가 단 댓글은 제외). 실패해도 댓글은 저장됐다.
    notification_service.notify_vote_comment(card, comment, profile)
    return JsonResponse({
        "status": "ok",
        "data": {"id": comment.id, "choice": comment.choice, "content": comment.content},
    })


@require_POST
def vote_report(request):
    """카드·댓글 신고를 검토 대기 상태로 기록한다."""
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    target_type = _text(data.get("target_type"), 10).upper()
    if target_type not in (VoteReport.TargetType.CARD, VoteReport.TargetType.COMMENT):
        return _error("target_type은 CARD 또는 COMMENT여야 합니다.")
    try:
        target_id = int(data.get("target_id"))
    except (TypeError, ValueError):
        return _error("target_id가 올바르지 않습니다.")
    if target_id <= 0:
        return _error("target_id가 올바르지 않습니다.")

    reason = _text(data.get("reason"), 500)
    card = None
    comment = None
    if target_type == VoteReport.TargetType.CARD:
        card = VoteCard.objects.filter(VISIBLE_VOTE_CARD, id=target_id).select_related("user").first()
        if card is None:
            return _error("카드를 찾지 못했습니다.", status=404)
        if card.user_id == profile.id:
            return _error("본인이 작성한 카드는 신고할 수 없습니다.", status=403)
        snapshot = {"card_id": card.id, "title": card.title, "author_id": card.user_id}
    else:
        comment = (
            VoteComment.objects.filter(
                card__in=VoteCard.objects.filter(VISIBLE_VOTE_CARD),
                id=target_id,
                is_deleted=False,
            )
            .select_related("card", "user")
            .first()
        )
        if comment is None:
            return _error("댓글을 찾지 못했습니다.", status=404)
        if comment.user_id == profile.id:
            return _error("본인이 작성한 댓글은 신고할 수 없습니다.", status=403)
        card = comment.card
        snapshot = {
            "card_id": card.id,
            "card_title": card.title,
            "comment_id": comment.id,
            "comment_author_id": comment.user_id,
            "comment_content": _text(comment.content, 1000),
        }

    report, created = VoteReport.objects.get_or_create(
        reporter=profile,
        target_type=target_type,
        target_id=target_id,
        defaults={
            "card": card,
            "comment": comment,
            "reason": reason,
            "target_snapshot": snapshot,
        },
    )
    return JsonResponse(
        {
            "status": "ok",
            "data": {
                "id": report.id,
                "target_type": report.target_type,
                "target_id": report.target_id,
                "report_status": report.status,
                "created": created,
            },
        },
        status=201 if created else 200,
    )


# ── ③ 찜 ────────────────────────────────────────────────────

def _liked_now(events):
    """(item_id → 최신 이벤트) 에서 지금 찜 상태인 것만. events 는 최신순."""
    latest = {}
    for e in events:
        meta = e["metadata"] if isinstance(e["metadata"], dict) else {}
        key = (e["user_id"], str(meta.get("item_id") or ""))
        if key[1] and key not in latest:
            latest[key] = (bool(meta.get("liked")), e["created_at"], meta)
    return latest


def _saved_all(profile):
    """GET /api/auth/saved?view=all — 화면 전체(마이페이지 · 찜한 키워드)가 쓰는 찜 원본.

    ★ 2026-09-19 — 찜의 원본을 서버 하나로 모은다.
      예전에는 브라우저 localStorage(LIKED)와 서버 기록이 따로 놀아 기기·계정마다 찜이 달랐다.
      SAVE 이벤트의 최신 상태가 원본이다(상품 매핑 여부와 상관없이 남는다).
    same_count — 같은 항목을 지금 찜해 둔 사용자 수(나 포함). 예전 화면은 난수였다.
    """
    mine_events = (UserEvent.objects.filter(user=profile, event_type=UserEvent.EventType.SAVE)
                   .order_by("-created_at", "-id").values("user_id", "metadata", "created_at"))
    mine = {item: v for (uid, item), v in _liked_now(mine_events).items() if v[0]}
    if not mine:
        return JsonResponse({"status": "ok", "data": {"items": [], "count": 0}})
    # 같은 항목을 찜한 사람 수
    others = (UserEvent.objects.filter(event_type=UserEvent.EventType.SAVE,
                                       metadata__item_id__in=list(mine))
              .order_by("-created_at", "-id").values("user_id", "metadata", "created_at"))
    same = {}
    for (uid, item), (liked, _at, _m) in _liked_now(others).items():
        if liked:
            same[item] = same.get(item, 0) + 1
    # 실데이터 상품(db-<product_source_id>)은 상품 정보 · 최신 가격을 붙인다
    src_ids = [int(m.group(1)) for m in (DB_ITEM_RE.match(i) for i in mine) if m]
    sources = {s.id: s for s in ProductSource.objects.filter(id__in=src_ids)
               .select_related("product", "product__brand", "source_brand", "source_category")}
    latest = {}
    if src_ids:
        for snap in (ProductSourceSnapshot.objects.filter(product_source_id__in=src_ids)
                     .order_by("product_source_id", "-observed_at", "-id")
                     .distinct("product_source_id")
                     .values("product_source_id", "list_price", "sale_price")):
            latest[snap["product_source_id"]] = snap
    items = []
    for item_id, (_liked, liked_at, meta) in sorted(mine.items(), key=lambda kv: kv[1][1], reverse=True):
        row = {"item_id": item_id, "liked_at": liked_at,
               "name": meta.get("name") or "", "brand": meta.get("brand") or "",
               "style": meta.get("style") or "", "same_count": same.get(item_id, 1)}
        m = DB_ITEM_RE.match(item_id)
        src = sources.get(int(m.group(1))) if m else None
        if src is not None:
            snap = latest.get(src.id) or {}
            brand = (src.product.brand.name if src.product_id and src.product.brand_id
                     else src.source_brand.name if src.source_brand_id else "")
            row.update({
                "name": src.source_name or row["name"],
                "brand": brand or row["brand"],
                # 상대 경로 사진에 베이스를 붙인다 (apps/api/images.py).
                # ★ 소스 코드를 넘기지 않는다 — 이 쿼리는 source 를 select_related
                #   하지 않아서, 줄마다 조회가 한 번 더 나간다. 경로 모양으로
                #   가려도 결과가 같다(상대 경로는 전부 goods_img 다).
                "image": absolute_image_url(src.thumbnail_url),
                "url": src.product_url,
                "category": src.source_category.source_category_name if src.source_category_id else "",
                "list_price": float(snap["list_price"]) if snap.get("list_price") is not None else None,
                "sale_price": float(snap["sale_price"]) if snap.get("sale_price") is not None else None,
            })
        items.append(row)
    return JsonResponse({"status": "ok", "data": {"items": items, "count": len(items)}})


@require_http_methods(["GET", "POST"])
def saved(request):
    """GET: 로그인 사용자의 일반 판매 찜 상품. POST: 찜/해제 기록.

    {"item_id": "db-17", "liked": true, "name": "...", "brand": "...", "style": "고프코어"}
    """
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    if request.method == "GET" and request.GET.get("view") == "all":
        return _saved_all(profile)
    if request.method == "GET":
        # 원본 상품을 매핑하지 못한 찜도 SAVE 이벤트에는 남는다.
        # 최신 이벤트가 해제인 상품은 되살리지 않는다.
        states = {}
        events = (UserEvent.objects.filter(user=profile, event_type=UserEvent.EventType.SAVE)
                  .order_by("-created_at", "-id").values_list("metadata", flat=True))
        for meta in events:
            if not isinstance(meta, dict):
                continue
            match = DB_ITEM_RE.match(str(meta.get("item_id") or ""))
            if match and match.group(1) not in states:
                states[match.group(1)] = bool(meta.get("liked"))
        ids = [int(pid) for pid, liked in states.items() if liked]
        sources = list(ProductSource.objects.filter(
            id__in=ids, status=ProductSource.Status.ACTIVE,
            market_type=ProductSource.MarketType.RETAIL,
        ).select_related("product", "product__brand", "source", "source_brand"))
        # 구버전에서 user_saved_item 만 남긴 찜은 이벤트가 전혀 없을 때 보완한다.
        if not states:
            product_ids = list(UserSavedItem.objects.filter(user=profile, product__isnull=False)
                               .values_list("product_id", flat=True))
            if product_ids:
                sources = list(ProductSource.objects.filter(
                    product_id__in=product_ids, status=ProductSource.Status.ACTIVE,
                    market_type=ProductSource.MarketType.RETAIL,
                ).select_related("product", "product__brand", "source", "source_brand")
                               .order_by("product_id", "-last_seen_at", "-id").distinct("product_id"))
        latest = {}
        source_ids = [source.id for source in sources]
        if source_ids:
            for snap in (ProductSourceSnapshot.objects.filter(product_source_id__in=source_ids)
                         .order_by("product_source_id", "-observed_at", "-id")
                         .distinct("product_source_id")
                         .values("product_source_id", "list_price", "sale_price", "discount_rate", "observed_at")):
                latest.setdefault(snap["product_source_id"], snap)
        items = []
        for source in sources:
            snap = latest.get(source.id)
            if not snap:
                continue
            brand = (source.product.brand.name if source.product_id and source.product.brand_id
                     else source.source_brand.name if source.source_brand_id else "")
            items.append({
                "id": source.id,
                "name": source.source_name or (source.product.canonical_name if source.product_id else ""),
                "brand": brand,
                "source": source.source.name,
                "image": absolute_image_url(source.thumbnail_url),
                "list_price": float(snap["list_price"]) if snap["list_price"] is not None else None,
                "sale_price": float(snap["sale_price"]) if snap["sale_price"] is not None else None,
                "discount_rate": float(snap["discount_rate"]) if snap["discount_rate"] is not None else None,
                "as_of": snap["observed_at"],
            })
        order = {pid: i for i, pid in enumerate(ids)}
        items.sort(key=lambda item: order.get(item["id"], len(order)))
        return JsonResponse({"status": "ok", "data": {"items": items, "count": len(items)}})
    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    item_id = _text(data.get("item_id"), 80)
    if not item_id:
        return _error("item_id 가 비어 있습니다.")
    liked = bool(data.get("liked"))
    style_term = _style_term(data.get("style"))

    with transaction.atomic():
        UserEvent.objects.create(
            user=profile, event_type=UserEvent.EventType.SAVE, term=style_term,
            metadata={"item_id": item_id, "liked": liked, "name": _text(data.get("name")),
                      "brand": _text(data.get("brand")),
                      "style": style_term.canonical_name if style_term else ""},
        )
        m = DB_ITEM_RE.match(item_id)
        product_id = None
        if m:
            product_id = (ProductSource.objects.filter(id=int(m.group(1)))
                          .values_list("product_id", flat=True).first())
        saved_item = None
        if product_id:
            if liked:
                saved_item, _created = UserSavedItem.objects.get_or_create(
                    user=profile, product_id=product_id)
            else:
                UserSavedItem.objects.filter(user=profile, product_id=product_id).delete()
    # 가격 하락 알림(1번)의 기준가 — 찜한 순간의 가격을 박아 둔다.
    # 해제했다가 다시 찜하면 행이 새로 생기므로 기준도 그때 가격이 된다.
    if liked and saved_item is not None and m:
        notification_service.sync_saved_price(saved_item, int(m.group(1)))
    notification_service.check_badges(profile)
    return JsonResponse({"status": "ok", "data": {"item_id": item_id, "liked": liked,
                                                   "saved_count": active_saved_count(profile)}})


# ── ④ 금주의 리포트 ─────────────────────────────────────────

@require_GET
def weekly_report(request):
    """GET /api/auth/weekly-report — 이번 주(월~일, KST) 활동 지표."""
    profile = _login_profile(request)
    if profile is None:
        return _error("로그인이 필요합니다.", status=401)
    now = timezone.now()
    _, _, prev = week_bounds(now)
    # 투표·찜의 '현재 상태'는 과거 기록 전체가 필요하고, 나머지는 지난주부터면 된다.
    events = _event_rows(profile, types=("VOTE", "SAVE"))
    events += _event_rows(profile, types=("SEARCH", "CHAT"), since=prev)
    sessions = list(ChatSession.objects.filter(user=profile, updated_at__gte=prev)
                    .values("started_at", "updated_at"))
    report = build_weekly_report(events, sessions, now)
    # 기록 API 이전에 들어간 user_saved_item 도 총 개수에는 반영한다.
    report["saved"]["total"] = max(report["saved"]["total"], UserSavedItem.objects.filter(user=profile).count())
    report["has_activity"] = any(e["at"] >= prev for e in events) or bool(sessions)
    return JsonResponse({"status": "ok", "data": report})
