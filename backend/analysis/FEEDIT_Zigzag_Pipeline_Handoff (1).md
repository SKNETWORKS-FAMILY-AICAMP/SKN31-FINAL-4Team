# FEEDIT Zigzag Collection Pipeline — 작업 인수인계 문서

작성 목적: 지금까지 진행한 **지그재그(Zigzag) 랭킹 수집 → 상세정보 확장 → S3 Raw 저장 → CrawlRun / RawDocument 연계** 작업을 다른 코딩 에이전트가 그대로 이어서 개발할 수 있도록 현재 구조, 확정된 설계, 구현 상태, 테스트 방법, 남은 작업을 정리한다.

---

## 1. 프로젝트 전제

- 프로젝트: **FEEDIT**
- 저장소: `SKN31-FINAL-4Team`
- 백엔드 루트 예시: `C:\SKN31-FINAL-4Team\backend`
- Django 기반
- 주요 모듈:
  - `apps.core`
  - `apps.dashboard`
  - `collection.common`
  - `collection.zigzag`
  - 이후 `analysis.normalization`

### 관리자 앱 네이밍
커스텀 관리자 앱은 전부 `dashboard`로 통일한다.

사용:
- `apps.dashboard`
- `dashboard:`
- `templates/dashboard/...`
- `static/dashboard/...`

사용 금지:
- `admin_dashboard`

---

## 2. 현재 목표 아키텍처

```text
CrawlTarget
    ↓
collection.common.runner.run_crawl_target()
    ↓
CrawlRun 생성 (RUNNING)
    ↓
source.code 기준 플랫폼 파이프라인 선택
    ↓
ZigzagPipeline.run_target()
    ↓
ZigzagPipeline.collect()
    ↓
ZigzagCollector
    ├─ 랭킹 GraphQL 수집
    └─ 필요 시 상품 상세 수집
    ↓
BasePlatformPipeline.run_target()
    ↓
S3Storage.upload_raw_json()
    ↓
S3 raw JSON 저장 + exists 검증
    ↓
runner.py
    ├─ RawDocument 생성
    ├─ CrawlRun 상태 완료
    └─ CrawlTarget last/next 갱신
```

정규화는 수집과 분리한다.

```text
RawDocument
    ↓
S3 JSON
    ↓
analysis/normalization/zigzag.py
    ↓
Product / ProductSource / Snapshot / Attribute ...
```

현재 수집 파이프라인에는 **OCR / LLM / 사전 매칭 / 정규화 로직을 넣지 않는다.**

---

## 3. 현재 DB 전제

### Source

현재 DB 실제 Zigzag Source:

```text
id=20
code="zigzag"
name="지그재그"
```

따라서 조회는 case-insensitive 권장:

```python
Source.objects.get(code__iexact="zigzag")
```

또는:

```python
CrawlTarget.objects.filter(
    source__code__iexact="zigzag"
)
```

### CrawlTarget

현재 확인된 Zigzag target:

```text
61 zigzag [여성>상의>전체]   RANKING {'limit': 100} True
62 zigzag [여성>아우터>전체] RANKING {'limit': 100} True
63 zigzag [여성>팬츠>전체]   RANKING {'limit': 100} True
65 zigzag [여성>원피스>전체] RANKING {'limit': 100} True
```

관리자에서 target URL을 이미 등록한다.

예:

```text
https://zigzag.kr/categories/-1?middle_category_id=507&sort=200
```

따라서 `params["category_id"]`를 중복으로 넣지 않고 URL에서 자동 추출한다.

우선순위:

```text
params.category_id
    ↓ 없으면
target_url middle_category_id / category_id
```

sort도:

```text
params.sort
    ↓ 없으면
target_url sort
    ↓ 없으면
DEFAULT_SORT
```

### CrawlRun

핵심 상태:
- `PENDING`
- `RUNNING`
- `SUCCESS`
- `PARTIAL_SUCCESS`
- `FAILED`
- `CANCELLED`

핵심 카운트:
- `discovered_count`
- `success_count`
- `failure_count`

### RawDocument

수집 성공 후 생성하며 정규화 초기 상태는:

```text
PENDING
```

---

## 4. `collection/common/pipeline.py`

