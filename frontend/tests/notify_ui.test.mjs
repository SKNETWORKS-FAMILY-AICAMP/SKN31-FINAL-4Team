/* 알림 — 헤더 아이콘 · 패널 · 읽음 · 알림 설정 · 사전 등재 요청을 실제로 실행해 본다.
   (AGENTS §5 — 인라인/모듈 JS 는 jsdom 으로 돌려 봐야 안다.) */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost:5173/' });
/* 사용자가 보고 있는 탭처럼 — 가려진 탭에서는 토스트를 모아 두기만 한다 (notify.js) */
Object.defineProperty(dom.window.document, 'hidden', { configurable:true, get:() => false });
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent','Event'])
  globalThis[key] = key === 'window' ? dom.window : dom.window[key];
/* notify.js 가 본문을 기다릴 때 쓴다 — jsdom 전역에 없어서 이 시험들이 통째로 죽어 있었다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
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

const asked = [];
const user = { id:7, username:'feedit01', email:'feedit01', nickname:'피딧회원', initial:'피',
  birth_date:'2000-01-02', height:170, weight:60, avatar:0, role:'user', job:'', major:'',
  bio:'', styles:[], saved_count:0, vote_count:0, badges:{} };
const reply = payload => ({ ok:true, status:200, text:async () => JSON.stringify(payload),
  json:async () => payload });

const NOW = new Date().toISOString();
let items = [
  { id:11, kind:'PRICE_DROP', title:'찜한 상품 2개가 내려갔어요.', body:'A 20% · B 12%',
    link:'mypage', payload:{}, read:false, created_at:NOW },
  { id:12, kind:'VOTE_RESULT', title:"10명 중 7명이 '살!'이라고 했어요.", body:'스퀘어 토 로퍼',
    link:'salmal', payload:{}, read:true, created_at:NOW },
];
/* 6개 제한을 확인하려고 뒤에 다섯 건을 더 붙인다 (모두 7건) */
for(let i = 0; i < 5; i++)
  items.push({ id:20 + i, kind:'BADGE', title:`뱃지 ${i}`, body:'', link:'mypage',
    payload:{}, read:true, created_at:NOW });
const setting = { enabled:true, kinds:{ PRICE_DROP:true, VOTE_RESULT:true, WEEKLY_REPORT:true,
  BADGE:true, TERM_ADDED:true } };

globalThis.fetch = async (url, opts = {}) => {
  const u = String(url), method = (opts.method || 'GET').toUpperCase();
  asked.push({ url:u, method, body:opts.body });
  if(u.includes('/api/auth/logout')) return reply({ status:'ok', data:{ authenticated:false } });
  if(u.includes('/api/auth/me')) return reply({ status:'ok', data:{ authenticated:true, csrf_token:'csrf', user } });
  if(u.includes('/api/auth/notification-settings')) return reply({ status:'ok', data:setting });
  if(u.includes('/api/auth/notifications')){
    if(method === 'GET') return reply({ status:'ok', data:{ items, unread:1, setting } });
    return reply({ status:'ok', data:{ read:1, unread:0 } });
  }
  if(u.includes('/api/auth/term-request'))
    return reply({ status:'ok', data:{ already:false, created:true, id:3, term:'블로코어', status:'PENDING' } });
  if(u.includes('/api/salmal/feedback')) return reply({ status:'ok', data:{ pending:[
    { card_id:5, title:'스퀘어 토 로퍼', image_url:'', vote_summary:{ buy_pct:70, total:10 }, feedback:null } ], done:[] } });
  if(u.includes('/api/auth/saved')) return reply({ status:'ok', data:{ items:[], count:0 } });
  if(u.includes('/api/dictionary')) return reply({ status:'ok', data:[] });
  return reply({ status:'empty', reason:'테스트 데이터 없음', data:null });
};

await import(`${root}/main.js`);
const router = await import(`${root}/app_shell/static/js/router.js`);
const profile = await import(`${root}/account/static/js/profile.js`);
document.getElementById('jumpBtn').click();
await new Promise(r => setTimeout(r, 120));

/* ① 로그인 상태면 알림 아이콘이 헤더에 뜬다. 닉네임 왼쪽 프로필 원은 없다. */
assert.equal(profile.AUTH.in, true, '세션 복구로 로그인 상태가 돼야 한다');
assert.equal(document.getElementById('notiWrap').hidden, false, '로그인하면 알림 아이콘이 보인다');
assert.equal(document.querySelectorAll('#mAuthBtn .meAv').length, 0, '닉네임 왼쪽 프로필 원은 없앴다');
assert.ok(document.getElementById('mAuthBtn').textContent.includes('피딧회원'));
const bell = document.getElementById('notiBtn');
assert.ok(bell.querySelector('svg'), '알림은 이모지가 아니라 아이콘(svg)이다');
assert.ok(document.getElementById('mNav').compareDocumentPosition(bell) & 4 ||
  document.getElementById('mAuthBtn').compareDocumentPosition(bell) & 4,
  '알림 아이콘은 닉네임 뒤(오른쪽)에 온다');

