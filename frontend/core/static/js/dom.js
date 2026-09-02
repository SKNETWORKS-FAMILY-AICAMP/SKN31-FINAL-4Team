export const $=(s,el=document)=>el.querySelector(s);
export const $$=(s,el=document)=>[...el.querySelectorAll(s)];
export const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

export const A=(typeof anime!=='undefined'&&anime)?anime:null;
export const HAS_A=!!A;
export const aAnimate  = HAS_A ? A.animate        : null;
export const aTimeline = HAS_A ? A.createTimeline : null;
export const aStagger  = HAS_A ? A.stagger        : null;
export const aSpring   = HAS_A ? (A.spring||A.createSpring) : null;
const aSplit    = HAS_A ? A.splitText      : null;
export const aDrawable = HAS_A ? A.createDrawable : null;
export const aUtils    = HAS_A ? A.utils          : null;
