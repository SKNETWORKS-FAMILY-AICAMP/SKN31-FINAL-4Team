/* 생성형 UI 스펙이 고정 variant 없이 안전한 HTML 캔버스로 조립되는지 확인한다. */
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const dom=new JSDOM('<!doctype html><body></body>',{url:'http://localhost:5173/'});
global.window=dom.window; global.document=dom.window.document; global.location=dom.window.location;
const api=await import('./chat_api.js');
const cssText=fs.readdirSync('css').map(f=>fs.readFileSync('css/'+f,'utf8')).join('\n');

let fail=0;
const ok=(cond,msg)=>{ console.log((cond?'  OK  ':'  X!! ')+msg); if(!cond)fail++; };
const block={type:'rank',slot:'full',title:'고프코어',rows:[{k:'트렌드 온도',v:'82점',up:true}]};
const report={
  ok:true,intent:'agent',as_of:{metric:'2026-09-10'},
  blocks:[{type:'generative_report',slot:'full',title:'고프코어 흐름',accent:'violet',
    surface:'soft',density:'airy',fingerprint:'abc123',modules:[
      {id:'metric:고프코어',kind:'metric',presentation:'hero',span:8,emphasis:'strong',block},
      {id:'evidence:고프코어',kind:'evidence',presentation:'editorial',span:4,
       emphasis:'quiet',block:{type:'note',text:'실제 결과만 사용합니다.'}},
    ]}],
};

console.log('=== 생성형 캔버스 ===');
const box=document.createElement('div'); box.innerHTML=api.reportHTML(report);
ok(!!box.querySelector('.skillReport--violet.skillReport--soft.skillReport--airy'), '디자인 토큰을 조합한다');
ok(box.querySelectorAll('.skillModule').length===2, '모델이 고른 모듈 수만큼 그린다');
ok(box.querySelector('.skillModule--hero').getAttribute('style').includes('span 8'), '12열 폭을 반영한다');
ok(!!box.querySelector('.skillModule--block-rank'), '블록 종류를 모듈 스타일 훅으로 남긴다');
ok(box.textContent.includes('82점'), '기존 데이터 블록을 재사용한다');
ok(!box.innerHTML.includes('variant'), '이름 붙은 레이아웃 variant 가 없다');
ok(box.textContent.includes('LIVE REPORT') && box.textContent.includes('SIGNALS'), '편집형 메타 헤더를 표시한다');

console.log('\n=== 이전 지표 프레임 통일 ===');
const legacyBox=document.createElement('div');
legacyBox.innerHTML=api.reportHTML({intent:'agent',as_of:{metric:'2026-09-11'},blocks:[
  {type:'rank',slot:'left',title:'니트',rows:[{k:'트렌드 온도',v:'56점'}]},
  {type:'bars',slot:'right',title:'플랫폼별 언급량',items:[{k:'에이블리',v:37,max:37}]},
]});
ok(!!legacyBox.querySelector('.skillReport--legacy'), '이전 2단 지표도 LIVE REPORT 외곽 프레임을 쓴다');
ok(legacyBox.textContent.includes('FEEDiT / LIVE REPORT') && legacyBox.textContent.includes('02 SIGNALS'),
  '이전 지표에도 같은 메타 헤더를 표시한다');
ok(!legacyBox.querySelector('.ansBar'), '브라우저 창 모양의 별도 헤더를 제거한다');

console.log('\n=== 근거 인용 카드 ===');
const evidence=structuredClone(report);
evidence.blocks[0].modules=[{id:'evidence:고프코어',kind:'evidence',presentation:'editorial',
  span:5,emphasis:'quiet',block:{type:'quotes',title:'근거가 된 대목',meta:'1건',
  items:[{body:'테크웨어 고프코어',src:'네이버',kind:'카페 글',tone:'긍정'}]}}];
const evidenceBox=document.createElement('div'); evidenceBox.innerHTML=api.reportHTML(evidence);
ok(!!evidenceBox.querySelector('blockquote.evidenceQuote'), '근거를 전용 인용 요소로 그린다');
ok(evidenceBox.querySelector('.evidenceMeta').textContent.includes('네이버 · 카페 글'), '출처 메타를 본문과 분리한다');
ok(!evidenceBox.querySelector('.skillModule--evidence .note'), '공용 안내문 스타일을 중첩하지 않는다');

console.log('\n=== 카드 개수 기반 KPI 배치 ===');
const sentiment=structuredClone(report);
sentiment.blocks[0].modules=[{id:'sentiment:고프코어',kind:'sentiment',presentation:'card',
  span:4,emphasis:'normal',columns:3,block:{type:'kpis',items:[
    {k:'구매의향 지수',v:'50',unit:'점',note:'표본 1건'},
    {k:'긍정 신호',v:'100.0',unit:'%',note:'구매고민'},
    {k:'부정 신호',v:'0.0',unit:'%',note:''},
  ]}}];
