/* 챗봇 대화 기록 DB 연동 (2026-09-18)
 *
 * 무엇을 지키나
 *   · 팝업을 열면 서버(/api/auth/chats)의 대화 목록이 뜬다 — 다른 기기에서 한 대화도
 *   · 대화를 누르면 본문을 받아 그리고, 이어 물으면 앞 턴(turn)이 챗봇 history 로 간다
 *   · 답이 끝나면 한 턴이 서버에 저장된다 · 이름 변경 · 고정 · 삭제도 서버로 간다
 *   · 브라우저에만 있던 옛 대화는 한 번 서버로 옮겨진다
 *   · 다른 계정으로 바꾸면 앞 사람 대화가 보이지 않는다
 *
 * 실행:  node tests/chat_history_db.test.mjs
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://localhost:5173/' });
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node',
                 'HTMLElement','CustomEvent','KeyboardEvent','MouseEvent','File','Blob'])
  globalThis[k] = k === 'window' ? dom.window : dom.window[k];
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
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

/* 연동 전 브라우저 기록 — 처음 로그인한 계정이 가져가 서버로 옮겨야 한다 */
localStorage.setItem('feedit.chat.v1', JSON.stringify({ v:1, uid:3, store:{
  general:{ activeId:null, convos:[{ id:2, title:'옛 대화', time:'9월 1일', pinned:false, messages:[
    { role:'me', text:'옛 질문' }, { role:'ai', html:'<p>옛 답</p>', turn:{ q:'옛 질문', intent:'trend', terms:[] } }]}]},
  salmal:{ activeId:null, convos:[] } } }));

/* ── 가짜 Django (/api/auth/*) ── */
let nextId = 100;
const DB = { jin: [], other: [] };
let who = 'jin';
DB.jin.push({ id: 1, key: 'dev2', mode: 'general', title: '발레코어 흐름', pinned: false,
  updated_at: '2026-09-17T10:00:00Z', messages: [
    { id: 11, role: 'USER', content: '발레코어 요즘 어때?', metadata: {} },
    { id: 12, role: 'ASSISTANT', content: '상승 중', metadata: { html: '<p>다른 기기에서 받은 답</p>',
      turn: { q: '발레코어 요즘 어때?', intent: 'trend.direction', terms: [{ canonical: '발레코어', facet: 'STYLE', term_key: 'k1' }] } } }]});
DB.other.push({ id: 2, key: 'oth1', mode: 'general', title: '남의 대화', pinned: false,
  updated_at: '2026-09-17T09:00:00Z', messages: [] });
const calls = [];
const ok = (data) => { const b = JSON.stringify({ status: 'ok', data }); return { ok: true, status: 200, text: async () => b, json: async () => JSON.parse(b) }; };
const row = (s) => ({ id: s.id, key: s.key, mode: s.mode, title: s.title, pinned: s.pinned, updated_at: s.updated_at });
globalThis.fetch = async (u, opt = {}) => {
  const url = new URL(String(u), 'http://localhost:5173');
  const method = (opt.method || 'GET').toUpperCase();
  const body = opt.body ? JSON.parse(opt.body) : {};
  if (url.pathname === '/api/auth/me') return ok({ authenticated: true, csrf_token: 'csrf' });
  if (url.pathname === '/api/auth/event') { calls.push(['event', body]); return ok({ recorded: 'CHAT' }); }
  if (url.pathname === '/api/auth/chats') {
    calls.push([method, body.op || '', body]);
    const mine = DB[who];
    if (method === 'GET') {
      const id = url.searchParams.get('id');
      if (id) { const s = mine.find(x => x.id === +id); return ok({ session: row(s), messages: s.messages }); }
      return ok({ sessions: mine.map(row) });
    }
    let s = mine.find(x => x.key === body.key && x.mode === body.mode);
    if (method === 'DELETE') { DB[who] = mine.filter(x => x !== s); return ok({ deleted: true }); }
    const mk = (title) => { s = { id: nextId++, key: body.key, mode: body.mode, title, pinned: !!body.pinned, updated_at: new Date().toISOString(), messages: [] }; mine.push(s); };
    const addTurn = (t) => {
      const a = { id: nextId++, role: 'USER', content: t.question, metadata: {} };
      const b = { id: nextId++, role: 'ASSISTANT', content: t.answer.text, metadata: { html: t.answer.html, turn: t.answer.turn } };
      s.messages.push(a, b); return [a.id, b.id];
    };
    if (body.op === 'turn') { if (!s) mk(body.title); const [x, y] = addTurn(body); return ok({ session: row(s), user_message_id: x, ai_message_id: y }); }
    if (body.op === 'import') { if (!s) mk(body.title); return ok({ session: row(s), ids: body.turns.map(addTurn) }); }
    if (body.op === 'update') { if ('title' in body) s.title = body.title; if ('pinned' in body) s.pinned = body.pinned; return ok({ session: row(s) }); }
    if (body.op === 'truncate') { s.messages = s.messages.filter(m => m.id < body.from_message_id); return ok({ deleted: 1 }); }
  }
  throw new Error('offline');            /* 챗봇 서버는 꺼져 있다 → 데모 답 */
};

