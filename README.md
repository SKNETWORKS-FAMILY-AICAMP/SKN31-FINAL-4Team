<div align="center">
  <img src="backend/apps/dashboard/static/dashboard/img/feedit-logo.png" width="64" alt="FEEDiT 로고" />

# FEEDiT

**데이터로 트렌드를 읽고, 근거를 바탕으로 구매를 결정하는 패션 AI 플랫폼**

[서비스 바로가기](https://fee-di-t-frontend.vercel.app/)
</div>

---

## 목차

1. [팀 소개](#팀-소개)
2. [프로젝트 소개](#프로젝트-소개)
3. [핵심 기능](#핵심-기능)
4. [기술 스택](#기술-스택)
5. [아키텍처](#아키텍처)
6. [데이터와 지표](#데이터와-지표)
7. [로컬 실행](#로컬-실행)
8. [문서](#문서)

---

## 팀 소개

| 유진영 | 고현아 | 김봉남 | 안혁진 | 전서연 |
| :---: | :---: | :---: | :---: | :---: |
| <a href="https://github.com/ujneg18-source"><img src="https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white" alt="유진영 GitHub" /></a> | <a href="https://github.com/hellene0708-cyber"><img src="https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white" alt="고현아 GitHub" /></a> | <a href="https://github.com/bongrybong"><img src="https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white" alt="김봉남 GitHub" /></a> | <a href="https://github.com/Jinxxxok"><img src="https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white" alt="안혁진 GitHub" /></a> | <a href="https://github.com/sxoxyn"><img src="https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white" alt="전서연 GitHub" /></a> |
| <img src="outputs/images/jy.png" width="120" height="120" alt="유진영 프로필 이미지" /> | <img src="outputs/images/ha.png" width="120" height="120" alt="고현아 프로필 이미지" /> | <img src="outputs/images/bn.png" width="120" height="120" alt="김봉남 프로필 이미지" /> | <img src="outputs/images/hj.png" width="120" height="120" alt="안혁진 프로필 이미지" /> | <img src="outputs/images/sy.png" width="120" height="120" alt="전서연 프로필 이미지" /> |
| <b>PM · 총괄</b> | <b>DB · Backend</b> | <b>Backend</b> | <b>Frontend · AI Agent</b> | <b>Frontend · AI Agent</b> |

---

## 프로젝트 소개

FEEDiT은 흩어진 패션 커머스·콘텐츠·검색 데이터를 모아 지금 주목받는 스타일과 아이템을 보여줍니다.
사용자는 트렌드 지표를 확인하고, AI 챗봇과 커뮤니티의 도움을 받아 구매를 판단할 수 있습니다.

### 해결하려는 문제

- **감에 의존하는 트렌드 판단**: 언급과 관심의 변화를 숫자로 확인하기 어렵습니다.
- **흩어진 구매 정보**: 가격, 콘텐츠 반응, 리세일 시세가 서로 다른 서비스에 있습니다.
- **구매 직전의 망설임**: 내 취향과 현재 트렌드를 함께 고려한 근거가 부족합니다.

FEEDiT은 데이터를 수집해 지표로 만들고, 그 결과를 챗봇·살!말? 투표·개인화 피드에 연결합니다.

## 핵심 기능

| 기능 | 사용자가 할 수 있는 일 |
| --- | --- |
| **트렌드 분석** | 6종 지표로 스타일·아이템의 현재 흐름과 변화를 살펴봅니다. |
| **AI 챗봇** | 일반 모드에서 트렌드·스타일을 묻고, 살!말? 모드에서 구매 조언을 받습니다. |
| **살!말? 커뮤니티** | 고민 상품을 공유하고 투표와 댓글로 다른 사람의 의견을 확인합니다. |
| **가상 피팅** | 상품 이미지를 FEEDiT 모델에 적용해 착용 모습을 미리 봅니다. |
| **내 피드** | 취향과 활동을 반영한 브리핑·추천을 확인합니다. |

## 기술 스택

| 구분 | 주요 기술 | 역할 |
| --- | --- | --- |
| **프론트** | Vite · Vanilla JavaScript · Vercel | 화면, 차트, 채팅 UI와 정적 웹 배포 |
| **백** | Python · Django · Celery · Redis | 서비스 API, 계정·투표, 정기 작업 |
| **AI** | OpenAI API · FashionSigLIP2 + LoRA | 챗봇·가상 피팅·상품 스타일 태깅 |
| **Data** | PostgreSQL (AWS RDS) · S3 · Playwright · YouTube Data API · Google Trends · Naver DataLab | 데이터 수집·저장·분석 |
| **운영체제** | Ubuntu Linux (GitHub Actions CI) | 자동 검증 실행 환경 |

운영 요청은 Vercel에서 EC2의 Django API 또는 챗봇 서버로 전달됩니다.
서버 구성과 배포 절차는 [시스템 구성](docs/ARCHITECTURE.md)과 [배포 안내](docs/DEPLOYMENT.md)에 정리했습니다.

## 아키텍처

### 1. 시스템 아키텍처

브라우저는 Vercel에서 웹 화면을 받고, 서버 요청은 EC2의 nginx를 거쳐 Django API 또는 챗봇으로 전달됩니다.
Django는 RDS의 서비스 데이터를 읽고 쓰며, 챗봇은 데이터 도구와 외부 모델 API를 조합해 응답합니다.

<p align="center"><img src="outputs/images/시스템_아키텍처.png" width="900" alt="FEEDiT 시스템 아키텍처" /></p>

- **Vercel**: 정적 화면 제공과 서버리스 함수의 API 중계
- **Django API**: 인증, 프로필, 지표, 투표, 관리자 기능
- **챗봇 서버**: 대화 처리, 도구 호출, 이미지 처리, 스트리밍 응답
- **RDS·S3**: 서비스 데이터와 수집 원본·이미지 객체 저장

### 2. 챗봇 · 일반 모드

일반 모드는 질문의 의도를 파악한 뒤 필요한 데이터 도구와 에이전트를 선택합니다.
트렌드·상품·스타일 정보를 모아 숫자와 근거를 확인하고, 결론과 다음 행동을 답변으로 조립합니다.

<p align="center"><img src="outputs/images/챗봇_일반모드_아키텍처.png" width="900" alt="FEEDiT 일반 모드 챗봇 아키텍처" /></p>

- **질문 라우팅**: 질문 유형과 필요한 도구 선택
- **정보 수집**: 트렌드 지표, 상품, 스타일, 취향 데이터 조회
- **검증·조립**: 숫자 대조 후 근거와 출처를 포함한 답변 생성

### 3. 챗봇 · 살!말? 모드

살!말? 모드는 상품과 취향 정보를 받아 다섯 신호를 병렬 수집합니다.
살말지수는 코드로 계산하고, 챗봇은 점수의 이유와 부족한 근거를 설명합니다.

<p align="center"><img src="outputs/images/챗봇_살말모드_아키텍처.png" width="900" alt="FEEDiT 살!말? 모드 챗봇 아키텍처" /></p>

- **입력**: 상품 이름·링크·사진과 사용자의 승인된 취향 정보
- **계산**: 취향·행동·트렌드·가격·투표의 가중 평균
- **응답**: 살/말 조언, 검증 근거, 신뢰도, 다음 행동

## 데이터와 지표

### 데이터가 흐르는 방식

| 단계 | 내용 |
| --- | --- |
| **수집** | 패션 커머스, 리세일 플랫폼, YouTube, 검색 신호를 각각 수집 |
| **정규화** | 플랫폼별 상품·용어를 FEEDiT의 표준 상품·패션 사전에 연결 |
| **저장** | 상품·브랜드 등 기준 정보와 가격·랭킹 등 시계열 기록을 분리 |
| **분석** | 정기 작업으로 지표를 계산하고 결과를 API와 챗봇 도구에 제공 |

상품·브랜드·카테고리 같은 기준 정보는 Master로, 가격·랭킹·조회수처럼 변하는 값은 Snapshot으로 관리합니다.
수집 원본은 S3에 보관해 분석 결과를 원본 데이터와 연결할 수 있도록 했습니다.

### 여섯 가지 트렌드 지표

| 지표 | 확인할 수 있는 것 |
| --- | --- |
| **언급량·온도** | 관심 수준과 최근 변화 방향 |
| **연관어** | 함께 언급되는 아이템·소재·컬러·핏·상황 |
| **구매의향** | 리뷰·댓글에서 드러난 긍정·부정 신호 |
| **수명주기** | 태동·확산·정점·쇠퇴 단계 |
| **할인율 변화** | 가격과 할인 흐름 |
| **리세일 시세** | 정가 대비 중고·리셀 가치 |

수치가 없는 항목을 임의의 0으로 채우지 않습니다.
관측이 부족하거나 추정된 값은 화면과 챗봇에서 구분해 표시합니다.

### 살말지수 계산 원칙

| 신호 | 기준 가중치 | 살펴보는 내용 |
| --- | ---: | --- |
| 취향 | 35% | 스타일·키워드와의 일치 |
| 행동 | 25% | 검색·찜 등 사용자 활동 |
| 트렌드 | 20% | 관심도와 변화 방향 |
| 가격 | 15% | 현재 가격·할인 정보 |
| 투표 | 5% | 커뮤니티의 살/말 의견 |

- 없는 신호는 50점으로 채우지 않고 계산 분모에서 제외합니다.
- 근거의 범위가 좁으면 낮은 신뢰도로 표시합니다.
- 지표·가격·상품 URL은 모델이 만들어내지 않고 데이터 도구의 결과를 사용합니다.
- 검증 단계에서 수치와 근거를 다시 대조합니다.

자세한 수집·계산 방식은 [데이터 파이프라인](docs/DATA_PIPELINE.md)을 참고하세요.

## 로컬 실행

개발 기준은 Python 3.13과 Node.js 20 계열입니다.
아래 명령 블록은 각각 저장소 루트에서 시작합니다. 데이터 기능에는 별도의 RDS 접근 권한과 환경변수가 필요합니다.

### 1. 환경 준비

~~~bash
cp .env.example .env
~~~

환경값은 팀의 관리 절차에 따라 채웁니다. 비밀값을 저장소에 커밋하지 않습니다.

### 2. 프론트엔드

~~~bash
cd frontend
nvm use
npm ci
npm run dev
~~~

개발 화면은 http://localhost:5173 에서 열립니다.

### 3. Django API

~~~bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-api.txt
cd backend
python manage.py runserver 8000
~~~

API 기본 주소는 http://localhost:8000 입니다.
DB와 Redis는 이 명령으로 자동 실행되지 않습니다.

### 4. 챗봇

~~~bash
source .venv/bin/activate
python -m pip install -r ChatBot/requirements.txt
python ChatBot/tools_env_check.py
cd ChatBot
python server.py
~~~

챗봇 기본 포트는 8770입니다. LLM 사용에는 공급자 접근 권한과 API 키가 필요합니다.
각 구성의 실행 조건과 검증 명령은 [개발 안내](docs/DEVELOPMENT.md)를 확인하세요.

## 문서

- [전체 문서](docs/README.md) · [기술 구성](docs/TECHNOLOGY.md) · [시스템 구성](docs/ARCHITECTURE.md)
- [데이터 파이프라인](docs/DATA_PIPELINE.md) · [개발 환경](docs/DEVELOPMENT.md) · [배포 안내](docs/DEPLOYMENT.md)

<div align="center"><sub>SK네트웍스 Family AI 31기 · 4팀</sub></div>
