/* 요금제 (2026-10-03) — 베타 동안은 아무것도 바뀌지 않고, 베타가 끝나면 표대로 막히는지 실제로 돌려 본다.
   (AGENTS §5 — 모듈 JS 는 jsdom 으로 실행해 봐야 안다.)

   ① 베타   — 서버가 billing.enforced=false 를 준다. 요금제 카드는 예전 안내만, 트렌드 EDIT 은 전부 열림,
              챗봇은 예전처럼 알파 횟수 주소를 부르고 확인증을 싣지 않는다.
   ② 베타 이후 — 프리는 EDIT 언급량·온도만 · 내보내기 잠금 · 신청 창 · 하루 횟수 · 관리자 심사. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost:5173/' });
Object.defineProperty(dom.window.document, 'hidden', { configurable:true, get:() => false });
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent','Event'])
  globalThis[key] = key === 'window' ? dom.window : dom.window[key];
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame = fn => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = id => clearTimeout(id);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.location = dom.window.location;
globalThis.history = dom.window.history;
globalThis.localStorage = dom.window.localStorage;
globalThis.sessionStorage = dom.window.sessionStorage;
globalThis.innerWidth = 1440; globalThis.innerHeight = 900;
globalThis.matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
globalThis.scrollTo = () => {};
globalThis.IntersectionObserver = class{ observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class{ observe(){} unobserve(){} disconnect(){} };
globalThis.confirm = () => true;
dom.window.confirm = () => true;

const EDIT = ['temp','assoc','sentiment','life','stock','resale'];
const FEAT = {
  FREE:{ salmal:true, chat_daily:20, trend_feed:true, trend_edit:['temp'], report_export:false, data_api:false },
  PRO:{ salmal:true, chat_daily:null, trend_feed:true, trend_edit:EDIT, report_export:true, data_api:false },
  BUSINESS:{ salmal:true, chat_daily:null, trend_feed:true, trend_edit:EDIT, report_export:true, data_api:true },
};
const billing = (enforced, plan = 'FREE', extra = {}) => ({
  enforced, signed_in:true, plan, label:plan,
  features:enforced ? FEAT[plan === 'ADMIN' ? 'BUSINESS' : plan] : FEAT.BUSINESS,
  plans:FEAT, request:null, chat:null, ...extra,
});
const user = { id:7, username:'feedit01', email:'feedit01@example.com', nickname:'피딧회원', initial:'피',
  birth_date:'2000-01-02', height:170, weight:60, avatar:0, role:'user', job:'', major:'',
  bio:'', styles:[], saved_count:0, vote_count:0, badges:{}, plan:'FREE', billing:billing(false) };

const asked = [];
let chatUse = { status:200, data:{ enforced:true, plan:'FREE', ticket:'v1.abc.def', chat:{ limit:20, used:4, remaining:16 } } };
let reviewRows = [];
const reply = (payload, status = 200) => ({ ok:status < 400, status, text:async () => JSON.stringify(payload),
  json:async () => payload });

globalThis.fetch = async (url, opts = {}) => {
  const u = String(url), method = (opts.method || 'GET').toUpperCase();
  asked.push({ url:u, method, body:opts.body });
  if(u.includes('/api/auth/me')) return reply({ status:'ok', data:{ authenticated:true, csrf_token:'csrf', user } });
  if(u.includes('/api/auth/alpha-chat-use')) return reply({ status:'ok', data:{ alpha:false, limit:null, used:0, remaining:null } });
  if(u.includes('/api/auth/alpha-quota')) return reply({ status:'ok', data:{ alpha:false, limit:null, used:0, remaining:null } });
  if(u.includes('/api/auth/plan-chat-use')){
    return reply(chatUse.status === 200 ? { status:'ok', data:chatUse.data }
      : { status:'error', reason:'오늘 프리 요금제의 AI 챗 이용 횟수(20회)를 모두 쓰셨어요.', data:chatUse.data }, chatUse.status);
  }
  if(u.includes('/api/auth/plan-requests')) return reply({ status:'ok', data:{ items:reviewRows, pending:reviewRows.length, enforced:true } });
  if(u.includes('/api/auth/plan-review')) { reviewRows = []; return reply({ status:'ok', data:{ status:'APPROVED' } }); }
  if(u.includes('/api/auth/plan-request')){
    const body = JSON.parse(opts.body || '{}');
    if(method === 'DELETE') return reply({ status:'ok', data:billing(true, 'FREE') });
    if(body.plan === 'FREE') return reply({ status:'ok', data:billing(true, 'FREE') });
    return reply({ status:'ok', data:billing(true, 'FREE', { request:{ plan:body.plan, status:'PENDING', requested_at:'2026-10-03T10:00:00+09:00' } }) }, 201);
  }
  if(u.includes('/api/v1/chat')) return new Response('event: done\ndata: {"ok":true}\n\n', { status:200 });
  if(u.includes('/api/auth/notifications')) return reply({ status:'ok', data:{ items:[], unread:0, setting:{ enabled:true, kinds:{} } } });
  if(u.includes('/api/auth/saved')) return reply({ status:'ok', data:{ items:[], count:0 } });
  if(u.includes('/api/dictionary')) return reply({ status:'ok', data:[] });
  return reply({ status:'empty', reason:'테스트 데이터 없음', data:null });
};

await import(`${root}/main.js`);
const router = await import(`${root}/app_shell/static/js/router.js`);
const profile = await import(`${root}/account/static/js/profile.js`);
const plan = await import(`${root}/account/static/js/plan.js`);
const chatApi = await import(`${root}/home/static/js/chat_api.js`);
document.getElementById('jumpBtn').click();
await new Promise(r => setTimeout(r, 150));

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const wait = (ms = 30) => new Promise(r => setTimeout(r, ms));
const toast = () => ($('#toast') || {}).textContent || '';
const card = k => $(`#prGrid .prCard[data-plan="${k}"]`);
const askedFor = part => asked.filter(a => a.url.includes(part));
let pass = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); pass++; };

ok(profile.AUTH.in, '세션 복구로 로그인 상태가 돼야 한다');

/* ═════════ ① 베타 — 지금과 똑같아야 한다 ═════════ */
ok(plan.planEnforced() === false, '서버가 enforced=false 를 주면 베타다');
router.goView('price'); await wait(80);
const betaTitle = $('#v-price .priceTitle').innerHTML;
ok(/베타 기간엔/.test(betaTitle), '베타 동안 머리글은 그대로');
card('PRO').click(); await wait();
ok(toast() === '현재 베타 기간으로 무료로 사용 가능합니다.', '베타 — 카드를 누르면 예전 안내만 뜬다');
ok(!$('#planModal').classList.contains('on'), '베타 — 신청 창은 열리지 않는다');
ok(askedFor('/api/auth/plan-request').length === 0, '베타 — 신청 주소를 부르지 않는다');
ok($$('#prGrid .prState').length === 0, '베타 — 카드에 이용 중 표시가 붙지 않는다');
ok($('#menuPlanReview').hidden, '베타 — 요금제 심사 메뉴는 보이지 않는다');

