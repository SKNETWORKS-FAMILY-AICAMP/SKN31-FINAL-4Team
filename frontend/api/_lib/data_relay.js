/* GET /api/data · /api/data/<지표> — 비즈니스 요금제의 데이터 API 를 Django 로 넘긴다 (2026-10-03).
 *
 * 밖의 시스템(엑셀 · BI · 사내 대시보드)이 API 키(Authorization: Bearer fdk_…)로 부른다.
 * 키 확인 · 요금제 · 하루 한도는 전부 Django(backend/apps/api/data_api_views.py)가 한다.
 * 여기서는 길만 낸다 — 판단하지 않는다.
 *
 * ★ 버셀 Hobby 는 함수가 12개까지라 새 파일을 만들지 않고 [kind].js 가 이 함수를 부른다.
 *   /api/data/<지표> 는 vercel.json 이 /api/data?__metric=<지표> 로 바꿔 넣는다.
 * ★ 캐시하지 않는다(no-store). 다른 쿼리 지표 주소(/api/trend 등)는 엣지에 5분 캐시되지만,
 *   여기는 키마다 허락이 다르다 — 키 없이 온 요청에 남의 응답이 나가면 안 된다.
 * ★ 상태 숫자를 그대로 돌려준다(401 · 403 · 429). 밖의 프로그램은 숫자로 판단한다.
 */
import { backendBase, backendToken } from './db.js';
import { clientIp } from './client_ip.js';

const METRIC_RE = /^[a-z_]{1,32}$/;

export async function relayData(req, res, url) {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  if (String(req.method || 'GET').toUpperCase() !== 'GET') {
    res.statusCode = 405;
    return res.end(JSON.stringify({ status:'error', reason:'GET 만 받습니다.', data:null }));
  }
  const base = backendBase();
  if (!base) {
    res.statusCode = 503;
    return res.end(JSON.stringify({ status:'error', reason:'데이터 API 서버가 연결돼 있지 않습니다.', data:null }));
  }
  const qs = new URLSearchParams(url.search);
  /* 지표 이름 — 다시 쓴 주소(__metric) 또는 원래 경로(/api/data/<지표>) 어느 쪽이 와도 같다 */
  const fromPath = url.pathname.replace(/^\/api\/data\/?/, '').split('/')[0];
  const metric = qs.get('__metric') || fromPath || '';
  qs.delete('__metric');
  qs.delete('kind');                       /* [kind] 라우팅이 붙인 값 — 지표 쿼리가 아니다 */
  if (metric && !METRIC_RE.test(metric)) {
    res.statusCode = 404;
    return res.end(JSON.stringify({ status:'error', reason:'없는 지표입니다.', data:null }));
  }
  const headers = { Accept:'application/json' };
  const token = backendToken();
  if (token) headers['X-FEEDiT-Token'] = token;
  const auth = req.headers.authorization;
  if (auth) headers.Authorization = String(auth).slice(0, 300);
  const apiKey = req.headers['x-api-key'];
  if (apiKey) headers['X-API-Key'] = String(apiKey).slice(0, 300);
  { const ip = clientIp(req); if (ip && token) headers['X-FEEDiT-Client-IP'] = ip; }
  const q = qs.toString();
  try {
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 25000);
    const upstream = await fetch(`${base}/data${metric ? '/' + metric : ''}${q ? '?' + q : ''}`,
      { headers, signal:c.signal, redirect:'manual' });
    clearTimeout(t);
    res.statusCode = upstream.status;
    for (const h of ['retry-after', 'x-ratelimit-limit', 'x-ratelimit-remaining']) {
      const v = upstream.headers.get(h);
      if (v) res.setHeader(h, v);
    }
    const text = await upstream.text();
    return res.end(text || JSON.stringify({ status:'error', reason:'데이터 API 응답이 비었습니다.', data:null }));
  } catch (error) {
    /* 백엔드 주소가 섞일 수 있어 사유만 준다 (auth/[action].js 와 같은 규칙) */
    console.error('[feedit] data relay failed:', error);
    res.statusCode = 502;
    return res.end(JSON.stringify({ status:'error', reason:'데이터 API 서버에 연결하지 못했습니다.', data:null }));
  }
}
