/* 경험치 · 레벨 · 홈페이지 피드백 — 실제 화면을 jsdom 으로 돌려 본다 (2026-09-25).

   ① 서버가 준 누적 XP 로 마이페이지 경험치 바와 요약이 그려진다
   ② 요약을 누르면 경험치 창에 오늘 · 이번 주 항목과 레벨 구간이 뜬다
   ③ '남기기' → 홈페이지 피드백 창. 짧은 글은 막고, 유형을 골라 보내면 경험치가 바뀐다
   ④ 레벨이 오르면 한 번 알려 준다
   ⑤ 운영 계정은 최고 레벨로 고정된다
   ⑥ 살!말? 댓글 레벨은 서버가 준 경험치로 센다 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost:5173/' });
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent','Event'])
  globalThis[key] = key === 'window' ? dom.window : dom.window[key];
globalThis.MutationObserver = dom.window.MutationObserver || class{observe(){} disconnect(){} takeRecords(){return []}};
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

const wait = ms => new Promise(r => setTimeout(r, ms));
const reply = payload => ({ ok:true, status:200, text:async () => JSON.stringify(payload), json:async () => payload });

/* 서버 모양 그대로 — backend/apps/api/xp.py compute_xp() */
function xpPayload(total, { siteFeedback = 0 } = {}){
  const d = (key, label, xp, max, hint, extra) => ({ key, label, xp, max, hint, ...extra });
  return {
    fixed:false, total, start:'2026-09-25',
    today:{ date:'2026-09-25', earned:9, cap:15, items:[
      d('visit','접속',3,3,'로그인한 채로 들어오면 +3',{count:1}),
      d('chat','챗봇 질문',1,4,'첫 질문 +1 · 3번째 질문 +3',{count:2}),
      d('vote','살!말? 투표',1,4,'첫 투표 +1 · 3번째 투표 +3',{count:1}),
      d('save','찜하기',4,4,'첫 찜 +1 · 3번째 찜 +3',{count:3}),
    ]},
    week:{ start:'2026-09-21', end:'2026-09-27', earned:42 + siteFeedback, cap:210,
      daily:{ earned:27, cap:105 },
      weekly:{ earned:15 + siteFeedback, cap:105, items:[
        d('attend','주간 올출석',0,5,'월~일 7일 모두 접속하면 +5',{count:3,goal:3}),
        d('hit','적중',5,25,'내 살/말 투표가 실제 결과와 맞을 때마다 +5',{count:1}),
        d('vote_feedback','투표 피드백',0,25,'마감된 내 카드에 샀는지 남기면 +25',{count:0}),
        d('dwell','트렌드 분석 체류',10,25,'화면을 보는 2분마다 +1 (50분까지)',{minutes:20,goal:50}),
        d('site_feedback','홈페이지 피드백',siteFeedback,25,'불편사항 · 버그를 남기면 +25',{count:siteFeedback ? 1 : 0}),
      ]},
    },
  };
}

const user = { id:7, username:'feedit01', email:'feedit01', nickname:'전서연', initial:'전',
  birth_date:'2000-01-02', height:170, weight:60, avatar:0, role:'user', job:'', major:'',
  bio:'', styles:[], saved_count:0, vote_count:0, badges:{}, xp:xpPayload(420) };

let serverXp = xpPayload(420);
const posted = [];
let feedbackItems = [];
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  if(u.includes('/api/auth/me')) return reply({ status:'ok', data:{ authenticated:true, csrf_token:'csrf', user } });
  if(u.includes('/api/auth/xp')) return reply({ status:'ok', data:{ xp:serverXp } });
  if(u.includes('/api/auth/site-feedback')){
    if((opts.method || 'GET') === 'POST'){
      const body = JSON.parse(opts.body);
      posted.push(body);
      serverXp = xpPayload(445, { siteFeedback:25 });
      feedbackItems = [{ id:1, kind:body.kind, kind_label:'수정사항·버그리포트', content:body.content,
        status:'OPEN', status_label:'확인 전', created_at:'2026.09.25 15:30' }];
      return { ok:true, status:201, text:async () => JSON.stringify({ status:'ok',
        data:{ item:feedbackItems[0], rewarded:true, xp:serverXp } }) };
    }
    return reply({ status:'ok', data:{ items:feedbackItems } });
  }
  if(u.includes('/api/auth/notifications')) return reply({ status:'ok', data:{ items:[], unread:0 } });
  if(u.includes('/api/salmal/feedback')) return reply({ status:'ok', data:{ pending:[], done:[], counts:{ pending:0, done:0 } } });
  if(u.includes('/api/auth/saved')) return reply({ status:'ok', data:{ items:[], count:0 } });
  if(u.includes('/api/products')) return reply({ status:'ok', data:{ items:[] } });
  return reply({ status:'empty', reason:'테스트 데이터 없음', data:null });
};

await import(`${root}/main.js`);
const router = await import(`${root}/app_shell/static/js/router.js`);
const profile = await import(`${root}/account/static/js/profile.js`);
const rank = await import(`${root}/account/static/js/rank.js`);
document.getElementById('jumpBtn').click();
await wait(150);
router.goView('mypage');
await wait(300);
const $ = id => document.getElementById(id);