현재 `BasePlatformPipeline`은 생성 시 `bucket`이 필수다.

잘못된 예:

```python
pipeline = ZigzagPipeline()
```

에러:

```text
TypeError:
BasePlatformPipeline.__init__() missing 1 required keyword-only argument: 'bucket'
```

정상:

```python
pipeline = ZigzagPipeline(
    bucket="feedit-data-team4",
    region_name="ap-northeast-2",
)
```

`run_target()` 역할:

```text
collect()
→ payload 획득
→ S3Storage.upload_raw_json()
→ exists() 검증
→ S3 메타 + counts 반환
```

따라서 플랫폼별 pipeline에서 직접 S3 저장 로직을 다시 만들지 않는다.

---

## 5. `collection/common/s3.py`

버킷:

```text
feedit-data-team4
```

리전:

```text
ap-northeast-2
```

주요 메서드:
- `build_raw_key()`
- `upload_json()`
- `upload_raw_json()`
- `exists()`

S3 key 패턴:

```text
raw/{source}/{entity_type}/{YYYY/MM/DD}/{source_entity_id}/{timestamp}.json
```

예:

```text
s3://feedit-data-team4/raw/zigzag/ranking/...
```

---

## 6. Zigzag 랭킹 수집 방식

과거 Playwright 기반 랭킹 스크롤 방식은 현재 구조에서 사용하지 않는다.

현재 기준:
- 랭킹: **GraphQL**
- 상세: 상품 상세 페이지 GET + `__NEXT_DATA__`
- DB 직접 Product 저장: 하지 않음
- Raw를 S3에 먼저 저장
- 정규화는 이후 별도 단계

---

## 7. Zigzag GraphQL

Endpoint:

```text
https://api.zigzag.kr/api/2/graphql
```

Operation:

```text
GetSearchResult
```

주요 상수:

```text
DEFAULT_PAGE_ID = "web_srp_clp_category"
DEFAULT_SORT = "200"
DEFAULT_LIMIT = 100
GOODS_CARD_TYPE = "UX_GOODS_CARD_ITEM"
```

GraphQL 카드에서 확보:
- goods_id
- catalog_product_id
- shop_id
- shop_name
- is_brand
- title
- product_url
- image_url
- price
- final_price
- discount_rate
- review_score
- display_review_count
- sellable_status
- is_ad
- managed_category_list

랭킹 collector 단독 테스트는 이미 성공했다.

---

## 8. Ranking item 표준 형태

```python
{
    "rank": 1,
    "source_product_id": "...",
    "catalog_product_id": "...",
    "product_name": "...",
    "store_id": "...",
    "store_name": "...",
    "is_brand": False,
    "category_id": "...",
    "category_name": "...",
    "category_path": [...],
    "product_url": "...",
    "thumbnail_url": "...",
    "regular_price": ...,
    "sale_price": ...,
    "discount_rate": ...,
    "review_score": ...,
    "review_count": ...,
    "sellable_status": ...,
    "is_ad": False,
}
```

---

## 9. 상세 수집 확인 결과

상품 상세 URL:

```text
https://store.zigzag.kr/catalog/products/{product_id}
```

실제 테스트 상품:

```text
171494656
[made] 모노 체크 스웨이드 자켓
```

HTTP GET 결과:

```text
STATUS: 200
LENGTH: 120693
__NEXT_DATA__ 존재
description 존재
```

Next.js 데이터 경로:

```text
root.props.pageProps.dehydratedState.queries[].state.data.product
```

상품 description:

```text
product.description
```

상품 이미지:

```text
product.product_image_list
```

가격 상세:

```text
product.product_price
```

고정 index만 신뢰하지 말고 `queries`를 순회해서:

```python
str(candidate.get("id")) == str(product_id)
```

인 product를 선택하는 것이 안전하다.

---

## 10. description 특성

상품마다 다르다.

### 텍스트가 있는 상품
유의미한 예:
- COLOR
- FABRIC
- SIZE
- MODEL SIZE & FITTING
- 소재 설명
- 핏
- 디테일
- 계절감

### 이미지 중심 상품
실제 테스트:

```text
TEXT LENGTH: 0
DETAIL IMAGES: 7
PRODUCT IMAGES: 6
```