router.goView('trend'); await wait(400);   /* 화면 전환 · 첫 그리기가 끝난 뒤에 누른다 */
ok($$('#sEdit .sItem.planLocked').length === 0, '베타 — EDIT 잠금 표시가 없다');
$('#sEdit .sItem[data-tr="assoc"]').click(); await wait();
ok($('#trTitle').textContent === '연관어', '연관어 탭으로 들어갔다');
ok(!$('#trBody .planLock'), '베타 — 연관어 탭이 잠기지 않는다');
ok(!$('#trTabs').hidden, '베타 — 연관어 검색창이 그대로 선다');
$('#trShareBtn').click(); await wait();
ok(!/프로 요금제부터/.test(toast()), '베타 — 공유 버튼이 요금제로 막히지 않는다');

const before = asked.length;
await chatApi.askStream({ question:'안녕', plan:'FREE' }, {});
const betaCalls = asked.slice(before);
ok(betaCalls.some(a => a.url.includes('/api/auth/alpha-chat-use')), '베타 — 예전처럼 알파 횟수 주소를 부른다');
ok(!betaCalls.some(a => a.url.includes('/api/auth/plan-chat-use')), '베타 — 요금제 횟수 주소는 부르지 않는다');
const betaChat = betaCalls.find(a => a.url.includes('/api/v1/chat'));
ok(betaChat && !('plan_ticket' in JSON.parse(betaChat.body)), '베타 — 챗봇 요청 본문이 예전과 같다(확인증 없음)');

/* ═════════ ② 베타 이후 — 프리 ═════════ */
plan.planApply(billing(true, 'FREE', { chat:{ limit:20, used:3, remaining:17, day:'2026-10-03' } }));
ok(plan.planEnforced(), '서버가 enforced=true 를 주면 요금제가 걸린다');

