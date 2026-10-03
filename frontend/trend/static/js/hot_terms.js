/* 검색바 예시 용어 — 홈의 HOT TREND TOP 10 과 같은 순위(/api/trend?rank=hot)를 그대로 쓴다.
   EDIT 여섯 파트의 검색바(언급량·온도 / 연관어 / 긍부정 / 수명주기 / 할인률 / 리세일)가 함께 쓴다.
   못 불러오면 지어내지 않고 비워 둔다(placeholder 만 보인다). 홈과 같이 30분마다 다시 확인한다. */
export var KW_HOT=[];
var hotAt=0, hotJob=null;
const TTL=30*60*1000, RETRY=30*1000;   /* 실패하면 30초 뒤에 다시 */

export function kwHotLoad(){
  if(hotJob)return hotJob;
  if(Date.now()-hotAt<(KW_HOT.length?TTL:RETRY))return Promise.resolve();
  hotAt=Date.now();
  return hotJob=kwHotFetch().finally(()=>{ hotJob=null });
}
async function kwHotFetch(){
  try{
    const r=await fetch('/api/trend?rank=hot&limit=8',{headers:{Accept:'application/json'}});
    const j=await r.json();
    if(r.ok&&j&&j.status==='ok'){
      const d=j.data||{};
      /* 홈과 같은 뽑기 — 상승 8 + 하락 2 */
      const terms=[...(d.rising||[]).slice(0,8),...(d.falling||[]).slice(0,2)]
        .map(x=>x&&x.term).filter(Boolean);
      if(terms.length)KW_HOT=terms;
    }
  }catch(e){}
}
