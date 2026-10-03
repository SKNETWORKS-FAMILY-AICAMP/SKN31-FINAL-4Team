"""/api/ 주소.

① 프론트(트렌드 분석 페이지)가 쓰는 읽기 전용 GET — views.py
② 관리자 수집 대상/이력 DRF API — crawl_views.py (SKN31-FINAL-4Team/backend 원본)
"""

from django.urls import path

from . import (
    activity_views, alpha_views, auth_views, chat_views, data_api_views, job_views, notification_views, plan_views,
    salmal_views, views, xp_views,
)
from .crawl_views import (
    CrawlRunDetailAPIView,
    CrawlRunListAPIView,
    CrawlTargetDetailAPIView,
    CrawlTargetListCreateAPIView,
)

app_name = "api"

urlpatterns = [
    # ── 사용자 세션·프로필 ──
    path("auth/me", auth_views.me, name="auth-me"),
    # ── 알파 테스트 계정 (해커톤 시연 15일 한정 · alpha_views.py 통째로 제거 가능) ──
    #   주소를 한 조각으로 둔다 — 프론트의 버셀 중계(frontend/api/auth/[action].js)가
    #   경로의 첫 조각만 보고 넘기므로 auth/alpha/quota 는 auth/alpha 로 잘린다.
    path("auth/alpha", alpha_views.alpha_account, name="auth-alpha"),
    path("auth/alpha-quota", alpha_views.alpha_quota, name="auth-alpha-quota"),
    path("auth/alpha-chat-use", alpha_views.alpha_chat_use, name="auth-alpha-chat-use"),
    path("auth/signup", auth_views.signup, name="auth-signup"),
    path("auth/login", auth_views.login, name="auth-login"),
    path("auth/google", auth_views.google_login, name="auth-google"),
    path("auth/google-signup", auth_views.google_signup, name="auth-google-signup"),
    path("auth/kakao-start", auth_views.kakao_start, name="auth-kakao-start"),      # 카카오 로그인 페이지 주소
    path("auth/kakao", auth_views.kakao_login, name="auth-kakao"),
    path("auth/kakao-signup", auth_views.kakao_signup, name="auth-kakao-signup"),
    path("auth/email-code", auth_views.email_code, name="auth-email-code"),        # 가입 이메일 인증번호 발송
    path("auth/email-verify", auth_views.email_check, name="auth-email-verify"),   # 인증번호 확인
    path("auth/logout", auth_views.logout, name="auth-logout"),
    path("auth/withdraw", auth_views.withdraw, name="auth-withdraw"),   # 회원 탈퇴 (계정·기록 삭제)
    path("auth/profile", auth_views.profile, name="auth-profile"),
    path("auth/gender", auth_views.gender, name="auth-gender"),                     # 성별만 (알림에서)
    path("auth/job-request", job_views.job_request, name="auth-job-request"),        # 직업 인증 신청
    path("auth/job-requests", job_views.job_requests, name="auth-job-requests"),     # (관리자) 목록
    path("auth/job-review", job_views.job_review, name="auth-job-review"),           # (관리자) 승인·반려
    # ── 요금제 (plan_views.py · 2026-10-03) — 베타(FEEDIT_PUBLIC_BETA) 동안은 신청을 받지 않는다 ──
    path("auth/plan", plan_views.plan, name="auth-plan"),                            # 내 요금제 · 오늘 챗봇 사용량
    path("auth/plan-request", plan_views.plan_request, name="auth-plan-request"),    # 신청 · 해지 · 신청 취소
    path("auth/plan-requests", plan_views.plan_requests, name="auth-plan-requests"),  # (관리자) 목록
    path("auth/plan-review", plan_views.plan_review, name="auth-plan-review"),       # (관리자) 승인·반려·해지
    path("auth/plan-chat-use", plan_views.plan_chat_use, name="auth-plan-chat-use"),  # 챗봇 한 번 — 횟수 · 확인증
    # ── 데이터 API 연동 (data_api_views.py · 2026-10-03) — 비즈니스 요금제 · 베타 동안은 닫혀 있다 ──
    path("auth/data-keys", data_api_views.data_keys, name="auth-data-keys"),        # 내 API 키 목록 · 만들기 · 폐기
    path("data", data_api_views.data_index, name="data-index"),                    # (API 키) 지표 목록
    path("data/<str:metric>", data_api_views.data_metric, name="data-metric"),     # (API 키) 지표 하나
    path("auth/weekly-videos", auth_views.weekly_videos, name="auth-weekly-videos"),
    # ── 사용자 활동 기록 · 금주의 리포트 (activity_views.py) ──
    path("auth/event", activity_views.event, name="auth-event"),                    # 검색 · 챗봇 사용
    path("auth/vote", activity_views.vote, name="auth-vote"),                       # 살!말? 투표
    path("auth/vote-comment", activity_views.vote_comment, name="auth-vote-comment"),
    path("auth/vote-report", activity_views.vote_report, name="auth-vote-report"),
    path("auth/saved", activity_views.saved, name="auth-saved"),                    # 찜 / 찜 해제
    path("auth/weekly-report", activity_views.weekly_report, name="auth-weekly-report"),
    path("auth/chats", chat_views.chats, name="auth-chats"),
    # ── 경험치 · 홈페이지 피드백 (xp_views.py) ──
    path("auth/xp", xp_views.xp, name="auth-xp"),                                   # 내 경험치 · 접속 · 체류
    path("auth/site-feedback", xp_views.site_feedback, name="auth-site-feedback"),  # 불편사항 · 버그리포트

    # ── 알림 (notification_views.py) ──
    path("auth/notifications", notification_views.notifications, name="auth-notifications"),
    path("auth/notification-settings", notification_views.notification_settings,
         name="auth-notification-settings"),
    path("auth/announcements", notification_views.announcements, name="auth-announcements"),  # 상단 띠 공지 (공개)
    path("auth/term-request", notification_views.term_request, name="auth-term-request"),                       # 챗봇 대화 기록 (chat_views.py)

    # ── 프론트 읽기 전용 ──
    path("health", views.health, name="health"),
    path("terms", views.terms, name="terms"),
    path("dictionary", views.dictionary, name="dictionary"),
    path("facets", views.facets, name="facets"),
    path("trend", views.trend, name="trend"),            # 언급량·온도 / 긍부정
    # ★ 2026-09-22 — 검색 지표. 언급(trend)과 일부러 나눈 주소다.
    #   "뭐라고 말했나" 와 "뭘 찾아봤나" 는 다른 현상이라 한 응답에 섞지 않는다.
    path("search", views.search, name="search"),         # 검색량·검색추이·지역·세그먼트
    path("sentiment", views.sentiment, name="sentiment"),  # 댓글 원문 기반 긍부정
    path("assoc", views.assoc, name="assoc"),            # 연관어
    path("discount", views.discount, name="discount"),   # 할인률 변화
    path("discount/facets", views.discount_facets, name="discount-facets"),
    path("resale", views.resale, name="resale"),         # 리세일 시세 지수
    path("resale/products", views.resale_products, name="resale-products"),
    path("lifecycle", views.lifecycle, name="lifecycle"),  # 수명주기
    path("products", views.products, name="products"),
    path("price-history", views.price_history, name="price-history"),  # 찜한 상품 가격 기록
    path("salmal/card", views.salmal_card, name="salmal-card"),
    path("salmal/search", views.salmal_search, name="salmal-search"),
    path("salmal/cards", salmal_views.cards, name="salmal-cards"),
    path("salmal/feedback", salmal_views.feedback, name="salmal-feedback"),
    path("salmal/cards/<int:card_id>", salmal_views.card, name="salmal-card-detail"),

    # ── 관리자 수집 API (DRF) ──
    path("crawl-targets/", CrawlTargetListCreateAPIView.as_view(), name="crawl-target-list-create"),
    path("crawl-targets/<int:pk>/", CrawlTargetDetailAPIView.as_view(), name="crawl-target-detail"),
    path("crawl-runs/", CrawlRunListAPIView.as_view(), name="crawl-run-list"),
    path("crawl-runs/<int:pk>/", CrawlRunDetailAPIView.as_view(), name="crawl-run-detail"),
]
