"""대시보드 페이지별 응답 시간 / 쿼리 수 측정 도구.

화면이 느려졌을 때 어느 페이지의 어느 쿼리가 문제인지 찾는 데 쓴다.

실행:
    docker exec feedit-web python manage.py shell -c "exec(open('/app/tools/perf_check.py').read())"

출력:
    페이지별 응답 시간(ms), 실행된 쿼리 개수, 가장 느린 쿼리

읽는 법:
    - 쿼리 개수가 많다        -> 반복 조회(N+1) 의심
    - 쿼리 하나가 유독 느리다 -> 무거운 컬럼을 같이 가져오는지 확인
    - 쿼리는 적은데 느리다    -> 외부 호출(S3 / Celery 등) 의심

주의:
    DEBUG 와 ALLOWED_HOSTS 를 이 shell 프로세스에서만 임시로 바꾼다.
    실행 중인 서버 설정에는 영향이 없다.
"""

import time

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client
from django.conf import settings

settings.DEBUG = True                 # 쿼리 로깅을 켜기 위해
settings.ALLOWED_HOSTS = ["*"]        # 이 shell 프로세스에만 적용된다

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()

client = Client()
if user:
    client.force_login(user)

URLS = [
    ("메인 대시보드", "/admin-dashboard/"),
    ("수집·플랫폼현황", "/admin-dashboard/collection/platform-status/"),
    ("수집·타겟URL", "/admin-dashboard/collection/targets/"),
    ("수집·진행로그", "/admin-dashboard/collection/runs/"),
    ("수집·원본데이터", "/admin-dashboard/collection/raw-documents/"),
    ("정규화·성공", "/admin-dashboard/normalization/products/"),
    ("정규화·실패", "/admin-dashboard/normalization/failures/"),
    ("정규화·유튜브", "/admin-dashboard/normalized/youtube/"),
    ("분석·트렌드지표", "/admin-dashboard/trend/metrics/"),
    ("분석·용어별지표", "/admin-dashboard/analytics/term-metrics/"),
    ("분석·상품별지표", "/admin-dashboard/analytics/product-metrics/"),
    ("분석·상품스냅샷", "/admin-dashboard/analytics/product-snapshot/"),
    ("시스템·상태", "/admin-dashboard/system/"),
    ("시스템·작업현황", "/admin-dashboard/jobs/"),
    ("시스템·API", "/admin-dashboard/system/api/"),
    ("시스템·AWS", "/admin-dashboard/system/aws/"),
    ("시스템·Celery", "/admin-dashboard/system/celery/"),
    ("사전·용어", "/admin-dashboard/dictionary/terms/"),
    ("사전·후보", "/admin-dashboard/dictionary/candidates/"),
    ("사전·브랜드매핑", "/admin-dashboard/dictionary/brands/"),
    ("데이터·브랜드", "/admin-dashboard/data/brands/"),
    ("데이터·카테고리", "/admin-dashboard/data/categories/"),
]


print(f"{'페이지':<20} {'상태':>5} {'시간':>9} {'쿼리':>6}   가장 느린 쿼리")
print("-" * 100)

rows = []
for label, url in URLS:
    reset_queries()
    started = time.perf_counter()
    try:
        response = client.get(url)
        status = response.status_code
    except Exception as exc:
        print(f"{label:<20} {'ERR':>5}   {type(exc).__name__}: {str(exc)[:50]}")
        continue
    elapsed = (time.perf_counter() - started) * 1000

    queries = connection.queries
    slowest = max(queries, key=lambda q: float(q["time"])) if queries else None
    slow_txt = ""
    if slowest:
        slow_txt = f"{float(slowest['time'])*1000:.0f}ms  {slowest['sql'][:45]}"

    rows.append((elapsed, label))
    print(f"{label:<20} {status:>5} {elapsed:>7.0f}ms {len(queries):>5}   {slow_txt}")

print("-" * 100)
print("\n느린 순:")
for elapsed, label in sorted(rows, reverse=True)[:6]:
    print(f"  {elapsed:>7.0f}ms  {label}")
