# 기술 스택과 버전

기준일: 2026-10-04. 아래는 **저장소에 선언되거나 잠긴 버전**입니다. 운영 서버 설치 상태나 패키지 공급자의 배포 가능 여부를 실측한 결과가 아닙니다. 이번 정리에서는 의존성 버전을 올리지 않았습니다.

| 라이브러리 | 버전 | 기준 파일 |
| --- | --- | --- |
| vite | 7.3.6 | frontend/package-lock.json |
| jsdom | 25.0.1 | frontend/package-lock.json |
| pg | 8.23.0 | frontend/package-lock.json |
| html-to-image | 1.11.13 | frontend/package-lock.json |
| html2canvas | 1.4.1 | frontend/package-lock.json |
| Django | ==6.1 | requirements.txt |
| gunicorn | ==26.2.0 | requirements.txt |
| psycopg | ==3.3.4 | requirements.txt |
| boto3 | ==1.43.83 | requirements.txt |
| celery | ==5.6.3 | requirements.txt |
| redis | ==8.1.0 | requirements.txt |
| pgvector | ==0.5.0 | requirements.txt |
| requests | ==2.34.2 | requirements.txt |
| PyYAML | ==6.0.3 | requirements.txt |
| torch | ==2.13.0 | requirements.txt |
| torchvision | ==0.28.0 | requirements.txt |
| transformers | ==5.16.1 | requirements.txt |
| ultralytics | ==8.4.137 | requirements.txt |
| onnx | ==1.22.0 | requirements.txt |
| onnxruntime | ==1.29.0 | requirements.txt |
| easyocr | ==1.7.2 | requirements.txt |
| opencv-python | ==5.0.0.93 | requirements.txt |
| playwright | ==1.62.0 | requirements.txt |

## 실행 환경과 범위

| 구분 | 기준 |
| --- | --- |
| Python | 로컬·CI 권장 3.13; 운영 설치 버전은 서버에서 확인 |
| Node | frontend/.nvmrc `20`; 실제 운영 Node는 Vercel 설정 확인 |
| Redis 서버 | 작업 큐에 필요; 운영 버전은 서버에서 확인 |
| PostgreSQL | RDS 사용; 서버 엔진 버전 미확인 |
| 프론트 방식 | Vanilla JS ES modules + CSS + Vite |
| 폰트 | Pretendard 1.3.9 CDN, Roboto Flex, Space Grotesk |
| 모션 | 프론트 CDN anime.js 4.5.0, Lenis 1.3.26 |

설치 대상은 분리됩니다. API는 `backend/requirements-api.txt`, 챗봇은 `ChatBot/requirements.txt`, 전체 분석/수집은 루트 `requirements.txt`를 사용합니다. 검색 수집 패키지에도 별도 requirements가 있습니다. API의 pandas는 `>=2.2.2,<3`, numpy와 lxml은 미고정이므로 완전한 재현 잠금 상태는 아닙니다.

## 모델과 오픈소스 사용

- 챗봇은 Python 도구 오케스트레이션과 HTTP API 호출을 사용합니다. 모델 식별자·역할은 `ChatBot/app/` 설정과 코드가 기준이며 실제 제공 권한은 별도 검증합니다.
- OCR/비전/속성 분석에는 EasyOCR, Ultralytics/ONNX, Transformers 및 SigLIP2 관련 코드가 있습니다. 분석 자산과 온라인 모델 API는 별도 경로입니다.
- README 시각화는 자체 SVG + GitHub Mermaid + Shields 배지입니다. 외부 통계 위젯이나 존재하지 않는 CI 성공 배지를 넣지 않습니다.
- 의존성별 라이선스는 원 프로젝트를 따릅니다. 이 저장소 전체의 라이선스나 수집 데이터·모델 가중치의 재배포 권한을 새로 부여하지 않습니다.

변경 시 manifest와 lock 파일을 함께 확인하고 해당 환경의 빌드·테스트를 수행하세요. [개발 안내](DEVELOPMENT.md)
