# 데이터 파이프라인

기준일: 2026-10-04. 지표의 데이터량이나 수집 성공을 정적인 문서 숫자로 보증하지 않습니다.

## 흐름

수집 대상과 사전 → 커머스/콘텐츠 원본 → 정규화·용어 연결 → 텍스트/이미지/검색 분석 → RDS 지표 → API·화면·챗봇.

- `backend/collection/`: 커머스·콘텐츠·검색 신호 수집.
- `backend/analysis/`: 토큰화·텍스트·비전·속성·지표 관련 분석.
- `backend/apps/core/`: 관리자·작업 조율·관리 명령.
- RDS 스키마: `dictionary`, `collection`, `commerce`, `content`, `analysis`, `app`.
- S3: 원본 JSON 및 객체 저장 경로. 실제 버킷과 수명주기는 운영 환경에서 확인.

## 검색 신호는 두 경로

정기 태스크의 검색 신호 수집과 `collection/search_volume/main.py`의 수동 CSV 파이프라인을 구분합니다. 수동 CLI는 로컬 raw/processed 파일을 생성하고, `load_search_metrics` 관리 명령으로 후속 적재합니다. CLI 실행만으로 S3·RDS 적재가 모두 완료된다고 설명하지 않습니다.

검색 수집 구현은 `backend/collection/search_volume/main.py`와 `collectors/`에 있습니다. 메인 CLI에서 네이버 데이터랩 호출은 현재 주석 처리되어 있습니다. 구현 파일이 있다는 이유만으로 모든 공급자가 매 실행마다 수집된다고 가정하지 않습니다.

## 정기 작업

설정 근거: `backend/config/celery.py`, `backend/config/settings.py`. 시간대는 Asia/Seoul입니다.

| 시각 | 작업 |
| --- | --- |
| 매일 04:10 | 텍스트 신호 수집·분석·35일 지표 재계산 |
| 매일 05:30 | 검색 일간 수집 |
| 월–금 06:10 | `collect_search_weekly` 실행; 이름과 달리 스케줄은 평일 |
| 매일 10:00 | 일간 알림 |
| 일요일 18:00 | 주간 리포트 알림 |

범용 크롤 대상 디스패치는 `CELERY_CRAWL_DISPATCH=0`으로 끌 수 있습니다. 실제 worker 큐·동시성과 텍스트 분석 상한은 운영 서버의 실행 설정을 확인해야 합니다.

## 분석 자산과 신뢰도

SentencePiece 모델·어휘, ONNX 모델, 참조 이미지, 회귀 테스트 fixture는 서비스/재현성에 필요할 수 있으므로 생성 결과와 일괄 삭제하지 않습니다. 배치 비전과 온라인 대화는 실행 환경이 다릅니다. API 이미지에는 무거운 OCR·브라우저·GPU 의존성을 설치하지 않습니다.

없는 수치·부족한 관측치·추정값은 화면과 챗봇에서 구분해야 합니다. 과거 분석 보고서의 행 수·커버리지·성능 수치는 해당 시점의 기록입니다. 현재 확인은 관리 명령·DB 조회·작업 로그를 통해 진행합니다.

[기술 명세](TECHNOLOGY.md)
