# 시스템 구성

기준일: 2026-10-04 · 저장소 설정 기준. 실제 가동 중인 인스턴스 수·규격·DB 엔진 버전·모델 제공 권한은 이 문서가 보증하지 않습니다.

## 요청 경로

1. 브라우저가 Vercel에서 `frontend/` 정적 번들을 받습니다.
2. 운영 `/api/*` 요청은 `frontend/api/` 서버리스 함수에서 백엔드로 전달됩니다.
3. EC2 nginx의 `/api/`는 Django/Gunicorn, `/v1/`는 챗봇 서버로 연결됩니다.
4. Django는 RDS PostgreSQL을 읽고 계정·투표·저장 항목 등을 기록합니다. 읽기 전용 서비스가 아닙니다.
5. 챗봇은 RDS 조회와 Django 도구 호출, 외부 언어·이미지 모델 호출을 조합하고 SSE로 응답합니다.

로컬 개발에서는 Vite가 `/api`를 Django로, `/api/v1`을 챗봇 `8770`으로 프록시합니다. 일부 Vercel 함수에는 `pg`를 통한 DB 직접 조회 폴백이 있습니다. 브라우저가 DB에 직접 연결하는 구조는 아닙니다.

## 서비스와 저장소

| 구성 | 구현·설정 | 책임 |
| --- | --- | --- |
| 프론트엔드 | Vite, Vanilla JS, CSS | 탐색·차트·채팅·계정 화면 |
| Vercel 함수 | `frontend/api/` | 인증 정보 전달, 서버 API 중계, 일부 조회 폴백 |
| API | Django + Gunicorn, 내부 8000 | 사용자 서비스와 관리자, RDS 읽기/쓰기 |
| 챗봇 | Python `ThreadingHTTPServer`, 8770 | 대화, SSE, 도구 실행, 피팅 |
| 작업 큐 | Redis + Celery worker/beat | 수집·분석·알림 스케줄 |
| 관계형 DB | AWS RDS PostgreSQL | dictionary / collection / commerce / content / analysis / app |
| 객체 저장소 | AWS S3 | 수집 원본·이미지 관련 객체와 접근 URL |
| 모델 | 외부 API 및 별도 분석 코드 | 텍스트 해석·이미지 생성, OCR·비전·임베딩 분석 |

## 운영 경계

이 저장소에는 서버용 Docker·Compose·프록시 설정이 없습니다. 실제 EC2의 프로세스 관리·nginx·포트·네트워크는 서버 설정을 확인해야 합니다.

- 로컬 Django 기본 포트는 `8000`, 챗봇 기본 포트는 `8770`입니다.
- EC2와 RDS의 사설 네트워크 접근은 별도 운영 설정이 필요합니다.
- 질문 추출기 `question_extract.py`와 Lexicon은 `ChatBot/vendor/`에 포함되어 있습니다.

## 모델 서빙의 구분

대화와 가상 피팅은 외부 모델 API 호출 경로가 구현되어 있습니다. 배치 분석에는 YOLO/ONNX, EasyOCR, Transformers/SigLIP2 관련 코드와 자산이 존재합니다. 이것을 별도 GPU 추론 서버의 상시 운영과 동일시하지 않습니다. 과거 문서의 RunPod 학습·성능 수치도 현재 서비스 응답 품질이나 실행 인프라를 증명하지 않습니다.

[배포 안내](DEPLOYMENT.md) · [기술 버전](TECHNOLOGY.md) · [데이터 흐름](DATA_PIPELINE.md)
