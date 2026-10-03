import { $ } from '../../../core/static/js/dom.js';
import { ME } from './profile.js';

/* ══════════════════════════════════════════════════════
   등급 뱃지 — 전부 48 그리드 · 획 1.4 로 한 가족처럼 읽히게.
   1~4 는 currentColor 를 따라가고, 5~7 만 금속/브랜드 그라디언트를 쓴다.
   ══════════════════════════════════════════════════════ */
/* ★ 2026-09-19 — 등급(Lv) 기준이 확정될 때까지 화면에서 숨겼다.
   ★ 2026-09-25 — 경험치 기준이 정해져 다시 켠다.
     ME.xp 는 서버(/api/auth/me · /api/auth/xp)가 기록으로 계산한 누적값이다
     (backend/apps/api/xp.py). 모든 일반 계정은 0 에서 시작하고,
     운영 계정은 계산하지 않고 최고 레벨로 고정한다(ME.xpFixed). */
export const RANK_ON=true;
const RANKS=[
  {k:'lv1',n:'Lv.1'}, {k:'lv2',n:'Lv.2'}, {k:'lv3',n:'Lv.3'},
  {k:'lv4',n:'Lv.4'}, {k:'lv5',n:'Lv.Max'}
];
export const RK_MAX=RANKS.length-1;
/* 레벨 구간 — 누적 경험치가 이 문턱을 넘을 때마다 한 단계 오른다.
   마지막 칸은 상한이 없으므로 Infinity 로 닫는다.
   ★ 레벨 구간은 여기 한 곳에만 있다. 서버는 누적 XP 만 준다.
     (한 주 최대 210 XP — Lv.2 는 2주, Lv.Max 는 매주 다 채워도 43주쯤 걸린다) */
export const RK_XP=[0, 300, 1200, 3600, 9000, Infinity];
export const rkName=i=>RANKS[rkClamp(i)].n;
/* Lv.4·Lv.Max 는 단색이 아니라 금속 그라디언트로 채운다 */
const RK_GRAD=['none','none','none',
  'linear-gradient(90deg,#c9a961,#f4e3b8 45%,#c9a961)',
  'linear-gradient(90deg,#ff6b4a,#ffb199 45%,#ff6b4a)'];
/* 누적 경험치로 레벨을 되돌린다. fixed(운영 계정)면 최고 레벨 */
export function rkLevelOf(xp,fixed){
  if(fixed)return RK_MAX;
  xp=Number(xp)||0;
  let i=0; while(i<RK_MAX && xp>=RK_XP[i+1]) i++;
  return i;
}
/* 현재 레벨 안에서 얼마나 왔는지 */
function rkProgress(xp){
  const i=rkLevelOf(xp), lo=RK_XP[i], hi=RK_XP[i+1];
  if(hi===Infinity) return {lv:i, cur:xp-lo, need:0, pct:100, max:true};
  return {lv:i, cur:xp-lo, need:hi-lo, pct:Math.round((xp-lo)/(hi-lo)*100), max:false};
}
export const rkClamp=i=>Math.max(0,Math.min(RK_MAX, i|0));

/* 글자 칩 — 심볼은 없다. 등급은 글자와 아바타 링 두 가지로만 말한다 */
export function rkChip(i,lg){
  if(!RANK_ON)return '';
  i=rkClamp(i);
  return '<span class="rk rk'+(i+1)+(lg?' lg':'')+'">'+RANKS[i].n+'</span>';
}

/* 아바타에 얹는 링.
   Lv.3 부터 두 겹이 되고, Lv.3 은 눈금 / Lv.4 는 표면 광택 /
   Lv.Max 는 광택 + 오라 + 이따금 링 전체가 밝아지는 플래시를 얻는다. */