/* ① 경험치 바 — 420 XP 는 Lv.2 (300~1,200) 의 120 / 900 */
assert.equal(rank.RANK_ON, true, '레벨 표시가 다시 켜져 있다');
assert.equal($('xpWrap').hidden, false, '경험치 바가 보인다');
assert.equal($('xpLv').textContent, 'Lv.2');
assert.equal($('xpNum').textContent, '120 / 900 XP');
assert.equal($('xpNext').textContent, 'Lv.3 까지 780 XP 남았습니다.');
assert.equal($('xpMore').hidden, false, '오늘 · 이번 주 요약이 보인다');
assert.equal($('xpMoreText').textContent, '오늘 9 / 15 · 이번 주 42 / 210 XP');
assert.ok($('avatarInitial').classList.contains('rk2'), '아바타 링이 Lv.2 로 칠해진다');
assert.match($('sFootRk').innerHTML, /Lv\.2/, '사이드바 칩도 Lv.2');

/* ② 경험치 창 */
$('xpMore').click();
await wait(30);
assert.ok($('xpModal').classList.contains('on'), '경험치 창이 열린다');
const rows = [...document.querySelectorAll('#xpDetail .xpRow')];
assert.equal(rows.length, 4 + 5, '오늘 4줄 + 이번 주 5줄');
assert.match(rows[3].textContent, /찜하기.*3회.*4\/ 4/, '다 채운 찜하기 줄');
assert.ok(rows[3].classList.contains('full'), '다 채운 줄은 full');
assert.match(rows[7].textContent, /20 \/ 50분/, '체류 시간은 분으로');
assert.match(document.querySelector('#xpDetail .xpHero').textContent, /420 XP.*Lv\.3 까지 780 XP/);
const ladder = [...document.querySelectorAll('#xpDetail .xpLadder li')];
assert.equal(ladder.length, 5);
assert.ok(ladder[1].classList.contains('on'), '레벨 구간에서 지금 칸(Lv.2)이 칠해진다');
assert.match(ladder[4].textContent, /Lv\.Max9,000/);

/* ③ 홈페이지 피드백 */
document.querySelector('#xpDetail [data-xp-go="feedback"]').click();
await wait(30);
assert.ok($('siteFbModal').classList.contains('on'), '피드백 창이 열린다');
assert.ok(!$('xpModal').classList.contains('on'), '경험치 창은 닫힌다');
assert.match($('sfPage').textContent, /마이페이지/, '보내는 화면이 붙는다');
assert.match($('sfList').textContent, /아직 남긴 피드백이 없어요/);
$('sfText').value = '짧음';
$('sfSend').click();
await wait(20);
assert.equal(posted.length, 0, '10자 미만은 보내지 않는다');
assert.equal($('sfMsg').className, 'fieldMsg err');
document.querySelector('#sfKinds [data-kind="BUG"]').click();
assert.equal(document.querySelector('#sfKinds [data-kind="BUG"]').getAttribute('aria-checked'), 'true');
assert.match($('sfText').placeholder, /어느 화면에서/, '버그리포트 안내 문구로 바뀐다');
$('sfText').value = '트렌드 분석 긍부정 탭에서 차트가 비어요\n새로고침하면 다시 나와요';
$('sfText').dispatchEvent(new Event('input', { bubbles:true }));
assert.equal($('sfCount').textContent, String($('sfText').value.length));
$('sfSend').click();
await wait(60);
assert.equal(posted.length, 1);
assert.deepEqual(posted[0], { kind:'BUG', content:'트렌드 분석 긍부정 탭에서 차트가 비어요\n새로고침하면 다시 나와요', page:'마이페이지' });
assert.match($('sfMsg').textContent, /\+25 XP/);
assert.equal($('sfText').value, '', '보내면 입력칸을 비운다');
assert.match($('sfList').textContent, /확인 전/, '내가 남긴 피드백 목록에 뜬다');
assert.equal($('xpNum').textContent, '145 / 900 XP', '응답의 경험치로 바가 바로 바뀐다');

/* ④ 레벨이 오르면 알려 준다 */
profile.applyXp(xpPayload(1200));
assert.equal($('xpLv').textContent, 'Lv.3');
assert.match($('toast').textContent, /레벨이 올랐어요 · Lv\.3/);

/* ⑤ 운영 계정 */
profile.applyXp({ fixed:true, total:null });
assert.equal($('xpLv').textContent, 'Lv.Max');
assert.equal($('xpNum').textContent, '운영 계정');
assert.equal($('xpMore').hidden, true, '운영 계정은 오늘 · 이번 주 요약을 감춘다');
assert.equal(profile.ME.rank, rank.RK_MAX);

/* ⑥ 댓글 레벨 — 서버가 준 xp 로 센다 */
assert.equal(rank.rkLevelOf(0), 0);
assert.equal(rank.rkLevelOf(299), 0);
assert.equal(rank.rkLevelOf(300), 1);
assert.equal(rank.rkLevelOf(9000), 4);
assert.equal(rank.rkLevelOf(0, true), 4, '운영 계정은 최고 레벨');
assert.equal(rank.rkLevelOf(undefined), 0, '값이 없으면 Lv.1');
const voteSrc = fs.readFileSync(new URL('../salmal/static/js/vote_app.js', import.meta.url), 'utf8');
assert.match(voteSrc, /rk:rkLevelOf\(comment\.xp, comment\.xp_fixed\)/, '댓글 레벨은 xp 로 센다');
assert.doesNotMatch(voteSrc, /rk:comment\.rank/, '예전 가짜 rank 를 쓰지 않는다');

/* ⑦ 버셀 중계가 새 주소를 넘긴다 */
const relay = fs.readFileSync(new URL('../api/auth/[action].js', import.meta.url), 'utf8');
assert.match(relay, /'xp', 'site-feedback'/);

console.log('✅ 경험치 바 · 경험치 창 · 홈페이지 피드백 · 레벨 업 · 운영 계정 고정을 확인했습니다.');
process.exit(0);