이는 실패가 아니다.

`description_html` 내부가 거의 `<img>` 태그로만 이루어진 상품이다.

---

## 11. OCR 방침

EasyOCR 테스트에서는 상세 이미지에서 실제 패션 속성이 추출되는 것을 확인했다.

예:
- `MONO CHECKERED SUEDE JACKET`
- 스웨이드
- 체크
- POLY
- 사이즈 정보
- 두께감
- 신축성
- 계절감

하지만 **OCR은 지금 수집 단계에 붙이지 않는다.**

추후:

```text
description_text 있으면
    → 텍스트 분석

description_text 없거나 부족하면
    → detail_image_urls OCR

둘 다 있으면
    → 합쳐서 분석
```

---

## 12. 상세 Raw JSON 설계

각 ranking item에:

```json
{
  "detail": {
    "collected": true,
    "source_product_id": "171494656",
    "description_html": "<p><img ...></p>",
    "description_text": "",
    "detail_image_urls": [
      "https://imgb.a-bly.com/data/editor/....jpg"
    ],
    "product_image_urls": [
      "https://cf.product-image.s.zigzag.kr/..."
    ],
    "sales_status": "ON_SALE",
    "display_status": "VISIBLE",
    "category_key": "fashion_clothing"
  }
}
```

원칙:
- `description_html` 원본 보존
- `description_text`도 같이 저장
- OCR하지 않음
- 상세 이미지 URL 저장
- 일반 상품 이미지도 별도 저장

---

## 13. ZigzagCollector에 필요한 메서드

```python
class ZigzagCollector:

    def collect_category_ranking(...):
        ...

    def collect_product_detail(
        self,
        source_product_id: str,
    ) -> dict:
        ...

    def enrich_ranking_details(
        self,
        items: list[dict],
        *,
        detail_limit: int | None = None,
    ) -> dict:
        ...
```

`collect_product_detail()`은:
1. 상품 상세 GET
2. `__NEXT_DATA__` 추출
3. JSON parse
4. product 탐색
5. `description_html`
6. BeautifulSoup으로 `description_text`
7. description 내부 `<img src>` → `detail_image_urls`
8. `product_image_list` → `product_image_urls`
를 반환한다.

필요 패키지:

```powershell
uv pip install beautifulsoup4
```

---

## 14. `enrich_ranking_details()` 원칙

```text
TOP100 item
    ↓
source_product_id
    ↓
collect_product_detail()
    ↓
item["detail"]에 병합
```

상세 하나가 실패해도 전체 ranking을 실패시키지 않는다.

실패 예:

```python
{
    "detail": {
        "collected": False,
        "skipped": False,
        "error_type": "Timeout",
        "error": "...",
    }
}
```

`detail_limit` 지원:

```text
detail_limit=3
```

이면 TOP100은 그대로 수집하고 상위 3개만 상세 조회한다.

---

## 15. ZigzagPipeline 최종 설계

파일:

```text
collection/zigzag/pipeline.py
```

핵심:
- `class ZigzagPipeline(BasePlatformPipeline)`
- `SOURCE = "ZIGZAG"`
- 현재 `RANKING`만 지원
- target URL에서 category/sort 자동 parse
- GraphQL ranking TOP100
- optional detail enrichment
- payload `schema_version = "2.1"`
- `raw_pages` 포함

중요:
CrawlRun의 counts는 **랭킹 기준**으로 유지한다.

예:

```text
ranking_count = 100
detail_success_count = 97
detail_failure_count = 3
```

이면 detail 일부 실패를 payload에서 따로 기록한다.

```python
payload["ranking"]["detail_success_count"]
payload["ranking"]["detail_failure_count"]
```

---

## 16. Target URL 파싱

예:

```text
https://zigzag.kr/categories/-1?middle_category_id=507&sort=200
```

결과:

```python
category_id = "507"
sort = "200"
```

사용:

```python
from urllib.parse import parse_qs, urlparse
```

이 설계는 유지한다.

---

## 17. 권장 CrawlTarget params

기본:

```json
{
  "limit": 100
}
```

상세 명시:

```json
{
  "limit": 100,
  "include_detail": true,
  "detail_limit": 100
}
```

테스트:

