/* 데이터 API 연동 (2026-10-03) — 버셀 중계와 계정 메뉴 '데이터 API' 창을 실제로 돌려 본다.

   ① 중계 — /api/data/<지표> 를 [kind].js 가 받아 Django /data/<지표> 로 넘긴다.
            API 키 머리글을 그대로 넘기고, 상태 숫자를 그대로 돌려주고, 절대 캐시하지 않는다.
            다른 지표 주소(discount 등)의 동작은 그대로다.
   ② 화면 — 베타 동안 메뉴가 없다. 베타 이후 비즈니스 · 운영만 메뉴가 서고, 키를 만들면 원문을 한 번만 보여 준다. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

let pass = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); pass++; };

/* ═════════ ① 버셀 중계 ═════════ */
const config = JSON.parse(fs.readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));
ok(config.rewrites.some(r => r.source === '/api/data/:metric' && r.destination === '/api/data?__metric=:metric'),
  '/api/data/<지표> 를 [kind].js 로 보내는 다시 쓰기 규칙');
const fnCount = (function walk(dir){
  return fs.readdirSync(dir, { withFileTypes:true }).reduce((n, e) =>
    e.name.startsWith('_') ? n : e.isDirectory() ? n + walk(dir + '/' + e.name) : n + (e.name.endsWith('.js') ? 1 : 0), 0);
})(new URL('../api', import.meta.url).pathname);
ok(fnCount <= 11, `버셀 함수 수를 늘리지 않는다 (지금 ${fnCount}개 · Hobby 한도 12)`);

const handler = (await import('../api/[kind].js')).default;
const response = () => ({
  statusCode: 0, headers: {}, raw: '',
  setHeader(k, v) { this.headers[k.toLowerCase()] = v; },
  end(body) { this.raw = body; },
  get body() { return JSON.parse(this.raw); },
});
const prevFetch = globalThis.fetch;
process.env.BACKEND_API_URL = 'https://backend.example/api';
process.env.BACKEND_API_TOKEN = 'shared-token';
let called = null;
let upstream = { status: 200, body: { status: 'ok', data: { series: [] } }, headers: {} };
globalThis.fetch = async (url, options) => {
  called = { url, options };
  return { ok: upstream.status < 400, status: upstream.status,
    headers: { get: h => upstream.headers[h] || null },
    text: async () => JSON.stringify(upstream.body), json: async () => upstream.body };
};

let res = response();
await handler({ method: 'GET', url: '/api/data?__metric=trend&term=%EB%B0%9C%EB%A0%88%EC%BD%94%EC%96%B4&kind=data',
  headers: { authorization: 'Bearer fdk_1_ab12cd34_secret', 'x-forwarded-for': '211.36.1.2' } }, res);
ok(called.url === 'https://backend.example/api/data/trend?term=%EB%B0%9C%EB%A0%88%EC%BD%94%EC%96%B4', '지표 경로와 쿼리를 그대로 넘긴다: ' + called.url);
ok(called.options.headers.Authorization === 'Bearer fdk_1_ab12cd34_secret', 'API 키 머리글을 넘긴다');
ok(called.options.headers['X-FEEDiT-Token'] === 'shared-token', '공유 토큰을 붙인다(브라우저 · 밖에는 안 보인다)');
ok(res.statusCode === 200 && res.headers['cache-control'] === 'no-store', '성공해도 캐시하지 않는다');

upstream = { status: 429, body: { status: 'error', code: 'RATE_LIMITED' }, headers: { 'retry-after': '60', 'x-ratelimit-remaining': '0' } };
res = response();
await handler({ method: 'GET', url: '/api/data/assoc?term=x', headers: { 'x-api-key': 'fdk_1_ab12cd34_secret' } }, res);
ok(called.url === 'https://backend.example/api/data/assoc?term=x', '다시 쓰기 전 경로(/api/data/<지표>)도 같다');
ok(called.options.headers['X-API-Key'] === 'fdk_1_ab12cd34_secret', 'X-API-Key 머리글도 넘긴다');
ok(res.statusCode === 429 && res.headers['retry-after'] === '60' && res.body.code === 'RATE_LIMITED', '상태 숫자 · Retry-After 를 그대로 돌려준다');

res = response(); called = null;
await handler({ method: 'GET', url: '/api/data', headers: {} }, res);
ok(called.url === 'https://backend.example/api/data', '/api/data 는 지표 목록');

