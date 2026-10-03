"""검색량 수집 (네이버 검색광고 · 데이터랩 · Google Trends · Google Ads)

★ 2026-09-21 — 하위 설정 패키지 이름이 sv_config 인 이유:
  원래 config 였는데, Django 프로젝트에도 backend/config 가 있어 최상위 이름이 겹쳤다.
  수집기가 sys.path 앞에 자기 폴더를 끼워 넣으면서 `from config.settings import ...` 가
  Django 설정을 집어 ImportError 로 죽는다 (Celery 안에서 부르면 바로 터진다).
  이름을 갈라 두면 단독 실행도, Django 안에서 import 하는 것도 둘 다 된다.
"""