export function rkRingHTML(i){
  if(!RANK_ON)return '';
  i=rkClamp(i);
  let h='<i></i>';
  if(i>=2) h+='<i class="o2"></i>';
  if(i===2) h+='<b class="ticks"></b>';
  if(i===4) h+='<i class="flash"></i><b class="aura"></b>';
  return '<span class="rkRing">'+h+'</span>';
}
/* 아바타 하나를 해당 등급으로 칠한다.
   안쪽 내용(이니셜·사진)은 건드리지 않고 링과 광택만 얹었다 뺐다 한다. */
export function rkPaintAv(el,i){
  if(!el)return;
  if(!RANK_ON){
    el.classList.remove('rkAv','rk1','rk2','rk3','rk4','rk5');
    el.querySelectorAll(':scope > .rkRing, :scope > .rkGloss').forEach(n=>n.remove());
    return;
  }
  i=rkClamp(i);
  el.classList.add('rkAv');
  el.classList.remove('rk1','rk2','rk3','rk4','rk5');
  el.classList.add('rk'+(i+1));
  el.querySelectorAll(':scope > .rkRing, :scope > .rkGloss').forEach(n=>n.remove());
  el.insertAdjacentHTML('afterbegin',
    rkRingHTML(i) + (i>=3 ? '<b class="rkGloss"></b>' : ''));
}
/* 마이페이지 경험치 바 — 레벨 색과 진행률을 한 번에 칠한다 */
export function xpPaint(){
  const w=$('#xpWrap'); if(!w)return;
  w.hidden=!RANK_ON;
  if(!RANK_ON)return;
  /* 운영 계정은 경험치를 세지 않는다 — 최고 레벨 · 바는 가득 */
  const p=ME.xpFixed
    ? {lv:RK_MAX, cur:0, need:0, pct:100, max:true}
    : rkProgress(Number(ME.xp)||0);
  const i=p.lv;
  w.classList.remove('rk1','rk2','rk3','rk4','rk5');
  w.classList.add('rk'+(i+1));
  w.classList.toggle('max', p.max);
  w.style.setProperty('--xp-grad', RK_GRAD[i]);
  const lv=$('#xpLv'); if(lv)lv.textContent=RANKS[i].n;
  const num=$('#xpNum');
  if(num) num.textContent = ME.xpFixed ? '운영 계정'
    : p.max ? (Number(ME.xp)||0).toLocaleString()+' XP'
    : p.cur.toLocaleString()+' / '+p.need.toLocaleString()+' XP';
  const nx=$('#xpNext');
  if(nx) nx.textContent = ME.xpFixed
    ? '운영 계정은 최고 레벨로 고정됩니다.'
    : p.max
    ? '최고 레벨입니다. 지금 판단 기준을 그대로 유지하셔도 됩니다.'
    : RANKS[i+1].n+' 까지 '+(p.need-p.cur).toLocaleString()+' XP 남았습니다.';
  /* 오늘 · 이번 주 요약 — 누르면 경험치 내역 창이 뜬다 (xp_panel.js) */
  const more=$('#xpMore');
  if(more){
    const info=ME.xpInfo;
    more.hidden=Boolean(ME.xpFixed)||!info||!info.today||!info.week;
    if(!more.hidden){
      const t=$('#xpMoreText',more)||more;
      t.textContent='오늘 '+info.today.earned+' / '+info.today.cap+
        ' · 이번 주 '+info.week.earned+' / '+info.week.cap+' XP';
    }
  }
  const fill=$('#xpFill');
  if(fill){
    fill.style.width='0%';
    /* 0% 를 한 번 확정시켜야 트랜지션이 처음부터 돈다.
       rAF 대신 강제 리플로우를 쓴다 — 탭이 백그라운드여도 값이 안 튄다. */
    void fill.offsetWidth;
    fill.style.width=p.pct+'%';
  }
}
/* 화면에 있는 내 아바타를 한 번에 맞춘다 */
export function rkPaintAll(){
  /* 헤더 닉네임 옆의 작은 원(.mAuth .meAv)은 2026-09-19 에 없앴다 (알림 아이콘 자리). */
  [$('#avatarInitial'), $('#trProfAv'), $('#sFoot .av')]
    .forEach(el=>rkPaintAv(el, ME.rank));
}
