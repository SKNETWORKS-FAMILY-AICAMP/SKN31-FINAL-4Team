/* 내 피드 · 금주의 리포트 — 실데이터 연결 확인.
 *
 * ★ 무엇을 보나
 *   · 내 피드 화제성 = /api/trend 트렌드 온도, 단계 = /api/lifecycle, 7일 언급량 = mention 합
 *   · 받기 전에는 숫자를 지어내지 않는다('–'), 지표가 없으면 사유를 적는다
 *   · 리포트 기간은 오늘 날짜로 계산, 활동 지표·요일별 활동·취향 지분은 /api/auth/weekly-report
 *   · '같이 지켜볼 스타일'은 태동·확산 먼저, 그다음 온도 순
 *
 * 돌리는 법:  node tests/trend_feed_report.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const W = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8')
  .replace(/<script[\s\S]*?<\/script>/g, '');
const dom = new JSDOM(html, { url: 'http://localhost:5173/', pretendToBeVisual: true });
globalThis.window = dom.window;
const winKeys = new Set();
for (let o = dom.window; o && o !== Object.prototype; o = Object.getPrototypeOf(o))
  Object.getOwnPropertyNames(o).forEach(k => winKeys.add(k));
for (const k of winKeys) {
  if (k in globalThis) continue;
  try { const v = dom.window[k]; globalThis[k] = typeof v === 'function' && !/^[A-Z]/.test(k) ? v.bind(dom.window) : v; } catch (e) {}
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
}
for (const k of ['navigator','localStorage','sessionStorage','location','history','Event','CustomEvent','EventTarget'])
  try { Object.defineProperty(globalThis, k, { value: dom.window[k], configurable: true, writable: true }); } catch (e) {}
globalThis.matchMedia ||= () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
dom.window.matchMedia ||= globalThis.matchMedia;

/* 스타일별 가짜 RDS — 없는 스타일은 empty */
const LAST = '2026-09-10';
const series = (temp, m) => { const o = []; for (let i = 20; i >= 0; i--) {
  const d = new Date(LAST + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - i);
  o.push({ date: d.toISOString().slice(0, 10), mention: i < 7 ? m : 2, temp: i >= 7 ? temp - 5 : temp, momentum: 60, level: 50 });
} return o; };
const DB = {
  '블록코어': { temp: 81, m: 10, stage: '확산' },
  '아메카지': { temp: 40, m: 3, stage: '쇠퇴' },
  '고프코어': { temp: 90, m: 5, stage: '정점' },
  '바이크코어': { temp: 55, m: 4, stage: '태동' },
  '클래식': { temp: 70, m: 4, stage: '확산' },
};
const ok = data => ({ ok: true, status: 200, text: async () => JSON.stringify({ status: 'ok', data }), json: async () => ({ status: 'ok', data }) });
const empty = { ok: true, status: 200, text: async () => JSON.stringify({ status: 'empty', reason: '측정된 자료가 없습니다.' }), json: async () => ({ status: 'empty' }) };
globalThis.fetch = async (url) => {
  const u = new URL(String(url), 'http://x');
  const term = u.searchParams.get('term') || '';
  const row = DB[term];
  if (u.pathname === '/api/trend' && term) return row ? ok({ term, facet: 'STYLE', series: series(row.temp, row.m) }) : empty;
  if (u.pathname === '/api/lifecycle') return row ? ok({ term, stage: row.stage, temp: row.temp }) : empty;
  if (u.pathname === '/api/auth/me') return ok({ authenticated: true, csrf_token: 't', user: null });
  if (u.pathname === '/api/auth/weekly-report') return ok(REPORT);
  if (u.pathname === '/api/v1/magazines') return { ok: true, status: 200, json: async () => ({ ok: true, term,
    found: true, articles: [{ magazine: '보그 코리아', title: '발레코어, 다시 무대 밖으로', url: 'https://www.vogue.co.kr/2026/09/01/a' },
                            { magazine: '가짜', title: '위험한 주소', url: 'javascript:alert(1)' }] }) };
  return empty;
};

