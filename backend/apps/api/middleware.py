"""읽기 전용 API 의 최소 방어 — 공유 토큰 한 개.

── 왜 필요한가 ──────────────────────────────────────────────
`/api/` 는 원래 SSM 굴 안에서만 닿을 수 있었다. 굴을 걷어내고 이 Django 를
EC2 에 올려 nginx 로 `/api/` 를 열면, **그 주소를 아는 사람은 누구나**
사전(dictionary_term 395행 · brand 2,775행)과 상품 목록을 통째로 긁을 수 있다.
로그인이 아직 없으므로, 챗봇(`/v1/`)이 쓰는 것과 같은 방식으로 막는다.

    브라우저 ─▶ 버셀 함수 ─(X-FEEDiT-Token)─▶ 이 Django ─▶ RDS

토큰은 **버셀 함수만** 안다. 브라우저에는 내려가지 않는다.
(버셀 쪽 이름은 `BACKEND_API_TOKEN`, 서버 쪽은 `FEEDIT_API_TOKEN` 이고
 두 값은 같아야 한다.)

── 비어 있으면 검사하지 않는다 ──────────────────────────────
`FEEDIT_API_TOKEN` 이 없으면 그냥 통과시킨다. 로컬 개발(127.0.0.1:8000)에서
토큰을 만들어 넣는 수고를 하지 않아도 되고, 지금 돌아가는 것이 안 깨진다.
**밖에 열 때는 반드시 넣어야 한다** — 안 넣으면 그대로 공개된다.
그래서 서버가 뜰 때 한 번 경고를 남긴다.

── 무엇을 막고 무엇을 안 막나 ───────────────────────────────
`/api/` 아래만 본다. `/admin/` 은 Django 자체 로그인이 지키므로 건드리지
않는다(여기서 같이 막으면 관리자가 브라우저로 못 들어온다).
"""

from __future__ import annotations

import hmac
import logging
import os

from django.http import JsonResponse

log = logging.getLogger(__name__)

HEADER = "HTTP_X_FEEDIT_TOKEN"          # 보내는 쪽 머리글 이름: X-FEEDiT-Token
GUARDED_PREFIX = "/api/"


class ApiTokenMiddleware:
    """`/api/` 앞에 서서 공유 토큰을 검사한다."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.token = (os.getenv("FEEDIT_API_TOKEN") or "").strip()
        # ★ 바이트로 견준다.
        #   hmac.compare_digest 는 str 을 받으면 **ASCII 만** 받는다. 누가
        #   한글이나 이모지가 든 머리글을 보내면 TypeError 가 나고, 401 이어야
        #   할 자리에서 500 이 난다(그리고 스택트레이스가 로그를 채운다).
        #   먼저 encode 해 두면 어떤 글자가 와도 그냥 '다른 값'이 된다.
        self.token_bytes = self.token.encode("utf-8")
        if not self.token:
            log.warning(
                "FEEDIT_API_TOKEN 이 비어 있습니다 — /api/ 가 누구에게나 열립니다. "
                "밖에 여는 서버라면 .env 에 넣으세요."
            )

    def __call__(self, request):
        if self.token and request.path.startswith(GUARDED_PREFIX):
            got = request.META.get(HEADER, "")
            # 글자 수가 다를 때 빨리 끝나면 길이가 새어 나간다. 상수 시간으로 견준다.
            if not hmac.compare_digest(got.encode("utf-8", "replace"), self.token_bytes):
                # 화면이 사유를 그대로 적을 수 있게 JSON 으로 답한다.
                # (HTML 오류 쪽을 돌려주면 프론트가 JSON 파싱에서 터진다.)
                return JsonResponse(
                    {
                        "status": "error",
                        "reason": (
                            "이 API 는 토큰이 있어야 합니다. "
                            "버셀 환경변수 BACKEND_API_TOKEN 과 서버 .env 의 "
                            "FEEDIT_API_TOKEN 이 같은 값인지 확인하세요."
                        ),
                        "data": None,
                    },
                    status=401,
                )
        return self.get_response(request)
