/* GET /api/discount · /api/resale · /api/lifecycle · /api/price-history · /api/sentiment · /api/search
 *
 * 트렌드 분석의 할인률 변화 · 리세일 시세 지수 · 수명주기 탭이 부르는 창구.
 * 세 주소를 **함수 하나**로 받는다 — 버셀 Hobby 요금제는 함수 개수가 12개로 묶여 있어
 * 탭마다 파일을 따로 두면 배포가 막힌다.
 *
 * ★ 계산은 Django(backend/apps/api/views.py)가 한다. 여기서는 그대로 넘기기만 한다.
 *   RDS 의 스냅샷 표를 여러 번 훑어 집계해야 해서, pg 직결로 똑같이 짜 두면
 *   화면과 백엔드가 서로 다른 숫자를 말하게 된다. 그래서 BACKEND_API_URL 이 필수다.
 *
 * 필요한 버셀 환경변수:
 *   BACKEND_API_URL    Django 주소 (예: https://feedit-official.duckdns.org/api)
 *   BACKEND_API_TOKEN  서버 .env 의 FEEDIT_API_TOKEN 과 같은 값
 */

import { viaBackend } from './_lib/db.js';
import { failed } from './_lib/reply.js';
/* 데이터 API (비즈니스 요금제 · 2026-10-03) — 키 확인은 Django 가 한다. 캐시하지 않는다. */
import { relayData } from './_lib/data_relay.js';

/* ★ 2026-09-22 — 'search'(검색 지표)를 여기 얹는다.
     처음엔 api/search.js 로 따로 뒀는데, 그러면 함수가 12개(한도)에 딱 차서
     다음에 주소를 하나만 더 만들어도 배포가 막힌다.
     이 파일이 애초에 그 문제 때문에 생긴 창구이므로 같은 방식으로 받는다. */
const ALLOWED = new Set(['discount', 'resale', 'lifecycle', 'price-history', 'sentiment', 'search']);

export default async function handler(req, res) {
  const url = new URL(req.url, 'http://x');
  // 파일 이름 [kind] 로 들어온 값 — 쿼리에도 kind 로 붙어 오므로 경로에서 직접 읽는다.
  const kind = url.pathname.replace(/^\/api\//, '').split('/')[0];
  /* ★ 지표 쿼리 주소들과 달리 API 키로 오고, 엣지에 캐시하면 안 된다 — 따로 넘긴다 */
  if (kind === 'data') return relayData(req, res, url);
  if (!ALLOWED.has(kind)) {
    res.statusCode = 404;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    return res.end(JSON.stringify({ status: 'error', reason: `없는 주소입니다: /api/${kind}`, data: null }));
  }

  const qs = new URLSearchParams(url.search);
  // Vercel은 /api/discount/facets를 이 기존 함수로 재작성한다.
  // 재작성 전/후 어느 URL이 req.url에 남아도 같은 Django 경로로 보낸다.
  const discountFacets = url.pathname === '/api/discount/facets'
    || (kind === 'discount' && qs.get('__facets') === '1');
  // /api/resale/products 역시 Vercel의 단일 세그먼트 함수([kind].js)가
  // 직접 받을 수 없으므로 vercel.json에서 /api/resale로 재작성한다.
  const resaleProducts = url.pathname === '/api/resale/products'
    || (kind === 'resale' && qs.get('__products') === '1');
  // 동적 경로 [kind]가 쿼리에 붙을 수 있지만, 할인률 후보의 kind는 실제 종류 필터다.
  // 경로 매개변수만 제거하고 사용자가 고른 종류는 Django로 전달한다.
  const nestedRoute = discountFacets || resaleProducts;
  const kindValues = nestedRoute ? qs.getAll('kind') : [];
  qs.delete('kind');
  if (nestedRoute) {
    const routeKind = kindValues.indexOf(kind);
    if (routeKind >= 0) kindValues.splice(routeKind, 1);
    kindValues.forEach((value) => qs.append('kind', value));
  }
  qs.delete('__facets');
  qs.delete('__products');
  const q = qs.toString();
  const backendPath = discountFacets
    ? '/discount/facets'
    : resaleProducts
      ? '/resale/products'
      : `/${kind}`;
  /* 리세일 집계와 상품 후보는 스냅샷을 많이 훑는다. 기본 8초는 정상 집계도
     끊어 버려 화면에 "This operation was aborted"가 나타났다. */
  const relayed = await viaBackend(backendPath + (q ? `?${q}` : ''),
    kind === 'resale' ? 25000 : 8000);
  if (!relayed) {
    return failed(
      res,
      'BACKEND_API_URL 이 설정돼 있지 않습니다. 이 지표는 Django API 를 거쳐야 계산됩니다 (버셀 환경변수).',
    );
  }
  res.statusCode = 200;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  /* ★ 2026-09-22 — 성공한 응답만 캐시한다.
       viaBackend 는 실패해도 {status:'error'} 객체를 돌려주는데, 그것도 truthy 라
       예전에는 이 줄을 그대로 타서 **에러가 엣지에 박혔다.**
       실제로 백엔드 배포 전에 받은 404 가 30분간 남아, 배포를 끝내고도
       화면이 계속 404 를 봤다. 고쳐 놓지 않으면 배포할 때마다 같은 일이 난다.
       (empty 도 캐시하지 않는다 — 적재가 막 끝난 직후일 수 있다.) */
  const cacheable = relayed && relayed.status === 'ok';
  res.setHeader('Cache-Control', !cacheable
    ? 'no-store'
    : discountFacets
      ? 's-maxage=120, stale-while-revalidate=600'
      : resaleProducts
        ? 's-maxage=60, stale-while-revalidate=300'
      /* 검색량은 하루 단위로만 바뀐다 — 더 길게 캐시해도 된다. */
      : kind === 'search'
        ? 's-maxage=1800, stale-while-revalidate=3600'
        : 's-maxage=300, stale-while-revalidate=600');
  return res.end(JSON.stringify(relayed));
}
