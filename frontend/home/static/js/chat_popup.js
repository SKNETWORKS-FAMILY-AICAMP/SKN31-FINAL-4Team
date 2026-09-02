import { $, $$ } from '../../../core/static/js/dom.js';
import { SAY, SM_ON, SM_SAY, ansCardHTML } from './chat.js';

/* ══════════════════════════════════════════════════════
   챗봇 팝업 — 일반 모드 · 살말 모드
   ------------------------------------------------------
   두 모드는 대화창 자체가 다르다. 각자 자기 대화 목록(CP_STORE)을
   따로 들고 있어서, 모드를 오가도 서로의 대화에 섞이지 않는다.
   홈의 입력창·칩 버튼은 이제 인라인으로 답을 펼치지 않고
   전부 이 팝업 하나로 모인다.
   ══════════════════════════════════════════════════════ */
const CP_STORE={ general:{convos:[],activeId:null}, salmal:{convos:[],activeId:null} };
let CP_UID=1;
/* 사이드바 프로필(이름·소개)은 모드별로 다르게 남겨 둔다 — 팝업 자체가 둘이라는 것을
   보여주는 자리라서다. 대화 안의 답변 라벨은 별개로 항상 FEEDiT 하나로 묶는다(아래). */
const CP_PROFILE={
  general:{name:'일반 모드', desc:'요즘 뜨는 트렌드를 알려드려요.',
    empty:'요즘 뜨는 트렌드가 궁금하다면 물어보세요.', ph:'궁금한 트렌드를 질문해 주세요.'},
  salmal :{name:'살말 모드', desc:'사도 되는지, 대신 판단해 드려요.',
    empty:'살까 말까 고민되는 아이템을 물어보세요.', ph:'고민되는 아이템을 질문해 주세요.'}
};
/* 답변 중엔 이 하나로 통일 — 별이 돌고 글자가 옅어졌다 밝아지며 "생각 중"을 표현한다 */
let cpTypeTimer=null;
/* escapeHtml 은 salmalBoot() 지역 함수라 팝업(전역 스코프)에서는 안 보인다 — 따로 하나 둔다 */
function cpEsc(s){
  return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
const cpMode =()=>SM_ON?'salmal':'general';
export const cpStore=()=>CP_STORE[cpMode()];
function cpActiveConvo(){
  const s=cpStore();
  return s.convos.find(c=>c.id===s.activeId)||null;
}
function cpTitleFrom(text){
  const t=text.replace(/\s+/g,' ').trim();
  return t.length>24 ? t.slice(0,24)+'…' : t;
}
function cpNowLabel(){
  const d=new Date();
  return (d.getMonth()+1)+'월 '+d.getDate()+'일';
}
export function cpNewConvo(){
  const s=cpStore();
  const c={id:CP_UID++, title:'', time:cpNowLabel(), messages:[]};
  s.convos.unshift(c);
  s.activeId=c.id;
  return c;
}
/* 질문 문장에서 어떤 카드를 보여줄지 고른다 — sendChat() 이 쓰던 것과 같은 규칙 */
export function cpKeyFor(v){
  if(SM_ON){
    if(/최저가|가격|싸|비싸|할인/.test(v))return 'smPrice';
    if(/내년|오래|수명|계속/.test(v))return 'smLife';
    if(/대신|비슷|대안|다른/.test(v))return 'smAlt';
    if(/투표|다들|사람들|반응/.test(v))return 'smVote';
    return 'smBuy';
  }
  if(/고프/.test(v))return 'gorp';
  if(/발레/.test(v))return 'ballet';
  if(/29CM|무신사|비교|온도/.test(v))return 'plat';
  if(/체형|코트|추천/.test(v))return 'body';
  return 'rise';
}
function cpPaintProfile(){
  const p=CP_PROFILE[cpMode()];
  $('#cpAv').textContent=SM_ON?'◑':'✧';
  $('#cpName').textContent=p.name;
  $('#cpDesc').textContent=p.desc;
  const empty=$('#cpEmptyText'); if(empty)empty.textContent=p.empty;
  const ta=$('#cpInput'); if(ta)ta.placeholder=p.ph;
}
export function cpRenderList(){
  const list=$('#cpList'); if(!list)return;
  const s=cpStore();
  if(!s.convos.length){
    list.innerHTML='<p class="cpListEmpty">아직 대화가 없습니다.</p>';
    return;
  }
  list.innerHTML=s.convos.map(c=>
    '<button type="button" class="cpItem'+(c.id===s.activeId?' on':'')+'" data-cid="'+c.id+'">'+
      '<em>'+c.time+'</em><span>'+cpEsc(c.title||'새 대화')+'</span>'+
    '</button>').join('');
}
/* AI 말풍선 한 줄 — 별 아이콘 + FEEDiT. 답을 기다리는 동안(pending)엔
   말풍선 대신 이 헤더만 돌고 옅어졌다 밝아지며 "생각 중"을 표현한다 */
function cpWhoHTML(){ return '<div class="who"><i class="cpStar">✧</i>FEEDiT</div>'; }
export function cpRenderThread(opts){
  const wrap=$('#cpThreadWrap'), th=$('#cpThread'); if(!wrap||!th)return;
  const c=cpActiveConvo();
  if(cpTypeTimer){ clearTimeout(cpTypeTimer); cpTypeTimer=null; }
  if(!c||!c.messages.length){ wrap.classList.remove('hasMsg'); th.innerHTML=''; return; }
  wrap.classList.add('hasMsg');
  const typeIdx=(opts&&opts.typeLast)?c.messages.length-1:-1;
  th.innerHTML=c.messages.map((m,idx)=>{
    if(m.role==='me') return '<div class="msg me"><div class="bub">'+cpEsc(m.text)+'</div></div>';
    if(m.pending) return '<div class="msg ai thinking">'+cpWhoHTML()+'</div>';
    if(idx===typeIdx) return '<div class="msg ai" data-type-target="1">'+cpWhoHTML()+'<div class="say"></div></div>';
    return '<div class="msg ai">'+cpWhoHTML()+'<div class="say">'+m.html+'</div>'+(m.key?ansCardHTML(m.key):'')+'</div>';
  }).join('');
  $$('i[data-w]',th).forEach(f=>f.style.width=f.dataset.w+'%');
  wrap.scrollTop=wrap.scrollHeight;
  if(typeIdx>=0){
    const m=c.messages[typeIdx];
    const target=th.querySelector('[data-type-target="1"] .say');
    if(target&&m)cpTypeHTML(target,m.html,()=>{
      if(m.key){
        const holder=document.createElement('div');
        holder.innerHTML=ansCardHTML(m.key);
        const cardEl=holder.firstElementChild;
        cardEl.classList.add('reveal');
        target.parentElement.appendChild(cardEl);
        $$('i[data-w]',cardEl).forEach(f=>f.style.width=f.dataset.w+'%');
        requestAnimationFrame(()=>{ requestAnimationFrame(()=>cardEl.classList.add('in')); });
      }
      wrap.scrollTop=wrap.scrollHeight;
    });
  }
}
/* 답 텍스트를 한 글자씩 밀어 넣는다. html 안의 태그(<b>…</b>)는 한 번에
   통째로 소비해서, 어느 순간에 잘라도 항상 닫힌 HTML만 그려지게 한다. */
function cpTypeHTML(el,html,done){
  el.innerHTML='';
  let i=0;
  const wrap=$('#cpThreadWrap');
  function step(){
    if(i>=html.length){ done&&done(); return; }
    if(html[i]==='<'){
      const end=html.indexOf('>',i);
      i=end===-1?html.length:end+1;
      el.innerHTML=html.slice(0,i);
      step();
      return;
    }
    i++;
    el.innerHTML=html.slice(0,i);
    if(wrap)wrap.scrollTop=wrap.scrollHeight;
    const prev=html[i-1];
    const delay=/[.,!?]/.test(prev)?110:14+Math.random()*16;
    cpTypeTimer=setTimeout(step,delay);
  }
  step();
}
/* 질문 하나를 대화에 밀어 넣는다 — 답은 곧장 나오지 않고, 잠깐 "생각 중" 상태로
   있다가 텍스트가 타이핑되듯 채워진 뒤 카드가 뒤따라 떠오른다 */
function cpAsk(text,key){
  if(!text)return;
  let c=cpActiveConvo(); if(!c)c=cpNewConvo();
  c.messages.push({role:'me', text});
  if(!c.title)c.title=cpTitleFrom(text);
  const html=(SM_ON?SM_SAY[key]:SAY[key])||SAY.rise;
  const aiMsg={role:'ai', html, key, pending:true};
  c.messages.push(aiMsg);
  cpRenderList();
  cpRenderThread();
  const delay=650+Math.random()*550;
  setTimeout(()=>{
    aiMsg.pending=false;
    if(cpActiveConvo()===c)cpRenderThread({typeLast:true});
  },delay);
}
export function cpSend(){
  const ta=$('#cpInput'); const v=(ta&&ta.value.trim())||'';
  if(!v)return;
  cpAsk(v,cpKeyFor(v));
  if(ta){ ta.value=''; ta.style.height=''; }
}
function openChatPopup(){
  const ov=$('#cpOverlay'); if(!ov)return;
  ov.classList.toggle('sm',SM_ON);
  ov.classList.add('on');
  document.body.style.overflow='hidden';
  cpPaintProfile(); cpRenderList(); cpRenderThread();
  setTimeout(()=>{ const ta=$('#cpInput'); if(ta)ta.focus(); },260);
}
export function closeChatPopup(){
  const ov=$('#cpOverlay'); if(!ov)return;
  ov.classList.remove('on');
  document.body.style.overflow='';
}
/* 홈 하단 예시 버튼("이거 사도 될까?" 등)에서 바로 넘어올 때 쓰는 진입점 */
export function openChatWith(text,key){
  openChatPopup();
  cpAsk(text, key||cpKeyFor(text));
}
