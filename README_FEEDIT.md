# FEEDIT Backend 실행 가이드

FEEDIT 백엔드를 팀원 누구나 같은 방식으로 실행할 수 있도록 정리한 가이드입니다.

---

## 셋업

1. AWS CLI 다운받기 

https://aws.amazon.com/ko/cli/
 
2. 계정 정보 입력
```powershell
aws configure
```

입력:

```text
AWS Access Key ID
AWS Secret Access Key
Default region name: ap-northeast-2
Default output format: json
```

인증 확인:

```powershell
aws sts get-caller-identity
```

정상적으로 계정 정보가 출력되면 완료입니다.

---

## 6. RDS 터널 열기

FEEDIT RDS는 외부에 직접 공개하지 않고 EC2 + AWS SSM을 통해 접속합니다.

새 PowerShell 창을 하나 열고 아래 명령어를 실행합니다.

```powershell
aws ssm start-session `
  --target i-00edfb038f240d56a `
  --document-name AWS-StartPortForwardingSessionToRemoteHost `
  --parameters "host=feedit-db.cncws8gyqmnk.ap-northeast-2.rds.amazonaws.com,portNumber=5432,localPortNumber=5433" `
  --region ap-northeast-2
```

정상 실행되면 대략 아래와 같이 표시됩니다.

```text
Port 5433 opened
Waiting for connections...
```

⚠️ 이 터미널은 Django를 사용하는 동안 끄지 않습니다.

터널 확인:

```powershell
Test-NetConnection 127.0.0.1 -Port 5433
```

정상:

```text
TcpTestSucceeded : True
```


---

## 8. Migration 적용

새 모델 변경사항이 있을 때:

```powershell
python manage.py makemigrations
```

DB 반영:

```powershell
python manage.py migrate
```

기존 migration만 적용할 경우에는:

```powershell
python manage.py migrate
```

만 실행하면 됩니다.

---


## 10. S3 연결 확인

버킷:

```text
feedit-data-team4
```

확인:

```powershell
aws s3 ls s3://feedit-data-team4
```

목록이 출력되면 S3 연결 완료입니다.

---

# 매번 개발 시작할 때

매일 아래 순서만 기억하면 됩니다.

### 터미널 1 — RDS 터널

```powershell
aws ssm start-session `
  --target i-00edfb038f240d56a `
  --document-name AWS-StartPortForwardingSessionToRemoteHost `
  --parameters "host=feedit-db.cncws8gyqmnk.ap-northeast-2.rds.amazonaws.com,portNumber=5432,localPortNumber=5433" `
  --region ap-northeast-2
```

### 터미널 2 — Django

```powershell
cd C:\SKN31-FINAL-4Team
.\.venv\Scripts\Activate.ps1
cd backend

python manage.py migrate
python manage.py runserver
```

---

# 데이터 저장 원칙

FEEDIT는 데이터를 크게 두 곳에 저장합니다.

```text
크롤러
   ↓
S3
원본 JSON / HTML / 텍스트
   ↓
정제 · 정규화 · 분석
   ↓
PostgreSQL RDS
정규화 데이터 / 스냅샷 / 분석 결과
```

### S3

원본 데이터 보관.

예:

- 원본 상품 JSON
- 원본 상품명
- 원본 브랜드명
- 원본 카테고리
- API 응답
- 콘텐츠 원문

### RDS

서비스에서 사용하는 구조화된 데이터 보관.

예:

- 표준 브랜드 / 카테고리 / 패션 용어
- 정규화 상품
- 플랫폼 상품 매핑
- 가격 / 순위 / 조회수 스냅샷
- 콘텐츠 분석 결과
- 트렌드 지표
- 사용자 데이터

---

## 참고. SessionManagerPlugin not found

```powershell
winget install Amazon.SessionManagerPlugin
```

설치 후 PowerShell을 새로 열고:

```powershell
session-manager-plugin --version
```