const sentimentBox=document.createElement('div'); sentimentBox.innerHTML=api.reportHTML(sentiment);
const sentimentModule=sentimentBox.querySelector('.skillModule--sentiment');
ok(sentimentModule.dataset.items==='3', '세 지표의 실제 카드 수를 렌더러에 전달한다');
ok(sentimentModule.getAttribute('style').includes('--skill-kpi-cols:3'), '세 지표를 한 줄 3칸으로 배치한다');
ok(/data-items="3"/.test(cssText) && /grid-template-columns:1fr/.test(cssText), '좁은 화면에서는 한 열로 안전하게 접는다');
ok(/skillModule--block-rank\.skillModule--editorial/.test(cssText), '이전 rank 스펙도 통일된 데이터 카드로 보정한다');

console.log('\n=== 안전한 토큰 폴백 ===');
const unsafe=structuredClone(report);
unsafe.blocks[0].accent='"><script>bad()</script>';
unsafe.blocks[0].modules[0].span='12;position:fixed';
const safe=document.createElement('div'); safe.innerHTML=api.reportHTML(unsafe);
ok(!!safe.querySelector('.skillReport--coral'), '허용하지 않은 색은 안전한 토큰으로 돌아간다');
ok(!safe.innerHTML.includes('<script>'), '문자열이 HTML 로 삽입되지 않는다');
ok(safe.querySelector('.skillModule').getAttribute('style')==='grid-column:span 12', '폭은 정수로 제한된다');
ok(/\.skillReport\b/.test(cssText) && /\.skillCanvas\b/.test(cssText), '새 캔버스 클래스가 CSS 에 있다');
ok(/container:skill-module/.test(cssText) && /@container skill-module/.test(cssText), 'KPI 열 수를 모듈 폭으로 결정한다');

console.log('\n=== 질문 유형별 템플릿 (2026-10-02) ===');
const days=(n,f)=>Array.from({length:n},(_,i)=>{const d=new Date(Date.UTC(2026,9,2-(n-1-i)));return f(d.toISOString().slice(0,10),i)});
const tpl=(template,blocks)=>({blocks:[{type:'generative_report',slot:'full',template,title:'제목',accent:'coral',surface:'paper',
  density:'balanced',modules:blocks.map((block,i)=>({id:'m'+i,kind:block.type,presentation:'hero',span:12,emphasis:'strong',block}))}]});
const draw=rep=>{const el=document.createElement('div'); el.innerHTML=api.reportHTML(rep); return el;};
const clean=el=>!/NaN|undefined|null/.test(el.textContent)&&!/NaN|undefined/.test(el.innerHTML);
const ticker={type:'ticker',term:'발레코어',facet:'스타일',as_of:'2026-10-02',temp:78,band:'따뜻함',verdict:'뜨거움',
  verdict_text:'언급량이 꾸준히 오르는 중입니다.',delta_1w:6,temp_1w_ago:72,top_pct:8,direction:'오르는 중',tone:'up',ratio:1.27,
  mention_7d:2884,mention_28d:9120,series:days(90,(d,i)=>({d,t:60+i*.2})),platforms:[{name:'유튜브',temp:84}],
  assoc:[{name:'리본 플랫',is_new:true}],notes:[]};
let el=draw(tpl('ticker',[ticker]));
ok(!!el.querySelector('.skillReport--tpl-ticker .tk'), '진단 질문 — 티커가 선다');
ok(el.querySelector('.skillReportTpl').textContent==='TICKER', '머리줄에 템플릿 이름을 적는다');
ok(el.querySelectorAll('.tkChart').length===3 && el.querySelectorAll('.tkChart.on').length===1, '7·28·90일 그래프를 미리 그리고 하나만 켠다');
ok(el.querySelector('.tkChart.on').dataset.range==='28', '기본은 28일');
api.tickerRange(el.querySelector('[data-tk-range="7"]'));
ok(el.querySelector('.tkChart.on').dataset.range==='7' && el.querySelector('.tkRangeNote.on').dataset.range==='7', '기간 버튼이 그래프와 문구를 함께 바꾼다');
ok(el.querySelector('[data-kw="리본 플랫"]'), '같이 뜨는 말은 눌러서 물어볼 수 있다');
const story=JSON.parse(el.querySelector('[data-rp-story]').dataset.rpStory);
ok(story.term==='발레코어' && story.series.length===28, '스토리 버튼이 티커 값을 들고 있다');
ok(api.storyHTML(story).includes('tkStoryCard') && api.storyHTML({temp:null})==='', '스토리 카드는 값이 있을 때만 그린다');
ok(clean(el), '티커에 NaN · undefined 가 없다');
const noDelta=draw(tpl('ticker',[{...ticker,delta_1w:null,temp_1w_ago:null,ratio:null,series:[]}]));
ok(noDelta.textContent.includes('관측이 모자라') && !noDelta.querySelector('.tkChart'), '없는 지난주 대비·그래프는 0 으로 채우지 않고 말한다');

