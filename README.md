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

---

# FEEDIT Frontend 실행법

## 1. Node.js 설치

Node 20 버전을 사용합니다 (`frontend/.nvmrc` 참고). nvm을 쓰는 경우:

```powershell
nvm use
```

## 2. frontend 폴더에서 패키지 설치

```powershell
cd frontend
npm install
```

## 3. 개발 서버 실행

```powershell
npm run dev
```
http://localhost:5173

`npm run dev`를 실행하면 Vite 개발 서버가 뜨면서 브라우저가 자동으로 열립니다.

## 종료

터미널에서 `Ctrl + C`

## 프로덕션 빌드 (배포용)

```powershell
npm run build
```
`frontend/dist/` 폴더에 정적 파일(HTML/CSS/JS)이 생성됩니다.

빌드 결과물을 로컬에서 미리 보려면:

```powershell
npm run preview
```

프론트엔드는 현재 백엔드(Django API)와는 별도로 빌드·배포되는 정적 SPA(Vite)입니다.