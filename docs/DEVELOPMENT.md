# 개발 환경과 검증

기준일: 2026-10-04. 저장소 루트에서 시작합니다. 권장 Python은 3.13, 프론트 Node 기준은 `frontend/.nvmrc`의 20 계열입니다. Vite의 Node 최소 패치 요구사항도 만족하는 버전을 사용하세요.

## 공통 준비

```bash
cp .env.example .env
```

실제 값은 팀의 환경 관리 절차로 채웁니다. `.env`를 문서·채팅·커밋에 포함하지 않습니다. RDS 접속 권한과 네트워크 경로가 있어야 데이터 기능을 검증할 수 있습니다. 운영 DB의 스키마 변경을 개발 시작 명령에 포함하지 않습니다.

## 프론트엔드

```bash
cd frontend
nvm use
npm ci
npm run dev
```

5173에서 Vite가 실행됩니다. `/api`는 `VITE_DJANGO_API_URL` 또는 `API_PORT`(기본 8000), `/api/v1`은 8770으로 전달됩니다. `npm run preview`는 빌드 결과 확인용이며 개발 프록시나 Vercel 함수를 동일하게 제공하지 않습니다.

## Django API

가벼운 API 환경의 예시입니다. 수집·비전 작업은 루트 `requirements.txt`의 별도 분석 환경이 필요합니다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-api.txt
cd backend
python manage.py runserver 8000
```

DB 접속 환경을 갖춘 뒤 `/api/health`, `/admin/`, `/admin-dashboard/`를 점검합니다. API 공유 토큰을 설정했다면 직접 요청에도 해당 인증이 필요합니다.

이 저장소는 DB·Redis를 자동으로 시작하지 않습니다. 로컬 서비스 또는 승인된 사설 네트워크 연결을 준비하고 `.env`의 `DB_*`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`를 맞춥니다. 주기 작업은 별도 Celery worker와 beat 프로세스가 필요합니다.

## 챗봇

```bash
python -m pip install -r ChatBot/requirements.txt
python ChatBot/tools_env_check.py
cd ChatBot
python server.py
```

기본 데이터 모드는 RDS입니다. `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`를 준비합니다. 질문 어휘 추출기는 `ChatBot/vendor/`에 포함되어 있어 따로 준비할 것이 없습니다. LLM을 사용하려면 공급자 접근 권한과 `OPENAI_API_KEY`가 필요합니다.

`FEEDIT_BACKEND_API`는 실행 환경에서 접근 가능한 Django `/api` 주소로 맞춥니다. 운영 주소는 실제 서버 설정을 확인하고, 로컬에서는 예를 들어 `http://127.0.0.1:8000/api`를 사용합니다. `FEEDIT_LLM_DISABLED=1`은 LLM 호출을 비활성화하지만 DB·추출기 의존성까지 없애지는 않습니다. `FEEDIT_DATA_BACKEND=sqlite`는 별도 데이터가 필요한 회귀/오프라인 경로입니다.

## 검증

```bash
# 프론트엔드 폴더
npm run build
npm test

# 저장소 루트: frontend의 잠긴 jsdom 의존성을 재사용
bash ChatBot/tests/run.sh

# 저장소 루트
PYTHONPATH=ChatBot python -m unittest discover -s ChatBot/tests -p 'test_*.py'
git diff --check

# backend 폴더: 빈 Postgres(pgvector)에 DB_* 를 맞추고
python -m pip install -r requirements-api.txt rapidfuzz beautifulsoup4
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py test apps
```

같은 검사를 GitHub Actions(`.github/workflows/ci.yml`)가 main 에 올릴 때와 PR 마다 돌립니다. 배포는 하지 않습니다.

Python 전체 테스트에는 환경·외부 의존성이 필요한 항목이 있을 수 있습니다. 네트워크 호출 도구(`tools_llm_check.py` 등)는 오프라인 검사로 취급하지 않습니다. 테스트 실패는 원인과 실행 환경을 기록하고, 통과한 검증과 분리해 보고합니다.

[협업 규칙](../frontend/docs/WORKFLOW.md)
