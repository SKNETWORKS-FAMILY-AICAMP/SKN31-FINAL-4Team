import { $, A, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';
import { stateOf, seriesOf, seriesFromRows, lastDateOf, unavailableHTML } from './live_data.js';

/* ══════════════════════════════════════════════════════
   차트 엔진 — 일 · 주 · 월 전환과 마우스오버 판독
   같은 아이템은 언제 봐도 같은 수치가 나와야 하므로 난수를 이름으로 고정한다.
   ══════════════════════════════════════════════════════ */
export function gSeed(s){ let h=2166136261; s=String(s);
  for(let i=0;i<s.length;i++){ h^=s.charCodeAt(i); h=Math.imul(h,16777619) }
  return (h>>>0)/4294967295;
}
function gRand(seed){ let x=seed*10000%1||0.137;
  return ()=>{ x=(x*9301+0.49297)%1; return x } }
/* ★ 2026-09-22 — 일별 기본 창을 30일 → 7일로 줄였다.
     화면은 '지금 뜨는 것'을 보는 곳이라 최근 1주가 기본이 맞다.
     창의 끝은 오늘이 아니라 **마지막 적재일**이다(resample 이 그렇게 잡는다).
     그래서 하루가 적재될 때마다 9/1~9/30 → 9/2~10/1 처럼 저절로 하루씩 민다.
     다만 1주에 관측이 몇 개 없으면 점 두어 개짜리 그래프가 되므로
     아래에서 30일로 넓힌다(WIDE_D). 넓혔다는 사실은 화면에 밝힌다. */
const GRAN=[['d','일별',7],['w','주별',26],['m','월별',18]];
const WIDE_D=30;        // 1주가 너무 비면 넓힐 창
const MIN_OBS_D=4;      // 1주 창에 이만큼은 관측이 있어야 그대로 쓴다
const G_UNIT={d:'일',w:'주',I:'',m:'개월'};
/* 오늘로부터 거슬러 올라가는 눈금 라벨 */
function gLabels(g,n,endIso){
  /* 실데이터는 마지막 적재일을 끝 눈금으로 쓴다. 장식용(난수)은 예전 기준일 그대로. */
  const now=endIso?new Date(endIso+'T00:00:00'):new Date(2026,7,19), out=[];
  for(let i=n-1;i>=0;i--){
    const t=new Date(now);
    if(g==='d')t.setDate(t.getDate()-i);
    else if(g==='w')t.setDate(t.getDate()-i*7);
    else t.setMonth(t.getMonth()-i);
    out.push(g==='m'?(t.getFullYear()+'.'+String(t.getMonth()+1).padStart(2,'0'))
      :(String(t.getMonth()+1).padStart(2,'0')+'.'+String(t.getDate()).padStart(2,'0')
        +(g==='w'?' 주':'')));
  }
  return out;
}
/* 추세 + 계절성 + 잡음. shape 로 곡선 성격을 바꾼다. */
function gSeries(key,g,shape,lo,hi){
  const n=GRAN.find(x=>x[0]===g)[2], r=gRand(gSeed(key+g+shape)), out=[];
  for(let i=0;i<n;i++){
    const p=i/(n-1); let base;
    if(shape==='rise')      base=Math.pow(p,1.7);
    else if(shape==='fall') base=1-Math.pow(p,1.5);
    else if(shape==='peak') base=Math.sin(p*Math.PI);
    else if(shape==='late') base=p<.62?p*.35:.22+Math.pow((p-.62)/.38,1.6)*.78;
    else                    base=.5+Math.sin(p*Math.PI*2)*.28;
    const noise=(r()-.5)*(g==='d'?.14:g==='w'?.09:.05);
    out.push(Math.max(0,Math.min(1,base+noise)));
  }
  const sm=out.map((v,i,a)=>g==='d'?(v*.6+(a[i-1]??v)*.25+(a[i+1]??v)*.15):v);
  return sm.map(v=>+(lo+v*(hi-lo)).toFixed(1));
}
/* 여러 계열을 한 좌표계에 그린다. 판독용 히트존은 계열과 무관하게 하나. */
export function gChart(host,cfg){
  const el=(typeof host==='string')?$(host):host; if(!el)return;
  const W=620,H=210,PL=34,PR=14,PT=14,PB=28;
  const g=el.dataset.g||'w';
  const N=GRAN.find(x=>x[0]===g)[2];
  const labels=gLabels(g,N);
  /* 계열 하나를 실값으로 만든다. index:true 면 최대값을 100 으로 둔 지수로 바꾼다
     (언급량처럼 단위가 다른 값을 온도 0–100 축에 겹칠 때). */
  const toLive=(s,d)=>{
    if(!d)return null;
    if(s.index){ const mx=Math.max.apply(null,d.filter(v=>v!=null))||1; d=d.map(v=>v==null?null:v/mx*100); }
    return Object.assign({},s,{data:d.map(v=>v==null?null:+(+v).toFixed(2))});
  };
  /* ★ 실데이터가 먼저다.
       cfg.rows — 날짜별 행을 직접 받은 차트 (할인률·리세일·수명주기)
       cfg.term — 용어 캐시(/api/trend)를 쓰는 차트
       값이 없으면 난수로 채우지 않고 '측정 불가'를 적고 끝낸다.
       둘 다 없는 차트(장식용 미니 스파크 등)만 예전처럼 씨드 난수를 쓴다. */
  /* ★ 관측이 하루뿐이면 추이를 그리지 않는다.
       한 점을 앞뒤로 이어 30일짜리 평평한 선을 만들면, 없던 과거를 지어낸 그림이 된다. */
  /* cfg.type==='bar' — 건수 막대. 주·월은 구간 합(agg:'sum'), 빈 구간은 잇지 않는다(fill:false). */
  const isBar=cfg.type==='bar';
  const opt=(s,n)=>({points:n||N,step:g,raw:true,agg:s.agg||(isBar?'sum':'avg'),fill:!isBar});
  const obsDays=(rows,field)=>new Set((rows||[]).filter(r=>r&&r[field]!=null&&r.date)
    .map(r=>String(r.date).slice(0,10))).size;
  const THIN='관측된 날짜가 하루뿐이라 추이를 그리지 않습니다. 적재가 쌓이면 자동으로 그려집니다.';
  if(cfg.rows){
    const thin=cfg.sets.every(s=>obsDays(s.rows||cfg.rows,s.field||'value')<2);
    if(thin&&cfg.rows.length){
      el.innerHTML=unavailableHTML(THIN,'');
      el.dataset.live='thin';
      return;
    }
    const live=cfg.sets.map(s=>toLive(s,seriesFromRows(s.rows||cfg.rows,Object.assign(opt(s),{field:s.field||'value'}))));
    if(live.every(Boolean)){
      el.dataset.live='ok';
      return gPaint(el,cfg,g,gLabels(g,N,lastDateOf(cfg.rows)),live);
    }
    el.innerHTML=unavailableHTML(cfg.emptyReason||'이 차트에 쓸 값이 아직 없습니다.',
      cfg.sets.filter((s,i)=>!live[i]).map(s=>s.name).join(' · ')+(live.some(Boolean)?' 계열이 비어 있어 섞어 그리지 않습니다.':''));
    el.dataset.live=live.some(Boolean)?'partial':'unavailable';
    return;
  }
  if(cfg.term){
    const st=stateOf(cfg.term);
    if(st.status==='empty'||st.status==='error'){
      el.innerHTML=unavailableHTML(st.reason,
        st.status==='error' ? '연결이 되면 자동으로 실제 값이 뜹니다.' : '');
      el.dataset.live='unavailable';
      return;
    }
    if(st.status==='ok'){
      if(st.byDate&&st.byDate.size<2){
        el.innerHTML=unavailableHTML(THIN,'');
        el.dataset.live='thin';
        return;
      }
      /* 창 안에 '진짜 관측'이 몇 개인지 센다.
         fill:true 면 빈 날을 앞뒤 값으로 메우므로, 그려진 점 수를 세면 안 된다.
         원본 byDate 에서 실제로 있는 날짜만 센다. */
      const obsInWindow=(n)=>{
        const endIso=lastDateOf(st.byDate); if(!endIso)return 0;
        const end=new Date(endIso+'T00:00:00Z'); let c=0;
        for(const k of st.byDate.keys()){
          const diff=(end-new Date(k+'T00:00:00Z'))/86400000;
          if(diff>=0&&diff<n)c++;
        }
        return c;
      };
      const build=(n)=>cfg.sets.map(s=>toLive(s,seriesOf(cfg.term,Object.assign(opt(s,n),{field:s.field||'mention'}))));

      let win=N, widened=false, live=build(win);
      if(g==='d'&&N<WIDE_D&&obsInWindow(N)<MIN_OBS_D){
        win=WIDE_D; widened=true; live=build(win);
      }
      if(live.every(Boolean)){
        el.dataset.live='ok';
        el.dataset.window=String(win);
        el.dataset.widened=widened?'1':'';
        el.dataset.unit=g;
        /* 단위 토글로 다시 그릴 때도 화면 각주가 따라오게 알린다.
           안 그러면 주별로 바꿔도 각주는 '최근 7일' 인 채로 남아 거짓말이 된다. */
        el.dispatchEvent(new CustomEvent('gwin',{bubbles:true}));
        return gPaint(el,cfg,g,gLabels(g,win,lastDateOf(st.byDate)),live);
      }
      /* 계열 중 하나라도 값이 없으면 섞어 그리지 않는다.
         반은 진짜, 반은 난수인 그래프는 읽는 사람을 속인다. */
      el.innerHTML=unavailableHTML(
        '이 지표는 아직 RDS 에 값이 없습니다.',
        (st.unavailable && st.unavailable.reason) || '');
      el.dataset.live='partial';
      return;
    }
  }
  const sets=cfg.sets.map(s=>Object.assign({},s,{data:gSeries(cfg.key+s.id,g,s.shape,s.lo,s.hi)}));
  el.dataset.live='seeded';
  return gPaint(el,cfg,g,labels,sets);
}

/* 좌표계에 실제로 그리는 부분. 값이 어디서 왔든 그리는 방법은 같다. */
function gPaint(el,cfg,g,labels,sets,quiet){
  /* ★ 실제 화면 폭으로 그린다 (2026-10-02 — "큰 모니터에서 그래프 글씨가 뭉개진다").
     예전에는 viewBox 를 620×210 으로 고정하고 카드 폭에 맞춰 SVG 를 통째로 늘렸다.
     맥북(카드 ≈735px)에선 1.2배라 티가 안 났지만, 27인치(카드 ≈1390px)에선 2.2배로
     늘어나 8.5 단위 글씨가 19px 로 부풀고, 배율이 정수가 아니라 저해상도(DPR 1) 화면에서
     글자 가장자리가 번졌다. 이제 viewBox 폭 = 카드의 실제 px 폭이라 1:1 로 그려진다 —
     글씨는 어느 화면에서나 같은 크기(CSS .axl)로 또렷하고, 높이는 폭을 따라 조금만
     자란다(기본 높이의 1.45배까지). 폭이 바뀌면(창 크기 · 숨었던 탭이 보일 때) 다시 그린다.
     자리를 못 재는 순간(숨은 탭 · jsdom)에는 예전처럼 620 기준으로 그려 두고 늘린다. */
  const host=el.querySelector('.chartBox');
  const live=Math.round((host&&host.clientWidth)||el.clientWidth||0);
  const measured=live>=200;
  const baseH=cfg.h||210;
  const W=measured?live:(cfg.wide?gWideW(el):620);
  const H=measured?Math.round(Math.min(baseH*1.45,Math.max(baseH,W*baseH/620))):baseH;
  const PL=34,PR=14,PT=14,PB=28;
  el._gArgs=[cfg,g,labels,sets]; el._gW=measured?W:0;
  gWatch(el);
  const n=labels.length;
  const isBar=cfg.type==='bar';
  const all=sets.reduce((a,s)=>a.concat(s.data),[]).filter(v=>v!=null);
  const mn=cfg.min!=null?cfg.min:Math.min.apply(null,all), mx=cfg.max!=null?cfg.max:Math.max.apply(null,all);
  const pad=(mx-mn)*.16||1, LO=cfg.min!=null?mn:mn-pad;
  /* 건수 막대는 눈금이 정수로 떨어지게 위쪽 끝을 '보기 좋은 수 × 4' 로 올린다 (5.8건 같은 눈금은 없다) */
  const niceStep=v=>{ const e=Math.pow(10,Math.floor(Math.log10(v||1))), f=v/e;
    return Math.max(1,([1,1.5,2,2.5,3,4,5,6,8,10].find(x=>f<=x+1e-9)||10)*e); };
  const HI=cfg.max!=null?mx:isBar?LO+Math.ceil(niceStep((mx-LO)*1.08/4))*4:mx+pad;
  /* 막대는 칸 가운데에 선다(선처럼 양 끝에 붙으면 첫·끝 막대가 반쪽이 된다) */
  const slot=(W-PL-PR)/Math.max(1,n);
  const X=isBar?(i=>PL+slot*(i+.5)):(i=>PL+(W-PL-PR)*(n===1?0:i/(n-1)));
  const Y=v=>PT+(H-PT-PB)*(1-(v-LO)/((HI-LO)||1));
  const line=d=>d.map((v,i)=>(i?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1)).join(' ');
  const gridY=[0,.25,.5,.75,1].map(p=>{
    const y=PT+(H-PT-PB)*p, v=(HI-(HI-LO)*p);
    return '<line class="grid" x1="'+PL+'" y1="'+y.toFixed(1)+'" x2="'+(W-PR)+'" y2="'+y.toFixed(1)+'"/>'+
      '<text class="axl" x="'+(PL-7)+'" y="'+(y+3).toFixed(1)+'" text-anchor="end">'+
      (Math.round(v*10)/10)+'</text>';
  }).join('');
  const step=Math.max(1,Math.ceil(n/6));
  const gridX=labels.map((l,i)=>(i%step===0||i===n-1)
    ? '<text class="axl" x="'+X(i).toFixed(1)+'" y="'+(H-8)+'" text-anchor="middle">'+l+'</text>':'').join('');
  const colorOf=s=>s.color||(s.accent?'var(--coral)':'var(--pink-0)');
  /* 막대: 한 칸에 계열 수만큼 나란히. 값이 없는 칸(null)은 세우지 않는다 — 0 과 '측정 못 함'은 다른 말이다. */
  const bw=slot*.74/Math.max(1,sets.length);
  const bars=isBar?sets.map((s,k)=>s.data.map((v,i)=>{
    if(v==null)return '';
    const y=Y(v), h=Math.max(0,(H-PB)-y);
    return '<rect class="gBar" data-s="'+s.id+'" x="'+(X(i)-slot*.37+bw*k).toFixed(1)+'" y="'+y.toFixed(1)+
      '" width="'+Math.max(1,bw-1).toFixed(1)+'" height="'+h.toFixed(1)+'" rx="1.5" style="fill:'+colorOf(s)+'"/>';
  }).join('')).join(''):'';
  const paths=isBar?'':sets.map(s=>'<path class="'+(s.accent?'ln2':'ln')+'" d="'+line(s.data)+'"/>').join('');
  const heads=isBar?'':sets.map(s=>'<circle class="'+(s.accent?'hd2':'hd')+'" data-s="'+s.id+'" r="4.5" cx="0" cy="0"/>').join('');
  el.innerHTML=
    '<div class="gSel">'+GRAN.map(x=>'<button type="button" data-g="'+x[0]+'"'+
      (x[0]===g?' class="on"':'')+'>'+x[1]+'</button>').join('')+'</div>'+
    '<div class="chartBox">'+
      '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'+
        (cfg.band?'<rect class="band" x="'+X(Math.round(n*cfg.band[0]))+'" y="'+PT+'" width="'+
          (X(Math.round(n*cfg.band[1]))-X(Math.round(n*cfg.band[0])))+'" height="'+(H-PT-PB)+'"/>':'')+
        gridY+gridX+
        '<line class="ax" x1="'+PL+'" y1="'+(H-PB)+'" x2="'+(W-PR)+'" y2="'+(H-PB)+'" stroke="var(--pink-3)"/>'+
        (isBar?'<rect class="gCol" x="0" y="'+PT+'" width="'+slot.toFixed(1)+'" height="'+(H-PT-PB)+'"/>'+bars:paths)+
        (isBar?'':'<line class="xh" x1="0" y1="'+PT+'" x2="0" y2="'+(H-PB)+'"/>')+heads+
        '<rect x="'+PL+'" y="0" width="'+(W-PL-PR)+'" height="'+H+'" fill="transparent" class="hit"/>'+
      '</svg>'+
      '<div class="gTip"></div>'+
    '</div>'+
    /* 범례는 한 계열이어도 단다 (2026-10-02) — '연관어 수' · '화제성 레벨' 처럼 하나만 그린
       그래프는 축에 숫자만 있어 무슨 지표인지가 각주에만 숨어 있었다. */
    (sets.length?'<div class="gLegend">'+sets.map(s=>
      '<span><i'+(isBar?' class="sq"':'')+' style="background:'+colorOf(s)+'"></i>'+s.name+'</span>').join('')+'</div>':'');
  /* 판독 — viewBox 가 늘어나므로 화면 좌표를 비율로 되돌려 인덱스를 찾는다 */
  const box=el.querySelector('.chartBox'), svg=el.querySelector('svg'), tip=el.querySelector('.gTip');
  const xh=el.querySelector('.xh'), hds=[...el.querySelectorAll('.hd,.hd2')], col=el.querySelector('.gCol');
  const fmt=(s,v)=>v==null?'–':(isBar?Math.round(v).toLocaleString():v.toFixed(1));
  const read=e=>{
    const r=svg.getBoundingClientRect(); if(!r.width)return;
    const px=(e.clientX-r.left)/r.width*W;
    let i=isBar?Math.floor((px-PL)/slot):Math.round((px-PL)/((W-PL-PR)/(n-1||1)));
    i=Math.max(0,Math.min(n-1,i));
    box.classList.add('hov');
    if(xh){ xh.setAttribute('x1',X(i)); xh.setAttribute('x2',X(i)); }
    if(col) col.setAttribute('x',(X(i)-slot/2).toFixed(1));
    hds.forEach((h,k)=>{ h.setAttribute('cx',X(i)); h.setAttribute('cy',Y(sets[k].data[i]??LO)) });
    tip.innerHTML='<span class="dt">'+labels[i]+'</span>'+sets.map(s=>
      '<span class="vv"><i style="background:'+(isBar&&colorOf(s)!=='var(--pink-0)'?colorOf(s):(s.accent?'var(--coral)':'var(--paper)'))  /* 검정 막대는 검정 말풍선 위에서 안 보여 종이색 점으로 */+'"></i>'+
      /* 무슨 값인지 늘 적는다 (2026-10-02) — 선 그래프는 색 점과 숫자만 있어 어느 지표인지 몰랐다 */
      '<span>'+s.name.replace(/\s*\(.*\)$/,'')+'</span>'+
      '<b>'+fmt(s,s.data[i])+'</b><span>'+(s.data[i]==null?'':(s.unit||''))+'</span></span>').join('');
    const ys=sets.map(s=>s.data[i]).filter(v=>v!=null).map(Y);
    const ty=(ys.length?Math.min.apply(null,ys):H-PB);
    /* 1:1 로 그렸으면 정수 px 에 세운다 — 소수점 위치의 말풍선 글씨가 번지지 않게 */
    if(measured){ tip.style.left=Math.round(X(i)/W*r.width)+'px'; tip.style.top=Math.round(ty/H*r.height-H*.04)+'px'; }
    else{ tip.style.left=(X(i)/W*100)+'%'; tip.style.top=(ty/H*100-4)+'%'; }
  };
  svg.addEventListener('mousemove',read);
  svg.addEventListener('mouseleave',()=>box.classList.remove('hov'));
  el.querySelector('.gSel').addEventListener('click',ev=>{
    const b=ev.target.closest('button'); if(!b)return;
    el.dataset.g=b.dataset.g; gChart(el,cfg);
    if(HAS_A)aAnimate(el.querySelectorAll('.ln,.ln2,.gBar'),{opacity:[0,1],duration:420,ease:'out(2)'});
  });
  if(isBar){
    /* 막대는 바닥에서 솟아오르게 — anime.js 가 없으면 그냥 서 있는 채로 둔다 */
    const bs=el.querySelectorAll('.gBar');
    if(HAS_A&&bs.length){ try{ aAnimate(bs,{scaleY:[0,1],duration:620,delay:aStagger(6),ease:'out(3)'}); }catch(e){} }
  } else if(!quiet) gDraw(el.querySelectorAll('.ln,.ln2'),1050,180);
  return el;
}
/* 카드 폭이 바뀌면 같은 값으로 다시 그린다 — 연출 없이. 높이만 바뀐 것(다시 그린 결과)은 무시한다. */
function gWatch(el){
  if(el._gRO||typeof ResizeObserver==='undefined')return;
  el._gRO=new ResizeObserver(()=>{
    const host=el.querySelector('.chartBox');
    const w=Math.round((host&&host.clientWidth)||el.clientWidth||0);
    if(w<200||Math.abs(w-(el._gW||0))<=4)return;
    cancelAnimationFrame(el._gRaf);
    el._gRaf=requestAnimationFrame(()=>{
      const a=el._gArgs; if(!a||!el.isConnected)return;
      gPaint(el,a[0],a[1],a[2],a[3],true);
    });
  });
  el._gRO.observe(el);
}
function gWideW(el){
  const grid=el.closest('.trGrid'), panel=el.closest('.panelC');
  const G=grid?grid.clientWidth:0;
  if(!G||!panel)return Math.round(620*1.7);
  const cs=getComputedStyle(panel);
  const chrome=parseFloat(cs.paddingLeft)+parseFloat(cs.paddingRight)+
               parseFloat(cs.borderLeftWidth)+parseFloat(cs.borderRightWidth);
  const wide=G-chrome;                               /* 지금 카드 안쪽 폭 */
  const base=(G-12)*1.5/2.5-chrome;                  /* 원래 두 칸일 때 왼쪽 카드 안쪽 폭 (.trGrid 1.5fr : 1fr, gap 12px) */
  return Math.round(620*Math.max(1,wide/Math.max(1,base)));
}
/* 선이 그려지며 들어오는 연출.
   createDrawable 은 "엘리먼트"가 아니라 "프록시"를 돌려주고, 그 프록시를 타깃으로
   써야 draw 가 먹는다. 엘리먼트를 그대로 넘기면 stroke-dasharray 가 0 인 채로 남아
   선이 통째로 사라진다. 끝나면 대시를 지워 어떤 경우에도 실선으로 남긴다. */
export function gDraw(paths,dur,stag){
  const ps=[...paths]; if(!ps.length)return;
  const clear=()=>ps.forEach(p=>{ p.style.strokeDasharray=''; p.style.strokeDashoffset=''; });
  const dr=HAS_A&&((A&&A.svg&&A.svg.createDrawable)||(A&&A.createDrawable));
  if(!dr){ clear(); return }
  let tg=[];
  try{ tg=ps.map(p=>dr(p)).filter(Boolean) }catch(e){ clear(); return }
  if(!tg.length){ clear(); return }
  try{
    aAnimate(tg,{draw:['0 0','0 1'],duration:dur||1050,
      delay:aStagger(stag==null?180:stag),ease:'inOut(3)',onComplete:clear});
  }catch(e){ clear() }
  /* 혹시 draw 가 끝까지 안 돌아도 선은 반드시 보이게 */
  setTimeout(clear,(dur||1050)+ps.length*(stag==null?180:stag)+260);
}
