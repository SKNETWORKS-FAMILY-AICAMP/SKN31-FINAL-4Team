/* 새로고침 복원 — "로그인했는데 로그인하라고 한다" 를 막는다.
 *
 * ★ 이 시험이 잡아낸 것 (2026-09-22)
 *   resumeNav 는 보던 화면(트렌드 분석)을 그 자리에서 **동기로** 세우는데,
 *   로그인 복구(/api/me)는 그보다 늦게 끝난다. 그 사이의 AUTH.in=false 를
 *   '로그아웃' 으로 읽어서 트렌드 관문 팝업이 떴고, 복구가 끝나도 다시
 *   판정하는 곳이 없어 팝업이 그대로 남았다. 마이페이지는 로그인 화면으로 튕겼다.
 *
 * 돌리는 법:  node tests/auth_restore_gate.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'), {url:'http://localhost:5173/'});
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement',
                 'KeyboardEvent','MouseEvent','CustomEvent','Event','MutationObserver','history'])
  globalThis[k] = k==='window'?dom.window:dom.window[k];
globalThis.requestAnimationFrame=(f)=>setTimeout(f,0);
globalThis.cancelAnimationFrame=(h)=>clearTimeout(h);
globalThis.addEventListener=dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener=dom.window.removeEventListener.bind(dom.window);
globalThis.location=dom.window.location;
globalThis.localStorage=dom.window.localStorage;
globalThis.sessionStorage=dom.window.sessionStorage;
globalThis.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
globalThis.scrollTo=()=>{};
globalThis.innerWidth=1280; globalThis.innerHeight=800;
globalThis.IntersectionObserver=class{observe(){}unobserve(){}disconnect(){}};
globalThis.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};

/* ── 새로고침 직전 상태: 트렌드 분석을 보고 있었고, 로그인돼 있다 ── */
sessionStorage.setItem('feedit.nav.v1', JSON.stringify({view:'trend',tr:'myfeed',style:null}));
localStorage.setItem('feedit.introSeen.v1','1');
/* 지난번 이 브라우저에서 로그인해 있던 이름 — 복구 전 헤더가 [로그인] 대신 이걸 먼저 보인다 */
localStorage.setItem('feedit:auth-hint','진');

/* 로그인 복구는 **늦게** 온다 — 이 지연이 이 버그의 전부다 */
const USER={id:1,username:'jin',nickname:'진',email:'jin@example.com',role:'user',styles:[]};
let meCalls=0, answerMe;
/* 복구 응답을 시험이 직접 놓아 준다 — '아직 안 왔다' 를 확실히 재현하기 위해서다 */
const meHeld=new Promise(r=>{ answerMe=r });
globalThis.fetch = async (u) => {
  const url=decodeURIComponent(String(u));
  const ok=(body)=>({ok:true,status:200,text:async()=>JSON.stringify(body),json:async()=>body});
  if(/\/api\/auth\/me$/.test(url)){
    meCalls++;
    await meHeld;                                      /* 화면은 이미 서 있다 */
    return ok({status:'ok',data:{authenticated:true,user:USER}});
  }
  await new Promise(r=>setTimeout(r,10));
  if(/saved/.test(url))return ok({status:'ok',data:{items:[]}});
  throw new Error('ECONNREFUSED');
};

await import(`${F}/main.js`);
const { AUTH } = await import(`${F}/account/static/js/profile.js`);

let pass=0, fail=0;
const t=async(n,f)=>{try{await f();console.log('✅',n);pass++}catch(e){console.log('❌',n,'\n   ',e.message);fail++}};
const wait=(ms)=>new Promise(r=>setTimeout(r,ms));
const gateOn=()=>document.getElementById('trendGateModal').classList.contains('on');

await t('새로고침 직후 — 복구 전에는 관문을 세우지 않는다', async () => {
  await wait(40);                                        /* /api/me 아직 오는 중 */
  assert.equal(document.body.dataset.view,'trend','트렌드 화면이 복원돼야 한다');
  assert.equal(AUTH.ready,false,'아직 판정할 때가 아니다');
  assert.equal(gateOn(),false,'복구 전에 로그인 팝업이 떴다');
  /* ★ 2026-10-02 — 헤더가 잠깐 [로그인] 으로 보였다가 이름으로 바뀌던 깜빡임 */
  const btn=document.getElementById('mAuthBtn');
  assert.ok(!btn.textContent.includes('로그인'),'복구 전에 [로그인] 이 보인다');
  assert.ok(btn.textContent.includes('진'),'지난번 이름을 먼저 보여야 한다');
  assert.ok(btn.classList.contains('pending'));
  assert.equal(btn.dataset.v,undefined,'복구 전에는 로그인 화면으로 가지 않는다');
});

await t('★ 복구가 끝나면 로그인 상태이므로 관문이 서지 않는다', async () => {
  answerMe(); await wait(120);
  assert.equal(meCalls,1,'세션은 한 번만 묻는다');
  assert.equal(AUTH.in,true,'세션 복구가 안 됐다');
  assert.equal(AUTH.ready,true);
  assert.equal(gateOn(),false,'로그인했는데 로그인 팝업이 떴다');
  const btn=document.getElementById('mAuthBtn');
  assert.ok(!btn.classList.contains('pending'),'복구 뒤에도 자리표시가 남았다');
  assert.ok(btn.classList.contains('me'));
});

await t('복구 뒤 트렌드로 다시 들어가도 조용하다', async () => {
  const { goView } = await import(`${F}/app_shell/static/js/router.js`);
  goView('home'); await wait(30);
  assert.equal(gateOn(),false,'트렌드를 벗어났는데 관문이 남았다');
  goView('trend'); await wait(30);
  assert.equal(gateOn(),false);
});

await t('★ 정말 로그아웃이면 그때는 관문이 선다', async () => {
  const { goView } = await import(`${F}/app_shell/static/js/router.js`);
  AUTH.in=false;
  document.dispatchEvent(new dom.window.CustomEvent('feedit:auth'));
  await wait(30);
  assert.equal(gateOn(),true,'로그아웃인데 관문이 없다');
  goView('home'); await wait(30);
  assert.equal(gateOn(),false);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail?1:0);
