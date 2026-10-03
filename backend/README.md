# FEEDiT Backend

Django API·관리자·수집·분석·정기 작업을 포함합니다. 사용자 데이터와 투표 등을 기록하므로 읽기 전용 API가 아닙니다.

| 경로 | 책임 |
| --- | --- |
| `apps/api/` | 사용자 API와 인증·계정·상품·지표 경로 |
| `apps/core/` | 관리자, 데이터 모델, 관리 명령, 작업 조율 |
| `collection/` | 커머스·콘텐츠·검색 수집 |
| `analysis/` | 정규화 이후 텍스트·비전·속성 분석 |
| `config/` | Django URL·설정·Celery |

API/정기 작업의 경량 설치는 `requirements-api.txt`, 전체 분석 환경은 루트 `requirements.txt`를 사용합니다. 데이터 모델과 마이그레이션을 기준으로 스키마를 확인하며 운영 스키마 변경은 별도 계획으로 수행합니다.

[실행·검증](../docs/DEVELOPMENT.md) · [운영 배포](../docs/DEPLOYMENT.md) · [데이터 흐름](../docs/DATA_PIPELINE.md)
