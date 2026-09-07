import { $, $$, HAS_A, aAnimate, aStagger } from '../../../core/static/js/dom.js';

/* ══════════════════════════════════════════════════════════════
   컬렉션 뱃지
   --------------------------------------------------------------
   등급(Lv)과는 다른 축이다. 등급은 실력, 뱃지는 발자국을 센다.
   참여형은 100/500/1,000 처럼 단계를 따로 한 장씩 준다.
   ══════════════════════════════════════════════════════════════ */
const BADGE_ICONS={
  sparkle:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6L12 3z"/></svg>',
  check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8.5 12.3l2.4 2.4 4.6-5"/></svg>',
  people:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="9" r="3"/><path d="M3.5 19c1-3 3-4.6 5.5-4.6s4.5 1.6 5.5 4.6"/><circle cx="17" cy="8.5" r="2.4"/><path d="M15.3 14.6c2-.3 3.6.9 4.4 3.1"/></svg>',
  shield:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5l7 2.6v5.4c0 4.6-3 7.6-7 9-4-1.4-7-4.4-7-9V6.1l7-2.6z"/><path d="M9.3 12l1.9 1.9 3.5-3.9"/></svg>',
  comment:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5h16v10H9l-4 3.6V15.5H4v-10z"/><path d="M8 9.5h8M8 12.3h5"/></svg>',
  calendar:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5.5" width="16" height="14.5" rx="2.5"/><path d="M4 10h16M8 3.5v3.5M16 3.5v3.5"/><path d="M9 14.3l2 2 4-4.3"/></svg>',
  target:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r=".8" fill="currentColor" stroke="none"/></svg>',
  tag:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12.5 3.5H5v7.5L14 20l7.5-7.5-9-9z"/><circle cx="9" cy="8.3" r="1.4"/></svg>',
  share:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5.5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="18.5" r="2.5"/><path d="M8.2 10.8l7.6-4.4M8.2 13.2l7.6 4.4"/></svg>',
  lock:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="10.5" width="14" height="9" rx="2"/><path d="M8 10.5V7.8a4 4 0 0 1 8 0v2.7"/></svg>'
};
/* 뱃지 정의: 참여형 배지는 100/500/1,000회 같은 단계(tier)를 개별 배지로 표시 */
export const BADGES=[
  {id:'b01',cat:'온보딩',icon:'sparkle',n:'스타일 입문자',tier:'',d:'가입 시 선호 스타일 선택, 프로필 완성',earned:true,date:'2026.06.02'},
  {id:'b02',cat:'온보딩',icon:'check',n:'첫 살말',tier:'',d:'첫 살/말 투표 완료',earned:true,date:'2026.06.03'},

  {id:'b03',cat:'참여/기여',icon:'people',n:'여론 조력자',tier:'1',d:'내 투표가 다른 사용자 결정에 1회 반영됨',earned:true,date:'2026.06.10'},
  {id:'b04',cat:'참여/기여',icon:'people',n:'여론 조력자',tier:'10',d:'내 투표가 다른 사용자 결정에 10회 반영됨',earned:true,date:'2026.07.02'},
  {id:'b05',cat:'참여/기여',icon:'people',n:'여론 조력자',tier:'50',d:'내 투표가 다른 사용자 결정에 50회 반영됨',earned:false,progress:'32/50'},

  {id:'b06',cat:'참여/기여',icon:'shield',n:'살말 백전',tier:'100',d:'누적 투표 100회 달성',earned:true,date:'2026.06.20'},
  {id:'b07',cat:'참여/기여',icon:'shield',n:'살말 백전',tier:'500',d:'누적 투표 500회 달성',earned:true,date:'2026.08.05'},
  {id:'b08',cat:'참여/기여',icon:'shield',n:'살말 백전',tier:'1000',d:'누적 투표 1,000회 달성',earned:false,progress:'500/1,000'},

  {id:'b09',cat:'참여/기여',icon:'comment',n:'성실 피드백러',tier:'10',d:'사후 만족도 피드백 10회 응답',earned:false,progress:'4/10'},
  {id:'b10',cat:'참여/기여',icon:'comment',n:'성실 피드백러',tier:'50',d:'사후 만족도 피드백 50회 응답',earned:false,progress:'4/50'},
  {id:'b11',cat:'참여/기여',icon:'comment',n:'성실 피드백러',tier:'100',d:'사후 만족도 피드백 100회 응답',earned:false,progress:'4/100'},

  {id:'b12',cat:'참여/기여',icon:'calendar',n:'개근상',tier:'7',d:'7일 연속 방문',earned:true,date:'2026.08.18'},
  {id:'b13',cat:'참여/기여',icon:'calendar',n:'개근상',tier:'30',d:'30일 연속 방문',earned:false,progress:'7/30'},
  {id:'b14',cat:'참여/기여',icon:'calendar',n:'개근상',tier:'100',d:'100일 연속 방문',earned:false,progress:'7/100'},

  {id:'b15',cat:'안목/선구안',icon:'target',n:'연속 적중',tier:'5',d:'살/말 판단이 실제 만족도와 5회 연속 일치',earned:false,progress:'3/5'},
  {id:'b16',cat:'안목/선구안',icon:'target',n:'연속 적중',tier:'10',d:'살/말 판단이 실제 만족도와 10회 연속 일치',earned:false,progress:'3/10'},
  {id:'b17',cat:'안목/선구안',icon:'target',n:'연속 적중',tier:'20',d:'살/말 판단이 실제 만족도와 20회 연속 일치',earned:false,progress:'3/20'},

  {id:'b18',cat:'안목/선구안',icon:'tag',n:'카테고리 안목러',tier:'',d:'특정 카테고리(ex. 아우터) 판단 정확도 상위 도달',earned:false,progress:'상위 24%'},

  {id:'b19',cat:'소셜/공유',icon:'share',n:'결산 공유러',tier:'',d:'시즌 취향 결산 또는 취향 리포트 공유',earned:false}
];
function bgMedal(b){
  const corner = b.earned
    ? (b.tier ? '<span class="chip">'+b.tier+'</span>' : '')
    : '<span class="lockChip">'+BADGE_ICONS.lock+'</span>';
  return '<div class="bgMedal"><div class="mr">'+BADGE_ICONS[b.icon]+'</div>'+corner+'</div>';
}
function bgTile(b){
  const sub = b.earned ? b.date : (b.progress || '미획득');
  return '<button type="button" class="bgTile '+(b.earned?'earned':'locked')+'" data-badge="'+b.id+'">'+
    bgMedal(b)+
    '<div class="bgTileName">'+b.n+(b.tier?' '+b.tier:'')+'</div>'+
    '<div class="bgTileSub">'+sub+'</div></button>';
}
/* 위쪽 상세 패널 — 타일을 고르면 여기가 바뀐다 */
export function bgDetail(b){
  const el=$('#bgDetail'); if(!el)return;
  el.className='bgDetail '+(b.earned?'earned':'locked');
  el.innerHTML =
    '<div class="ddIcon">'+BADGE_ICONS[b.icon]+'</div>'+
    '<div class="ddInfo">'+
      '<div class="ddName">'+b.n+(b.tier?' '+b.tier:'')+
        ' <span class="ddTag">'+b.cat+'</span></div>'+
      '<div class="ddDesc">'+b.d+'</div>'+
      '<div class="ddStatus">'+
        (b.earned ? b.date+' 달성' : (b.progress ? '진행중 · '+b.progress : '미획득'))+
      '</div>'+
    '</div>';
}
export function bgRender(){
  const host=$('#badgeGrid'); if(!host)return;
  const cats=[...new Set(BADGES.map(b=>b.cat))];
  const got=BADGES.filter(b=>b.earned).length;
  host.innerHTML = cats.map(cat=>{
    const items=BADGES.filter(b=>b.cat===cat);
    const n=items.filter(b=>b.earned).length;
    return '<div class="bgSection">'+
      '<div class="bgSecTitle">'+cat+' <span class="cnt">'+n+'/'+items.length+'</span></div>'+
      '<div class="bgTiles">'+items.map(bgTile).join('')+'</div></div>';
  }).join('');
  const c=$('#bgCount');  if(c)c.textContent=got;
  const t=$('#bgTotal');  if(t)t.textContent=BADGES.length;
  const bar=$('#bgBar');
  if(bar){ bar.style.width='0%'; void bar.offsetWidth;
           bar.style.width=(got/BADGES.length*100)+'%' }
  /* 처음 열면 가장 최근에 딴 것을 보여 준다 */
  const recent=[...BADGES].filter(b=>b.earned).sort((a,b2)=>a.date<b2.date?1:-1)[0]||BADGES[0];
  bgRender.sel=recent.id;
  bgDetail(recent);
  const tile=$('.bgTile[data-badge="'+recent.id+'"]',host);
  if(tile)tile.classList.add('active');
  if(HAS_A){
    aAnimate($$('.bgTile',host),{opacity:[0,1],translateY:[8,0],scale:[.96,1],
      duration:460,delay:aStagger(14,{start:60}),ease:'out(3)',
      onComplete:()=>$$('.bgTile',host).forEach(e=>{e.style.transform='';e.style.opacity=''})});
  }
}
