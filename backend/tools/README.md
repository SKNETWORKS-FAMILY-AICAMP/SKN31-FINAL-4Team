# tools

`manage.py shell` 로 실행하는 진단용 스크립트 모음입니다.
장고 앱이 아니라 필요할 때만 돌리는 일회성 도구라 `INSTALLED_APPS` 에 넣지 않습니다.

## perf_check.py

대시보드 페이지별 응답 시간과 쿼리 수를 측정합니다.

```
docker exec feedit-web python manage.py shell -c "exec(open('/app/tools/perf_check.py').read())"
```

읽는 법

- 쿼리 개수가 많다 → 반복 조회(N+1) 의심
- 쿼리 하나가 유독 느리다 → 무거운 컬럼을 같이 가져오는지 확인
- 쿼리는 적은데 느리다 → 외부 호출(S3 / Celery 등) 의심