res = response(); called = null;
await handler({ method: 'POST', url: '/api/data?__metric=trend', headers: {} }, res);
ok(res.statusCode === 405 && called === null, 'GET 말고는 받지 않는다');
res = response(); called = null;
await handler({ method: 'GET', url: '/api/data?__metric=../auth/me', headers: {} }, res);
ok(res.statusCode === 404 && called === null, '이상한 지표 이름은 넘기지 않는다');

/* 다른 지표 주소는 예전 그대로 — 성공하면 엣지에 캐시한다 */
upstream = { status: 200, body: { status: 'ok', data: {} }, headers: {} };
res = response();
await handler({ method: 'GET', url: '/api/discount?style=x', headers: {} }, res);
ok(called.url === 'https://backend.example/api/discount?style=x' && /s-maxage/.test(res.headers['cache-control']), '할인률 중계는 그대로');

delete process.env.BACKEND_API_URL;
res = response();
await handler({ method: 'GET', url: '/api/data?__metric=trend', headers: {} }, res);
ok(res.statusCode === 503, '백엔드 주소가 없으면 503');
globalThis.fetch = prevFetch;

/* ═════════ ② 화면 ═════════ */
const root = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost:5173/' });
Object.defineProperty(dom.window.document, 'hidden', { configurable:true, get:() => false });
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent','Event'])
  globalThis[key] = key === 'window' ? dom.window : dom.window[key];
globalThis.MutationObserver = dom.window.MutationObserver;
globalThis.requestAnimationFrame = fn => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = id => clearTimeout(id);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.location = dom.window.location;
globalThis.history = dom.window.history;
globalThis.localStorage = dom.window.localStorage;
globalThis.sessionStorage = dom.window.sessionStorage;
globalThis.innerWidth = 1440; globalThis.innerHeight = 900;
globalThis.matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
globalThis.scrollTo = () => {};
globalThis.IntersectionObserver = class{ observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class{ observe(){} unobserve(){} disconnect(){} };
globalThis.confirm = () => true;
let copied = '';
Object.defineProperty(globalThis, 'navigator', { configurable:true, value:{ clipboard:{ writeText:async t => { copied = t } }, userAgent:'node' } });

const EDIT = ['temp','assoc','sentiment','life','stock','resale'];
const FEAT = {
  FREE:{ salmal:true, chat_daily:20, trend_feed:true, trend_edit:['temp'], report_export:false, data_api:false },
  PRO:{ salmal:true, chat_daily:null, trend_feed:true, trend_edit:EDIT, report_export:true, data_api:false },
  BUSINESS:{ salmal:true, chat_daily:null, trend_feed:true, trend_edit:EDIT, report_export:true, data_api:true },
};
const billing = (enforced, plan) => ({ enforced, signed_in:true, plan, features:enforced ? FEAT[plan] : FEAT.BUSINESS,
  plans:FEAT, request:null, chat:null });
const user = { id:7, username:'biz01', email:'biz@example.com', nickname:'팀장', role:'user', job:'', major:'',
  bio:'', styles:[], saved_count:0, vote_count:0, badges:{}, plan:'BUSINESS', billing:billing(false, 'BUSINESS') };

const asked = [];
let keys = [];
const keyPayload = extra => ({ enforced:true, allowed:true, plan:'BUSINESS', keys, max_keys:5, used_today:12,
  limits:{ per_day:10000, per_minute:60 },
  metrics:[{ metric:'trend', path:'/api/data/trend', about:'언급량 · 트렌드 온도 추이', params:'term (필수) · source' }], ...extra });
const reply = (payload, status = 200) => ({ ok:status < 400, status, text:async () => JSON.stringify(payload), json:async () => payload });
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url), method = (opts.method || 'GET').toUpperCase();
  asked.push({ url:u, method, body:opts.body });
  if(u.includes('/api/auth/me')) return reply({ status:'ok', data:{ authenticated:true, csrf_token:'csrf', user } });
  if(u.includes('/api/auth/data-keys')){
    if(method === 'POST'){
      keys = [...keys, { id:'ab12cd34', name:JSON.parse(opts.body).name, hint:'fdk_…wxyz', created_at:'2026-10-03T12:00:00+09:00', last_used_at:null }];
      return reply({ status:'ok', data:keyPayload({ key:'fdk_7_ab12cd34_THIS-IS-THE-SECRET-wxyz' }) }, 201);
    }
    if(method === 'DELETE'){ keys = keys.filter(k => k.id !== JSON.parse(opts.body).key_id); return reply({ status:'ok', data:keyPayload() }); }
    return reply({ status:'ok', data:keyPayload() });
  }
  if(u.includes('/api/auth/notifications')) return reply({ status:'ok', data:{ items:[], unread:0, setting:{ enabled:true, kinds:{} } } });
  if(u.includes('/api/auth/alpha-quota')) return reply({ status:'ok', data:{ alpha:false } });
  if(u.includes('/api/auth/saved')) return reply({ status:'ok', data:{ items:[], count:0 } });
  if(u.includes('/api/dictionary')) return reply({ status:'ok', data:[] });
  return reply({ status:'empty', reason:'테스트 데이터 없음', data:null });
};

