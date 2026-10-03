/* 버셀 API 함수 — 응답 계약 시험.
 *
 * ★ 여기서 지키는 것은 SQL 정확성이 아니라 **약속**이다:
 *     ok     값이 있다
 *     empty  붙었는데 값이 없다        ← 기다릴 일
 *     error  못 붙었다                 ← 고칠 일
 *   이 둘을 뭉뚱그리면 화면이 "DB 가 죽었는데 값이 없는 척" 하게 된다.
 *   지금 프론트가 딱 그 상태였다 — 트렌드 수치가 전부 씨드 난수라
 *   DB 가 없어도 화면이 멀쩡해 보였다.
 *
 * 진짜 RDS 없이 돌린다. `tests/fake_pg/pg.mjs` 가 pg 자리에 들어가
 * 받은 SQL·인자를 기록하고 정해진 행을 돌려준다.
 *
 *   node --experimental-loader=./tests/fake_pg/loader.mjs tests/api.test.mjs
 *   또는  npm test
 */
import assert from 'node:assert/strict';
import * as fake from './fake_pg/pg.mjs';

process.env.DATABASE_URL = 'postgres://u:p@h:5432/feedit';

// 응답을 받아 두는 가짜 res
const mkRes = () => {
  const r = { statusCode: 0, headers: {}, body: null };
  r.setHeader = (k, v) => { r.headers[k] = v; };
  r.end = (s) => { r.body = JSON.parse(s); };
  return r;
};
const req = (u) => ({ url: u, method: 'GET' });

let pass = 0, fail = 0;
const t = async (name, fn) => {
  try { await fn(); console.log('✅', name); pass++; }
  catch (e) { console.log('❌', name, '\n   ', e.message); fail++; }
};

const trend    = (await import('../api/trend.js')).default;
const assoc    = (await import('../api/assoc.js')).default;
const products = (await import('../api/products.js')).default;
const health   = (await import('../api/health.js')).default;

// ── 지표가 있을 때 ─────────────────────────────────────
await t('트렌드 — 값이 있으면 시계열을 돌려준다', async () => {
  fake.__setNext({ rows: [
    { metric_date: '2026-09-01', mention_count: 12, document_count: 5, source_count: 2,
      sentiment_avg: '0.3', growth_rate: '0.1', trend_score: '55.5',
      metrics: { temp: 61.2, momentum: 1.4 }, canonical_name: '발레코어', term_type: 'STYLE' },
  ]});
  const res = mkRes();
  await trend(req('/api/trend?term=발레코어&days=30'), res);
  assert.equal(res.body.status, 'ok');
  assert.equal(res.body.data.term, '발레코어');
  assert.equal(res.body.data.series[0].temp, 61.2, 'metrics JSON 안의 temp 를 꺼내야 한다');
  assert.equal(res.body.data.series[0].mention, 12);
});

await t('트렌드 — 없는 값은 지어내지 않고 사유를 붙인다', async () => {
  fake.__setNext({ rows: [
    { metric_date: '2026-09-01', mention_count: 12, document_count: 5, source_count: 2,
      sentiment_avg: null, growth_rate: null, trend_score: '55.5',
      metrics: {}, canonical_name: '발레코어', term_type: 'STYLE' },
  ]});
  const res = mkRes();
  await trend(req('/api/trend?term=발레코어'), res);
  assert.equal(res.body.status, 'ok');
  assert.ok(res.body.unavailable, 'unavailable 이 있어야 한다');
  assert.ok(res.body.unavailable.fields.includes('temp'));
  assert.ok(/RDS/.test(res.body.unavailable.reason));
});

// ── 값이 없을 때 vs 못 붙을 때를 가른다 ────────────────
await t('트렌드 — 사전엔 있는데 지표가 없으면 empty + 이유', async () => {
  let call = 0;
  fake.__setNext(() => (++call === 1 ? { rows: [] } : { rows: [{ '?column?': 1 }] }));
  const res = mkRes();
  await trend(req('/api/trend?term=엄브로'), res);
  assert.equal(res.body.status, 'empty');
  assert.equal(res.body.known, true);
  assert.ok(/사전에 있지만/.test(res.body.reason));
});

await t('트렌드 — 사전에도 없으면 그렇게 말한다', async () => {
  fake.__setNext({ rows: [] });
  const res = mkRes();
  await trend(req('/api/trend?term=없는말'), res);
  assert.equal(res.body.status, 'empty');
  assert.equal(res.body.known, false);
  assert.ok(/찾지 못했습니다/.test(res.body.reason));
});

