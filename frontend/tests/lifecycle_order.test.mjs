/* 수명주기 — 발주 판별 (METRIC-002, 2026-09-27).
 *
 * 서버(/api/lifecycle)가 준 order_timing 을 그대로 적는지, 없으면(판정 보류)
 * 지어내지 않는지 실제로 그려 본다.
 *
 * 돌리는 법:  node tests/lifecycle_order.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8'), { url: 'http://localhost:5173/' });
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node',
                 'HTMLElement','CustomEvent','KeyboardEvent','MouseEvent'])
  globalThis[k] = k === 'window' ? dom.window : dom.window[k];
globalThis.MutationObserver = dom.window.MutationObserver;
globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
globalThis.cancelAnimationFrame = (h) => clearTimeout(h);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
globalThis.scrollTo = () => {};
globalThis.innerWidth = 1280; globalThis.innerHeight = 800;
globalThis.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.location = dom.window.location;
globalThis.localStorage = dom.window.localStorage;

const today = new Date();
const iso = (d) => d.toISOString().slice(0, 10);
const series = Array.from({ length: 40 }, (_, i) => {
  const d = new Date(today); d.setDate(d.getDate() - (39 - i));
  return { date: iso(d), level: 50, ma28: 50, momentum: 40, temp: 55, mention: 10 };
});
let LIFE = null;
const reply = (obj) => { const body = JSON.stringify(obj);
  return { ok: true, status: 200, text: async () => body, json: async () => JSON.parse(body) }; };
globalThis.fetch = async (u) => {
  const url = decodeURIComponent(String(u));
  if (url.includes('/api/lifecycle')) return reply(LIFE);
  if (url.includes('/api/dictionary'))
    return reply({ status: 'ok', data: [{ label: '엄브로', facet: '브랜드', kind: 'brand', en: 'UMBRO' },
                                       { label: '키르시', facet: '브랜드', kind: 'brand', en: 'KIRSH' }], total: 2 });
  return reply({ status: 'empty', reason: '적재 전입니다.' });
};

let pass = 0, fail = 0;
const t = async (n, f) => {
  try { await f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; }
};
const wait = (ms = 60) => new Promise((r) => setTimeout(r, ms));

await import(`${F}/main.js`);
const S = await import(`${F}/style/static/js/search.js`);
const D = await import(`${F}/trend/static/js/dispatch.js`);
await wait();

const base = (extra) => ({ status: 'ok', data: {
  label: '엄브로', term: '엄브로', facet: 'brand', as_of: iso(today), data_as_of: iso(today),
  points: 40, stage: '쇠퇴', progress: 80, level: 50, momentum: 40, temp: 55, inflow_pct: -12,
  weekly_temp: [{ weeks_ago: 0, temp: 55 }], series, sales_series: [], rule: '규칙', ...extra } });
/* 같은 주소는 캐시가 먹으므로 시험마다 다른 브랜드로 묻는다 */
const render = async (brand) => {
  S.FS.pick = { 브랜드: [brand] };
  D.trRender('life'); await wait(); D.trRender('life'); await wait();
  return document.getElementById('trBody');
};

await t('서버의 발주 판별을 그대로 적는다', async () => {
  LIFE = base({ order_timing: { code: 'AVOID', label: '발주 비추천', reason: '최고점을 지나 내려가는 중입니다.' } });
  const body = await render('엄브로');
  const row = body.querySelector('.lcOrder');
  assert.ok(row, '발주 관점 줄이 없다');
  assert.equal(row.dataset.order, 'AVOID');
  assert.match(row.textContent, /발주 관점 · 발주 비추천/);
  assert.match(row.textContent, /최고점을 지나/);
});

await t('판별이 없으면(판정 보류 · 옛 서버) 발주 문구를 지어내지 않는다', async () => {
  LIFE = base({ label: '키르시', term: '키르시', order_timing: null });
  const body = await render('키르시');
  assert.match(body.textContent, /쇠퇴/, '화면이 새 응답으로 그려지지 않았다');
  assert.equal(body.querySelector('.lcOrder'), null);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
