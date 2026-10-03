# 데이터 API — 비즈니스 요금제

기준일: 2026-10-03 · 코드: `backend/apps/api/data_api.py` · `data_api_views.py` · `frontend/api/_lib/data_relay.js`

FEEDiT 의 트렌드 지표를 사내 시스템 · 엑셀 · BI 도구에서 직접 받아 가는 길입니다.
화면(트렌드 분석)과 **같은 계산 결과**를 JSON 으로 돌려줍니다. 숫자를 새로 만들지 않습니다.

> 베타 동안(`FEEDIT_PUBLIC_BETA` 켜짐)에는 닫혀 있습니다.
> 키를 만들 수 없고, 지표 주소는 `403 BETA` 로 답합니다.

## 키

- 비즈니스 요금제 또는 운영 계정만 만들 수 있습니다. 계정 메뉴 › **데이터 API**.
- 계정당 살아 있는 키는 5개까지입니다.
- 키 원문(`fdk_…`)은 **만든 직후 한 번만** 보입니다. 서버에는 해시만 남습니다.
- 요금제가 비즈니스에서 내려가면 키는 지워지지 않고 멈춥니다(`403 PLAN`). 다시 올라가면 그대로 씁니다.
- 새어 나간 키는 같은 창에서 바로 폐기합니다. 폐기는 요금제와 상관없이 언제나 됩니다.

## 부르는 법

```bash
curl -G "https://<서비스 주소>/api/data/trend" \
  -H "Authorization: Bearer fdk_…" \
  --data-urlencode "term=발레코어"
```

`Authorization: Bearer` 대신 `X-API-Key: fdk_…` 머리글도 받습니다. GET 만 받습니다.

| 지표 | 주소 | 내용 | 받는 값 |
| --- | --- | --- | --- |
| 목록 | `/api/data` | 쓸 수 있는 지표 · 한도 | — |
| trend | `/api/data/trend` | 언급량 · 트렌드 온도 추이 | `term` (필수) · `source` |
| search | `/api/data/search` | 검색량 · 검색 추이 · 지역 | `term` (필수) |
| assoc | `/api/data/assoc` | 연관어 | `term` (필수) · `sort=pmi\|lift\|count` |
| sentiment | `/api/data/sentiment` | 긍부정(구매 의향) | `term` (필수) · `subject` |
| lifecycle | `/api/data/lifecycle` | 수명주기 | `term` 또는 `style` · `kind` · `brand` · `item` |
| discount | `/api/data/discount` | 할인률 변화 | `style` · `kind` · `brand` · `item` 또는 `source_id` |
| resale | `/api/data/resale` | 리세일 지수 | `style` · `kind` · `brand` · `item` 또는 `product_id` · `source_id` · `days` |
| terms | `/api/data/terms` | 지표가 있는 용어 목록 | `rank=hot` (선택) |

응답 모양은 화면이 받는 `/api/<지표>` 와 같습니다 — `{"status": "ok" | "empty" | "error", "data": …}`.
`empty` 는 "그 말의 지표가 아직 없다" 는 뜻이며 오류가 아닙니다.

상품 목록 · 사전 통째 받기는 내주지 않습니다.

## 한도와 오류

| 상태 | `code` | 뜻 |
| --- | --- | --- |
| 401 | `NO_KEY` · `INVALID_KEY` | 키가 없거나 틀렸거나 폐기됐다 |
| 403 | `PLAN` | 지금 요금제가 비즈니스가 아니다 |
| 403 | `BETA` | 아직 베타 — 열리지 않았다 |
| 404 | `NO_METRIC` | 없는 지표 (횟수를 쓰지 않는다) |
| 429 | `RATE_LIMITED` | 키 하나당 분당 한도(기본 60) — `Retry-After: 60` |
| 429 | `DAILY_LIMIT` | 계정당 하루 한도(기본 10000) — 한국시간 0시에 다시 열린다 |

응답 머리글 `X-RateLimit-Limit` · `X-RateLimit-Remaining` 이 하루 한도와 남은 횟수입니다.
응답은 어디에도 캐시되지 않습니다(`Cache-Control: no-store`). 같은 값을 자주 쓰면 받는 쪽에서 보관해 주세요.

## 구조

```text
밖의 시스템 ─(Bearer fdk_…)─▶ 버셀 /api/data/<지표> ([kind].js → _lib/data_relay.js)
                               ─(X-FEEDiT-Token + 키 그대로)─▶ Django /api/data/<지표>
                               ─ 키 확인 · 요금제 · 한도 ─▶ views.py 의 같은 함수
```

- 버셀 함수 수(Hobby 한도 12)를 늘리지 않으려고 `[kind].js` 가 받아 넘깁니다. `vercel.json` 이 `/api/data/:metric` 을 바꿔 넣습니다.
- 키 · 사용량은 `app_user.profile_metadata` 의 `data_api_keys` · `data_api_usage` 에 둡니다. 새 표가 없습니다.
- 분당 한도는 API 프로세스 메모리로 셉니다 — gunicorn 워커마다 따로 세므로 대략적인 상한입니다. 하루 한도는 DB 로 정확히 셉니다.