```json
{
  "limit": 100,
  "include_detail": true,
  "detail_limit": 3
}
```

---

## 18. `collection/common/runner.py`

목표:

```text
CrawlTarget
→ CrawlRun
→ ZigzagPipeline
→ S3
→ RawDocument
→ CrawlRun 완료
```

핵심 함수:

```python
run_crawl_target(
    *,
    target_id: int,
    bucket: str,
    region_name: str | None = None,
    run_type=...
) -> dict
```

플랫폼 router는 반드시 source code를 normalize:

```python
source_code = (source_code or "").upper().strip()

if source_code == "ZIGZAG":
    return ZigzagPipeline(
        bucket=bucket,
        region_name=region_name,
    )
```

DB의 `zigzag` 소문자와 pipeline의 `ZIGZAG` 대문자를 안전하게 연결한다.

---

## 19. 예상 성공 결과

```python
{
    "ok": True,
    "target_id": 61,
    "crawl_run_id": ...,
    "raw_document_id": ...,
    "source": "zigzag",
    "status": "SUCCESS",
    "counts": {
        "discovered": 100,
        "success": 100,
        "failure": 0,
    },
    "s3": {
        "bucket": "feedit-data-team4",
        "key": "raw/zigzag/ranking/...",
        "uri": "s3://feedit-data-team4/raw/zigzag/ranking/...",
        "verified": True,
    },
}
```

---

## 20. 현재 완료 상태

완료:
- GraphQL ranking collector 단독 테스트
- ranking 정상 수집
- URL category 자동 추출 설계
- 상세 page GET 성공
- `__NEXT_DATA__` 확인
- `product.description` 확인
- `product.product_image_list` 확인
- description 내부 detail image URL 추출 성공
- OCR 가능성 검증
- S3/runner 구조 설계

아직 실제로 끝내야 함:
- `collector.py`에 detail 메서드 최종 통합 확인
- `pipeline.py` 최종본 실제 반영 확인
- target 61 `detail_limit=3` 실행
- S3 JSON 확인
- RawDocument 확인
- `detail_limit=100`
- 61/62/63/65 전체 실행
- Celery 연결
- Dashboard 실행 버튼 연결
- 이후 normalization

---

## 21. 마지막 발생 오류

Django shell에서:

```text
OperationalError: the connection is closed
```

코드 자체보다 DB connection/session 문제 가능성이 높다.

우선:

```powershell
exit()
python manage.py shell
```

새 shell에서:

```python
from django.db import connection

connection.close()
connection.ensure_connection()

print(connection.is_usable())
```

`True`면 계속.

새 shell에서도 실패하면:
- RDS
- SSM tunnel
- DB host/port
- AWS session
을 확인한다.

---

## 22. 다음 테스트: target 61 params

```python
from apps.core.models import CrawlTarget

target = CrawlTarget.objects.get(
    id=61
)

target.params = {
    **(target.params or {}),
    "include_detail": True,
    "detail_limit": 3,
}

target.save(
    update_fields=[
        "params",
        "updated_at",
    ]
)

print(target.target_url)
print(target.params)
```

---

## 23. Pipeline 단독 테스트

```python
from collection.zigzag.pipeline import ZigzagPipeline

pipeline = ZigzagPipeline(
    bucket="feedit-data-team4",
    region_name="ap-northeast-2",
)

result = pipeline.collect(
    target_type="RANKING",
    target_url=(
        "https://zigzag.kr/categories/-1?"
        "middle_category_id=507&sort=200"
    ),
    params={
        "limit": 100,
        "include_detail": True,
        "detail_limit": 3,
    },
)

print(result["platform_data"])
```

예상:

```python
{
    "category_id": "507",
    "ranking_count": 100,
    "include_detail": True,
    "detail_success_count": 3,
    "detail_failure_count": 0,
}
```

---

## 24. S3 직접 테스트

```python
from collection.zigzag.pipeline import ZigzagPipeline

pipeline = ZigzagPipeline(
    bucket="feedit-data-team4",
    region_name="ap-northeast-2",
)

result = pipeline.run_target(
    target_type="RANKING",
    target_url=(
        "https://zigzag.kr/categories/-1?"
        "middle_category_id=507&sort=200"
    ),
    params={
        "limit": 100,
        "include_detail": True,
        "detail_limit": 3,
    },
)

print(result)
```

