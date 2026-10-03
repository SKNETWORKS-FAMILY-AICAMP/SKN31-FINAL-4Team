import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

process.env.BACKEND_API_URL = 'https://backend.example/api';
process.env.BACKEND_API_TOKEN = 'test-token';

let called;
globalThis.fetch = async (url, options) => {
  called = { url: String(url), options };
  return {
    ok: true,
    status: 200,
    text: async () => JSON.stringify({ status: 'ok', data: { items: [] } }),
  };
};

const handler = (await import('../api/[kind].js')).default;
const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));
assert.ok(config.rewrites.some((row) =>
  row.source === '/api/resale/products' && row.destination === '/api/resale?__products=1'));

function response() {
  return {
    statusCode: 0,
    headers: {},
    setHeader(name, value) { this.headers[name] = value; },
    end(body) { this.body = body; },
  };
}

const rewritten = response();
await handler({
  method: 'GET',
  url: '/api/resale?__products=1&q=%EB%82%98%EC%9D%B4%ED%82%A4&limit=16',
}, rewritten);
assert.equal(rewritten.statusCode, 200);
assert.equal(called.url, 'https://backend.example/api/resale/products?q=%EB%82%98%EC%9D%B4%ED%82%A4&limit=16');

const category = response();
await handler({
  method: 'GET',
  url: '/api/resale?__products=1&kind=resale&kind=%EC%87%BC%EC%B8%A0&limit=24',
}, category);
assert.equal(called.url, 'https://backend.example/api/resale/products?limit=24&kind=%EC%87%BC%EC%B8%A0');
assert.doesNotMatch(called.url, /__products/);

console.log('✅ Vercel 리세일 상품 검색 중계 경로 통과');
