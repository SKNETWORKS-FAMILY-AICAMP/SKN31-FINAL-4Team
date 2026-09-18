# FEEDIT term metrics package

배치 위치:

```text
backend/
└─ analysis/
   └─ metrics/
      ├─ __init__.py
      ├─ common.py
      ├─ reaction.py
      ├─ commerce.py
      ├─ content.py
      ├─ aggregate.py
      └─ pipeline.py
```

## 전제

`TermMetricDaily`에 다음 reaction 필드가 migration 되어 있어야 한다.

- neutral_count
- question_count
- purchase_count
- experience_count
- praise_count
- critique_count
- chitchat_count
- positive_rate
- neutral_rate
- negative_rate
- question_rate
- purchase_rate
- experience_rate
- praise_rate
- critique_rate

기존 필드:
- positive_count
- negative_count
- raw_count
- mention_count
- document_count
- content_count
- creator_count
- log_count
- percentile
- level
- ma7
- ma28
- momentum
- trend_temperature
- metrics

## 핵심 설계

- `reaction.py`: `analysis.text_document` JSON mention을 실제 term 신호로 사용.
- COMMENT는 intent/polarity까지 실제 count/rate 저장.
- `commerce.py`: `ProductSourceSnapshot`에서 상품 노출/랭킹/반응 보조 신호.
- `content.py`: `ContentItem/ContentSnapshot`에서 콘텐츠/크리에이터/engagement 보조 신호.
- `aggregate.py`: source별 normalize → source=NULL(ALL) → MA/Momentum/Temperature.
- `metrics` JSON에는 각 계층의 raw detail을 보존.

## 하루 실행

```python
from datetime import date
from analysis.metrics import run_term_metric_pipeline

result = run_term_metric_pipeline(
    date(2026, 9, 14)
)

print(result)
```

## 기간 실행

```python
from datetime import date
from analysis.metrics import run_term_metric_range

results = run_term_metric_range(
    date(2026, 8, 1),
    date(2026, 9, 14),
)
```

## 처음 테스트할 때

commerce/content 모델 필드가 로컬 최신 모델과 다르면 일단 reaction만 검증 가능:

```python
run_term_metric_pipeline(
    date(2026, 9, 14),
    commerce=False,
    content=False,
    reaction=True,
)
```

그 다음 commerce/content를 각각 켜서 검증한다.

## 주의

Commerce term-product 연결은 현재 다음 순서의 실용 fallback을 사용한다.

1. `Product.item_term`
2. `ProductSource.attributes.tags`
3. `normalized_name/source_name` 문자열 포함

향후 ProductAttribute 또는 ontology relation이 완전히 정규화되면
`commerce._product_term_filter()`만 교체하면 된다.

Content term 연결도 실제 핵심 term mention은 `TextDocument`를 사용하고,
`content.py`는 title/description과 snapshot engagement를 보조 신호로 사용한다.
