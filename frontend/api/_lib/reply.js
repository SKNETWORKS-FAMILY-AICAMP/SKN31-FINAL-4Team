/* 응답 모양을 한 곳에서 정한다 — 특히 "측정 불가"를 어떻게 말하는지.
 *
 * ── 왜 이게 따로 있나 ─────────────────────────────────────
 * 이 서비스에서 제일 위험한 실패는 "DB 가 안 붙었는데 화면에 그럴듯한 숫자가
 * 떠 있는 것"이다. 지금 프론트가 딱 그 상태다 — 트렌드 수치가 전부 씨드
 * 난수(`chart_engine.js gRand`)라서 값이 없어도 화면은 멀쩡해 보인다.
 *
 * 그래서 모든 응답은 세 가지 중 하나로만 말한다:
 *
 *   ok        값이 있다. data 를 쓴다.
 *   empty     붙었는데 값이 없다. "아직 측정할 자료가 없습니다".
 *   error     못 붙었다. 화면에 숫자를 그리면 안 된다.
 *
 * empty 와 error 는 **반드시 구별한다.** 둘 다 '숫자 없음'이지만
 * 사람이 할 일이 다르다 — 앞은 기다리는 것이고 뒤는 고치는 것이다.
 */

/** 값이 있다. */
export function ok(res, data, extra = {}) {
  return send(res, 200, { status: 'ok', ...extra, data });
}

/**
 * 붙긴 했는데 값이 없다.
 *
 * @param reason 사람이 읽을 이유. 화면에 그대로 뜬다.
 *               "브랜드는 관측이 모자라 방향을 말할 수 없습니다" 처럼
 *               **무엇이 없어서 못 하는지**까지 적는다.
 */
export function empty(res, reason, extra = {}) {
  return send(res, 200, { status: 'empty', reason, ...extra, data: null });
}

/** 못 붙었거나 질의가 깨졌다. 화면은 숫자를 그리지 않는다. */
export function failed(res, reason, extra = {}) {
  return send(res, 200, { status: 'error', reason, ...extra, data: null });
}

function send(res, code, body) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  // 지표는 자주 안 바뀐다. 잠깐 캐시해 RDS 부담과 응답 시간을 줄인다.
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=600');
  res.end(JSON.stringify(body));
}

/**
 * DB 결과를 위 세 갈래로 옮긴다.
 *
 * `q()` 는 실패해도 던지지 않으므로, 여기서 한 번에 가른다.
 * 이 함수를 거치면 각 엔드포인트에 try/catch 가 흩어지지 않는다.
 */
export function fromQuery(res, r, { emptyReason, map }) {
  if (!r.ok) {
    const 안내 =
      r.code === 'not_configured'
        ? 'AWS RDS 접속 정보가 아직 설정되지 않았습니다.'
        : `AWS RDS 에 연결하지 못했습니다 (${r.code}).`;
    /* ★ 2026-09-21 보안 — Postgres 원문에는 스키마·표·컬럼·제약 이름이 섞인다.
     *   그걸 브라우저까지 보내면 남의 DB 구조를 읽어 주는 꼴이다.
     *   원문은 서버 로그(버셀 Functions 로그)에만 남기고, 화면에는
     *   배포가 아닐 때만 붙인다 — 로컬에서 고칠 때는 그대로 보여야 한다.
     *
     *   화면(dispatch.js)은 detail 이 없으면 "연결이 되면 자동으로 실제 값이
     *   뜹니다." 로 떨어지므로, 빠져도 문구가 비지 않는다. */
    if (r.error) console.error('[feedit] query failed:', r.code, r.error);
    const deployed =
      process.env.NODE_ENV === 'production' || Boolean(process.env.VERCEL);
    return failed(res, 안내, deployed ? {} : { detail: r.error });
  }
  if (!r.rows.length) return empty(res, emptyReason);
  return ok(res, map ? map(r.rows) : r.rows);
}
