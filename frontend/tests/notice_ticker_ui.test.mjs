/* 운영 공지 · 성별 요청 알림 · 상단 실시간 공지 (2026-10-02).
 *   돌리는 법:  node tests/notice_ticker_ui.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

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
globalThis.innerWidth = 1440; globalThis.innerHeight = 900;
globalThis.matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
globalThis.scrollTo = () => {};
globalThis.IntersectionObserver = class{ observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class{ observe(){} unobserve(){} disconnect(){} };

const NOW = new Date().toISOString();
const user = { id:7, username:'feedit01', email:'feedit01', nickname:'피딧회원', role:'user',
  styles:[], saved_count:0, vote_count:0, badges:{}, gender:null };
let items = [
  { id:31, kind:'PROFILE_GENDER', title:'성별을 알려 주세요.', body:'코디 입혀보기 모델과 추천 코디를 성별에 맞춰 드려요.',
    link:'', payload:{ action:'gender' }, read:false, created_at:NOW },
  { id:32, kind:'ADMIN_NOTICE', title:'점검 안내', body:'02:00~02:30\n챗봇 잠시 멈춤',
    link:'trend', payload:{ batch:'abc' }, read:false, created_at:NOW },
];
let tickers = [{ id:5, message:'가을 트렌드 리포트가 열렸어요', link:'trend' }];
const asked = [];
const reply = payload => ({ ok:true, status:200, text:async () => JSON.stringify(payload), json:async () => payload });
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url), method = (opts.method || 'GET').toUpperCase();
  asked.push({ u, method, body:opts.body });
  if(u.includes('/api/auth/me')) return reply({ status:'ok', data:{ authenticated:true, csrf_token:'csrf', user } });
  if(u.includes('/api/auth/announcements')) return reply({ status:'ok', data:{ items:tickers } });
  if(u.includes('/api/auth/gender')){
    const g = JSON.parse(opts.body).gender;
    items = items.filter(i => i.kind !== 'PROFILE_GENDER');
    return reply({ status:'ok', data:{ authenticated:true, user:{ ...user, gender:g } } });
  }
  if(u.includes('/api/auth/notifications')){
    if(method === 'GET') return reply({ status:'ok', data:{ items, unread:items.filter(i => !i.read).length,
      setting:{ enabled:true, kinds:{} } } });
    return reply({ status:'ok', data:{ read:1, unread:0 } });
  }
  return reply({ status:'empty', reason:'테스트 데이터 없음', data:null });
};

let pass = 0, fail = 0;
const t = async (n, f) => { try{ await f(); console.log('✅', n); pass++ }catch(e){ console.log('❌', n, '\n   ', e.message); fail++ } };
const wait = ms => new Promise(r => setTimeout(r, ms));

await import(`${root}/main.js`);
const profile = await import(`${root}/account/static/js/profile.js`);
const notify = await import(`${root}/account/static/js/notify.js`);
const ticker = await import(`${root}/app_shell/static/js/ticker.js`);
document.getElementById('jumpBtn').click();
await wait(200);

await t('상단 실시간 공지 — 헤더 아래 가운데 띠로 뜨고, 누르면 그 화면으로 간다', async () => {
  const el = document.getElementById('mTicker');
  assert.ok(el, '띠가 헤더 안에 붙는다');
  assert.ok(el.closest('.mHead'));
  assert.equal(el.hidden, false);
  assert.match(el.textContent, /가을 트렌드 리포트가 열렸어요/);
  el.querySelector('[data-tick-go="trend"]').click();
  await wait(30);
  assert.ok(document.getElementById('v-trend').classList.contains('on'), '트렌드 화면으로 이동');
});

await t('× 로 닫은 공지는 다시 뜨지 않고, 새 공지는 뜬다', async () => {
  document.querySelector('#mTicker [data-tick-close]').click();
  assert.equal(document.getElementById('mTicker').hidden, true);
  ticker.tickerPaint(tickers);
  assert.equal(document.getElementById('mTicker').hidden, true, '닫은 공지는 이 브라우저에서 다시 안 뜬다');
  ticker.tickerPaint([...tickers, { id:6, message:'새 공지', link:'' }]);
  const el = document.getElementById('mTicker');
  assert.equal(el.hidden, false);
  assert.match(el.textContent, /새 공지/);
  assert.doesNotMatch(el.textContent, /가을 트렌드/);
  ticker.tickerPaint([]);
  assert.equal(el.hidden, true, '내리면 사라진다');
});

await t('운영 공지 · 성별 요청은 알림함에 제 이름과 아이콘으로 뜬다', async () => {
  notify.notiRefresh();
  await wait(60);
  document.getElementById('notiBtn').click();
  await wait(30);
  const list = document.getElementById('notiList').textContent;
  assert.match(list, /성별을 알려 주세요/);
  assert.match(list, /점검 안내/);
  assert.match(list, /공지/);
  assert.match(list, /프로필/);
});

await t('성별 요청을 누르면 바로 고르는 창이 뜨고, 고르면 저장 · 알림이 내려간다', async () => {
  const row = [...document.querySelectorAll('#notiList .notiItem')].find(r => /성별을 알려/.test(r.textContent));
  assert.ok(row, '성별 요청 줄');
  row.querySelector('.notiOpen').click();
  await wait(60);
  const modal = document.getElementById('genderAskModal');
  assert.ok(modal.classList.contains('show'), '고르는 창이 뜬다');
  modal.querySelector('[data-gender="FEMALE"]').click();
  await wait(80);
  const sent = asked.find(a => a.u.includes('/api/auth/gender'));
  assert.ok(sent, '성별만 저장하는 주소로 보낸다');
  assert.deepEqual(JSON.parse(sent.body), { gender:'FEMALE' });
  assert.equal(profile.ME.gender, 'FEMALE', '입혀보기 · 코디가 쓰는 ME.gender 가 바로 바뀐다');
  assert.equal(modal.classList.contains('show'), false);
  document.getElementById('notiBtn').click();      /* 알림함을 다시 열면 */
  await wait(80);
  assert.ok(!/성별을 알려/.test(document.getElementById('notiList').textContent), '알림이 내려간다');
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