/* ② 안 읽은 알림이 있으면 점이 뜬다 */
assert.equal(document.getElementById('notiDot').hidden, false, '안 읽은 알림이 있으면 점이 뜬다');

/* ②-b 로그인하면 안 읽은 알림이 오른쪽 위 토스트로 뜬다 (2026-09-19)
   본문(mainmode)에 들어온 뒤 600ms 있다가 뜬다 — 그만큼 기다려 준다 (notify.js waitForMain) */
await new Promise(r => setTimeout(r, 760));
const toasts = document.querySelectorAll('#notiToasts .notiToast');
assert.equal(toasts.length, 1, '안 읽은 알림 1건이 토스트로 뜬다');
assert.ok(toasts[0].textContent.includes('찜한 상품 2개가 내려갔어요.'), '토스트에 제목이 보인다');
toasts[0].querySelector('.ntX').dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));

/* ③ 아이콘을 누르면 패널이 열리고 목록이 그려진다 */
bell.dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 60));
assert.ok(document.getElementById('notiPanel').classList.contains('on'), '패널이 열린다');
const rows = document.querySelectorAll('#notiList .notiItem');
assert.equal(rows.length, 7, '받은 알림 수만큼 그린다');
assert.ok(rows[0].classList.contains('unread'), '안 읽은 것은 표시가 남는다');
assert.ok(rows[0].textContent.includes('찜한 상품 2개가 내려갔어요.'));
assert.ok(rows[0].textContent.includes('찜한 상품 변동'), '종류 이름을 같이 보여 준다');

/* ③-b 6개가 넘으면 스크롤로 넘긴다 */
const list = document.getElementById('notiList');
assert.ok(list.classList.contains('scrolls'), '6개가 넘으면 스크롤이 생긴다');

/* ④ 알림 본문을 누르면 읽음으로 바꾸고 그 화면으로 간다 */
rows[0].querySelector('.notiOpen').dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 60));
const read = asked.find(a => a.url.includes('/api/auth/notifications') && a.method === 'POST');
assert.ok(read, '읽음 처리를 서버에 알린다');
assert.equal(JSON.parse(read.body).op, 'read');
assert.equal(JSON.parse(read.body).id, 11);
assert.equal(document.getElementById('notiDot').hidden, true, '다 읽으면 점이 사라진다');
/* 2026-09-19 — 종류별로 갈 곳이 정해졌다: 가격 하락은 트렌드 분석 › 찜한 키워드 */
await new Promise(r => setTimeout(r, 60));
assert.equal(document.body.dataset.view, 'trend', '가격 하락 알림은 트렌드 분석으로 간다');

/* ⑤ 휴지통 — 한 건 삭제. 지운 줄 알았는데 남아 있으면 안 되므로 서버에도 보낸다 */
router.goView('home');
document.getElementById('notiBtn').dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 60));
const first = document.querySelector('#notiList .notiItem');
const firstId = Number(first.dataset.id);
assert.ok(first.querySelector('.notiDel svg'), '알림마다 휴지통 아이콘이 있다');
first.querySelector('.notiDel').dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 60));
const del = asked.filter(a => a.url.includes('/api/auth/notifications') && a.method === 'POST')
  .map(a => JSON.parse(a.body)).find(b => b.op === 'delete');
assert.ok(del, '삭제를 서버에 알린다');
assert.equal(del.id, firstId);
assert.equal(document.querySelectorAll('#notiList .notiItem').length, 6, '지운 알림은 목록에서 빠진다');
assert.equal(document.getElementById('notiList').classList.contains('scrolls'), false,
  '6개가 되면 스크롤이 없어진다');

/* ⑥ 모두 삭제 */
document.getElementById('notiDelAll').dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 60));
const delAll = asked.filter(a => a.url.includes('/api/auth/notifications') && a.method === 'POST')
  .map(a => JSON.parse(a.body)).find(b => b.op === 'delete_all');
assert.ok(delAll, '모두 삭제를 서버에 알린다');
assert.equal(document.querySelectorAll('#notiList .notiItem').length, 0);
assert.ok(document.getElementById('notiList').textContent.includes('새 알림이 없어요'));
assert.equal(document.getElementById('notiList').textContent.includes('여기에 쌓여요'), false,
  '빈 화면 설명 문구는 뺐다');

/* ⑦ 알림 설정 — 닉네임 메뉴가 아니라 알림 패널 아래에서만 연다 */
assert.equal(document.getElementById('menuNotiSet'), null,
  "닉네임 메뉴에서 '알림 설정'은 뺐다");
document.getElementById('notiSetLink').dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 60));
const modal = document.getElementById('notiSetModal');
assert.ok(modal.classList.contains('on'), '알림 설정 모달이 열린다');
assert.equal(document.getElementById('notiSetAll').checked, true, '전체 알림 스위치가 서버 값을 따른다');
const kinds = document.querySelectorAll('#notiSetKinds .notiSw');
assert.equal(kinds.length, 7, '구현한 알림 7종을 종류별로 끌 수 있다 (2026-09-19 직업 인증 결과 · 살말 새 댓글 추가)');
assert.deepEqual([...kinds].map(k => k.dataset.kind),
  ['PRICE_DROP','VOTE_RESULT','WEEKLY_REPORT','BADGE','TERM_ADDED','JOB_REVIEW','VOTE_COMMENT']);

