/* 기존 회원가입 디자인을 그대로 실행해 실제 계정 API 요청으로 이어지는지 확인한다. */
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

const asked=[];
const user={username:'feedit01',email:'feedit01',nickname:'피딧회원',initial:'피',birth_date:'2000-01-02',
  height:170,weight:60,gender:'FEMALE',avatar:0,role:'user',job:'',major:'',bio:'',styles:[],saved_count:0,vote_count:0};
const reply=payload=>({ok:true,status:200,text:async()=>JSON.stringify(payload),json:async()=>payload});
globalThis.fetch=async (url,opts={})=>{
  asked.push({url:String(url),opts});
  if(String(url).includes('/api/auth/me')) return reply({status:'ok',data:{authenticated:false,csrf_token:'csrf',user:null}});
  if(String(url).includes('/api/auth/email-code')) return reply({status:'ok',data:{sent:true,ttl:600}});
  if(String(url).includes('/api/auth/email-verify')) return reply({status:'ok',data:{verified:true,email:'feedit01@example.com'}});
  if(String(url).includes('/api/auth/signup')) return reply({status:'ok',data:{authenticated:true,csrf_token:'csrf2',user}});
  if(String(url).includes('/api/dictionary')) return reply({status:'ok',data:[]});
  return reply({status:'empty',reason:'테스트 데이터 없음',data:null});
};

await import(`${root}/main.js`);
const router=await import(`${root}/app_shell/static/js/router.js`);
const profile=await import(`${root}/account/static/js/profile.js`);
document.getElementById('jumpBtn').click();
router.goView('signup');
document.getElementById('suId').value='feedit01';
document.getElementById('suNickname').value='피딧회원';
document.getElementById('suPw').value='Secret!234';
document.getElementById('suPw2').value='Secret!234';
document.getElementById('suBirth').value='2000-01-02';
document.getElementById('suHeight').value='170';
document.getElementById('suWeight').value='60';
document.getElementById('suEmail').value='feedit01@example.com';
document.getElementById('signupForm').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
await new Promise(resolve=>setTimeout(resolve,20));
assert.equal(document.getElementById('signupErr').textContent,'이메일 인증을 완료해 주세요.');
/* 이메일 인증 — 인증번호 받기 → 6자리 입력 → 확인 */
document.getElementById('suEmailSend').click();
await new Promise(resolve=>setTimeout(resolve,20));
assert.equal(document.getElementById('suCodeRow').hidden,false,'인증번호를 보내면 입력 칸이 열린다');
document.getElementById('suCode').value='123456';
document.getElementById('suCodeCheck').click();
await new Promise(resolve=>setTimeout(resolve,20));
assert.equal(document.getElementById('suEmailMsg').textContent,'이메일 인증이 완료됐어요.');
document.getElementById('signupForm').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
await new Promise(resolve=>setTimeout(resolve,20));
assert.equal(asked.some(x=>x.url.includes('/api/auth/signup')),false,'필수 동의 전에는 가입 요청을 보내지 않아야 한다');
assert.equal(document.getElementById('signupErr').textContent,'성별을 선택해 주세요.');
document.querySelector('input[name="suGender"][value="FEMALE"]').checked=true;
document.getElementById('signupForm').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
await new Promise(resolve=>setTimeout(resolve,20));
assert.equal(document.getElementById('signupErr').textContent,'만 14세 이상만 가입할 수 있습니다.');
document.getElementById('suAgeAgree').checked=true;
document.getElementById('suTermsAgree').checked=true;
document.getElementById('suPrivacyAgree').checked=true;
document.getElementById('signupForm').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
await new Promise(resolve=>setTimeout(resolve,80));

const call=asked.find(x=>x.url.includes('/api/auth/signup'));
assert.ok(call,'회원가입 API를 호출해야 한다');
assert.equal(JSON.parse(call.opts.body).username,'feedit01');
assert.equal(JSON.parse(call.opts.body).email,'feedit01@example.com','인증을 마친 이메일을 함께 보낸다');
assert.equal(JSON.parse(call.opts.body).gender,'FEMALE');
assert.equal(profile.ME.gender,'FEMALE');
assert.equal(profile.AUTH.in,true,'DB 가입 성공 뒤에만 로그인 상태가 된다');
assert.equal(document.getElementById('mAuthBtn').textContent.includes('피딧회원'),true);
assert.ok(document.getElementById('styleSelectModal').classList.contains('on'),'기존 스타일 선택 디자인을 이어서 보여 준다');
console.log('✅ 기존 회원가입 화면이 실제 DB API와 연결됩니다.');
process.exit(0);