확인:

```text
verified = True
```

---

## 25. CrawlTarget 기반 실제 실행

```python
from collection.common.runner import run_crawl_target

result = run_crawl_target(
    target_id=61,
    bucket="feedit-data-team4",
    region_name="ap-northeast-2",
)

print(result)
```

---

## 26. RawDocument 확인

```python
from apps.core.models import RawDocument

raw = RawDocument.objects.get(
    id=result["raw_document_id"]
)

print(raw.id)
print(raw.document_type)
print(raw.s3_uri)
print(raw.normalization_status)
```

목표:

```text
RANKING
s3://feedit-data-team4/raw/zigzag/ranking/...
PENDING
```

---

## 27. S3 JSON 필수 확인

detail 수집 대상 item:

```json
{
  "detail": {
    "collected": true,
    "description_html": "...",
    "description_text": "...",
    "detail_image_urls": [...],
    "product_image_urls": [...]
  }
}
```

이미지형 상품은:

```json
"description_text": ""
```

이어도 정상이다.

`detail_image_urls`가 있으면 이후 OCR 대상이 된다.

---

## 28. detail_limit=3 성공 후

```python
target = CrawlTarget.objects.get(id=61)

target.params = {
    **(target.params or {}),
    "include_detail": True,
    "detail_limit": 100,
}

target.save(
    update_fields=[
        "params",
        "updated_at",
    ]
)
```

---

## 29. 전체 Zigzag target 배치

```python
from apps.core.models import CrawlTarget
from collection.common.runner import run_crawl_target

BUCKET = "feedit-data-team4"
REGION = "ap-northeast-2"

targets = (
    CrawlTarget.objects
    .filter(
        source__code__iexact="zigzag",
        target_type="RANKING",
        is_active=True,
    )
    .order_by("id")
)

for target in targets:

    print()
    print("=" * 80)
    print(target.id, target.name)

    try:
        result = run_crawl_target(
            target_id=target.id,
            bucket=BUCKET,
            region_name=REGION,
        )

        print("SUCCESS")
        print("RUN:", result["crawl_run_id"])
        print("RAW:", result["raw_document_id"])
        print("COUNTS:", result["counts"])
        print("S3:", result["s3"]["uri"])

    except Exception as exc:
        print(
            "FAILED |",
            type(exc).__name__,
            "|",
            exc,
        )
```

---

## 30. 이후 Celery

동기 runner가 완전히 성공한 뒤:

```text
Dashboard ▶
    ↓
Celery task
    ↓
run_crawl_target()
```

기존 프로젝트에는 Celery가 있다.

실제 `apps/core/tasks.py`를 먼저 확인한 뒤 연결할 것.

과거 서버 오류:

```text
ProfileNotFound('The config profile (feedit) could not be found')
```

AWS credential/profile 방식은 로컬/EC2 환경별로 확인 필요.

---

## 31. 이후 Dashboard

collection target의 실행 버튼:

```text
target.id
    ↓
Celery.delay(...)
    ↓
run_crawl_target()
```

namespace는 반드시:

```text
dashboard:
```

---

## 32. 이후 정규화

수집 완료 후:

```text
RawDocument
normalization_status=PENDING
    ↓
S3 JSON
    ↓
Zigzag Normalizer
```

입력:
- ranking
- product name
- store/shop
- category
- price
- rank
- review
- description_text
- detail_image_urls
- product_image_urls

---

## 33. Brand 정규화 관련 확정사항

Brand 실제 필드:
- `brand_code`
- `name`
- `english_name`

사용 금지:
- `code`
- `name_en`

resolve 방향:

```python
Brand.objects.filter(
    name=clean_name
).first()
```

없으면:

```python
Brand.objects.filter(
    english_name__iexact=clean_name
).first()
```

fallback:

```python
Brand.objects.filter(
    brand_code="BRAND_NON_BRAND_SHOP"
).first()
```

`BRAND_NON_BRAND_SHOP`:
- 정식 브랜드가 아닌 쇼핑몰/보세/셀러 fallback
- 향후 브랜드 트렌드 확산 분석을 위해 유지

