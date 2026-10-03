/* 살!말? 조회·카드 생성·삭제·사후 피드백을 Django로 중계한다.
 *
 * ★ 2026-09-21 — 파일 이름이 `[action].js` 였을 때는 **한 조각 주소만** 받았다.
 *   그래서 카드 삭제가 부르는 `/api/salmal/cards/42` (DELETE) 는 버셀에
 *   맞는 함수가 없어 버셀이 자기 404 쪽(HTML)을 돌려줬고 — Django 까지 가지도
 *   못했다 — 화면에는 "404" 만 떴다. `[...action].js` 로 바꿔 뒤에 몇 조각이
 *   붙든 받는다. 첫 조각으로 허용 여부를 가리는 건 그대로다.
 *   (버셀 Hobby 요금제의 함수 12개 제한은 그대로 — 파일 수는 늘지 않는다.) */
import { backendBase, backendToken } from '../_lib/db.js';

const ALLOWED = new Set(['cards', 'feedback']);

export default async function handler(req, res) {
  const url = new URL(req.url, 'http://x');
  const action = url.pathname.replace(/^\/api\/salmal\//, '').split('/')[0];
  const method = String(req.method || 'GET').toUpperCase();
  if (!ALLOWED.has(action) || !['GET', 'POST', 'DELETE'].includes(method)) {
    return send(res, 404, { status:'error', reason:'없는 살말 주소입니다.', data:null });
  }
  const base = backendBase();
  if (!base) return send(res, 503, {
    status:'error', reason:'BACKEND_API_URL이 설정되지 않아 살말 데이터를 불러올 수 없습니다.', data:null,
  });
  const headers = { Accept:'application/json' };
  const token = backendToken();
  if (token) headers['X-FEEDiT-Token'] = token;
  if (req.headers.cookie) headers.Cookie = req.headers.cookie;
  if (req.headers['x-csrftoken']) headers['X-CSRFToken'] = req.headers['x-csrftoken'];
  if (req.headers.origin) headers.Origin = req.headers.origin;
  if (req.headers.referer) headers.Referer = req.headers.referer;
  let body;
  if (method === 'POST' || method === 'DELETE') {
    headers['Content-Type'] = 'application/json';
    body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body || {});
  }
  /* ★ 2026-09-21 — 카드 삭제는 `/api/salmal/cards/42` 처럼 조각이 하나 더 붙는다.
     파일 이름의 캐치올(`[...action]`)로 받는 게 정석이지만, 버셀이 그 주소를
     함수로 잡아 주지 않는 경우가 있어 vercel.json 의 rewrite 로도 같은 곳에
     닿게 해 뒀다. 그때는 경로가 `/api/salmal/cards` + `__card=42` 로 들어오므로,
     여기서 다시 `/salmal/cards/42` 로 펴서 Django 에 넘긴다.
     `__card` 는 우리가 붙인 내부 값이라 그대로 흘려보내지 않는다. */
  const cardId = (url.searchParams.get('__card') || '').replace(/[^0-9]/g, '');
  url.searchParams.delete('__card');
  const query = url.searchParams.toString();
  let upstreamPath = url.pathname.replace(/^\/api/, '');
  if (cardId && /^\/salmal\/cards\/?$/.test(upstreamPath)) upstreamPath = `/salmal/cards/${cardId}`;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    const upstream = await fetch(`${base}${upstreamPath}${query ? `?${query}` : ''}`, {
      method, headers, body, signal:controller.signal, redirect:'manual',
    });
    clearTimeout(timer);
    return relay(res, upstream.status, await upstream.text());
  } catch (error) {
    return send(res, 502, {
      status:'error', reason:'살말 서버에 연결하지 못했습니다.',
      detail:String(error && error.message || error).slice(0, 140), data:null,
    });
  }
}

function send(res, status, body) {
  return sendText(res, status, JSON.stringify(body));
}

/* ★ 2026-09-21 — Django 가 500 을 내면 JSON 이 아니라 HTML 오류 쪽을 돌려준다.
   예전에는 그 HTML 을 Content-Type: application/json 으로 그대로 흘려보내서
   화면이 "Unexpected token '<'" 로 깨졌다. JSON 이 아니면 사유로 바꿔 보낸다. */
function relay(res, status, body) {
  const head = String(body || '').trimStart().charAt(0);
  if (head === '{' || head === '[') return sendText(res, status, body);
  const plain = String(body || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  return send(res, status >= 400 ? status : 502, {
    status: 'error',
    reason: `살말 서버가 ${status} 를 돌려줬습니다. 잠시 뒤 다시 시도해 주세요.`,
    detail: plain.slice(0, 140) || null,
    data: null,
  });
}

function sendText(res, status, body) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  return res.end(body);
}
