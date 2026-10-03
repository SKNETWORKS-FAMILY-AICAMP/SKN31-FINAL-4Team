/* 회원가입·로그인·프로필 요청을 Django로 중계한다.
 * 세션·CSRF 쿠키를 브라우저와 백엔드 사이에 그대로 전달한다. */
import { backendBase, backendToken } from '../_lib/db.js';

const ALLOWED = new Set(['me', 'signup', 'login', 'logout', 'withdraw', 'profile', 'weekly-videos', 'google', 'google-signup',
  // 카카오 로그인 · 가입 이메일 인증 (backend/apps/api/auth_views.py)
  'kakao-start', 'kakao', 'kakao-signup', 'email-code', 'email-verify',
  // 활동 기록 · 금주의 리포트 (backend/apps/api/activity_views.py)
  'event', 'vote', 'vote-comment', 'vote-report', 'saved', 'weekly-report',
  // 직업 인증 신청 · 관리자 심사 (backend/apps/api/job_views.py)
  'job-request', 'job-requests', 'job-review',
  // 요금제 신청 · 관리자 승인 · 챗봇 하루 횟수 (backend/apps/api/plan_views.py · 2026-10-03)
  'plan', 'plan-request', 'plan-requests', 'plan-review', 'plan-chat-use',
  // 데이터 API 키 관리 — 비즈니스 요금제 (backend/apps/api/data_api_views.py · 2026-10-03)
  'data-keys',
  // 챗봇 대화 기록 (backend/apps/api/chat_views.py)
  'chats',
  // 경험치 · 홈페이지 피드백 (backend/apps/api/xp_views.py)
  'xp', 'site-feedback',
  // 알림 · 알림 설정 · 용어 등재 요청 (backend/apps/api/notification_views.py)
  'notifications', 'notification-settings', 'term-request',
  // 상단 띠 공지(로그인 없이) · 성별만 저장(알림에서) — 2026-10-02
  'announcements', 'gender',
  // 알파 테스트 계정 (해커톤 시연 15일 한정 · backend/apps/api/alpha_views.py)
  //   이 함수는 경로의 첫 조각만 보고 넘기므로 'alpha/quota' 같은 두 조각 주소는 쓰지 않는다.
  'alpha', 'alpha-quota', 'alpha-chat-use']);

export default async function handler(req, res) {
  const url = new URL(req.url, 'http://x');
  const action = url.pathname.replace(/^\/api\/auth\//, '').split('/')[0];
  /* ★ 물음표 뒤(질의 문자열)를 반드시 같이 넘긴다.
       예전에는 `${base}/auth/${action}` 만 불러서 **?term=… 이 통째로 사라졌다.**
       그래서 금주의 리포트가 '민소매'로 영상을 찾아 달라고 해도 Django 는 term 을
       못 받고 취향·찜 기반으로 떨어져, 한 줄 요약은 '민소매'인데 영상은 신발이
       나왔다(2026-09-18). salmal/[action].js 는 원래 넘기고 있었다. */
  const query = url.search || '';
  if (!ALLOWED.has(action)) return send(res, 404, { status:'error', reason:'없는 인증 주소입니다.', data:null });
  const base = backendBase();
  if (!base) return send(res, 503, {
    status:'error', reason:'BACKEND_API_URL이 설정되지 않아 로그인 서버에 연결할 수 없습니다.', data:null,
  });

  const method = String(req.method || 'GET').toUpperCase();
  if (!['GET', 'POST', 'DELETE'].includes(method)) {
    return send(res, 405, { status:'error', reason:'지원하지 않는 요청 방식입니다.', data:null });
  }
  const headers = { Accept:'application/json' };
  const token = backendToken();
  if (token) headers['X-FEEDiT-Token'] = token;
  if (req.headers.cookie) headers.Cookie = req.headers.cookie;
  if (req.headers['x-csrftoken']) headers['X-CSRFToken'] = req.headers['x-csrftoken'];
  /* Django는 HTTPS 요청의 CSRF를 검사할 때 Origin·Referer도 본다.
     중계하면서 빠뜨리면 403 HTML 오류 페이지가 돌아와 화면이 JSON을 못 읽는다.
     서버 .env 의 DJANGO_CSRF_TRUSTED_ORIGINS 에 버셀 주소가 있어야 통과한다. */
  if (req.headers.origin) headers.Origin = req.headers.origin;
  if (req.headers.referer) headers.Referer = req.headers.referer;
  let body;
  if (method === 'POST' || method === 'DELETE') {
    headers['Content-Type'] = 'application/json';
    body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body || {});
  }

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    const upstream = await fetch(`${base}/auth/${action}${query}`, {
      method, headers, body, signal:controller.signal, redirect:'manual',
    });
    clearTimeout(timer);
    const text = await upstream.text();
    const cookies = typeof upstream.headers.getSetCookie === 'function'
      ? upstream.headers.getSetCookie()
      : [upstream.headers.get('set-cookie')].filter(Boolean);
    if (cookies.length) res.setHeader('Set-Cookie', cookies);
    res.statusCode = upstream.status;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    return res.end(text || JSON.stringify({ status:'error', reason:'인증 서버 응답이 비었습니다.', data:null }));
  } catch (error) {
    /* ★ 2026-09-21 보안 — fetch 실패 메시지에는 백엔드 주소가 섞여 나온다.
       배포에서는 로그로만 남기고 화면에는 사유만 준다. */
    console.error('[feedit] auth relay failed:', error);
    const deployed =
      process.env.NODE_ENV === 'production' || Boolean(process.env.VERCEL);
    return send(res, 502, {
      status:'error', reason:'로그인 서버에 연결하지 못했습니다.',
      ...(deployed ? {} : { detail:String(error && error.message || error).slice(0, 140) }),
      data:null,
    });
  }
}

function send(res, status, body) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  return res.end(JSON.stringify(body));
}