el=draw(tpl('why',[{type:'timeline',term:'발레코어',window:60,points:days(60,(d,i)=>({d,m:i===30?300:20})),
  spikes:[{d:days(60,d=>d)[30],m:300,x:15,src:'유튜브',body:'올가을 하울'}],
  evidence:[{src:'유튜브',kind:'영상',body:'올가을 하울 <b>10벌</b>',url:'https://youtu.be/x',at:'2026-09-03',tone:'긍정'}],
  sentiment:{pos:64,neg:12,neu:24,n:900,days:28}}]));
ok(el.querySelectorAll('.tlBadge').length>=2 && el.querySelector('.tlMarks li'), '원인 질문 — 급상승에 번호와 설명이 붙는다');
ok(el.querySelector('a.tlCard[href="https://youtu.be/x"][rel="noopener"]'), '근거 카드는 원문으로 간다');
ok(!el.querySelector('.tlCard b'), '근거 본문의 태그는 글자로 남는다');

el=draw(tpl('versus',[{type:'versus',a:{term:'고프코어',temp:64,delta_1w:-2,series:days(28,(d,i)=>({d,t:66-i*.1}))},
  b:{term:'블록코어',temp:72,delta_1w:5,series:days(28,(d,i)=>({d,t:60+i*.5}))},
  rows:[{k:'트렌드 온도',a:64,b:72,av:'64°',bv:'72°',lo:54,hi:82,better:'b'}]}]));
ok(el.querySelector('.vsWin.b').textContent==='블록코어' && el.textContent.includes('역전'), '비교 질문 — 앞선 쪽과 역전 날짜를 적는다');

el=draw(tpl('leaderboard',[{type:'leaderboard',as_of:'2026-10-02',window_days:7,short:true,
  items:[1,2,3,4].map(r=>({rank:r,term:'용어'+r,facet:'스타일',temp:90-r,verdict:'뜨거움',band:'따뜻함',date:'2026-10-02'}))}]));
ok(el.querySelectorAll('.lbCard').length===3 && el.querySelectorAll('.lbRow').length===1, '순위 질문 — 1~3위 카드와 나머지 줄');
ok(el.textContent.includes('찾은 것 4개가 전부'), '요청보다 적으면 그렇다고 적는다');

el=draw(tpl('verdict',[{type:'verdict',term:'리본 플랫',score:72,rec:'살',allowed:true,confidence:'보통',coverage:60,
  signals:[{label:'트렌드',weight:20,score:85,why:'온도 상승'}],missing:[{label:'취향',weight:35}]},
  {type:'lifecycle',term:'발레코어',stage:'확산',progress:33,age_weeks:9,weekly:[]}]));
ok(el.querySelector('.vd--buy .vdStamp b').textContent==='살!', '판정 질문 — 살 도장');
ok(el.querySelector('.vdRow--missing') && el.textContent.includes('자료 없음'), '빠진 신호를 숨기지 않는다');
ok(el.querySelector('.lcLabel.on').textContent==='확산', '수명주기에 지금 단계를 표시한다');
const hold=draw(tpl('verdict',[{type:'verdict',score:55,rec:'보류',allowed:false,confidence:'낮음',coverage:30,signals:[],missing:[]}]));
ok(hold.querySelector('.vd--hold') && hold.textContent.includes('정하지 않았어요'), '근거가 모자라면 보류라고 말한다');

el=draw(tpl('orbit',[{type:'orbit',term:'발레코어',items:[['리본 플랫',3.4,412,true],['레그워머',2.9,288,false],['랩스커트',2.6,251,false]]
  .map(([name,lift,co,is_new])=>({name,lift,co,is_new}))}]));
ok(el.querySelectorAll('.obBubble').length===3 && el.querySelector('.obBubble.new'), '연관 질문 — 연관 강도만큼 놓는다');

el=draw(tpl('lowsignal',[{type:'lowsignal',term:'모브코어',n:9,need:20,window:28,points:[{d:'2026-09-16',m:2},{d:'2026-10-01',m:3}],
  first_seen:'2026-09-16',sources:[{name:'유튜브',n:7}],near:['라벤더 니트']}]));
ok(el.querySelectorAll('.lsTicks i.on').length===9 && el.querySelectorAll('.lsDot').length===2, '관측 부족 — 9/20 과 관측된 날만 점으로');
ok(!el.querySelector('.tkTemp'), '관측이 얇으면 온도 숫자를 크게 세우지 않는다');

const evil=draw(tpl('ticker',[{...ticker,term:'<img src=x onerror=alert(1)>'}]));
ok(!evil.querySelector('img') && evil.textContent.includes('<img'), '용어 이름은 글자로만 들어간다');
ok(/\.tk\{/.test(cssText) && /\.vdStamp\{/.test(cssText) && /\.obBubble\{/.test(cssText) && /\.lsTicks\{/.test(cssText), '템플릿 클래스가 CSS 에 있다');
ok(/@container skill-module \(max-width:640px\)/.test(cssText), '좁은 폭에서는 모듈 폭으로 접는다');

console.log(fail?`\n실패 ${fail}건`:'\n전부 통과');
process.exit(fail?1:0);
