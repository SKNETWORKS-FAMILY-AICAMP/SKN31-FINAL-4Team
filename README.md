# SKN31-FINAL-4Team

> **FEEDIT — 패션 데이터를 수집·분석하여 트렌드와 인사이트를 제공하는 AI 패션 트렌드 분석 플랫폼**

## 👥 팀명

**SK네트웍스 Family AI 31기 4팀**

---

# 🧭 프로젝트 구조

현재 FEEDIT의 Django는 **데이터 수집·저장·분석을 관리하기 위한 내부 백엔드 시스템**으로 사용합니다.

```text
[1] 데이터 수집
        ↓
[2] 원본 데이터 저장
        ↓
[3] 클리닝 / 전처리
        ↓
[4] 분석 / 지표 계산
        ↓
[5] 서비스용 DB 저장
        ↓
[6] API / 서비스 연결
```

전체 구조는 아래 기준으로 관리합니다.

```text
SKN31-FINAL-4Team/
│
├── backend/
│   │
│   ├── apps/
│   │   └── Django가 관리하는 영역
│   │       DB Model / Service / Celery / Admin 등
│   │
│   ├── collection/
│   │   └── 외부 플랫폼에서 데이터를 가져오는 영역
│   │       Musinsa / YouTube / Ably / Zigzag 등
│   │
│   ├── analysis/
│   │   └── 수집한 데이터를 분석하는 영역
│   │       Trend / Keyword / Ranking / Score 등
│   │
│   ├── config/
│   │   └── Django 실행 환경
│   │       Settings / URL / Celery 설정 등
│   │
│   ├── static/
│   ├── templates/
│   └── manage.py
│
├── frontend/
│   └── FEEDIT 사용자 서비스 Frontend
│
├── .env
├── docker-compose.yml
└── README.md
```

### Backend 역할 한눈에 보기

```text
collection
    ↓
외부 데이터 수집
    ↓
apps
    ↓
Django ORM / DB 저장 / Celery / Admin
    ↓
analysis
    ↓
트렌드 분석 / 지표 계산
    ↓
DB / API
```

### 폴더 선택 기준

```text
외부 사이트에서 데이터를 가져온다
→ collection/

Django ORM / Admin / Celery를 사용한다
→ apps/

수집한 데이터를 계산·분석한다
→ analysis/

Django 실행 설정이다
→ config/
```

> **Django Dashboard / Admin은 개발팀이 크롤러 실행 상태와 수집 데이터를 확인하기 위한 내부 관리자 화면입니다.**

---

# 🔥 Git 협업 규칙

충돌을 최소화하기 위해 **팀원별 Branch → Commit → Push → Pull Request → Merge** 방식으로 작업합니다.

## 1. Branch 구조

`main`에는 **확인된 안정적인 코드만** 합칩니다.

각 팀원은 자신의 Branch에서 작업합니다.

```text
main
 │
 ├── dev/봉남
 ├── dev/진영
 ├── dev/현아
 ├── dev/서연
 └── dev/혁진
```

### 절대 금지

```text
main에서 바로 개발 ❌
main에 바로 push ❌
다른 팀원 branch에서 작업 ❌
```

---

## 2. 처음 프로젝트 받기

```bash
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN31-FINAL-4Team.git

cd SKN31-FINAL-4Team
```

자신의 Branch를 생성합니다.

```bash
git checkout -b dev/내이름
```

예:

```bash
git checkout -b dev/봉남
```

처음 한 번 GitHub에 Branch를 등록합니다.

```bash
git push -u origin dev/봉남
```

---

## 3. 매일 작업 시작 전

### ① main 최신화

```bash
git checkout main
git pull origin main
```

### ② 내 Branch로 이동

```bash
git checkout dev/내이름
```

### ③ 최신 main 반영

```bash
git merge main
```

이제 개발을 시작합니다.

---

## 4. 작업 완료 후 Commit

```bash
git add .
git commit -m "기능: 무신사 랭킹 데이터 수집 구현"
```

### Commit Message

```text
타입: 변경 내용
```

예:

```text
기능: 유튜브 영상 수집 기능 추가
수정: 무신사 카테고리 파싱 오류 수정
리팩터: 크롤러 공통 헤더 분리
설정: Celery 설정 추가
문서: README 실행 방법 수정
삭제: 미사용 크롤러 코드 제거
```

---

## 5. 내 Branch Push

```bash
git push origin dev/내이름
```

예:

```bash
git push origin dev/봉남
```

