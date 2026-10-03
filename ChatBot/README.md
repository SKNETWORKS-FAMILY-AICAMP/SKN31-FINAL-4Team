# FEEDiT ChatBot

Python 표준 HTTP 서버와 데이터 도구로 구성한 대화 서비스입니다. 기준일: 2026-10-04.

## 책임

일반 모드는 지표·상품·스타일을 설명하고 코디를 제안합니다. 살말 모드는 구매 판단·상품 비교·코디 인계·가상 피팅 도구를 사용합니다. SSE 응답과 프론트 블록 렌더링의 계약을 함께 유지합니다. 데이터에 없는 수치·주소를 모델 생성으로 대신하지 않습니다.

온도·모멘텀·순위·플랫폼별 온도·긍부정은 트렌드 분석 화면과 같은 Django API(`/api/trend`, `/api/sentiment`)를 같은 인자로 읽고, 화면과 같은 규칙으로 요약합니다(`app/trend_view.py`). 그래서 `FEEDIT_BACKEND_API`에 닿지 못하면 이 축은 "읽지 못했다"고 답합니다. 연관어·근거·순위 도구는 아직 RDS 지표 표를 직접 읽습니다.

## 실행

저장소 루트의 `.env`와 Python 환경을 준비합니다.

```bash
python -m pip install -r ChatBot/requirements.txt
python ChatBot/tools_env_check.py
cd ChatBot
python server.py
```

기본 포트 8770, 기본 데이터 모드는 RDS입니다. DB 접근 정보가 필요합니다. 질문 어휘 추출기(`vendor/question_extract.py`)와 Lexicon(`vendor/feedit_crawler/`, `vendor/config/lexicon.yaml`)은 저장소에 포함되어 있습니다. 모델 호출에는 `OPENAI_API_KEY`, Django 도구에는 접근 가능한 `FEEDIT_BACKEND_API`를 설정합니다. `tools_llm_check.py`는 실제 모델 호출이므로 오프라인 점검이 아닙니다.

`FEEDIT_PUBLIC_BETA` 기본값은 1입니다. 토큰·플랜 정책은 `app/plans.py`와 서버 설정을 함께 확인합니다. SQLite 어댑터와 `tools_make_bundle.sh`는 별도 외부 데이터가 있는 오프라인/이전 환경용이며 운영 RDS 배포의 준비 명령이 아닙니다.

## 테스트

```bash
# 루트에서: frontend 의존성 설치 후 실행
bash ChatBot/tests/run.sh
PYTHONPATH=ChatBot python -m unittest discover -s ChatBot/tests -p 'test_*.py'
```

브라우저 테스트는 `frontend/package-lock.json`에 잠긴 jsdom을 재사용합니다. `ChatBot/node_modules`를 별도로 설치하거나 Git에 넣지 않습니다. 테스트가 사용하는 임시 복사본은 실행 종료 시 정리됩니다.

[전체 실행](../docs/DEVELOPMENT.md) · [시스템 구성](../docs/ARCHITECTURE.md) · [작업 원칙](AGENTS.md)
