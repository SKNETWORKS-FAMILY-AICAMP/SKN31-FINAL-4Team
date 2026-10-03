/* 홈 HOT TREND TOP 10 · LIVE 투표 TOP 10 — 자동 갱신 (2026-10-01)
 *
 * 왜 있나
 *   홈의 트렌드 TOP 10 이 2026-09-08 순위에 멈춰 있었다. 서버(/api/trend?rank=hot)가
 *   한 번 적재한 장기 이력 버전을 읽었고, 화면도 페이지를 열 때 한 번만 읽었다.
 *   살!말? 모드의 투표 TOP 10 은 모드를 처음 켤 때 한 번 읽고 끝이었다.
 *
 *   · 트렌드 TOP 10 — 30분마다 확인, 기준일이나 순위가 바뀌면 다시 그린다 (지표는 하루 한 번 바뀐다)
 *   · 투표 TOP 10   — 살!말? 모드에 들어올 때마다, 20초마다, 내가 투표한 직후 다시 읽는다
 *
 * 실행:  node tests/home_hot_refresh.test.mjs
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://localhost:5173/', pretendToBeVisual: true });
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node',
                 'HTMLElement','CustomEvent','Event','KeyboardEvent','MouseEvent','File','Blob'])
  globalThis[k] = k === 'window' ? dom.window : dom.window[k];
globalThis.MutationObserver = dom.window.MutationObserver || class { observe(){} disconnect(){} takeRecords(){ return [] } };
globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
globalThis.cancelAnimationFrame = (h) => clearTimeout(h);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
globalThis.scrollTo = () => {};
globalThis.innerWidth = 1440;
globalThis.innerHeight = 900;
globalThis.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.location = dom.window.location;
globalThis.localStorage = dom.window.localStorage;

/* ── 가짜 서버 ── */
const hotDay = (asOf, terms) => ({ status: 'ok', data: {
  as_of: asOf, rule: '…',
  basis: { source: 'ALL', metric_version: 'feedit-unified-text-v1', refresh: 'daily' },
  rising: terms.map((t, i) => ({ term: t, facet: 'ITEM', change_pct: 90 - i * 10, temp: 70, date: asOf })),
  falling: [] } });
const cards = (rows) => ({ status: 'ok', data: { items: rows.map(([id, title, total, buy]) => ({
  id, title, closed: false, vote_summary: { total, buy_pct: buy } })) } });

let HOT = hotDay('2026-09-29', ['니트', '플리스']);
let CARDS = cards([[1, '살로몬 XT-6', 12, 75], [2, '아크테릭스 베타', 5, 40]]);
const calls = [];
globalThis.fetch = async (u, opt = {}) => {
  const url = String(u);
  /* 상단 실시간 공지(ticker.js)도 화면이 보이면 다시 묻는다 — 이 시험이 세는 것(HOT · 살말)과는 따로다 */
  if (url.startsWith('/api/auth/announcements')) {
    const text = JSON.stringify({ status: 'ok', data: { items: [] } });
    return { ok: true, status: 200, text: async () => text, json: async () => JSON.parse(text) };
  }
  calls.push({ url, cache: opt.cache });
  let body = null;
  if (url.startsWith('/api/trend?rank=hot')) body = HOT;
  else if (url.startsWith('/api/salmal/cards')) body = CARDS;
  else if (url.startsWith('/api/auth/me')) body = { status: 'ok', data: { csrf_token: 'test' } };
  else if (url.startsWith('/api/auth/vote')) body = { status: 'ok', data: { vote_count: 3 } };
  if (!body) throw new Error('offline');
  const text = JSON.stringify(body);
  return { ok: true, status: 200, text: async () => text, json: async () => JSON.parse(text) };
};

let pass = 0, fail = 0;
const t = async (n, f) => {
  try { await f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; }
};
const wait = (ms = 0) => new Promise(r => setTimeout(r, ms));
/* 시간을 앞으로 돌린다 — 실제로 30분을 기다리지 않는다 */
const realNow = Date.now;
let skew = 0;
Date.now = () => realNow() + skew;

await import(`${F}/main.js`);
const C = await import(`${F}/home/static/js/chat.js`);
const A = await import(`${F}/account/static/js/account_api.js`);
document.body.dataset.view = 'home';
const list = () => document.querySelector('#hotList');
const names = () => [...list().querySelectorAll('.k')].map(e => e.textContent);
const visible = () => document.dispatchEvent(new dom.window.Event('visibilitychange'));

if (!list().querySelector('button')) C.hotBuild();     /* 라우터가 아직 안 불렀으면 직접 */
await wait(30);

await t('트렌드 TOP 10 이 매일 갱신 기준으로 그려진다', () => {
  assert.deepEqual(names().slice(0, 2), ['니트', '플리스']);
  assert.match(list().querySelector('.hotNote').textContent, /2026-09-29 기준 · 전 플랫폼 합산 .* 매일 갱신/);
});

await t('30분 안에는 다시 읽지 않는다', async () => {
  const before = calls.filter(c => c.url.startsWith('/api/trend?rank=hot')).length;
  HOT = hotDay('2026-09-30', ['패딩', '니트']);
  skew += 5 * 60 * 1000;
  visible(); await wait(30);
  assert.equal(calls.filter(c => c.url.startsWith('/api/trend?rank=hot')).length, before);
  assert.deepEqual(names().slice(0, 2), ['니트', '플리스']);
});

await t('★ 30분이 지나 돌아오면 다음 날 순위로 바뀐다', async () => {
  skew += 30 * 60 * 1000;
  visible(); await wait(30);
  assert.deepEqual(names().slice(0, 2), ['패딩', '니트']);
  assert.match(list().querySelector('.hotNote').textContent, /2026-09-30 기준/);
});

await t('살!말? 모드에 들어오면 투표 TOP 10 을 새로 읽는다 (캐시 없이)', async () => {
  C.smSwitch(true, null, true);
  await wait(1100);
  assert.deepEqual(names().slice(0, 2), ['살로몬 XT-6', '아크테릭스 베타']);
  const last = calls.filter(c => c.url.startsWith('/api/salmal/cards')).pop();
  assert.equal(last.cache, 'no-store');
});

await t('★ 투표하면 바로 다시 읽는다', async () => {
  CARDS = cards([[2, '아크테릭스 베타', 30, 60], [1, '살로몬 XT-6', 12, 75]]);
  await A.saveVote({ cardKey: 'k2', title: '아크테릭스 베타', choice: 'BUY' });
  await wait(30);
  assert.deepEqual(names().slice(0, 2), ['아크테릭스 베타', '살로몬 XT-6']);
});

await t('★ 살!말? 모드를 보는 동안 20초마다 다시 읽는다', async () => {
  CARDS = cards([[3, '뉴발란스 993', 41, 80], [2, '아크테릭스 베타', 30, 60]]);
  skew += 21 * 1000;
  visible(); await wait(30);
  assert.equal(names()[0], '뉴발란스 993');
});

await t('다른 화면에 있으면 읽지 않는다', async () => {
  const before = calls.length;
  document.body.dataset.view = 'trend';
  skew += 60 * 60 * 1000;
  visible(); await wait(30);
  assert.equal(calls.length, before);
  document.body.dataset.view = 'home';
});

Date.now = realNow;
console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