await t('★ DB 가 안 붙으면 empty 가 아니라 error 다', async () => {
  const e = new Error('connect ETIMEDOUT'); e.code = 'ETIMEDOUT';
  fake.__setNext(e);
  const res = mkRes();
  await trend(req('/api/trend?term=발레코어'), res);
  assert.equal(res.body.status, 'error', '값 없음과 연결 실패는 달라야 한다');
  assert.ok(/연결하지 못했습니다/.test(res.body.reason));
});

// ── 연관어 ─────────────────────────────────────────────
await t('연관어 — 표가 통째로 비면 그 사실을 말한다', async () => {
  let call = 0;
  fake.__setNext(() => (++call === 1 ? { rows: [] } : { rows: [{ n: '0' }] }));
  const res = mkRes();
  await assoc(req('/api/assoc?term=발레코어'), res);
  assert.equal(res.body.status, 'empty');
  assert.equal(res.body.total_rows, 0);
  assert.ok(/통째로 비어/.test(res.body.reason));
});

await t('연관어 — 값이 있으면 점수와 함께 돌려준다', async () => {
  fake.__setNext({ rows: [
    { term: '새틴', facet: 'MATERIAL', cooccurrence_count: '9', lift: '2.31', pmi: '1.21',
      association_percentile: '96.4', score: '96.4', basis: ['text'],
      metric_date: '2026-09-01', metric_version: 'feedit-unified-text-v1' },
  ]});
  const res = mkRes();
  await assoc(req('/api/assoc?term=발레코어'), res);
  assert.equal(res.body.status, 'ok');
  assert.equal(res.body.data.items[0].score, 96.4);
  assert.equal(res.body.data.items[0].lift, 2.31);
  assert.equal(res.body.data.window_days, 28);
  assert.equal(res.body.data.as_of, '2026-09-01');
});

// ── 상품 ───────────────────────────────────────────────
await t('상품 — 가격 스냅샷이 없으면 0 이 아니라 null + 사유', async () => {
  fake.__setNext({ rows: [
    { id: 1, name: '베이스볼 하프 셔츠', brand: '커버낫', brand_en: 'COVERNAT',
      source_product_id: '4914421', product_url: 'https://x', market_type: 'RETAIL',
      source_brand_name: null, source_category_name: '셔츠', source_code: 'musinsa',
      source_name: '무신사', list_price: null, sale_price: null, discount_rate: null,
      stock_status: null, observed_at: null },
  ]});
  const res = mkRes();
  await products(req('/api/products?q=셔츠'), res);
  assert.equal(res.body.status, 'ok');
  const p = res.body.data.items[0];
  assert.equal(p.price.sale, null, '가격이 없으면 null 이어야 한다');
  assert.ok(p.price.unavailable, '왜 없는지 말해야 한다');
  assert.ok(/1건은 가격 기록이 아직 없습니다/.test(res.body.note));
});

await t('★ 상품 — 검색어+브랜드 둘 다 주면 $ 번호가 어긋나지 않는다', async () => {
  fake.__setNext({ rows: [] });
  const res = mkRes();
  await products(req('/api/products?q=엄브로&brand=UMBRO&limit=7'), res);
  const last = fake.CALLS[fake.CALLS.length - 1];
  assert.deepEqual(last.args, ['%엄브로%', 'UMBRO', 8, 0]);
  assert.ok(/\$1/.test(last.sql) && /\$2/.test(last.sql) && /LIMIT \$3 OFFSET \$4/.test(last.sql),
    'LIMIT/OFFSET 이 $3/$4 이어야 한다: ' + last.sql.slice(-80));
});

await t('★ 상품 — 스타일은 여러 개 달리는 연결 표로만 고른다', async () => {
  fake.__setNext({ rows: [] });
  const res = mkRes();
  await products(req('/api/products?style=고프코어&limit=16&offset=32'), res);
  const last = fake.CALLS[fake.CALLS.length - 1];
  assert.deepEqual(last.args, ['고프코어', 17, 32]);
  assert.match(last.sql,/commerce\.product_term/);
  /* 없어진 단일 스타일 FK(p.style_id) 를 다시 들이지 않는다 */
  assert.ok(!/style_id/.test(last.sql), '단일 스타일 FK 를 조인하면 안 된다: ' + last.sql);
  assert.match(last.sql,/ps\.thumbnail_url/);
});

