/* 계정 브라우저 API가 CSRF를 먼저 받고, 비밀번호를 POST 본문으로만 보내는지 확인한다. */
import assert from 'node:assert/strict';

const calls=[];
globalThis.fetch=async (url,opts={})=>{
  calls.push({url,opts});
  if(url.endsWith('/me')) return reply(200,{
    status:'ok',data:{authenticated:false,csrf_token:'csrf-123',user:null},
  });
  return reply(200,{
    status:'ok',data:{authenticated:true,csrf_token:'csrf-456',user:{nickname:'피딧'}},
  });
};
const reply=(status,payload)=>({
  ok:status>=200&&status<300,status,text:async()=>JSON.stringify(payload),
});

const api=await import('../account/static/js/account_api.js');
const logged=await api.loginAccount('feedit01','Secret!234');
assert.equal(logged.authenticated,true);
assert.equal(calls.length,2,'CSRF 준비 GET 뒤 로그인 POST가 나가야 한다');
assert.equal(calls[0].url,'/api/auth/me');
assert.equal(calls[1].url,'/api/auth/login');
assert.equal(calls[1].opts.credentials,'same-origin');
assert.equal(calls[1].opts.headers['X-CSRFToken'],'csrf-123');
assert.deepEqual(JSON.parse(calls[1].opts.body),{username:'feedit01',password:'Secret!234'});
assert.ok(!calls[1].url.includes('Secret'),'비밀번호가 URL에 들어가면 안 된다');
await api.weeklyVideos();
assert.equal(calls[2].url,'/api/auth/weekly-videos');
assert.equal(calls[2].opts.method,'GET');
assert.equal(calls[2].opts.credentials,'same-origin','개인화 추천에도 세션 쿠키를 보내야 한다');
console.log('✅ 계정 API가 세션·CSRF 방식으로 로그인합니다.');
