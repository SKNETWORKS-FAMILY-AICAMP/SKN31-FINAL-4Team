import os
import sys

from celery.schedules import crontab
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

load_dotenv(ROOT_DIR / ".env")

DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"


_SECRET = os.getenv("DJANGO_SECRET_KEY", "").strip()
if not _SECRET:
    if DEBUG:
        _SECRET = "dev-only-insecure-key"     # 로컬에서만. 배포에는 안 온다.
    else:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY 가 비어 있습니다. 이 저장소는 public 이라 "
            "기본값을 쓰면 세션을 위조당합니다. 서버 .env 에 넣고 다시 띄우세요:\n"
            '    python3 -c "import secrets;print(secrets.token_urlsafe(64))"'
        )
SECRET_KEY = _SECRET

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "15.164.151.62",
    "feedit-official.duckdns.org",
    "feedit-api",   # 기존 서버에서 쓰는 호스트 이름과의 호환성
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "apps.core",
    "django.contrib.humanize",
    "apps.dashboard.apps.AdminDashboardConfig",
    "apps.api.apps.ApiConfig",
    "rest_framework",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # 정적 파일(관리자 화면 CSS)을 gunicorn 에서도 내보내기 위함 — SecurityMiddleware 바로 다음이어야 함
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # /api/ 공유 토큰 검사 (FEEDIT_API_TOKEN 이 비어 있으면 검사하지 않음)
    'apps.api.middleware.ApiTokenMiddleware',
    # /admin-dashboard/ 는 운영 계정(is_staff)만 — 앱 로그인 세션으로는 못 들어온다
    'apps.dashboard.middleware.DashboardStaffMiddleware',
]

# ── DRF (2026-09-23 보안) ────────────────────────────────────
# 기본값을 '운영 계정만'으로 둔다. DRF 를 쓰는 뷰는 관리자용 수집 API 뿐이고,
# 나중에 새 DRF 뷰를 더할 때 권한을 빠뜨려도 열리지 않게 한다.
# BasicAuthentication 은 뺀다 — 백엔드 구간이 http 인 동안 비밀번호가 평문으로 다닌다.
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["apps.api.permissions.IsOperator"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
}

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "OPTIONS": {
            "options": '-c search_path=dictionary,"$user",public',
        },
        # ★ 연결을 다시 쓴다 (2026-10-02 — 동시 접속 렉). 예전 기본값 0 은 요청마다 RDS 에
        #   새로 접속(TLS 포함)했다. 60초 동안 살려 두고, 꺼낼 때 살아 있는지 먼저 본다.
        #   gunicorn 스레드 하나가 연결 하나를 쥔다(워커 3 × 스레드 4 = 최대 12).
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True


STATIC_URL = 'static/'
# 원본 정적 폴더가 있을 때만 등록 (없으면 staticfiles.W004 경고가 뜸)
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STATIC_ROOT = BASE_DIR / "staticfiles"    

# ── 메일 발송 (회원가입 이메일 인증 · apps/api/email_verify.py) ──
# Django 6.1 은 EMAIL_HOST 같은 옛 설정 대신 MAILERS 를 쓴다(섞으면 기동이 막힌다).
# 서버 .env 에 EMAIL_HOST 가 있으면 SMTP 로 보내고, 없으면 콘솔에 찍는다(DEBUG 에서만 발송 허용).
# 예) Gmail: EMAIL_HOST=smtp.gmail.com, EMAIL_HOST_USER=주소, EMAIL_HOST_PASSWORD=앱 비밀번호
_EMAIL_HOST = os.getenv("EMAIL_HOST", "").strip()
_EMAIL_USER = os.getenv("EMAIL_HOST_USER", "").strip()
if _EMAIL_HOST:
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'OPTIONS': {
                'host': _EMAIL_HOST,
                'port': int(os.getenv("EMAIL_PORT", "587")),
                'username': _EMAIL_USER,
                'password': os.getenv("EMAIL_HOST_PASSWORD", "").strip(),
                'use_tls': os.getenv("EMAIL_USE_TLS", "1") == "1",
                'timeout': 10,
            },
        },
    }
