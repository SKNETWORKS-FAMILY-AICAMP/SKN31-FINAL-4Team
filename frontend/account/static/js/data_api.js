import { $ } from '../../../core/static/js/dom.js';
import { createDataKey, dataKeys, revokeDataKey } from './account_api.js';
import { PLAN_EVENT, planAllows, planEnforced, planState } from './plan.js';

/* ══════════════════════════════════════════════════════════════
   데이터 API 연동 — 비즈니스 요금제 (2026-10-03)
   --------------------------------------------------------------
   계정 메뉴 '데이터 API' → 키 만들기 · 폐기 · 쓰는 법.
   지표 자체는 밖의 시스템이 키로 부른다 (GET /api/data/<지표>, backend/apps/api/data_api_views.py).

   ★ 베타 동안에는 메뉴가 서지 않는다.
     서버가 요금제를 켜고(enforced) 지금 요금제가 data_api 를 허락할 때(비즈니스 · 운영)만 보인다.
     서버도 베타 동안은 키를 만들지 않고 지표 주소를 닫아 둔다 — 화면은 안내일 뿐이다.
   ══════════════════════════════════════════════════════════════ */

const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>Number(n||0).toLocaleString('ko-KR');
const when=v=>{ if(!v)return '아직 안 씀'; const d=new Date(v);
  return isNaN(d)?'':(d.getMonth()+1)+'.'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0') };

let STATE=null;       /* 서버 응답 {keys, metrics, limits, used_today, allowed, max_keys} */
let FRESH=null;       /* 방금 만든 키 원문 — 창을 닫으면 버린다 */

/* 메뉴 — 요금제가 허락할 때만 */
export function dataApiMenuPaint(){
  const b=$('#menuDataApi'); if(!b)return;
  const st=planState();
  b.hidden=!(planEnforced()&&st.signed_in&&planAllows('data_api'));
}
document.addEventListener(PLAN_EVENT,dataApiMenuPaint);

function modal(on){
  const m=$('#dataApiModal'); if(!m)return;
  m.classList.toggle('on',on);
  if(!on)FRESH=null;
}

function guideHTML(){
  const base=(typeof location!=='undefined'?location.origin:'')+'/api/data';
  /* 한글 검색어는 --data-urlencode 가 알아서 바꿔 준다 — 예시가 %EB%B0… 로 읽기 어렵지 않게 */
  const sample='curl -G "'+base+'/trend" \\\n  -H "Authorization: Bearer fdk_…" \\\n  --data-urlencode "term=발레코어"';
  const rows=(STATE&&STATE.metrics||[]).map(m=>
    '<tr><th>'+esc(m.metric)+'</th><td>'+esc(m.about)+'</td><td>'+esc(m.params)+'</td></tr>').join('');
  return '<div class="daGuide">'+
    '<h4>쓰는 법</h4>'+
    '<p>키를 <b>Authorization: Bearer</b> 머리글에 넣어 GET 으로 부릅니다.<br>'+
      '화면과 같은 계산 결과가 JSON 으로 옵니다.</p>'+
    '<pre class="daCode">'+esc(sample)+'</pre>'+
    '<table class="daTbl"><thead><tr><th>지표</th><th>내용</th><th>받는 값</th></tr></thead><tbody>'+rows+'</tbody></table>'+
    '<p class="daNote">목록은 <code>'+esc(base)+'</code> 로도 받을 수 있어요.<br>'+
      '응답은 저장되지 않으니(캐시 없음) 같은 값을 자주 쓰면 받는 쪽에서 보관해 주세요.</p>'+
  '</div>';
}

function paint(msg){
  const host=$('#dataApiBody'); if(!host)return;
  if(!STATE){ host.innerHTML='<p class="jrEmpty">'+esc(msg||'불러오는 중입니다.')+'</p>'; return; }
  const lim=STATE.limits||{};
  const keys=STATE.keys||[];
  const full=keys.length>=(STATE.max_keys||5);
  const fresh=FRESH?'<div class="daFresh">'+
      '<b>새 키 — 지금 한 번만 보여요.</b>'+
      '<p>창을 닫으면 다시 볼 수 없습니다. 안전한 곳에 복사해 두세요.</p>'+
      '<div class="daFreshRow"><code id="dataApiFreshKey">'+esc(FRESH)+'</code>'+
      '<button type="button" class="pill sm" data-da-copy>복사</button></div></div>':'';
  const list=keys.length?keys.map(k=>
    '<div class="daKey"><div><b>'+esc(k.name)+'</b><span>'+esc(k.hint)+'</span></div>'+
    '<em>만듦 '+when(k.created_at)+' · 마지막 사용 '+when(k.last_used_at)+'</em>'+
    '<button type="button" class="pill ghost sm" data-da-revoke="'+esc(k.id)+'">폐기</button></div>').join('')
    :'<p class="daEmpty">아직 만든 키가 없어요.</p>';
  host.innerHTML=
    '<p class="jrLead">사내 시스템 · 엑셀 · BI 도구에서 FEEDiT 지표를 직접 받아 가는 키입니다.<br>'+
      '오늘 '+fmt(STATE.used_today)+' / '+fmt(lim.per_day)+'회 사용 · 키 하나당 분당 '+fmt(lim.per_minute)+'회까지</p>'+
    fresh+
    '<div class="daKeys">'+list+'</div>'+
    (STATE.allowed
      ? '<div class="daMake"><input type="text" id="dataApiName" maxlength="40" placeholder="키 이름 (예: 마케팅 대시보드)" autocomplete="off"'+(full?' disabled':'')+'>'+
        '<button type="button" class="pill sm" data-da-make'+(full?' disabled title="키는 '+(STATE.max_keys||5)+'개까지 — 쓰지 않는 키를 먼저 폐기해 주세요"':'')+'>키 만들기</button></div>'
      : '<p class="daNote">지금 요금제에서는 새 키를 만들 수 없어요. 남은 키는 폐기만 할 수 있습니다.</p>')+
    '<p class="fieldMsg err" id="dataApiErr" hidden></p>'+
    guideHTML();
}

export async function dataApiOpen(){
  STATE=null; FRESH=null;
  modal(true); paint();
  try{ STATE=await dataKeys(); paint(); }
  catch(e){ paint((e&&e.message)||'키 목록을 불러오지 못했습니다.'); }
}

function fail(msg){ const el=$('#dataApiErr'); if(el){ el.textContent=msg; el.hidden=false; } }

async function onClick(e){
  const make=e.target.closest('[data-da-make]'), rv=e.target.closest('[data-da-revoke]'),
        cp=e.target.closest('[data-da-copy]');
  if(cp){
    try{ await navigator.clipboard.writeText(FRESH||''); cp.textContent='복사했어요'; }
    catch(_){ cp.textContent='직접 선택해 복사해 주세요'; }
    return;
  }
  if(!make&&!rv)return;
  const btn=make||rv;
  if(btn.disabled)return;
  if(rv&&typeof confirm==='function'&&!confirm('이 키를 폐기할까요?\n이 키를 쓰는 시스템은 바로 막힙니다.'))return;
  btn.disabled=true;
  try{
    if(make){
      const name=(($('#dataApiName')||{}).value||'').trim();
      const d=await createDataKey(name);
      FRESH=d.key||null; STATE=d;
    }else{
      STATE=await revokeDataKey(rv.dataset.daRevoke);
    }
    paint();
  }catch(err){ btn.disabled=false; fail((err&&err.message)||'처리하지 못했습니다.'); }
}

function bind(){
  const menu=$('#menuDataApi'), body=$('#dataApiBody'), m=$('#dataApiModal');
  if(menu&&!menu.dataset.bound){
    menu.dataset.bound='1';
    menu.addEventListener('click',()=>{
      const am=$('#acctMenu'); if(am)am.classList.remove('on');
      const w=am&&am.closest('.mAuthWrap'); if(w)w.classList.remove('open');
      dataApiOpen();
    });
  }
  if(body&&!body.dataset.bound){ body.dataset.bound='1'; body.addEventListener('click',onClick); }
  /* 닫기(✕) — 공통 [data-close-modal] 이 .on 을 떼므로, 방금 만든 키 원문도 여기서 같이 버린다 */
  if(m&&!m.dataset.bound){
    m.dataset.bound='1';
    m.addEventListener('click',e=>{ if(e.target.closest('[data-close-modal]'))FRESH=null; });
  }
  dataApiMenuPaint();
}
if(typeof document!=='undefined'){
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);
  else bind();
}
