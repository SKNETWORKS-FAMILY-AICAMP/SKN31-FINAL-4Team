# KREAM crawler

프로젝트의 `backend/collection/kream/`에 이 파일들을 배치한다.

## 설치

```bash
pip install curl-cffi
```

## 단독 테스트

프로젝트 루트에서 Django 환경과 무관하게 import path가 잡히는 위치라면:

```bash
python -m collection.kream.test_kream 748804
```

또는 URL:

```bash
python -m collection.kream.test_kream https://kream.co.kr/products/748804
```

## API 헤더 값 갱신

KREAM 프론트 변경으로 값이 달라질 경우 코드 수정 없이 환경변수로 교체한다.

```env
KREAM_API_VERSION=64
KREAM_WEB_BUILD_VERSION=26.12.1
KREAM_WEB_REQUEST_SECRET=kream-djscjsghdkd
KREAM_REQUEST_TIMEOUT=20
```

브라우저 DevTools > Network에서 실제 상품 페이지 요청의 `x-kream-*` 헤더를 확인해 현재 값으로 갱신한다.

## 수집 구조

- `client.py`: 세션/헤더/GET JSON
- `product.py`: screen/header API 호출
- `parser.py`: 상품 master, snapshot, ranking, option, 체결/호가 파싱
- `collector.py`: 한 상품을 최종 payload로 조립
- `pipeline.py`: FEEDIT BasePlatformPipeline 연결

주의: 로그인 우회/캡차 우회/고빈도 호출을 구현하지 않는다. 운영에서는 요청 간격과 실패 backoff를 둔다.
