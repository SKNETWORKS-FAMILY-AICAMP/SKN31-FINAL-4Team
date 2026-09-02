import { $, $$ } from '../../../core/static/js/dom.js';
import { IMG } from '../../../home/static/js/chat.js';

/* ── 살!말? ─────────────────────────────────────────── */
var SM={buy:938,no:346,voted:null};
export function mVote(side){
  if(SM.voted===side)return;
  if(SM.voted)SM[SM.voted]--;
  SM[side]++; SM.voted=side;
  $$('.smBtns button').forEach(b=>b.classList.toggle('picked',b.dataset.vote===side));
  mPaintVote();
}
export function mPaintVote(){
  const tot=SM.buy+SM.no, pb=Math.round(SM.buy/tot*100);
  const buy=$('#smBuy'), no=$('#smNo'), meta=$('#smMeta');
  if(!buy)return;
  buy.style.width=pb+'%'; no.style.width=(100-pb)+'%';
  buy.textContent='살 '+pb+'%'; no.textContent='말 '+(100-pb)+'%';
  buy.classList.toggle('tight',pb<28); no.classList.toggle('tight',(100-pb)<28);
  if(meta)meta.textContent=tot.toLocaleString()+' 표 · 마감까지 6시간'+(SM.voted?' · 투표함':'');
}
export function smBuild(){
  const host=$('#smFeed'); if(!host)return;
  const rows=[[13,'폴로 케이블 니트',68],[6,'셀비지 데님 5포켓',54],[15,'스웨이드 봄버',81],
              [4,'트랙 자켓 · 삼선',37],[17,'발레 플랫',72],[9,'플리스 집업',29]];
  host.innerHTML=rows.map(r=>
    '<div class="smCard"><div class="im"><img src="'+IMG(r[0])+'" alt="" loading="lazy"></div>'+
    '<div class="bd"><b>'+r[1]+'</b><div class="mini"><i style="width:'+r[2]+'%"></i></div>'+
    '<span>살 '+r[2]+'% · 말 '+(100-r[2])+'%</span></div></div>').join('');
}