/* 금주의 리포트 활동 지표 — activity_views.weekly_report 응답 모양 */
const REPORT = {
  week: { start: '2026-09-14', end: '2026-09-20' },
  search: { keywords: 5, count: 9, prev_keywords: 2, delta: 3, top: { label: '발레코어', count: 4, facet: '스타일' } },
  vote: { count: 2, prev: 3, delta: -1, total: 6 },
  saved: { new: 1, total: 7 },
  chat: { minutes: 13, sessions: 2, avg_minutes: 6 },
  activity: { days: [1, 0, 4, 2, 0, 0, 0], hours: Object.assign(Array(24).fill(0), { 21: 3, 22: 2 }) },
  taste: { items: [{ label: '발레코어', share: 60, delta: 10 }, { label: '고프코어', share: 40, delta: null }],
           signals: 5, prev_signals: 2, new_style: '고프코어' },
  has_activity: true,
};

let pass = 0, fail = 0;
const t = async (n, f) => { try { await f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.stack.split('\n').slice(0, 3).join('\n    ')); fail++; } };
const wait = () => new Promise(r => setTimeout(r, 30));

await import(`${W}/main.js`);
const { ME } = await import(`${W}/account/static/js/profile.js`);
const D = await import(`${W}/trend/static/js/dispatch.js`);
const body = () => document.getElementById('trBody');
ME.styles.clear(); ['block', 'ameka', 'street'].forEach(x => ME.styles.add(x));
ME.saved = 7; ME.votes = 3;

await t('내 피드 — 받기 전에는 숫자를 지어내지 않는다', () => {
  D.trRender('myfeed');
  assert.equal(body().querySelector('.tpBigDeg').textContent, '–');
  assert.match(body().querySelector('#tpHero').textContent, /불러오는 중/);
});

await t('내 피드 화제성 = 트렌드 온도 · 7일 전 대비 · 수명주기 단계', async () => {
  await wait();
  const h = body().querySelector('#tpHero').textContent;
  assert.match(body().querySelector('.tpBigDeg').textContent, /^81°$/);
  assert.match(h, /▲ 5° 지난주 대비/);
  assert.match(h, /확산/);
  assert.match(h, /최근 7일 언급 70건\(지난주 14건\)/);
});

await t('7일 언급량 카드 — 지표가 없는 스타일(스트릿웨어)은 – 로 남는다', () => {
  const g = body().querySelector('#tpSignal').textContent;
  assert.match(body().querySelector('.tpSignalNum').textContent, /^91/);   // 70 + 21
  assert.match(g, /블록코어 70건 \+56/);
  assert.match(g, /스트릿웨어 –/);
});

await t('브리핑 — 올라가는 구간(태동·확산) 수를 센다', () => {
  const b = body().querySelector('#tpBrief').textContent;
  assert.match(b, /블록코어는 온도 81°로 확산 구간/);
  assert.match(b, /스트릿웨어는 지표 없음/);
  assert.match(body().querySelector('.tpBriefScore').textContent, /^1/);
});

await t('리포트 — 기간 · 받기 전에는 키워드 · 활동 지표를 지어내지 않는다', async () => {
  D.trRender('report');
  const r = body().querySelector('#wkReport').textContent;
  assert.match(r, /\d{4}\.\d{2} · W\d · \d+\/\d+ – \d+\/\d+/);
  assert.match(body().querySelector('#wkLine').textContent, /확인하고 있습니다/);
  const m = [...body().querySelectorAll('.wkMetric strong')].map(e => e.textContent);
  /* ★ 2026-09-19 — 받기 전에는 숫자 자리에 뼈대(WK_SKEL)만 둔다. 값이 오면 카운트업으로 굴러 올라간다.
     지어낸 숫자가 없으면 된다 — 단위만 남는다. */
  assert.deepEqual(m, ['개', '개', '표', '분']);
  assert.ok(m.every(x => !/\d/.test(x)), '받기 전에 숫자를 지어내면 안 된다');
  await wait();
});

