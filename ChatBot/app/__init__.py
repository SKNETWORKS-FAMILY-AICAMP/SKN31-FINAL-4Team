"""feedit-chat 앱 패키지.

★ 여기서 `.env` 를 한 번 읽는다.
  `app` 을 import 하는 모든 경로(server.py · tools_*.py · tests)가 여기를 지나므로
  키를 읽는 곳이 한 군데로 모인다. 부르는 쪽마다 dotenv 를 부르면
  "어떤 진입점에서는 키가 있고 어떤 데서는 없는" 상황이 생긴다.

  이미 있는 환경변수는 덮지 않는다 — 도커 env_file 과 셸 지정이 항상 이긴다.
"""
from . import env as _env

_env.load()
