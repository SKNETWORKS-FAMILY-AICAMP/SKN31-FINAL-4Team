/* Google 버튼이 GIS 코드 팝업 → /api/auth/google 로 이어지고,
 * 처음 온 계정은 가입 폼(Google 모드) → /api/auth/google-signup 으로 가입되는지 확인한다. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root=new URL('..',import.meta.url).href.replace(/\/$/,'');
const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
const dom=new JSDOM(html,{url:'http://localhost:5173/'});
for(const key of ['window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement','KeyboardEvent','MouseEvent','CustomEvent'])
  globalThis[key]=key==='window'?dom.window:dom.window[key];
globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);
globalThis.cancelAnimationFrame=id=>clearTimeout(id);
globalThis.addEventListener=dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener=dom.window.removeEventListener.bind(dom.window);
globalThis.location=dom.window.location;
globalThis.history=dom.window.history;
globalThis.localStorage=dom.window.localStorage;
globalThis.innerWidth=1440; globalThis.innerHeight=900;
globalThis.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
globalThis.scrollTo=()=>{};
globalThis.IntersectionObserver=class{observe(){} unobserve(){} disconnect(){}};
globalThis.ResizeObserver=class{observe(){} unobserve(){} disconnect(){}};
globalThis.MutationObserver=class{observe(){} disconnect(){} takeRecords(){return []}};

/* GIS 대역 — requestCode() 가 불리면 코드를 콜백으로 돌려준다 */
let initCfg=null, requested=0;
globalThis.google={accounts:{oauth2:{initCodeClient(cfg){
  initCfg=cfg;
  return {requestCode(){ requested++; setTimeout(()=>cfg.callback({code:'code-'+requested}),0) }};
}}}};

const asked=[];
const user={username:'google_1',email:'me@gmail.com',nickname:'구글회원',initial:'구',birth_date:'',
  height:null,weight:null,avatar:0,role:'user',job:'',major:'',bio:'',styles:[],saved_count:0,vote_count:0};
const reply=payload=>({ok:true,status:200,text:async()=>JSON.stringify(payload),json:async()=>payload});
globalThis.fetch=async (url,opts={})=>{
  url=String(url); asked.push({url,opts});
  if(url.includes('/api/auth/me')) return reply({status:'ok',data:{authenticated:false,csrf_token:'csrf',google_client_id:'cid.apps.googleusercontent.com',user:null}});
  if(url.endsWith('/api/auth/google')) return reply({status:'ok',data:{authenticated:false,needs_signup:true,csrf_token:'csrf2',google:{email:'me@gmail.com',name:'구글회원'},user:null}});
  if(url.includes('/api/auth/google-signup')) return reply({status:'ok',data:{authenticated:true,csrf_token:'csrf3',google_client_id:'cid.apps.googleusercontent.com',user}});
  if(url.includes('/api/dictionary')) return reply({status:'ok',data:[]});
  return reply({status:'empty',reason:'테스트 데이터 없음',data:null});
};
const wait=ms=>new Promise(r=>setTimeout(r,ms));

await import(`${root}/main.js`);
const router=await import(`${root}/app_shell/static/js/router.js`);
const profile=await import(`${root}/account/static/js/profile.js`);
await wait(60);
assert.ok(initCfg,'화면이 뜰 때 GIS 코드 클라이언트를 미리 만들어야 한다');
assert.equal(initCfg.client_id,'cid.apps.googleusercontent.com');
assert.equal(initCfg.ux_mode,'popup');
assert.ok(initCfg.scope.includes('openid'));

router.goView('login');
document.getElementById('googleLoginBtn').click();
assert.equal(requested,1,'클릭 순간 동기적으로 팝업(requestCode)을 열어야 한다');
await wait(80);

const g=asked.find(x=>x.url.endsWith('/api/auth/google'));
assert.ok(g,'인가 코드를 서버로 보내야 한다');
assert.deepEqual(JSON.parse(g.opts.body),{code:'code-1'});
assert.equal(g.opts.headers['X-CSRFToken'],'csrf');
assert.equal(document.body.dataset.view,'signup','처음 온 Google 계정은 가입 화면으로 간다');
assert.equal(document.getElementById('suId').value,'me@gmail.com');
assert.equal(document.getElementById('suId').readOnly,true);
assert.equal(document.getElementById('suPwBlock').hidden,true,'Google 가입은 비밀번호를 받지 않는다');
assert.equal(document.getElementById('suNickname').value,'구글회원');

document.getElementById('suHeight').value='170';
document.getElementById('suWeight').value='60';
document.getElementById('suAgeAgree').checked=true;
document.getElementById('suTermsAgree').checked=true;
document.getElementById('suPrivacyAgree').checked=true;
document.getElementById('signupForm').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
await wait(80);
const s=asked.find(x=>x.url.includes('/api/auth/google-signup'));
assert.ok(s,'Google 가입 API를 호출해야 한다');
const body=JSON.parse(s.opts.body);
assert.equal(body.nickname,'구글회원');
assert.ok(!('password' in body) && !('username' in body),'Google 가입은 아이디·비밀번호를 보내지 않는다');
assert.equal(asked.some(x=>x.url.endsWith('/api/auth/signup')),false);
assert.equal(profile.AUTH.in,true);
console.log('✅ Google 로그인 버튼이 코드 팝업 → 서버 교환 → Google 가입까지 이어집니다.');
process.exit(0);