/* 한 종류만 끄고 저장 */
kinds[0].checked = false;
document.getElementById('notiSetSave').dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
await new Promise(r => setTimeout(r, 80));
const saved = asked.find(a => a.url.includes('/api/auth/notification-settings') && a.method === 'POST');
assert.ok(saved, '설정을 서버에 저장한다');
const body = JSON.parse(saved.body);
assert.equal(body.enabled, true);
assert.equal(body.kinds.PRICE_DROP, false, '끈 종류가 그대로 간다');
assert.equal(body.kinds.BADGE, true);

/* 전체를 끄면 종류별 칸이 흐려진다 */
const allSw = document.getElementById('notiSetAll');
allSw.checked = false;
allSw.dispatchEvent(new dom.window.Event('change', { bubbles:true }));
assert.ok(document.getElementById('notiSetKinds').classList.contains('off'));

modal.classList.remove('on');

/* ⑧ 2026-09-19 — 계정 메뉴와 알림창은 한 번에 하나만 */
const click = el => el.dispatchEvent(new dom.window.MouseEvent('click', { bubbles:true }));
click(document.getElementById('notiBtn'));
assert.ok(document.getElementById('notiPanel').classList.contains('on'), '알림창이 열린다');
click(document.getElementById('mAuthBtn'));
assert.ok(document.getElementById('acctMenu').classList.contains('on'), '계정 메뉴가 열린다');
assert.equal(document.getElementById('notiPanel').classList.contains('on'), false, '계정 메뉴를 열면 알림창이 닫힌다');
click(document.getElementById('notiBtn'));
assert.ok(document.getElementById('notiPanel').classList.contains('on'));
assert.equal(document.getElementById('acctMenu').classList.contains('on'), false, '알림창을 열면 계정 메뉴가 닫힌다');
click(document.getElementById('notiBtn'));

/* ⑨ 마감 알림 → 살말로 가지 않고 피드백 창만. 만족도(1~5)는 없다. 카드 정보를 누르면 그 카드로 */
router.goView('home');
await new Promise(r => setTimeout(r, 40));
await window.feeditOpenFeedback(5);
const fb = document.getElementById('fbModal');
assert.ok(fb.classList.contains('on'), '피드백 창이 뜬다');
assert.equal(document.body.dataset.view, 'home', '살말 화면으로 넘어가지 않는다');
assert.equal(fb.querySelector('.fbScale'), null, '만족도 1~5 는 뺐다');
assert.ok(fb.textContent.includes('구매하셨나요'));
click(fb.querySelector('[data-p="BOUGHT"]'));
assert.ok(fb.textContent.includes('구매하셨다면 후기를 들려주세요'));
click(fb.querySelector('.fbTop'));
await new Promise(r => setTimeout(r, 60));
assert.equal(fb.classList.contains('on'), false, '카드 정보를 누르면 창을 닫고');
assert.equal(document.body.dataset.view, 'salmal', '그 카드가 있는 살말로 간다');

/* ⑩ 내 피드 머리 — 지금 계정 이름 + 직업 배지(등급 자리) */
router.goView('trend');
await new Promise(r => setTimeout(r, 400));
assert.equal(document.getElementById('trProfNm').textContent, '피딧회원');
assert.equal(document.querySelector('#trProfRk .jobBadge').textContent, 'Basic', '승인 전이면 Basic 배지');

/* ⑪ 2026-09-20 — 로그아웃 뒤 트렌드 분석: 로그인 안내 뒤편에 앞 계정 이름·피드가 비치면 안 된다 */
click(document.getElementById('mAuthBtn'));
click(document.getElementById('menuLogout'));
await new Promise(r => setTimeout(r, 120));
assert.equal(profile.AUTH.in, false);
router.goView('trend');
await new Promise(r => setTimeout(r, 400));
assert.ok(document.getElementById('trendGateModal').classList.contains('on'), '로그인 안내가 뜬다');
assert.notEqual(document.getElementById('trProfNm').textContent, '피딧회원', '앞 계정 이름이 남지 않는다');
assert.equal(document.querySelector('#sFoot .who b').textContent.includes('피딧회원'), false);
/* 2026-09-20 — 바깥을 누르거나 Esc 를 눌러도 닫히지 않는다. 취소 · 로그인으로만 빠져나간다 */
const gate = document.getElementById('trendGateModal');
click(gate);
dom.window.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key:'Escape' }));
assert.ok(gate.classList.contains('on'), '로그인 안내는 바깥 클릭 · Esc 로 닫히지 않는다');
click(document.getElementById('trendGateCancel'));
await new Promise(r => setTimeout(r, 60));
assert.equal(gate.classList.contains('on'), false);
assert.equal(document.body.dataset.view, 'home', '취소하면 홈으로');

console.log('✅ 알림 아이콘 · 패널 · 읽음 · 삭제 · 알림 설정이 실제로 동작합니다.');
process.exit(0);
