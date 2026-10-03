/* 차트가 실데이터를 쓰는지, 없을 때 난수로 채우지 않는지.
 *
 * ★ node --check 로는 못 잡는다. gChart 를 gPaint 로 쪼개면서
 *   변수 하나만 밖에 남아도 ReferenceError 가 나는데, 문법 검사는 통과시킨다.
 *   그래서 실제로 그려 본다.
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><div id="c"></div>', { url: 'http://localhost/' });
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.Element = dom.window.Element;
globalThis.SVGElement = dom.window.SVGElement;
globalThis.getComputedStyle = dom.window.getComputedStyle;
/* 차트가 new CustomEvent('gwin') 을 쏜다 — Node 전역 CustomEvent 는 jsdom 요소가 받지 않는다 */
globalThis.CustomEvent = dom.window.CustomEvent;

let fetchReply = null;
/* 진짜 fetch 처럼 text() 를 준다. 코드가 text() → JSON.parse 로 읽기 때문이다
   (그래야 HTML 이 왔을 때 "JSON 이 아니다" 라고 말할 수 있다). */
globalThis.fetch = async (u) => {
  const body = typeof fetchReply === 'function' ? fetchReply(u) : fetchReply;
  return { ok: true, status: 200,
    text: async () => JSON.stringify(body),
    json: async () => body };
};

const live = await import('../trend/static/js/live_data.js');
const { gChart } = await import('../trend/static/js/chart_engine.js');

let pass = 0, fail = 0;
const t = async (n, f) => {
  try { await f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; }
};
const host = () => { document.body.innerHTML = '<div id="c"></div>'; return document.getElementById('c'); };
const CFG = (term) => ({ key: 'k', term, sets: [{ id: 'a', shape: 'rise', lo: 0, hi: 1 }] });

// 오늘 날짜로 90일치 만들기 — 날짜가 안 맞으면 seriesOf 가 null 을 준다
const days = (n) => {
  const out = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    out.push({ date: d.toISOString().slice(0, 10), mention: 10 + (i % 7), score: 50 });
  }
  return out;
};

await t('값이 있으면 실제로 그린다', async () => {
  fetchReply = { status: 'ok', data: { term: '발레코어', facet: 'STYLE', series: days(90) } };
  await live.prime('발레코어');
  const el = host();
  gChart(el, CFG('발레코어'));
  assert.equal(el.dataset.live, 'ok', '실데이터로 표시돼야 한다');
  assert.ok(el.querySelector('svg'), 'svg 가 그려져야 한다');
  assert.ok(!/측정 불가/.test(el.textContent));
});

await t('★ 값이 없으면 난수로 채우지 않고 측정 불가를 적는다', async () => {
  fetchReply = { status: 'empty', reason: '‘엄브로’ 은 사전에 있지만 최근 90일 안에 측정된 지표가 없습니다.' };
  await live.prime('엄브로');
  const el = host();
  gChart(el, CFG('엄브로'));
  assert.equal(el.dataset.live, 'unavailable');
  assert.ok(/측정 불가/.test(el.textContent));
  assert.ok(/사전에 있지만/.test(el.textContent), '왜 없는지 그대로 보여야 한다');
  assert.ok(!el.querySelector('path'), '선을 그리면 안 된다');
});

await t('★ DB 가 안 붙으면 그 사실을 말한다 (값 없음과 다르게)', async () => {
  fetchReply = { status: 'error', reason: 'AWS RDS 에 연결하지 못했습니다 (ETIMEDOUT).' };
  await live.prime('키르시');
  const el = host();
  gChart(el, CFG('키르시'));
  assert.equal(el.dataset.live, 'unavailable');
  assert.ok(/연결하지 못했습니다/.test(el.textContent));
  assert.ok(/연결이 되면 자동으로/.test(el.textContent), '고치면 된다는 걸 알려야 한다');
});

await t('term 을 안 주는 장식용 차트는 예전처럼 돈다', async () => {
  const el = host();
  gChart(el, { key: 'deco', sets: [{ id: 'a', shape: 'rise', lo: 0, hi: 1 }] });
  assert.equal(el.dataset.live, 'seeded');
  assert.ok(el.querySelector('svg'), '기존 화면이 깨지면 안 된다');
});

await t('★ 계열 일부만 있으면 섞어 그리지 않는다', async () => {
  fetchReply = { status: 'ok',
    data: { term: '새틴', facet: 'MATERIAL', series: days(90) },
    unavailable: { fields: ['temp'], reason: 'temp 는 RDS 에 없습니다.' } };
  await live.prime('새틴');
  const el = host();
  gChart(el, { key: 'k', term: '새틴',
    sets: [{ id: 'a', field: 'mention' }, { id: 'b', field: 'temp' }] });
  assert.equal(el.dataset.live, 'partial');
  assert.ok(/측정 불가/.test(el.textContent));
  assert.ok(/temp 는 RDS 에 없습니다/.test(el.textContent));
});

await t('없는 날은 0 으로 떨어뜨리지 않는다', async () => {
  const sparse = days(90).filter((_, i) => i % 3 === 0);   // 사흘에 하루만 관측
  fetchReply = { status: 'ok', data: { term: '나일론', facet: 'MATERIAL', series: sparse } };
  await live.prime('나일론');
  const s = live.seriesOf('나일론', { points: 30, step: 'd', field: 'mention' });
  assert.ok(s, '값이 나와야 한다');
  assert.equal(s.length, 30);
  assert.ok(s.every((v) => v >= 0 && v <= 1), '0~1 범위여야 한다');
  const zeros = s.filter((v) => v === 0).length;
  assert.ok(zeros <= 6, `빈 날을 0 으로 채우면 안 된다 (0이 ${zeros}개)`);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
