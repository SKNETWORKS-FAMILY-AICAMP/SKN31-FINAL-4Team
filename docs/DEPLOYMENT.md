# 배포와 운영

기준일: 2026-10-04. 이 저장소에는 서버용 Docker·Compose·nginx 설정이 없습니다. 기존 EC2가 사용하는 구성은 서버에서 별도로 관리하며, 이 문서만으로 운영 배포가 재현된다고 가정하지 않습니다.

## Vercel 프론트엔드

- 프로젝트 루트: `frontend/`
- 설치: `frontend/vercel.json`의 현재 설정은 `npm install`; 로컬 재현은 `npm ci`
- 빌드: `npm run build`
- 출력: `dist/`
- 라우팅 및 함수 설정: `frontend/vercel.json`, `frontend/api/`
- 서버 변수: `BACKEND_API_URL`, `BACKEND_API_TOKEN`, `CHAT_BACKEND_URL`, `CHAT_BACKEND_TOKEN`; 직접 DB 폴백을 사용할 때만 `DATABASE_URL` 또는 `PG*`

운영값은 Vercel 프로젝트 설정에서 관리합니다. 브라우저 번들에 비밀값을 넣지 않습니다.

## API·챗봇·작업 큐

- Django 진입점: `backend/config/wsgi.py`; API 의존성: `backend/requirements-api.txt`.
- 챗봇 진입점: `ChatBot/server.py`; 의존성: `ChatBot/requirements.txt`; 기본 포트: `8770`.
- 수집·분석·주기 작업은 `backend/config/celery.py`와 `backend/apps/core/tasks.py`에 정의되어 있습니다. Redis와 worker/beat 프로세스가 별도로 필요합니다.
- RDS·S3·외부 모델 API 연결은 실제 서버 환경변수와 네트워크 권한이 필요합니다. 비밀값은 저장소에 저장하지 않습니다.

배포 전 서버의 현재 실행 방식, 프록시, 포트, 비밀값 제공 방식, DB 백업 및 마이그레이션 계획을 확인합니다. 코드만 바꾸어도 운영 서버에 자동 적용되는 것으로 가정하지 않습니다.

## 확인

1. `frontend`에서 `npm ci`, `npm run build`, `npm test`를 실행합니다.
2. 서버에서 API, 챗봇, Redis, worker, beat의 실제 프로세스와 로그를 확인합니다.
3. `/api/health`, `/api/v1/health`와 로그인·조회·대화 경로를 확인합니다. 상태 코드만으로 실데이터 연결을 단정하지 않습니다.
4. 스키마 변경은 백업과 마이그레이션 계획을 확인한 뒤 별도 실행합니다.

로컬 실행은 [개발 안내](DEVELOPMENT.md), 서비스 구성은 [시스템 구성](ARCHITECTURE.md)을 봅니다.
