/* node 의 import 해석을 가로채 'pg' 를 가짜로 바꾼다.
   api/_lib/db.js 를 시험용으로 고치지 않기 위해서다 —
   시험을 위해 제품 코드를 고치면, 시험이 통과해도 제품이 도는지는 모른다. */
const FAKE = new URL('./pg.mjs', import.meta.url).href;
export function resolve(specifier, context, next) {
  if (specifier === 'pg') return { url: FAKE, shortCircuit: true };
  return next(specifier, context);
}