let pass = 0, fail = 0;
const t = async (n, f) => {
  try { await f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; }
};
const wait = (ms = 0) => new Promise(r => setTimeout(r, ms));
const settle = async () => { for (let i = 0; i < 12; i++) await wait(60); };

await import(`${F}/main.js`);
const CP = await import(`${F}/home/static/js/chat_popup.js`);
const P  = await import(`${F}/account/static/js/profile.js`);
P.AUTH.in = true; P.ME.mail = 'jin';
const click = (el) => el.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
const listText = () => document.querySelector('#cpList').textContent;

CP.openChatPopup();
await settle();

await t('팝업을 열면 서버의 대화 목록이 뜬다 (다른 기기에서 한 대화 포함)', () => {
  assert.match(listText(), /발레코어 흐름/);
});
await t('브라우저에만 있던 옛 대화가 서버로 옮겨진다', () => {
  const imp = calls.find(c => c[1] === 'import');
  assert.ok(imp, 'import 요청이 없다');
  assert.equal(imp[2].turns[0].question, '옛 질문');
  assert.ok(DB.jin.some(s => s.title === '옛 대화' && s.messages.length === 2));
  assert.equal(localStorage.getItem('feedit.chat.v1'), null, '옛 키는 계정 쪽으로 옮겨져야 한다');
});

const dev2 = () => CP.cpStore().convos.find(c => c.key === 'dev2');
await t('대화를 누르면 본문을 서버에서 받아 그린다', async () => {
  const item = document.querySelector('.cpItem[data-cid="' + dev2().id + '"]');
  click(item); await settle();
  assert.match(document.querySelector('#cpThread').textContent, /다른 기기에서 받은 답/);
});
await t('이어 물으면 앞 턴이 챗봇 history 로 가고, 새 턴이 서버에 저장된다', async () => {
  const ta = document.querySelector('#cpInput'); ta.value = '그럼 고프코어는?';
  CP.cpSend(); await settle();
  const hist = CP.cpHistoryFor(dev2());
  assert.equal(hist[0].terms[0].canonical, '발레코어', '앞 턴의 용어가 history 에 있어야 한다');
  const s = DB.jin.find(x => x.key === 'dev2');
  assert.equal(s.messages.length, 4);
  assert.equal(s.messages[2].content, '그럼 고프코어는?');
  const ev = calls.find(c => c[0] === 'event');
  assert.equal(ev[1].conversation_id, 'cp-general-dev2', '금주의 리포트 기록도 같은 대화 id');
  const turn = calls.filter(c => c[1] === 'turn').pop();
  assert.ok(Number.isFinite(turn[2].answer_ms) && turn[2].answer_ms >= 0, '응답 시간(answer_ms)을 같이 보낸다');
});
await t('고정 · 이름 변경이 서버로 간다', async () => {
  const c = dev2();
  click(document.querySelector('.cpKebab[data-menu="' + c.id + '"]')); await wait(10);
  click(document.querySelector('#cpMenu [data-mi="pin"]')); await settle();
  assert.equal(DB.jin.find(x => x.key === 'dev2').pinned, true);
  CP.cpEditTitle(c.id);
  const inp = document.querySelector('.cpTitleIn'); inp.value = '발레→고프';
  inp.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); await settle();
  assert.equal(DB.jin.find(x => x.key === 'dev2').title, '발레→고프');
});
await t('새로고침 뒤(브라우저 사본을 지워도) 서버에서 그대로 복원된다', async () => {
  localStorage.clear();
  const c = dev2(); CP.cpStore().convos = []; CP.cpStore().activeId = null;
  CP.closeChatPopup(); P.ME.mail = 'x'; CP.openChatPopup(); await settle();   // 계정 전환으로 강제 재수화
  P.ME.mail = 'jin'; CP.closeChatPopup(); CP.openChatPopup(); await settle();
  const again = CP.cpStore().convos.find(x => x.key === 'dev2');
  assert.ok(again, '목록에 다시 떠야 한다');
  assert.equal(again.title, '발레→고프');
  click(document.querySelector('.cpItem[data-cid="' + again.id + '"]')); await settle();
  assert.equal(again.messages.length, 4);
  /* 챗봇이 꺼진 데모 답에는 turn 이 없어 맥락은 첫 턴(발레코어)만 남는다 */
  assert.equal(CP.cpHistoryFor(again)[0].terms[0].canonical, '발레코어', '서버에서 받은 턴이 맥락으로 이어진다');
});
await t('다른 계정으로 바꾸면 앞 사람 대화가 안 보인다', async () => {
  who = 'other'; P.ME.mail = 'other';
  CP.closeChatPopup(); CP.openChatPopup(); await settle();
  assert.doesNotMatch(listText(), /발레/);
  assert.match(listText(), /남의 대화/);
  who = 'jin'; P.ME.mail = 'jin'; CP.closeChatPopup(); CP.openChatPopup(); await settle();
});
await t('삭제하면 서버에서도 지워진다', async () => {
  const c = CP.cpStore().convos.find(x => x.key === 'dev2');
  CP.cpDeleteConvo(c.id); await settle();
  assert.ok(!DB.jin.some(x => x.key === 'dev2'));
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
