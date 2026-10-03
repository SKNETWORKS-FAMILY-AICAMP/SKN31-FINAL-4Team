/* Vercel 할인률 후보 경로가 Django의 같은 경로로 중계되는지 확인한다. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const previous = {
  backend: process.env.BACKEND_API_URL,
  token: process.env.BACKEND_API_TOKEN,
  fetch: globalThis.fetch,
};
const handler = (await import('../api/[kind].js')).default;
const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));
assert.ok(config.rewrites.some((row) =>
  row.source === '/api/discount/facets' && row.destination === '/api/discount?__facets=1'));

const response = () => ({
  statusCode: 0,
  headers: {},
  body: null,
  setHeader(key, value) { this.headers[key] = value; },
  end(body) { this.body = JSON.parse(body); },
});

try {
  process.env.BACKEND_API_URL = 'https://backend.example/api';
  process.env.BACKEND_API_TOKEN = 'test-token';
  let called;
  globalThis.fetch = async (url, options) => {
    called = { url, options };
    return { ok: true, json: async () => ({
      status: 'ok', matched: 2,
      data: { style: [], brand: [], kind: [], item: [{ label: '상품', count: 2 }] },
    }) };
  };

  const ok = response();
  await handler({ method: 'GET', url: '/api/discount/facets?style=%EC%8A%A4%ED%8A%B8%EB%A6%BF&brand=A&brand=B&limit=10' }, ok);
  assert.equal(called.url, 'https://backend.example/api/discount/facets?style=%EC%8A%A4%ED%8A%B8%EB%A6%BF&brand=A&brand=B&limit=10');
  assert.equal(called.options.headers['X-FEEDiT-Token'], 'test-token');
  assert.equal(ok.body.status, 'ok');
  assert.equal(ok.body.data.item[0].count, 2);

  const category = response();
  await handler({ method: 'GET', url: '/api/discount/facets?kind=%EC%9B%90%ED%94%BC%EC%8A%A4&item_limit=24&item_offset=24' }, category);
  assert.equal(called.url, 'https://backend.example/api/discount/facets?item_limit=24&item_offset=24&kind=%EC%9B%90%ED%94%BC%EC%8A%A4');
  assert.equal(category.body.status, 'ok');

  const rewritten = response();
  await handler({ method: 'GET', url: '/api/discount?__facets=1&limit=10' }, rewritten);
  assert.equal(called.url, 'https://backend.example/api/discount/facets?limit=10');
  assert.equal(rewritten.body.status, 'ok');

  const rewrittenCategory = response();
  await handler({ method: 'GET', url: '/api/discount?__facets=1&kind=discount&kind=%EC%9B%90%ED%94%BC%EC%8A%A4&item_limit=24' }, rewrittenCategory);
  assert.equal(called.url, 'https://backend.example/api/discount/facets?item_limit=24&kind=%EC%9B%90%ED%94%BC%EC%8A%A4');
  assert.equal(rewrittenCategory.body.status, 'ok');

  const ordinaryDiscount = response();
  await handler({ method: 'GET', url: '/api/discount?term=%EB%8D%B0%EB%8B%98' }, ordinaryDiscount);
  assert.equal(called.url, 'https://backend.example/api/discount?term=%EB%8D%B0%EB%8B%98');

  globalThis.fetch = async () => ({ ok: false, status: 404 });
  const oldBackend = response();
  await handler({ method: 'GET', url: '/api/discount/facets?limit=10' }, oldBackend);
  assert.equal(oldBackend.body.status, 'error');
  assert.match(oldBackend.body.reason, /404/);

  delete process.env.BACKEND_API_URL;
  const noBackend = response();
  await handler({ method: 'GET', url: '/api/discount/facets' }, noBackend);
  assert.equal(noBackend.body.status, 'error');
  assert.match(noBackend.body.reason, /BACKEND_API_URL/);

  console.log('✅ 할인률 후보 Vercel 중계 및 기존 할인률 경로 7건 통과');
} finally {
  if (previous.backend === undefined) delete process.env.BACKEND_API_URL;
  else process.env.BACKEND_API_URL = previous.backend;
  if (previous.token === undefined) delete process.env.BACKEND_API_TOKEN;
  else process.env.BACKEND_API_TOKEN = previous.token;
  globalThis.fetch = previous.fetch;
}