/* 트렌드 분석 — 언급량·온도만 열리고 나머지 다섯은 잠긴다 */
const locked = $$('#sEdit .sItem.planLocked').map(b => b.dataset.tr).sort();
ok(JSON.stringify(locked) === JSON.stringify(['assoc','life','resale','sentiment','stock']), '프리 — EDIT 다섯 탭에 잠금 표시: ' + locked);
ok(!!$('#trBody .planLock'), '보고 있던 연관어 탭이 그 자리에서 잠긴다');
ok(/연관어는 프로 요금제부터/.test($('#trBody .planLock h4').textContent), '잠금 문구에 탭 이름과 조사가 맞게 들어간다');
ok($('#trTabs').hidden, '잠긴 탭에는 검색창을 세우지 않는다');
ok($('#trBody .planLock [data-v="price"]'), '요금제 보기 버튼이 있다');
$('#sEdit .sItem[data-tr="sentiment"]').click(); await wait();
ok(/긍부정은 프로 요금제부터/.test($('#trBody .planLock h4').textContent), '받침 있는 이름에는 "은"');
$('#sEdit .sItem[data-tr="temp"]').click(); await wait();
ok(!$('#trBody .planLock'), '프리 — 언급량·온도는 열려 있다');
$('#trShareBtn').click(); await wait();
ok(/리포트 내보내기\(저장 · 공유\)는 프로 요금제부터/.test(toast()), '프리 — 공유는 잠금 안내');
$('#trDownloadBtn').click(); await wait();
ok($('#trDlMenu').hidden, '프리 — 다운로드 메뉴가 열리지 않는다');

/* 챗봇 — 요금제 횟수 주소를 부르고, 받은 확인증을 실어 보낸다 */
const mark = asked.length;
await chatApi.askStream({ question:'발레코어 어때?', plan:'FREE' }, {});
const live = asked.slice(mark);
ok(live.some(a => a.url.includes('/api/auth/plan-chat-use')), '베타 이후 — 요금제 횟수를 센다');
ok(!live.some(a => a.url.includes('/api/auth/alpha-chat-use')), '베타 이후 — 알파 횟수는 부르지 않는다');
ok(JSON.parse(live.find(a => a.url.includes('/api/v1/chat')).body).plan_ticket === 'v1.abc.def', '확인증을 챗봇 요청에 싣는다');
ok(plan.planState().chat.used === 4, '오늘 사용량을 받아 둔다');
chatUse = { status:429, data:{ enforced:true, plan:'FREE', ticket:null, chat:{ limit:20, used:20, remaining:0 } } };
const chatBefore = askedFor('/api/v1/chat').length;
await assert.rejects(chatApi.askStream({ question:'또', plan:'FREE' }, {}), e => e.planQuota === true && /20회/.test(e.message));
pass++;
ok(askedFor('/api/v1/chat').length === chatBefore, '한도를 넘으면 챗봇 서버까지 가지 않는다');

/* 요금제 화면 — 머리글 · 이용 중 표시 · 신청 창 */
router.goView('price'); await wait(80);
ok(!/베타 기간엔/.test($('#v-price .priceTitle').innerHTML), '베타 이후 — 머리글이 바뀐다');
ok(/이용 중/.test(card('FREE').querySelector('.prState').textContent), '프리 카드에 이용 중');
ok(/20\/20회/.test(card('FREE').querySelector('.prState').textContent), '오늘 AI 챗 사용량이 같이 보인다');
ok(/언급량·온도까지/.test($$('#faq details p')[3].textContent), '자주 묻는 질문의 프리 제한이 표와 맞게 바뀐다');

card('PRO').click(); await wait();
ok($('#planModal').classList.contains('on'), '프로 카드를 누르면 신청 창이 열린다');
ok($('#planModalTitle').textContent === '프로 요금제 신청', '창 제목');
ok(!$('#planCompany'), '프로 신청에는 팀 이름 칸이 없다');
$('#planNote').value = '실무용';
$('#planForm').dispatchEvent(new dom.window.Event('submit', { cancelable:true, bubbles:true }));
await wait(60);
const sent = askedFor('/api/auth/plan-request').at(-1);
ok(sent && sent.method === 'POST' && JSON.parse(sent.body).plan === 'PRO' && JSON.parse(sent.body).note === '실무용', '신청 내용을 서버로 보낸다');
ok(!$('#planModal').classList.contains('on'), '신청하면 창이 닫힌다');
ok(/신청 심사 중/.test((card('PRO').querySelector('.prState') || {}).textContent || ''), '프로 카드에 신청 심사 중');
router.goView('trend'); await wait(400);
$('#sEdit .sItem[data-tr="assoc"]').click(); await wait();
ok(/심사 중이에요/.test($('#trBody .planLock p').textContent), '잠금 안내가 심사 중인 신청을 알려 준다');

router.goView('price'); await wait(80);
card('BUSINESS').click(); await wait();
ok(!!$('#planCompany'), '비즈니스 신청에는 팀 이름 칸이 있다');
const reqCount = askedFor('/api/auth/plan-request').length;
$('#planForm').dispatchEvent(new dom.window.Event('submit', { cancelable:true, bubbles:true }));
await wait(40);
ok(!$('#planFormErr').hidden && /팀\(회사\) 이름/.test($('#planFormErr').textContent), '팀 이름이 비면 막는다');
ok(askedFor('/api/auth/plan-request').length === reqCount, '막힌 신청은 서버로 가지 않는다');
$('#planModal [data-close-modal]').click(); await wait();