else:
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.console.EmailBackend',
        },
    }
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "").strip() or (
    f"FEEDiT <{_EMAIL_USER}>" if _EMAIL_USER else "FEEDiT <noreply@localhost>"
)

_REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
_REDIS_PORT = os.getenv("REDIS_PORT", "6379")

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    f"redis://{_REDIS_HOST}:{_REDIS_PORT}/0",
)

CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    f"redis://{_REDIS_HOST}:{_REDIS_PORT}/1",
)

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Seoul"
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True



CELERY_BEAT_SCHEDULE = {
    "dispatch-due-crawl-targets": {
        "task": "core.dispatch_due_targets",

        # 60초마다 CrawlTarget 확인
        "schedule": 60.0,
        "kwargs": {"batch_size": 2},
    },
    # ── 알림 (apps/api/tasks.py) ──
    #   시간대는 app.conf.timezone = Asia/Seoul 이다.
    #   매일 10:00 — 찜한 상품 가격 하락(하루 한 번 묶어서) · 용어 사전 등재
    "notify-daily": {
        "task": "app.notify_daily",
        "schedule": crontab(hour=10, minute=0),
    },
    #   일요일 18:00 — 주간 트렌드 리포트 (주 1회)
    "notify-weekly": {
        "task": "app.notify_weekly",
        "schedule": crontab(hour=18, minute=0, day_of_week=0),
    },
    # ── 검색 신호 (2026-09-22) ──
    #   ★ config/celery.py 에도 같은 항목이 있다. 일부러 양쪽에 둔다.
    #     celery.py 가 app.conf.beat_schedule 을 통째로 대입하는데,
    #     config_from_object("django.conf:settings") 와의 적용 순서가
    #     환경에 따라 달라 한쪽만 넣으면 조용히 등록되지 않는다.
    #     (2026-09-22 실측: EC2 에서 celery.py 쪽만 넣었더니 beat 에 안 잡혔다.)
    #     둘 다 같은 내용이면 어느 쪽이 이기든 결과가 같다.
    "collect-search-daily": {
        "task": "core.collect_search_daily",
        "schedule": crontab(hour=5, minute=30),
    },
    "collect-search-weekly": {
        "task": "core.collect_search_weekly",
        "schedule": crontab(hour=6, minute=10, day_of_week="1-5"),
    },
    "collect-search-volume-monthly": {
        "task": "core.collect_search_volume_monthly",
        "schedule": crontab(hour=6, minute=40, day_of_month="2"),
    },
    # ── 운영 알림 (2026-09-27) ──
    #   매일 09:20 — 장기 미갱신 소스가 있으면 운영 계정 · 메일로 알린다 (apps/core/services/ops_alerts.py)
    #   ★ config/celery.py 의 beat_schedule 에도 같은 항목이 있다(두 곳 모두 넣는 이유는 그쪽 주석).
    "check-data-freshness": {
        "task": "core.check_data_freshness",
        "schedule": crontab(hour=9, minute=20),
    },
}

# ★ 2026-09-20 — config/celery.py 와 같은 스위치 (크롤하지 않는 서버에서는 끈다)
if os.getenv("CELERY_CRAWL_DISPATCH", "1") == "0":
    CELERY_BEAT_SCHEDULE.pop("dispatch-due-crawl-targets", None)

AWS_STORAGE_BUCKET_NAME = os.getenv(
    "AWS_STORAGE_BUCKET_NAME"
)

AWS_REGION = os.getenv(
    "AWS_REGION",
    "ap-northeast-2",
)

YOUTUBE_API_KEY = os.getenv(
    "YOUTUBE_API_KEY"
)

# KURE candidates remain review-only unless both values are configured from a
# calibrated benchmark.  Environment variables keep deployment tuning out of
# the pipeline code.
KURE_HIGH_CONFIDENCE_THRESHOLD = (
    float(os.getenv("KURE_HIGH_CONFIDENCE_THRESHOLD"))
    if os.getenv("KURE_HIGH_CONFIDENCE_THRESHOLD")
    else None
)
KURE_HIGH_CONFIDENCE_MARGIN_THRESHOLD = (
    float(os.getenv("KURE_HIGH_CONFIDENCE_MARGIN_THRESHOLD"))
    if os.getenv("KURE_HIGH_CONFIDENCE_MARGIN_THRESHOLD")
    else None
)


