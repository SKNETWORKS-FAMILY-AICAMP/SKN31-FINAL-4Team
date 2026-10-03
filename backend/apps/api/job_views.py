"""직업 인증 — 신청 · 관리자 심사 (2026-09-19).

예전 화면(job.js)은 심사 대기열을 브라우저 안에만 두는 목업이었다.
  · 신청을 해도 서버에 남지 않았고, 관리자가 심사 메뉴를 열어도 신청이 보이지 않았다.
이제 신청은 app_user.profile_metadata["job_request"] 에, 증빙 서류는 S3 에 둔다 (새 표 없음).

규칙
  · 인증이 필요한 직업(MD · Buyer · … · Student)을 고르면 **승인 전까지 직업은 비어 있다**(= Basic 으로 보인다).
    이미 승인된 직업이 있던 사람은 새 신청이 승인될 때까지 예전 직업을 그대로 쓴다.
  · Basic · 비움은 서류 없이 바로 반영된다(진행 중 신청은 취소).
  · 승인 · 반려는 운영 계정(슈퍼유저 · 스태프)만.

  POST   /api/auth/job-request   {job, major?, doc_data_url?, doc_name?}   본인 신청 · Basic 전환
  DELETE /api/auth/job-request                                            진행 중 신청 취소
  GET    /api/auth/job-requests?status=PENDING|ALL                        (관리자) 신청 목록
  POST   /api/auth/job-review    {user_id, approve: bool, reason?}        (관리자) 승인 · 반려
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.models import AppUser

from .salmal_storage import VoteImageError, _bucket, _client

# 화면(job.js JOBS)과 같은 목록 — fashion:true 인 직업만 서류가 필요하다
DOC_JOBS = {"MD", "Buyer", "Designer", "Stylist", "Creator", "Editor", "Marketer", "Platform", "Student"}
MAX_DOC_BYTES = 3 * 1024 * 1024
DOC_RE = re.compile(r"^data:(image/(?:jpeg|png|webp)|application/pdf);base64,([A-Za-z0-9+/=]+)$")
DOC_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
DOC_PREFIX = "images/job_doc/"


def _ok(data, status=200):
    return JsonResponse({"status": "ok", "data": data}, status=status)


def _error(reason, status=400):
    return JsonResponse({"status": "error", "reason": reason, "data": None}, status=status)


def _body(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _me(request):
    if not request.user.is_authenticated:
        return None
    return AppUser.objects.filter(user=request.user).first()


def _is_admin(request):
    return request.user.is_authenticated and (request.user.is_superuser or request.user.is_staff)


def job_request_public(meta):
    """로그인 응답에 싣는 내 신청 상태 — 서류 위치는 빼고 보낸다."""
    req = (meta or {}).get("job_request")
    if not isinstance(req, dict):
        return None
    return {k: req.get(k) for k in ("job", "major", "status", "requested_at", "decided_at", "reason")}


def _upload_doc(data_url):
    match = DOC_RE.fullmatch(str(data_url or "").strip())
    if match is None:
        raise VoteImageError("서류는 JPG · PNG · WebP 이미지나 PDF 만 올릴 수 있어요.")
    mime, payload = match.groups()
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise VoteImageError("서류 파일이 올바르지 않습니다.") from exc
    if len(raw) > MAX_DOC_BYTES:
        raise VoteImageError("서류 파일은 3MB 이하로 올려 주세요.")
    key = f"{DOC_PREFIX}{timezone.localtime():%Y/%m/%d}/{uuid.uuid4().hex}.{DOC_EXT[mime]}"
    try:
        _client().put_object(Bucket=_bucket(), Key=key, Body=raw, ContentType=mime)
    except (BotoCoreError, ClientError) as exc:
        raise VoteImageError("서류를 저장하지 못했습니다.") from exc
    return key, mime


def _doc_url(key):
    if not key or not str(key).startswith(DOC_PREFIX):
        return None
    try:
        return _client().generate_presigned_url(
            "get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=600)
    except (BotoCoreError, ClientError, VoteImageError):
        return None


@require_http_methods(["POST", "DELETE"])
def job_request(request):
    profile = _me(request)
    if profile is None:
        return _error("로그인이 필요합니다.", 401)
    if _is_admin(request):
        return _error("운영 계정은 직업 대신 ADMIN 으로 표시됩니다.", 409)
    meta = dict(profile.profile_metadata or {})
    req = meta.get("job_request") if isinstance(meta.get("job_request"), dict) else None

    if request.method == "DELETE":
        if req and req.get("status") == "PENDING":
            req.update(status="CANCELLED", decided_at=timezone.now().isoformat())
            meta["job_request"] = req
            profile.profile_metadata = meta
            profile.save(update_fields=["profile_metadata", "updated_at"])
        return _ok({"job": meta.get("job") or "", "job_request": job_request_public(meta)})

    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    job = str(data.get("job") or "").strip()
    major = str(data.get("major") or "").strip()[:20]

    with transaction.atomic():
        if job in ("", "Basic"):
            # 서류가 필요 없는 선택 — 바로 반영하고 진행 중 신청은 취소
            meta["job"], meta["major"] = "", ""
            if req and req.get("status") == "PENDING":
                req.update(status="CANCELLED", decided_at=timezone.now().isoformat())
                meta["job_request"] = req
        elif job in DOC_JOBS:
            if not data.get("doc_data_url"):
                return _error("선택한 직업을 확인할 서류를 첨부해 주세요.")
            try:
                key, mime = _upload_doc(data.get("doc_data_url"))
            except VoteImageError as exc:
                return _error(str(exc), 400)
            meta["job_request"] = {
                "job": job, "major": major if job == "Student" else "",
                "doc_key": key, "doc_type": mime,
                "doc_name": str(data.get("doc_name") or "")[:120],
                "status": "PENDING", "requested_at": timezone.now().isoformat(),
                "decided_at": None, "decided_by": None, "reason": "",
            }
            # ★ 승인 전에는 새 직업을 달지 않는다. 기존에 승인된 직업은 그대로 둔다.
        else:
            return _error("알 수 없는 직업입니다.")
        profile.profile_metadata = meta
        profile.save(update_fields=["profile_metadata", "updated_at"])
    return _ok({"job": meta.get("job") or "", "major": meta.get("major") or "",
                "job_request": job_request_public(meta)}, status=201)


@require_GET
def job_requests(request):
    if not _is_admin(request):
        return _error("운영 계정만 볼 수 있습니다.", 403)
    want = (request.GET.get("status") or "PENDING").upper()
    rows = []
    for p in (AppUser.objects.filter(profile_metadata__has_key="job_request")
              .select_related("user")):
        req = (p.profile_metadata or {}).get("job_request")
        if not isinstance(req, dict) or req.get("status") == "CANCELLED":
            continue
        if want != "ALL" and req.get("status") != want:
            continue
        rows.append({
            "user_id": p.id, "nickname": p.nickname or p.user.username, "username": p.user.username,
            "current_job": (p.profile_metadata or {}).get("job") or "",
            "job": req.get("job"), "major": req.get("major") or "",
            "status": req.get("status"), "requested_at": req.get("requested_at"),
            "decided_at": req.get("decided_at"), "reason": req.get("reason") or "",
            "doc_name": req.get("doc_name") or "", "doc_type": req.get("doc_type") or "",
            "doc_url": _doc_url(req.get("doc_key")),
        })
    rows.sort(key=lambda r: (r["status"] != "PENDING", r["requested_at"] or ""), reverse=False)
    return _ok({"items": rows, "pending": sum(1 for r in rows if r["status"] == "PENDING")})


@require_POST
def job_review(request):
    if not _is_admin(request):
        return _error("운영 계정만 심사할 수 있습니다.", 403)
    data = _body(request)
    if data is None:
        return _error("요청 형식이 올바른 JSON이 아닙니다.")
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return _error("user_id 가 올바르지 않습니다.")
    approve = bool(data.get("approve"))
    with transaction.atomic():
        p = AppUser.objects.select_for_update().filter(id=user_id).first()
        if p is None:
            return _error("사용자를 찾지 못했습니다.", 404)
        meta = dict(p.profile_metadata or {})
        req = meta.get("job_request")
        if not isinstance(req, dict) or req.get("status") != "PENDING":
            return _error("심사 대기 중인 신청이 아닙니다.", 409)
        req.update(status="APPROVED" if approve else "REJECTED",
                   decided_at=timezone.now().isoformat(), decided_by=request.user.username,
                   reason=str(data.get("reason") or "")[:200])
        if approve:
            meta["job"], meta["major"] = req.get("job") or "", req.get("major") or ""
        meta["job_request"] = req
        p.profile_metadata = meta
        p.save(update_fields=["profile_metadata", "updated_at"])
    # 신청자에게 결과 알림 (알림 설정 '직업 인증 결과'를 끈 사람은 제외). 실패해도 심사는 끝났다.
    from . import notification_service
    notification_service.notify_job_review(p, req.get("job"), approve, req.get("reason") or "",
                                           req.get("requested_at") or "")
    return _ok({"user_id": user_id, "status": req["status"], "job": meta.get("job") or ""})