/* ═════════ ③ 베타 이후 — 프로로 승인된 뒤 ═════════ */
plan.planApply(billing(true, 'PRO'));
ok($$('#sEdit .sItem.planLocked').length === 0, '프로 — EDIT 잠금이 모두 풀린다');
ok(/이용 중/.test(card('PRO').querySelector('.prState').textContent), '프로 카드에 이용 중');
card('FREE').click(); await wait();
ok($('#planModalTitle').textContent === '프리로 바꾸기', '프로 사용자가 프리를 누르면 해지 창');
$('#planForm').dispatchEvent(new dom.window.Event('submit', { cancelable:true, bubbles:true }));
await wait(60);
ok(JSON.parse(askedFor('/api/auth/plan-request').at(-1).body).plan === 'FREE', '해지는 plan=FREE 로 보낸다');
ok(plan.planState().plan === 'FREE', '해지하면 바로 프리');

/* ═════════ ④ 운영 계정 — 심사 ═════════ */
ok($('#menuPlanReview').hidden, '일반 회원에게는 심사 메뉴가 없다');
profile.ME.role = 'admin';
plan.planApply(billing(true, 'ADMIN'));
ok(!$('#menuPlanReview').hidden, '운영 계정 + 베타 이후 — 심사 메뉴가 보인다');
reviewRows = [{ user_id:7, nickname:'피딧회원', username:'feedit01', email:'feedit01@example.com',
  current_plan:'FREE', plan:'PRO', from_plan:'FREE', note:'실무용', company:'', contact:'',
  status:'PENDING', requested_at:'2026-10-03T10:00:00+09:00', decided_at:null, reason:'' }];
$('#menuPlanReview').click(); await wait(60);
ok($('#planReviewModal').classList.contains('on'), '심사 창이 열린다');
ok(/피딧회원/.test($('#planReviewList').textContent) && /메모 실무용/.test($('#planReviewList').textContent), '신청 내용이 보인다');
$('#planReviewList [data-pr-reason="7"]').value = '확인 완료';
$('#planReviewList [data-pr-ok="7"]').click(); await wait(60);
const decided = askedFor('/api/auth/plan-review').at(-1);
ok(decided && JSON.parse(decided.body).approve === true && JSON.parse(decided.body).user_id === 7, '승인을 서버로 보낸다');
ok(JSON.parse(decided.body).reason === '확인 완료', '사유를 같이 보낸다');
ok(/심사를 기다리는 신청이 없습니다/.test($('#planReviewList').textContent), '승인 뒤 목록을 다시 받는다');
reviewRows = [{ user_id:8, nickname:'팀장', username:'lead01', email:'', current_plan:'BUSINESS', plan:'BUSINESS',
  from_plan:'FREE', note:'', company:'피딧', contact:'010', status:'APPROVED',
  requested_at:'2026-10-01T10:00:00+09:00', decided_at:'2026-10-02T10:00:00+09:00', reason:'' }];
$('#planReviewList [data-pr-tab="ALL"]').click(); await wait(60);
ok(!!$('#planReviewList [data-pr-revoke="8"]'), '이용 중인 유료 사용자에게는 프리로 되돌리기 버튼');
$('#planReviewList [data-pr-revoke="8"]').click(); await wait(60);
ok(JSON.parse(askedFor('/api/auth/plan-review').at(-1).body).op === 'revoke', '되돌리기는 op=revoke');
$('#planReviewModal [data-close-modal]').click();

/* ═════════ ⑤ 다시 베타로 — 모든 것이 원래대로 ═════════ */
profile.ME.role = 'user';
plan.planApply(billing(false));
ok($$('#sEdit .sItem.planLocked').length === 0, '베타로 돌아가면 잠금 표시가 사라진다');
ok($('#v-price .priceTitle').innerHTML === betaTitle, '머리글도 원래 문구로');
ok($$('#prGrid .prState').length === 0, '카드 표시도 사라진다');
ok($('#menuPlanReview').hidden, '심사 메뉴도 숨는다');
ok(plan.planGuard('report_export') === true, '베타 — 내보내기는 언제나 통과');

/* 옛 서버(billing 없음) — 아무것도 막지 않는다 */
plan.planApply(undefined);
ok(plan.planEnforced() === false, 'billing 이 없으면 베타처럼 연다');

console.log(`✅ 요금제 화면 ${pass}개 통과`);
process.exit(0);