await t('★ 상품 — 큰 카테고리를 페이지 분할 전에 SQL로 거른다', async () => {
  fake.__setNext({ rows: [] });
  const res = mkRes();
  await products(req('/api/products?style=고프코어&category_group=outer&limit=16'), res);
  const last = fake.CALLS[fake.CALLS.length - 1];
  assert.match(last.sql,/~\*/,'카테고리 정규식이 LIMIT보다 앞선 WHERE에 있어야 한다');
  assert.match(last.sql,/NOT \(\(/,'앞서 판정되는 신발·원피스를 제외해야 한다');
  assert.equal(last.args.at(-2),17);
  assert.equal(last.args.at(-1),0);
  assert.ok(last.args.some(x=>String(x).includes('아우터')));
});

// ── 진단 ───────────────────────────────────────────────
await t('진단 — 접속 정보가 없으면 붙어 보지도 않고 안내한다', async () => {
  const save = process.env.DATABASE_URL; delete process.env.DATABASE_URL;
  const res = mkRes();
  await health(req('/api/health'), res);
  assert.equal(res.body.configured, false);
  assert.ok(/Environment Variables/.test(res.body.verdict));
  process.env.DATABASE_URL = save;
});

await t('진단 — 지표가 0행이면 원인을 짚어 준다', async () => {
  let call = 0;
  fake.__setNext((sql) => {
    call++;
    if (/version\(\)/.test(sql)) return { rows: [{ v: 'PostgreSQL 17.9 on x', db: 'feedit' }] };
    if (/UNION ALL/.test(sql)) return { rows: [
      { i: 0, n: '3375' }, { i: 8, n: '0' }, { i: 9, n: '0' } ] };
    if (/information_schema/.test(sql)) return { rows: [
      { column_name: 'mention_count' }, { column_name: 'trend_score' } ] };
    return { rows: [] };
  });
  const res = mkRes();
  await health(req('/api/health'), res);
  assert.equal(res.body.connected, true);
  assert.equal(res.body.tables['analysis.term_metric_daily'].rows, 0);
  assert.ok(/rds_sync/.test(res.body.verdict), '왜 0행인지 짚어야 한다');
  assert.deepEqual(res.body.metric_columns.needed_missing,
    ['temp','momentum','ma7','ma28','level','pct_rank']);
  assert.ok(/상품은 3,375건/.test(res.body.verdict));
});


// ══════════════════════════════════════════════════════════
//  챗봇 경로 — 배포된 곳에서 어디를 부르나
// ══════════════════════════════════════════════════════════
const chatHealth = (await import('../api/_v1/health.js')).default;
const chat       = (await import('../api/_v1/chat.js')).default;
const virtualFit = (await import('../api/v1/virtual-fitting.js')).default;

const mkStreamRes = () => {
  const r = { statusCode: 0, headers: {}, chunks: [] };
  r.setHeader = (k, v) => { r.headers[k] = v; };
  r.write = (s) => { r.chunks.push(String(s)); };
  r.end = (s) => { if (s) r.chunks.push(String(s)); r.done = true; };
  return r;
};
const postReq = (body) => {
  const handlers = {};
  const req = { method: 'POST', url: '/api/v1/chat',
                on: (e, f) => { handlers[e] = f; return req; } };
  queueMicrotask(() => { handlers.data && handlers.data(body); handlers.end && handlers.end(); });
  return req;
};

await t('★ 챗봇 주소 — 배포에서는 같은 도메인 /api 를 쓴다', async () => {
  const src = await (await import('node:fs/promises'))
    .readFile(new URL('../home/static/js/chat_api.js', import.meta.url), 'utf8');
  assert.ok(/LOCAL_FILE \? DIRECT : '\/api'/.test(src),
    '5173/4173 이 아니면 127.0.0.1 을 부르던 규칙이 남아 있으면 안 된다');
  assert.ok(!/location\.port === '5173'/.test(src));
});

await t('챗봇 health — 뒤 서버가 없으면 503 이라 목업으로 떨어진다', async () => {
  delete process.env.CHAT_BACKEND_URL;
  const res = mkRes();
  await chatHealth(req('/api/v1/health'), res);
  assert.equal(res.statusCode, 503, '200 을 주면 화면이 빈 답을 보게 된다');
  assert.equal(res.body.backend, 'missing');
  assert.ok(/CHAT_BACKEND_URL/.test(res.body.reason));
});

await t('★ 챗봇 chat — 뒤 서버가 없어도 SSE 모양을 지킨다', async () => {
  delete process.env.CHAT_BACKEND_URL;
  const res = mkStreamRes();
  await chat(postReq('{"q":"발레코어 어때"}'), res);
  const out = res.chunks.join('');
  assert.equal(res.headers['Content-Type'], 'text/event-stream; charset=utf-8');
  for (const ev of ['status', 'text', 'done']) {
    assert.ok(out.includes(`event: ${ev}`), `${ev} 이벤트가 있어야 한다`);
  }
  assert.ok(/지어내는 대신/.test(out), '못 답한다고 말해야 한다');
  assert.ok(res.done);
});

await t('챗봇 chat — POST 가 아니면 받지 않는다', async () => {
  const res = mkStreamRes();
  await chat({ method: 'GET', url: '/api/v1/chat' }, res);
  assert.equal(res.statusCode, 405);
});

await t('★ 입혀보기 — Vercel 함수가 EC2 API와 토큰을 중계한다', async () => {
  process.env.CHAT_BACKEND_URL = 'http://chat.example.test/';
  process.env.CHAT_BACKEND_TOKEN = 'server-only-token';
  let call;
  globalThis.fetch = async (url, options) => {
    call = { url, options };
    return { status: 200, text: async () => JSON.stringify({ ok: true, image: 'data:image/png;base64,eA==' }) };
  };
  const res = mkRes();
  await virtualFit({ method: 'POST', headers: { 'x-forwarded-for': '203.0.113.7' },
    body: { items: [{ image: 'data:image/jpeg;base64,eA==', category: '상의' }], model_id: 'woman' } }, res);
  assert.equal(res.statusCode, 200);
  assert.equal(call.url, 'http://chat.example.test/v1/virtual-fitting');
  assert.equal(call.options.headers['X-FEEDiT-Token'], 'server-only-token');
  assert.equal(call.options.headers['X-Forwarded-For'], '203.0.113.7');
  assert.equal(JSON.parse(call.options.body).model_id, 'woman');
  delete process.env.CHAT_BACKEND_URL;
  delete process.env.CHAT_BACKEND_TOKEN;
});

await t('입혀보기 — 백엔드 HTML 오류도 읽을 수 있는 JSON 오류로 바꾼다', async () => {
  process.env.CHAT_BACKEND_URL = 'http://chat.example.test';
  globalThis.fetch = async () => ({ status: 404, text: async () => 'The page could not be found' });
  const res = mkRes();
  await virtualFit({ method: 'POST', headers: {}, body: { items: [{}] } }, res);
  assert.equal(res.statusCode, 502);
  assert.equal(res.body.ok, false);
  assert.ok(/올바른 응답/.test(res.body.message));
  delete process.env.CHAT_BACKEND_URL;
});


// ══════════════════════════════════════════════════════════
//  Django API 경유 — RDS 를 열지 않는 길
// ══════════════════════════════════════════════════════════
await t('★ BACKEND_API_URL 이 있으면 Django 로 넘긴다 (pg 를 안 부른다)', async () => {
  process.env.BACKEND_API_URL = 'http://feedit-official.duckdns.org/api';
  const before = fake.CALLS.length;
  let called = null;
  globalThis.fetch = async (u) => { called = u; return {
    ok: true, json: async () => ({ status: 'ok', data: { term: '발레코어', series: [] } }) }; };
  const res = mkRes();
  await trend(req('/api/trend?term=발레코어&days=30'), res);
  assert.equal(called, 'http://feedit-official.duckdns.org/api/trend?term=발레코어&days=30');
  assert.equal(fake.CALLS.length, before, 'DB 에 직접 붙으면 안 된다');
  assert.equal(res.body.status, 'ok');
  delete process.env.BACKEND_API_URL;
});

await t('백엔드가 죽으면 값 없음이 아니라 오류로 말한다', async () => {
  process.env.BACKEND_API_URL = 'http://x/api';
  globalThis.fetch = async () => { throw new Error('ECONNREFUSED'); };
  const res = mkRes();
  await trend(req('/api/trend?term=발레코어'), res);
  assert.equal(res.body.status, 'error');
  assert.ok(/닿지 못했습니다/.test(res.body.reason));
  delete process.env.BACKEND_API_URL;
});

await t('BACKEND_API_URL 이 없으면 예전처럼 pg 로 간다', async () => {
  delete process.env.BACKEND_API_URL;
  const before = fake.CALLS.length;
  fake.__setNext({ rows: [] });
  const res = mkRes();
  await trend(req('/api/trend?term=발레코어'), res);
  assert.ok(fake.CALLS.length > before, 'pg 를 불러야 한다');
});

await t('★ 긍부정 — Vercel 동적 함수가 Django 직접 집계 API를 중계한다', async () => {
  process.env.BACKEND_API_URL = 'http://feedit-official.duckdns.org/api';
  const kind = (await import('../api/[kind].js')).default;
  let called = null;
  globalThis.fetch = async (u) => { called = u; return {
    ok: true, json: async () => ({ status: 'ok', data: { term: '나이키', method: 'BRAND_CONTEXT', series: [] } }) }; };
  const res = mkRes();
  await kind(req('/api/sentiment?term=나이키&subject=brand'), res);
  assert.equal(called, 'http://feedit-official.duckdns.org/api/sentiment?term=%EB%82%98%EC%9D%B4%ED%82%A4&subject=brand');
  assert.equal(res.body.data.method, 'BRAND_CONTEXT');
  delete process.env.BACKEND_API_URL;
});

await t('★ 살말 — 카드 삭제처럼 조각이 더 붙는 주소도 중계한다', async () => {
  /* ★ 2026-09-21 회귀 방지 — 중계 파일이 [action].js 였을 때는 한 조각만 받아서
     /api/salmal/cards/42 (DELETE) 가 버셀 404 로 떨어졌다. 카드 삭제가 안 됐다. */
  process.env.BACKEND_API_URL = 'http://feedit-official.duckdns.org/api';
  process.env.BACKEND_API_TOKEN = 'server-only-token';
  const salmal = (await import('../api/salmal/[...action].js')).default;
  let called = null, options = null;
  globalThis.fetch = async (url, opts) => {
    called = url; options = opts;
    return { status:200, text:async()=>JSON.stringify({status:'ok',data:{id:42,deleted:true}}) };
  };
  const res = mkRes();
  await salmal({
    url:'/api/salmal/cards/42', method:'DELETE',
    headers:{cookie:'sessionid=abc','x-csrftoken':'tok'},
    body:{},
  }, res);
  assert.equal(called, 'http://feedit-official.duckdns.org/api/salmal/cards/42');
  assert.equal(options.method, 'DELETE');
  assert.equal(options.headers['X-CSRFToken'], 'tok');
  assert.equal(options.headers.Cookie, 'sessionid=abc');
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.deleted, true);
  delete process.env.BACKEND_API_URL;
  delete process.env.BACKEND_API_TOKEN;
});

await t('★ 살말 — rewrite 로 들어온 __card 도 같은 Django 주소로 편다', async () => {
  /* 버셀이 캐치올 주소를 함수로 안 잡아 줄 때를 대비한 두 번째 길
     (vercel.json rewrite). 내부 값 __card 는 Django 로 새 나가면 안 된다. */
  process.env.BACKEND_API_URL = 'http://feedit-official.duckdns.org/api';
  let called = null;
  globalThis.fetch = async (url) => {
    called = url;
    return { status:200, text:async()=>JSON.stringify({status:'ok',data:{id:42,deleted:true}}) };
  };
  const salmal = (await import('../api/salmal/[...action].js')).default;
  const res = mkRes();
  await salmal({ url:'/api/salmal/cards?__card=42', method:'DELETE', headers:{}, body:{} }, res);
  assert.equal(called, 'http://feedit-official.duckdns.org/api/salmal/cards/42');
  assert.ok(!/__card/.test(called), '내부 값이 백엔드로 새 나가면 안 된다');
  assert.equal(res.statusCode, 200);
  delete process.env.BACKEND_API_URL;
});

await t('★ 인증 — 세션·CSRF 쿠키와 POST 본문을 Django로 중계한다', async () => {
  process.env.BACKEND_API_URL = 'http://feedit-official.duckdns.org/api';
  process.env.BACKEND_API_TOKEN = 'server-only-token';
  const auth = (await import('../api/auth/[action].js')).default;
  let called = null, options = null;
  globalThis.fetch = async (url, opts) => {
    called = url; options = opts;
    return {
      status:201,
      headers:{ getSetCookie:()=>['sessionid=abc; HttpOnly; Path=/','csrftoken=xyz; Path=/'] },
      text:async()=>JSON.stringify({status:'ok',data:{authenticated:true,user:{nickname:'테스트'}}}),
    };
  };
  const res = mkRes();
  await auth({
    url:'/api/auth/signup', method:'POST',
    headers:{cookie:'csrftoken=old','x-csrftoken':'old'},
    body:{username:'tester',password:'password'},
  }, res);
  assert.equal(called, 'http://feedit-official.duckdns.org/api/auth/signup');
  assert.equal(options.headers['X-FEEDiT-Token'], 'server-only-token');
  assert.equal(options.headers.Cookie, 'csrftoken=old');
  assert.equal(options.headers['X-CSRFToken'], 'old');
  assert.equal(JSON.parse(options.body).username, 'tester');
  assert.equal(res.statusCode, 201);
  assert.equal(res.headers['Set-Cookie'].length, 2);
  delete process.env.BACKEND_API_URL;
  delete process.env.BACKEND_API_TOKEN;
});

await t('★ 추천 영상 — 로그인 쿠키를 붙여 개인화 Django API로 중계한다', async () => {
  process.env.BACKEND_API_URL = 'http://feedit-official.duckdns.org/api';
  const auth = (await import('../api/auth/[action].js')).default;
  let called = null, options = null;
  globalThis.fetch = async (url, opts) => {
    called = url; options = opts;
    return {
      status:200,
      headers:{getSetCookie:()=>[]},
      text:async()=>JSON.stringify({status:'ok',data:{items:[{youtube_id:'abc123'}]}}),
    };
  };
  const res = mkRes();
  await auth({url:'/api/auth/weekly-videos',method:'GET',headers:{cookie:'sessionid=abc'}},res);
  assert.equal(called,'http://feedit-official.duckdns.org/api/auth/weekly-videos');
  assert.equal(options.headers.Cookie,'sessionid=abc');
  assert.equal(options.method,'GET');
  assert.equal(res.body.data.items[0].youtube_id,'abc123');
  delete process.env.BACKEND_API_URL;
});

// ── 사전 — 용어 표와 브랜드 표를 합쳐서 준다 ────────────
const dictionary = (await import('../api/dictionary.js')).default;

await t('★ 사전 — 용어와 브랜드를 합쳐서 준다', async () => {
  delete process.env.BACKEND_API_URL;
  let call = 0;
  fake.__setNext(() => (++call === 1
    ? { rows: [{ label: '발레코어', facet: 'STYLE', kind: 'term', en: 'balletcore' },
               { label: '새틴',     facet: 'MATERIAL', kind: 'term', en: 'satin' }] }
    : { rows: [{ label: '스투시', facet: 'BRAND', kind: 'brand', en: 'Stussy' }] }));
  const res = mkRes();
  await dictionary(req('/api/dictionary'), res);
  assert.equal(res.body.status, 'ok', JSON.stringify(res.body));
  const m = Object.fromEntries(res.body.data.map((x) => [x.label, x]));
  assert.equal(m['스투시'].kind, 'brand');
  assert.equal(m['스투시'].facet, '브랜드', '코드가 아니라 화면 축 이름이어야 한다');
  assert.equal(m['새틴'].facet, '소재');
  assert.equal(res.body.counts['브랜드'], 1, JSON.stringify(res.body.counts));
});

await t('★ 사전 — 브랜드만 못 읽어도 용어는 보낸다', async () => {
  let call = 0;
  fake.__setNext((sql) => {
    call++;
    if (/FROM dictionary\.brand/.test(sql)) throw new Error('permission denied');
    return { rows: [{ label: '발레코어', facet: 'STYLE', kind: 'term', en: '' }] };
  });
  const res = mkRes();
  await dictionary(req('/api/dictionary'), res);
  assert.equal(res.body.status, 'ok', JSON.stringify(res.body));
  assert.equal(res.body.data.length, 1);
  assert.ok(/브랜드는 못 읽었습니다/.test(res.body.note || ''), res.body.note);
});

await t('사전 — RDS 에 못 붙으면 빈 사전이 아니라 오류다', async () => {
  fake.__setNext(new Error('ECONNREFUSED'));
  const res = mkRes();
  await dictionary(req('/api/dictionary'), res);
  assert.equal(res.body.status, 'error', JSON.stringify(res.body));
  assert.ok(/연결하지 못했습니다/.test(res.body.reason));
});

console.log(`\n(백엔드 경유 포함) ${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
