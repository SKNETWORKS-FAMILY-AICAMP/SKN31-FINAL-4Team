/* 챗봇 JS 시험의 브라우저 전역 — frontend/tests 의 UI 시험과 같은 것을 채운다.
 *
 * ★ 2026-09-27 — 챗봇 팝업 모듈이 router.js 를 거쳐 앱 셸 · 인트로 · 알파 안내까지
 *   끌고 들어오면서, 불러오는 순간 addEventListener · innerWidth · matchMedia 같은
 *   창 전역을 찾는다. 시험마다 따로 채우면 하나씩 빠뜨려 import 단계에서 통째로 멈췄다.
 *   이미 채운 값은 건드리지 않는다(setTimeout 은 Node 것을 그대로 쓴다 — jsdom 것으로 덮으면 재귀에 빠진다).
 */
export function browserEnv(dom){
  const w = dom.window;
  const put = (k, v) => { if (globalThis[k] === undefined) { try { globalThis[k] = v } catch (e) {} } };
  globalThis.window = w;
  globalThis.document = w.document;
  for (const k of ['Element','HTMLElement','SVGElement','Node','Event','CustomEvent','MouseEvent',
                   'KeyboardEvent','getComputedStyle','location','localStorage','sessionStorage',
                   'File','Blob','FormData'])
    put(k, w[k]);
  put('MutationObserver', w.MutationObserver || class { observe(){} disconnect(){} takeRecords(){ return [] } });
  put('requestAnimationFrame', (f) => setTimeout(f, 0));
  put('cancelAnimationFrame', (h) => clearTimeout(h));
  put('addEventListener', w.addEventListener.bind(w));
  put('removeEventListener', w.removeEventListener.bind(w));
  put('matchMedia', () => ({ matches: false, addEventListener(){}, addListener(){}, removeEventListener(){} }));
  put('scrollTo', () => {});
  put('innerWidth', 1440);
  put('innerHeight', 900);
  put('IntersectionObserver', class { observe(){} unobserve(){} disconnect(){} });
  put('ResizeObserver', class { observe(){} unobserve(){} disconnect(){} });
}
