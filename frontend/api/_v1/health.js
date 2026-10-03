/* GET /api/v1/health — 챗봇이 지금 답할 수 있는 상태인가.
 *
 * `chat_api.js` 의 `isUp()` 이 이걸 부른다. 200 이면 실서버 경로로 가고,
 * 아니면 화면이 조용히 목업 답변으로 떨어진다.
 *
 * ── 왜 200/503 을 정확히 갈라야 하나 ──────────────────────
 * 여기서 무턱대고 200 을 주면, 챗봇이 못 답하는 상황인데도 화면은
 * 실서버라고 믿고 질문을 보낸다. 그러면 사용자는 **빈 답**을 본다.
 * 목업으로 떨어지는 편이 낫다 — 적어도 화면이 깨지지 않는다.
 *
 * 그래서 뒤에 진짜 챗봇 서버(CHAT_BACKEND_URL)가 붙어 있을 때만 200 이다.
 */

export default async function handler(req, res) {
  const backend = (process.env.CHAT_BACKEND_URL || '').replace(/\/+$/, '');
  const body = {
    ok: false,
    backend: backend ? 'configured' : 'missing',
    checked_at: new Date().toISOString(),
    reason: '',
  };

  if (!backend) {
    body.reason =
      '챗봇 서버 주소(CHAT_BACKEND_URL)가 설정돼 있지 않습니다. ' +
      'feedit-chat 을 어딘가에 올리고 그 주소를 버셀 환경변수에 넣으세요. ' +
      '지금은 화면이 목업 답변으로 동작합니다.';
    return json(res, 503, body);
  }

  try {
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 3000);
    const r = await fetch(backend + '/v1/health', { signal: c.signal });
    clearTimeout(t);
    body.ok = r.ok;
    body.reason = r.ok ? '' : `챗봇 서버가 ${r.status} 를 돌려줬습니다.`;
    /* ★ 뒤 서버가 돌려준 것을 그대로 붙인다 (2026-09-22).
       "어느 코드가 배포돼 있나" 를 화면만 보고는 알 수 없어, 컨테이너를 받아
       놓고도 옛 동작을 한참 들여다봤다. 챗봇의 /v1/health 는 기준일·지표 버전·
       도구 목록만 돌려준다 — 비밀값이 없으니 그대로 실어 한 번의 조회로 가른다. */
    try {
      const upstream = await r.json();
      if (upstream && typeof upstream === 'object') body.upstream = upstream;
    } catch (_parseError) {
      /* 본문이 JSON 이 아니면 그냥 넘어간다 — 상태 코드가 이미 답이다 */
    }
    return json(res, r.ok ? 200 : 503, body);
  } catch (e) {
    body.reason = `챗봇 서버에 닿지 못했습니다: ${String(e.message || e).slice(0, 160)}`;
    return json(res, 503, body);
  }
}

function json(res, code, obj) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(obj));
}