# ══════════════════════════════════════════════════════════════
#  배포 설정 (feedit 프론트 연동용)
# ══════════════════════════════════════════════════════════════

# 정적 파일 — whitenoise 가 압축·해시해서 내보낸다.
#   배포 전에 한 번: python manage.py collectstatic --noinput
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# ★ 2026-09-27 — 시험(manage.py test)에서는 collectstatic 을 돌리지 않으므로 해시 목록(manifest)이 없다.
#   그대로 두면 관리자 화면을 그리는 순간 'Missing staticfiles manifest entry' 로 터진다.
#   시험에서만 일반 저장소를 쓴다. 운영 설정은 그대로다.
if len(sys.argv) > 1 and sys.argv[1] == "test":
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
    # 시험 계정 비밀번호 해시가 시험 시간의 대부분을 먹는다 — 시험에서만 빠른 해시를 쓴다
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# 앞단 프록시(Caddy/nginx)가 있을 때만 켠다.
if os.getenv("DJANGO_BEHIND_PROXY", "False").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

# ── 쿠키 보안 (2026-09-21) ──────────────────────────────────
#
# ★ 기본값은 꺼짐이다. 일부러 그렇게 뒀다.
#   지금 이 서버는 http 로만 열려 있다(443 미개방). 그 상태에서 Secure 를
#   켜면 브라우저가 쿠키를 아예 저장하지 않아 **운영 대시보드 로그인이
#   그 자리에서 막힌다.** 시연 중인 배포를 깨뜨리지 않으려고 스위치로 뒀다.
#
#   TLS 를 붙인 다음(보안 가이드 2번) 서버 .env 에 한 줄만 넣으면 켜진다:
#       DJANGO_SECURE_COOKIES=1
#   코드를 다시 고칠 필요가 없다.
# Secure 쿠키와 전체 HTTP→HTTPS 강제는 별도 스위치다. Vercel의
# BACKEND_API_URL이 아직 HTTP인 단계에서 둘을 같이 켜면 사용자 API가
# 301을 반환하고 인증 헤더가 리다이렉트에서 유실될 수 있다.
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "0") == "1"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "0") == "1"

# HTTPS가 실제로 확인되기 전 1년 HSTS/preload를 켜면 장애 복구가 어렵다.
# 처음에는 0, 안정화 뒤 300 → 86400 → 31536000 순으로 늘린다.
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_HSTS_INCLUDE_SUBDOMAINS", "0") == "1"
SECURE_HSTS_PRELOAD = os.getenv("DJANGO_HSTS_PRELOAD", "0") == "1"

# 관리자 OTP는 배포 직후 잠금 사고를 막기 위해 명시적으로 켠다.
# HTTPS와 OTP 테이블 마이그레이션을 확인한 뒤 운영 .env에 1을 넣는다.
DASHBOARD_OTP_REQUIRED = os.getenv("DASHBOARD_OTP_REQUIRED", "0") == "1"
DASHBOARD_OTP_ISSUER = os.getenv("DASHBOARD_OTP_ISSUER", "FEEDiT Admin")
DASHBOARD_SESSION_AGE = int(os.getenv("DASHBOARD_SESSION_AGE", "3600"))
DASHBOARD_ALLOWED_EMAILS = tuple(
    email.strip().casefold()
    for email in os.getenv("DASHBOARD_ALLOWED_EMAILS", "").split(",")
    if email.strip()
)

# 켜든 말든 항상 좋은 것들 — 쿠키를 자바스크립트가 못 읽게, 크로스사이트 전송 제한.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

_LOCAL_FRONTEND_PORTS = (4173, 4174, *range(5173, 5184))
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([
    *(
        f"http://{host}:{port}"
        for host in ("localhost", "127.0.0.1")
        for port in _LOCAL_FRONTEND_PORTS
    ),
    *[
        o.strip()
        for o in os.getenv(
            "DJANGO_CSRF_TRUSTED_ORIGINS",
            "https://feedit-official.duckdns.org",
        ).split(",")
        if o.strip()
    ],
]))