await t('리포트 — 한 줄 요약 · 히어로 · 영상 · 웹매거진이 모두 가장 많이 검색한 키워드(발레코어)', async () => {
  await wait();
  assert.match(body().querySelector('#wkLine').textContent, /가장 관심 있었던 키워드는 발레코어입니다/);
  assert.match(body().querySelector('#wkHero h3').textContent, /^발레코어/);
  assert.match(body().querySelector('#wkHero .wkState').textContent, /가장 많이 검색한 키워드/);
  assert.equal(body().querySelector('#wkVideoBadge').textContent, '발레코어');
  assert.match(body().querySelector('#wkMagCard .wkCardHead em').textContent, /^발레코어$/);
  // 스타일 10종 밖의 키워드는 '이 스타일 더 보기' 대신 언급량 · 온도로 보낸다
  const btn = body().querySelector('#wkHero [data-wk-kw]');
  assert.equal(btn.dataset.wkKw, '발레코어');
});

await t('리포트 — 활동 지표 4칸 = weekly-report 실기록', () => {
  const m = [...body().querySelectorAll('.wkMetric')].map(e => e.textContent);
  assert.match(m[0], /검색한 키워드5개\+3 · 지난주 대비/);
  assert.match(m[1], /새로 찜한 것1개총 7개 추적 중/);
  assert.match(m[2], /살!말\? 투표2표-1 · 지난주 대비/);
  assert.match(m[3], /트렌드 분석13분평균 사용 시간 6분/);
});

await t('리포트 — 요일별 활동 · 활동 시간대 · 취향 지분(지난주 대비 %p)', () => {
  const days = body().querySelector('#wkDaysCard').textContent;
  assert.match(days, /PEAK · 21시 – 23시/);
  assert.match(days, /수요일에 가장 많이 활동/);
  assert.equal(body().querySelector('#wkDaysCard .wkDay.peak .l').textContent, '수');
  const taste = body().querySelector('#wkTasteCard').textContent;
  assert.match(taste, /발레코어60%\+10%p/);
  assert.match(taste, /고프코어40%비교 전/);
  assert.match(taste, /새로 유입된 축은 고프코어/);
});

await t('추천 웹매거진 — 가장 관심 있던 키워드로 웹 검색한 기사에 바로 연결한다', async () => {
  await wait();
  const card = body().querySelector('#wkMagCard');
  assert.match(card.querySelector('.wkCardHead em').textContent, /^발레코어$/);
  const links = [...card.querySelectorAll('a.wkMagRow')];
  assert.equal(links.length, 1);                                   // http(s) 가 아닌 주소는 뺀다
  assert.equal(links[0].getAttribute('href'), 'https://www.vogue.co.kr/2026/09/01/a');
  assert.match(links[0].textContent, /보그 코리아발레코어, 다시 무대 밖으로/);
  assert.ok(!card.innerHTML.includes('google.com/search'));
});

await t('리포트 — 이번 주 검색 기록이 없으면 첫 관심 스타일로 대신하고 그렇다고 적는다', async () => {
  const saved = REPORT.search.top; REPORT.search.top = null;
  D.trRender('report'); await wait(); await wait();
  assert.match(body().querySelector('#wkLine').textContent, /검색 기록이 없어 관심 스타일 블록코어의 흐름/);
  assert.match(body().querySelector('#wkHero h3').textContent, /^블록코어/);
  assert.ok(body().querySelector('#wkHero [data-fit-style="block"]'));
  const l = body().querySelector('#wkHeroLedger').textContent;
  assert.match(l, /트렌드 온도81°/);
  assert.match(l, /수명주기 단계확산/);
  REPORT.search.top = saved;
});

await t('같이 지켜볼 스타일 — 태동·확산 먼저, 그다음 온도 순 (지표 없는 스타일 제외)', () => {
  const names = [...body().querySelectorAll('#wkNextGrid .wkNextCard b')].map(b => b.textContent);
  assert.deepEqual(names, ['클래식', '바이크코어', '고프코어']);
  assert.match(body().querySelector('#wkNextGrid').textContent, /확산 · 70°/);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
