# FEEDIT Backend 실행법

## 1. Docker Desktop 실행

Docker Desktop을 먼저 켭니다.

## 2. 프로젝트 루트에서 실행

```powershell
docker compose --env-file .env -f docker/compose.yml up --build
```
http://localhost:8000/dashboard/

## 종료 
```powershell
docker compose --env-file .env -f docker/compose.yml down
```

Docker가 Django + Redis + SSM Tunnel을 실행하고, DB는 AWS RDS를 사용함