---

## 6. Pull Request

GitHub 접속 후 자신의 Branch를 Push하면

**Compare & pull request**

버튼이 나타납니다.

```text
내 Branch
    ↓
Pull Request
    ↓
팀원 확인 / Review
    ↓
Merge
    ↓
main
```

PR에는 **무엇을 작업했는지 간단하게 작성**합니다.

예:

```text
[무신사 수집 기능 추가]

- 여성 아우터 랭킹 수집
- 상품명 / 브랜드 / 가격 저장
- 공통 Header 분리
```

---

## Git 용어 간단 정리

| 용어 | 의미 |
|---|---|
| 🌳 Branch | 내 작업 공간 |
| 💾 Commit | 작업 기록 |
| ☁️ Push | 내 코드를 GitHub에 올리기 |
| 📥 Pull | GitHub의 최신 코드 가져오기 |
| 📩 PR | 내 코드를 main에 합쳐달라고 요청 |
| 👀 Review | 팀원이 코드 확인 |
| 🔀 Merge | 코드를 main에 합치기 |

---

# 🚀 FEEDIT 로컬 환경 세팅

처음 Clone 받은 팀원은 아래 순서대로 실행합니다.

## 1. 프로젝트 Clone

```bash
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN31-FINAL-4Team.git

cd SKN31-FINAL-4Team
```

---

## 2. Python 가상환경 생성

프로젝트 루트에서 실행합니다.

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### macOS / Linux

```bash
source .venv/bin/activate
```

터미널 앞에 아래처럼 표시되면 성공입니다.

```text
(.venv)
```

---

## 3. Python 패키지 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. 환경변수 설정

프로젝트 루트의 `.env.example`을 참고하여 `.env`를 생성합니다.

```text
SKN31-FINAL-4Team/
├── .env
├── docker-compose.yml
├── backend/
└── frontend/
```

> `.env`에는 DB 비밀번호, API Key 등 민감한 정보가 포함될 수 있으므로 **Git에 올리지 않습니다.**

---

## 5. PostgreSQL / Redis 실행

Docker Desktop을 먼저 실행합니다.

프로젝트 루트에서:

```bash
docker compose up -d
```

실행 상태 확인:

```bash
docker compose ps
```

PostgreSQL과 Redis가 `running` 상태이면 정상입니다.

---

## 6. Django DB Migration

```bash
cd backend

python manage.py migrate
```

---

## 7. Django 실행

```bash
python manage.py runserver
```

정상 실행되면:

```text
http://127.0.0.1:8000/
```

으로 접속합니다.

Django Admin:

```text
http://127.0.0.1:8000/admin/
```

---

# ⚙️ Celery 실행

크롤러 예약 실행 또는 비동기 작업을 사용할 경우 실행합니다.

**Django 서버와 별도의 터미널에서 실행합니다.**

## Celery Worker

```bash
cd backend
celery -A config worker -l info
```

Windows에서 Worker 실행 문제가 있는 경우:

```bash
celery -A config worker -l info -P solo
```

## Celery Beat

새 터미널에서:

```bash
cd backend
celery -A config beat -l info
```

최종적으로 개발 중에는 아래 프로세스가 실행될 수 있습니다.

```text
Docker
├── PostgreSQL
└── Redis

Django
└── python manage.py runserver

Celery
├── Worker
└── Beat
```

---

# ✅ 매일 개발 시작할 때

이미 최초 세팅을 완료했다면 매번 전부 설치할 필요 없습니다.

### 1. 최신 코드 받기

```bash
git checkout main
git pull origin main

git checkout dev/내이름
git merge main
```

### 2. 가상환경 실행

```bash
.venv\Scripts\activate
```

### 3. Docker 실행

```bash
docker compose up -d
```

### 4. Django 실행

```bash
cd backend
python manage.py runserver
```

크롤러 스케줄링이 필요하면 Celery Worker / Beat도 별도 터미널에서 실행합니다.

---

# 📌 핵심 규칙

```text
수집 코드
→ backend/collection/

Django / DB / Celery / Admin
→ backend/apps/

분석 코드
→ backend/analysis/

Django 설정
→ backend/config/
```

그리고 Git 작업은 항상:

```text
main 최신화
    ↓
내 Branch 이동
    ↓
main merge
    ↓
개발
    ↓
commit
    ↓
push
    ↓
PR
    ↓
review
    ↓
merge
```

**main에서 직접 개발하거나 Push하지 않습니다.**