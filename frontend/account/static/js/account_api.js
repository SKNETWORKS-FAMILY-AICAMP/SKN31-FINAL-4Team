/* 계정 API — 비밀번호와 세션 토큰은 저장하지 않는다.
 * Django의 HttpOnly 세션 쿠키가 로그인 상태를 담당한다. */
let csrfToken = '';
let sessionPromise = null;

async function request(path, { method='GET', body, bootstrap=true, base='/api/auth/' } = {}) {
  if (method !== 'GET' && bootstrap && !csrfToken) await session();
  const headers = { Accept:'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && csrfToken) headers['X-CSRFToken'] = csrfToken;
  let response;
  try {
    response = await fetch(base + path, {
      method,
      credentials:'same-origin',
      headers,
      body:body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (_) {
    throw new Error('로그인 서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.');
  }
  const text = await response.text();
  let payload;
  try { payload = JSON.parse(text); }
  catch (_) {
    if (response.status === 413) throw new Error('보내는 내용이 너무 커요. 이미지를 더 작은 것으로 바꿔 주세요.');
    // 상태 숫자를 같이 보여 준다 — 404는 서버에 인증 주소가 없음, 403은 CSRF 거부, 502/504는 서버 꺼짐
    throw new Error(`로그인 서버가 올바른 JSON을 돌려주지 않았습니다 (${response.status}).`);
  }
  if (payload && payload.data && payload.data.csrf_token) csrfToken = payload.data.csrf_token;
  if (!response.ok || !payload || payload.status !== 'ok') {
    const error = new Error((payload && payload.reason) || `로그인 API 오류 (${response.status})`);
    /* 상태 숫자와 서버가 같이 보낸 값을 붙여 둔다 — 요금제 하루 한도(429)처럼
       사유 말고도 남은 횟수 같은 값이 필요한 화면이 있다 (2026-10-03). */
    error.status = response.status;
    error.data = (payload && payload.data) || null;
    throw error;
  }
  return payload.data;
}

export function session(force=false) {
  if (!force && sessionPromise) return sessionPromise;
  sessionPromise = request('me', { bootstrap:false }).catch(error => {
    sessionPromise = null;
    throw error;
  });
  return sessionPromise;
}

/* ── 알파 테스트 계정 (해커톤 시연 15일 한정) ──────────────────
   백엔드 apps/api/alpha_views.py 와 한 쌍이다. 기간이 끝나면 이 블록과
   app_shell/static/js/alpha.js 를 함께 지우면 된다. */
export const alphaAccount = ({ nickname = '', styles = [] } = {}) =>
  request('alpha', { method:'POST', body:{ nickname, styles } });
export const alphaQuota = () =>
  request('alpha-quota');
export const alphaChatUse = () =>
  request('alpha-chat-use', { method:'POST', body:{} });

export const loginAccount = (username, password) =>
  request('login', { method:'POST', body:{ username, password } });

export const signupAccount = data =>
  request('signup', { method:'POST', body:data });

export const logoutAccount = () =>
  request('logout', { method:'POST', body:{} }).finally(() => { sessionPromise = null; });

/* 회원 탈퇴 — 서버에서 계정과 딸린 기록(찜 · 투표 · 알림 · 인증)을 실제로 지운다.
   지우면 세션도 함께 끊기므로 캐시해 둔 세션을 반드시 버린다. */
export const withdrawAccount = () =>
  request('withdraw', { method:'POST', body:{} }).finally(() => { sessionPromise = null; });

/* 직업 인증 — 신청 · 취소 · (관리자) 목록 · 승인/반려 */
export const jobRequestSubmit = ({ job, major = '', docDataUrl = '', docName = '' }) =>
  request('job-request', { method:'POST', body:{ job, major, doc_data_url:docDataUrl, doc_name:docName } });
export const cancelJobRequest = () =>
  request('job-request', { method:'DELETE', body:{} });
export const jobRequestsList = (status = 'PENDING') =>
  request('job-requests?status=' + encodeURIComponent(status));
export const jobReviewDecide = ({ userId, approve, reason = '' }) =>
  request('job-review', { method:'POST', body:{ user_id:userId, approve, reason } });

/* 요금제 — 신청 · 해지 · 신청 취소 · (관리자) 목록 · 승인/반려/해지 · 챗봇 하루 횟수
   (backend/apps/api/plan_views.py · 2026-10-03). 베타 동안 서버는 신청을 받지 않는다(409). */
export const planStatus = () =>
  request('plan');
export const planRequestSubmit = ({ plan, note = '', company = '', contact = '' }) =>
  request('plan-request', { method:'POST', body:{ plan, note, company, contact } });
export const cancelPlanRequest = () =>
  request('plan-request', { method:'DELETE', body:{} });
export const planRequestsList = (status = 'PENDING') =>
  request('plan-requests?status=' + encodeURIComponent(status));
export const planReviewDecide = ({ userId, approve, reason = '' }) =>
  request('plan-review', { method:'POST', body:{ user_id:userId, approve, reason } });
export const planRevoke = ({ userId, reason = '' }) =>
  request('plan-review', { method:'POST', body:{ user_id:userId, op:'revoke', reason } });
export const planChatUse = () =>
  request('plan-chat-use', { method:'POST', body:{} });

/* 데이터 API 키 — 비즈니스 요금제 (backend/apps/api/data_api_views.py · 2026-10-03).
   베타 동안 서버는 키를 만들지 않는다(409). 원문 키는 만든 응답(data.key)에 한 번만 온다. */
export const dataKeys = () =>
  request('data-keys');
export const createDataKey = (name = '') =>
  request('data-keys', { method:'POST', body:{ name } });
export const revokeDataKey = keyId =>
  request('data-keys', { method:'DELETE', body:{ key_id:keyId } });

export const saveAccount = data =>
  request('profile', { method:'POST', body:data });

/* 성별만 저장 — 알림의 '성별을 알려 주세요' 에서 (2026-10-02).
   /profile 은 닉네임 · 키 · 몸무게까지 다시 검사해, 예전 기준 계정은 다른 칸 때문에 막힐 수 있다. */
export const saveGender = gender =>
  request('gender', { method:'POST', body:{ gender } });

/* 상단 띠 공지 — 로그인 없이 본다. 실패는 조용히 빈 목록(띠가 안 뜰 뿐이다) */
export const liveAnnouncements = () =>
  request('announcements').then(d => (d && Array.isArray(d.items)) ? d.items : []).catch(() => []);

/* term 을 주면 그 키워드 태그가 붙은 영상만 찾는다 (금주의 리포트 · 가장 많이 검색한 키워드) */
export const weeklyVideos = (term = '') =>
  request('weekly-videos' + (term ? '?term=' + encodeURIComponent(term) : ''));

/* ── 활동 기록 ─────────────────────────────────────────────
 * 검색 · 살!말? 투표 · 찜 · 챗봇 사용을 서버(user_event · chat_session)에 남긴다.
 * 금주의 리포트가 이 기록으로 채워진다.
 * ★ 기록은 화면 동작을 막으면 안 된다 — 실패(비로그인 401 · 서버 꺼짐)는 조용히 넘긴다. */
const quiet = promise => promise.catch(() => null);

export const logSearch = (q, facet = '', style = '') =>
  quiet(request('event', { method:'POST', body:{ type:'SEARCH', q, facet, style } }));

export const logChat = (conversationId, title = '') =>
  quiet(request('event', { method:'POST', body:{ type:'CHAT', conversation_id:conversationId, title } }));

/* choice: 'BUY' | 'PASS' | null(투표 취소) */
export const saveVote = ({ cardKey, title = '', brand = '', style = '', choice = null }) =>
  quiet(request('vote', { method:'POST', body:{ card_key:cardKey, title, brand, style, choice } }))
    /* 투표가 서버에 들어간 뒤 알린다 — 홈의 LIVE 투표 TOP 10 이 바로 다시 읽는다 (2026-10-01) */
    .then(r => { if (r) { try { document.dispatchEvent(new CustomEvent('feedit:vote')); } catch (e) {} } return r; });

export const saveVoteComment = ({ cardId, content }) =>
  request('vote-comment', { method:'POST', body:{ card_id:cardId, content } });

export const deleteVoteComment = commentId =>
  request('vote-comment', { method:'DELETE', body:{ comment_id:commentId } });

export const reportVoteTarget = ({ targetType, targetId, reason='' }) =>
  request('vote-report', {
    method:'POST',
    body:{ target_type:targetType, target_id:targetId, reason },
  });

export const createVoteCard = data =>
  request('cards', { method:'POST', body:data, base:'/api/salmal/' });

/* 살!말? 사후 피드백 — 마감된 내 카드의 작성 현황 {pending, done, counts} · 작성/수정 */
export const feedbackList = () =>
  request('feedback', { base:'/api/salmal/' });

export const saveFeedback = ({ cardId, purchase, satisfaction = null, helpful = null, comment = '' }) =>
  request('feedback', { method:'POST', base:'/api/salmal/',
    body:{ card_id:cardId, purchase, satisfaction, helpful, comment } });

export const deleteVoteCard = cardId =>
  request(`cards/${cardId}`, { method:'DELETE', body:{}, base:'/api/salmal/' });

export const saveLiked = ({ itemId, liked, name = '', brand = '', style = '' }) =>
  quiet(request('saved', { method:'POST', body:{ item_id:itemId, liked, name, brand, style } }));

/* 찜 전체(마이페이지 · 찜한 키워드) — 서버 SAVE 기록의 최신 상태가 원본. same_count 포함 */
export const savedAll = () => request('saved?view=all');

/* 할인률 페이지의 찜목록은 브라우저 저장소가 아닌 로그인 사용자의 DB 기록을 읽는다. */
export const savedProducts = () => request('saved');

/* 할인률 화면은 저장 성공/실패를 즉시 보여줘야 하므로 오류를 숨기지 않는다. */
export const setSavedProduct = ({ itemId, liked, name = '', brand = '' }) =>
  request('saved', { method:'POST', body:{ item_id:itemId, liked, name, brand } });

/* ── 알림 ─────────────────────────────────────────────────
 * 목록·설정은 실패를 그대로 올린다(화면이 사유를 적는다).
 * 읽음 처리만 조용히 넘긴다 — 읽음이 안 됐다고 패널이 멈추면 안 된다. */
export const notifications = () => request('notifications');

export const readNotification = id =>
  quiet(request('notifications', { method:'POST', body:{ op:'read', id } }));

export const readAllNotifications = () =>
  quiet(request('notifications', { method:'POST', body:{ op:'read_all' } }));

/* 삭제는 조용히 넘기지 않는다 — 지운 줄 알았는데 남아 있으면 안 된다 */
export const deleteNotification = id =>
  request('notifications', { method:'POST', body:{ op:'delete', id } });

export const deleteAllNotifications = () =>
  request('notifications', { method:'POST', body:{ op:'delete_all' } });

export const notificationSettings = () => request('notification-settings');

/* kinds 는 보낸 종류만 바뀐다 — 안 보낸 종류는 서버가 그대로 둔다 */
export const saveNotificationSettings = ({ enabled, kinds }) =>
  request('notification-settings', { method:'POST', body:{ enabled, kinds } });

/* 용어 사전 등재 요청 — 이미 사전에 있으면 {already:true, canonical_name} 이 온다 */
export const requestTerm = (term, note = '') =>
  request('term-request', { method:'POST', body:{ term, note } });

/* 금주의 리포트 — 실패하면 예외를 그대로 올려 화면이 사유를 적게 한다 */
/* 경험치 · 홈페이지 피드백 (backend/apps/api/xp_views.py) */
export const xpState = () => request('xp');
export const xpVisit = () => request('xp', { method:'POST', body:{ type:'VISIT' } });
export const xpDwell = seconds => request('xp', { method:'POST', body:{ type:'DWELL', seconds } });
export const siteFeedbackList = () => request('site-feedback');
export const sendSiteFeedback = ({ kind, content, page = '' }) =>
  request('site-feedback', { method:'POST', body:{ kind, content, page } });

export const weeklyReport = () =>
  request('weekly-report');

/* ── Google 로그인 ──────────────────────────────────────────
 * Google Identity Services(GIS)의 코드 팝업으로 '인가 코드'만 받아 서버로 넘긴다.
 * 코드→토큰 교환과 신원 확인은 Django가 client_secret으로 한다.
 * 클라이언트 ID는 공개 값이라 /api/auth/me 응답에서 받아 쓴다. */
const GSI_SRC = 'https://accounts.google.com/gsi/client';
let gsiPromise = null;

function loadGsi() {
  if (globalThis.google && globalThis.google.accounts && globalThis.google.accounts.oauth2) {
    return Promise.resolve(globalThis.google);
  }
  if (gsiPromise) return gsiPromise;
  gsiPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = GSI_SRC;
    script.async = true;
    script.onload = () => resolve(globalThis.google);
    script.onerror = () => {
      gsiPromise = null;
      reject(new Error('Google 로그인 스크립트를 불러오지 못했습니다. 네트워크를 확인해 주세요.'));
    };
    document.head.appendChild(script);
  });
  return gsiPromise;
}

/* 코드 클라이언트는 미리 만들어 둔다.
 * ★ 클릭 뒤에 fetch·스크립트 로딩을 기다렸다가 팝업을 열면, 사파리 등은
 *   '사용자 동작이 아니다'라며 팝업을 막는다. 그래서 화면이 뜰 때 준비하고,
 *   클릭 순간에는 requestCode() 만 동기로 부른다. */
let codeClient = null;
let codeWaiter = null;
let preparePromise = null;

export function prepareGoogle() {
  if (preparePromise) return preparePromise;
  preparePromise = (async () => {
    const me = await session();
    if (!me.google_client_id) return false;
    const google = await loadGsi();
    codeClient = google.accounts.oauth2.initCodeClient({
      client_id: me.google_client_id,
      scope: 'openid email profile',
      ux_mode: 'popup',
      select_account: true,
      callback: resp => {
        const w = codeWaiter; codeWaiter = null;
        if (!w) return;
        if (resp && resp.code) w.resolve(resp.code);
        else w.reject(new Error((resp && resp.error_description) || 'Google 인증을 완료하지 못했습니다.'));
      },
      error_callback: err => {
        const w = codeWaiter; codeWaiter = null;
        if (!w) return;
        const closed = Boolean(err && err.type === 'popup_closed');
        const e = new Error(closed ? 'Google 로그인 창이 닫혔습니다.'
          : '팝업이 차단됐는지 확인한 뒤 다시 시도해 주세요.');
        e.cancelled = closed;
        w.reject(e);
      },
    });
    return true;
  })().catch(error => { preparePromise = null; throw error; });
  return preparePromise;
}

/* 클릭 핸들러 안에서 await 없이 바로 부를 것.
 * 결과: { authenticated:true, user } 이면 로그인 끝,
 *       { authenticated:false, needs_signup:true, google:{email,name} } 이면 가입 폼으로 */
export function googleLogin() {
  if (!codeClient) {
    return prepareGoogle().then(ready => {
      throw new Error(ready
        ? 'Google 로그인 준비가 끝났습니다. 버튼을 한 번 더 눌러 주세요.'
        : 'Google 로그인이 아직 설정되지 않았습니다. 서버의 GOOGLE_CLIENT_ID 를 확인해 주세요.');
    });
  }
  const codePromise = new Promise((resolve, reject) => { codeWaiter = { resolve, reject }; });
  codeClient.requestCode();   // 동기 호출 — 팝업이 사용자 클릭에 묶인다
  return codePromise
    .then(code => request('google', { method:'POST', body:{ code } }))
    .then(data => { if (data.authenticated) sessionPromise = null; return data; });
}

export const googleSignupAccount = data =>
  request('google-signup', { method:'POST', body:data }).finally(() => { sessionPromise = null; });

/* ── 카카오 로그인 ─────────────────────────────────────────
 * 카카오 JS SDK v2 는 팝업 로그인이 없어 페이지 이동으로 간다.
 * kakaoStart 가 준 주소로 나갔다가 ?code=&state= 를 달고 돌아오면 kakaoLogin 을 부른다.
 * 결과 모양은 googleLogin 과 같다 ({ authenticated } 또는 { needs_signup, kakao:{email,name} }). */
export const kakaoStart = redirectUri =>
  request('kakao-start', { method:'POST', body:{ redirect_uri:redirectUri } }).then(data => data.url);

export const kakaoLogin = (code, state) =>
  request('kakao', { method:'POST', body:{ code, state } })
    .then(data => { if (data.authenticated) sessionPromise = null; return data; });

export const kakaoSignupAccount = data =>
  request('kakao-signup', { method:'POST', body:data }).finally(() => { sessionPromise = null; });

/* ── 가입 이메일 인증 — 인증번호 발송 · 확인 (확인 결과는 서버 세션에 남는다) ── */
export const emailCode = email =>
  request('email-code', { method:'POST', body:{ email } });

export const emailVerify = (email, code) =>
  request('email-verify', { method:'POST', body:{ email, code } });

/* ── 챗봇 대화 기록 (RDS app.chat_session · app.chat_message) ──────────
 * 원본은 서버다. 브라우저 localStorage 는 화면을 빨리 그리는 사본일 뿐이다.
 * 목록/본문 조회는 실패를 그대로 올린다(화면이 다시 시도). 쓰기는 조용히 실패한다 —
 * 저장이 안 된다고 대화가 막히면 안 된다. */
export const chatList = (mode = '') =>
  request('chats' + (mode ? '?mode=' + encodeURIComponent(mode) : ''));

export const chatLoad = sessionId =>
  request('chats?id=' + encodeURIComponent(sessionId));

export const chatSaveTurn = data =>
  quiet(request('chats', { method:'POST', body:{ op:'turn', ...data } }));

export const chatImport = data =>
  quiet(request('chats', { method:'POST', body:{ op:'import', ...data } }));

export const chatUpdate = data =>
  quiet(request('chats', { method:'POST', body:{ op:'update', ...data } }));

export const chatTruncate = data =>
  quiet(request('chats', { method:'POST', body:{ op:'truncate', ...data } }));

export const chatDelete = ({ mode, key }) =>
  quiet(request('chats', { method:'DELETE', body:{ mode, key } }));