await import(`${root}/main.js`);
const plan = await import(`${root}/account/static/js/plan.js`);
document.getElementById('jumpBtn').click();
await new Promise(r => setTimeout(r, 200));
const $ = s => document.querySelector(s);
const wait = (ms = 40) => new Promise(r => setTimeout(r, ms));

ok(plan.planEnforced() === false, '베타로 시작한다');
ok($('#menuDataApi').hidden, '베타 — 비즈니스 계정이어도 데이터 API 메뉴가 없다');
ok(!asked.some(a => a.url.includes('/api/auth/data-keys')), '베타 — 키 주소를 부르지 않는다');

plan.planApply(billing(true, 'FREE'));
ok($('#menuDataApi').hidden, '베타 이후 프리 — 메뉴 없음');
plan.planApply(billing(true, 'PRO'));
ok($('#menuDataApi').hidden, '베타 이후 프로 — 메뉴 없음');
plan.planApply(billing(true, 'BUSINESS'));
ok(!$('#menuDataApi').hidden, '베타 이후 비즈니스 — 메뉴가 선다');

$('#menuDataApi').click(); await wait();
ok($('#dataApiModal').classList.contains('on'), '메뉴를 누르면 창이 열린다');
ok(/아직 만든 키가 없어요/.test($('#dataApiBody').textContent), '키가 없으면 그렇게 말한다');
ok(/오늘 12 \/ 10,000회/.test($('#dataApiBody').textContent), '오늘 사용량과 한도');
ok(/\/api\/data\/trend" /.test($('#dataApiBody .daCode').textContent) && /--data-urlencode "term=발레코어"/.test($('#dataApiBody .daCode').textContent), '부르는 법 예시(curl)');

$('#dataApiName').value = '마케팅 대시보드';
$('#dataApiBody [data-da-make]').click(); await wait();
const post = asked.filter(a => a.url.includes('/api/auth/data-keys') && a.method === 'POST').at(-1);
ok(post && JSON.parse(post.body).name === '마케팅 대시보드', '키 이름을 보낸다');
ok($('#dataApiFreshKey').textContent === 'fdk_7_ab12cd34_THIS-IS-THE-SECRET-wxyz', '만든 키 원문을 보여 준다');
ok(/마케팅 대시보드/.test($('#dataApiBody .daKeys').textContent) && /fdk_…wxyz/.test($('#dataApiBody .daKeys').textContent), '목록에는 끝 네 자리만');
$('#dataApiBody [data-da-copy]').click(); await wait();
ok(copied === 'fdk_7_ab12cd34_THIS-IS-THE-SECRET-wxyz', '복사 버튼');

$('#dataApiModal [data-close-modal]').click(); await wait();
ok(!$('#dataApiModal').classList.contains('on'), '닫힌다');
$('#menuDataApi').click(); await wait();
ok(!$('#dataApiFreshKey') && !/THIS-IS-THE-SECRET/.test($('#dataApiBody').textContent), '다시 열면 원문은 없다');

$('#dataApiBody [data-da-revoke="ab12cd34"]').click(); await wait();
const del = asked.filter(a => a.method === 'DELETE').at(-1);
ok(del && JSON.parse(del.body).key_id === 'ab12cd34', '폐기를 보낸다');
ok(/아직 만든 키가 없어요/.test($('#dataApiBody').textContent), '폐기하면 목록에서 빠진다');

plan.planApply(billing(false, 'BUSINESS'));
ok($('#menuDataApi').hidden, '다시 베타로 — 메뉴가 숨는다');

console.log(`✅ 데이터 API ${pass}개 통과`);
process.exit(0);
