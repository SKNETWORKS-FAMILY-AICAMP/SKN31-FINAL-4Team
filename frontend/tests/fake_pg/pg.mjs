// 가짜 pg — 실제로 붙지 않고, 받은 SQL·인자를 기록하고 정해진 행을 돌려준다.
export const CALLS = [];
export let NEXT = null;            // {rows} | Error
export function __setNext(v){ NEXT = v; }
class Pool {
  constructor(cfg){ this.cfg = cfg; }
  async query(sql, args){
    CALLS.push({sql, args});
    const n = typeof NEXT === 'function' ? NEXT(sql, args) : NEXT;
    if (n instanceof Error) throw n;
    return { rows: (n && n.rows) || [], rowCount: ((n && n.rows) || []).length };
  }
}
export default { Pool };