---

## 34. 향후 OCR / 분석

```text
description_text
    ↓
텍스트 정규화

detail_image_urls
    ↓
OCR
    ↓
OCR text

description_text + OCR text
    ↓
FEEDIT Dictionary
    ↓
Attribute extraction
```

추출 후보:
- ITEM
- STYLE
- MATERIAL
- COLOR
- DETAIL
- FIT
- SIZE
- SEASON
- TPO

---

## 35. 중요한 개발 원칙

1. **Raw 원본 보존**
   - GraphQL raw_pages
   - description_html
   - image URLs

2. **수집과 분석 분리**
   - OCR / LLM / dictionary matching / normalization은 수집 코드에 넣지 않음

3. **상세 실패가 ranking 실패를 의미하지 않음**
   - ranking 100 성공, detail 97/3 실패 가능
   - detail counts 별도 기록

4. **category_id 중복 등록 금지**
   - target URL에서 자동 추출

5. **Source 대소문자 주의**
   - DB `zigzag`
   - Pipeline `ZIGZAG`
   - router/query는 case-insensitive 처리

---

## 36. 다음 에이전트가 가장 먼저 할 일

### STEP 1
DB 연결 복구.

### STEP 2
아래 실제 파일을 직접 열어 현재 저장된 코드 확인:

```text
collection/zigzag/constants.py
collection/zigzag/client.py
collection/zigzag/collector.py
collection/zigzag/pipeline.py
collection/common/pipeline.py
collection/common/s3.py
collection/common/runner.py
apps/core/models.py
```

특히 `collector.py`에:
- `collect_product_detail`
- `enrich_ranking_details`

가 실제 저장되어 있는지 확인.

### STEP 3
target 61:
```json
{
  "limit": 100,
  "include_detail": true,
  "detail_limit": 3
}
```

### STEP 4
`run_crawl_target(target_id=61)` 실행.

### STEP 5
S3 JSON에서:
```text
ranking.items[].detail.description_html
ranking.items[].detail.description_text
ranking.items[].detail.detail_image_urls
ranking.items[].detail.product_image_urls
```
확인.

### STEP 6
RawDocument:
```text
normalization_status=PENDING
```
확인.

### STEP 7
`detail_limit=100`.

관찰:
- 총 수행시간
- timeout
- 상세 실패율
- rate limit
- S3 JSON 크기

### STEP 8
61 / 62 / 63 / 65 전체 실행.

### STEP 9
Celery 연결.

### STEP 10
Dashboard ▶ 버튼 연결.

### STEP 11
정규화 시작.

---

## 37. 잠재 이슈

### 상세 100개 요청
카테고리 하나당:
- GraphQL pagination
- 상세 최대 100 GET

4개 카테고리면 약 400 상세 GET 가능.

향후 필요 시:
- retry
- timeout 조절
- sleep
- concurrency 제한
- 캐싱
- 이전 상세 재사용

을 검토.

먼저 순차 처리로 안정성 검증.

### S3 JSON 크기
현재 구조:

```text
TOP100
+ raw_pages
+ description_html 100개
```

상세 HTML이 매우 크므로 파일이 커질 수 있다.

먼저 실제 크기 측정 후 필요하면:
- ranking/detail 분리
- gzip
- detail 별도 S3 object

검토.

현재 단계에서는 미리 분리하지 않는다.

### Next.js 데이터 구조 변경 가능성
`queries[0]`만 고정으로 쓰지 말고 queries 순회 + product id match 유지.

---

## 38. 현재 한 줄 요약

현재 FEEDIT Zigzag 파이프라인은:

```text
CrawlTarget URL
→ category 자동 추출
→ Zigzag GraphQL TOP100
→ 상품별 상세 __NEXT_DATA__
→ description HTML / detail image URL 확보
→ S3 Raw JSON
→ RawDocument PENDING
```

구조로 확정되어 있다.

지금 가장 중요한 다음 작업은:

```text
DB 연결 복구
→ collector/pipeline 실제 통합 상태 확인
→ target 61 detail_limit=3
→ S3 + RawDocument까지 성공
```

이다.

OCR / 사전 매칭 / 속성 추출은 그 이후 정규화 단계에서 진행한다.
