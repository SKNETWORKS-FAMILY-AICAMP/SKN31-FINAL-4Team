/* 이번 변경의 브라우저 경계: 중단 signal과 하단 행동 버튼 마크업. */
import { JSDOM } from 'jsdom';
import { browserEnv } from './browser_env.mjs';
/* chat_api.js 가 alpha.js 를 불러오고, alpha.js 는 불러오는 순간 document 를 본다 */
browserEnv(new JSDOM('<!doctype html><body></body>', {url:'http://localhost:5173/'}));

let lastSignal=null;
global.fetch=async (_url,opt={})=>{
  lastSignal=opt.signal;
  return await new Promise((_resolve,reject)=>{
    if(!opt.signal)return reject(new Error('signal missing'));
    /* 브라우저 fetch 는 이미 끊긴 signal 을 받으면 곧바로 거절한다.
       askStream 이 알파 횟수 차감(await)을 먼저 하므로, 그 사이에 끊기면 이 경우가 된다. */
    if(opt.signal.aborted)return reject(new Error('aborted'));
    opt.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true});
  });
};

const api=await import('./chat_api.js');
let fail=0;
const ok=(condition,message)=>{
  console.log((condition?'  OK  ':'  X!! ')+message);
  if(!condition)fail++;
};

console.log('=== 실행 중단 ===');
const controller=new AbortController();
const pending=api.askStream({question:'x'},{},{signal:controller.signal});
controller.abort();
let stopped=false;
try{await pending}catch(_error){stopped=true}
ok(stopped,'AbortController로 진행 중인 스트림을 끊는다');
ok(lastSignal===controller.signal,'fetch에 같은 signal을 전달한다');

console.log('\n=== 첨부 이미지 바로 입혀보기 ===');
ok(api.wantsVirtualFit('AI 여자 모델에게 입혀줘',['data:image/jpeg;base64,eA==']),
  '이미지와 착장 요청이 함께 오면 바로 입혀보기로 분기한다');
ok(!api.wantsVirtualFit('이 옷의 소재를 설명해 줘',['data:image/jpeg;base64,eA==']),
  '일반 이미지 질문은 분석 응답 경로를 유지한다');
ok(api.responseCardHTML({key:'trend',fit:{}},()=>'<div>발레코어 목업</div>')==='',
  '착장 전용 메시지에는 질문 key 기반 목업 카드를 붙이지 않는다');
ok(api.responseCardHTML({key:'trend',cardHtml:'<div>실제 카드</div>',fit:{}},()=>'' ).includes('실제 카드'),
  '기존 응답에서 연 착장 카드는 실제 리포트를 유지한다');

console.log('\n=== 비교 지표 라벨 ===');
const metricHTML=api.reportHTML({intent:'agent',as_of:{},blocks:[{
  type:'generative_report',slot:'full',title:'비교',accent:'coral',surface:'paper',density:'balanced',
  modules:[{kind:'direction',presentation:'card',emphasis:'normal',span:6,columns:2,
    block:{type:'kpis',title:'스트릿웨어',meta:'스타일',items:[{k:'방향',v:'상승'}]}}]
}]});
ok(metricHTML.includes('스트릿웨어')&&metricHTML.includes('스타일'),
  '나란히 본 각 KPI 묶음에 용어와 지표 분류를 표시한다');

console.log('\n=== 응답 하단 버튼 ===');
const html=api.actionsHTML([
  {label:'물어보기',type:'community'},
  {label:'입혀보기',type:'virtual_fit'},
  {label:'지표로 보기',type:'view',view:'trend'},
]);
ok((html.match(/class="pill ghost actBtn/g)||[]).length===3,'모든 행동이 같은 카드형 버튼 문법을 쓴다');
ok(html.includes('act-community')&&html.includes('act-virtual_fit'),'행동별 시각 훅이 있다');
ok(html.includes('actIcon')&&html.includes('actArrow'),'아이콘과 방향 표시를 분리한다');

console.log(fail?'\n실패 '+fail+'건':'\n전부 통과');
process.exit(fail?1:0);
