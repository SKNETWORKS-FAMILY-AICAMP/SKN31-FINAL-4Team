/* 챗봇 팝업 화면 — 말풍선 아이콘 줄 · 착장 위젯 · 대화 줄 메뉴 (2026-09-14)
 *
 * 왜 있나
 *   서버가 보내는 것과 화면이 그리는 것은 다르다(AGENTS.md §5). 착장 칸을
 *   가변으로 바꾸고 옵션을 스위치로 세웠는데, 그 둘은 서버 테스트로는 한 줄도
 *   지켜지지 않는다 — 여기서 실제 DOM 을 그려 확인한다.
 *
 * 실행:  node tests/chat_popup_ui.test.mjs
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const popupCss = fs.readFileSync(new URL('../home/static/css/chat_popup.css', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://localhost:5173/' });
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node',
                 'HTMLElement','CustomEvent','KeyboardEvent','MouseEvent','File','Blob'])
  globalThis[k] = k === 'window' ? dom.window : dom.window[k];
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
globalThis.cancelAnimationFrame = (h) => clearTimeout(h);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
globalThis.scrollTo = () => {};
/* 인트로 로더가 창 너비로 슬롯을 잰다 — 다른 UI 시험과 같은 창 크기를 준다 */
globalThis.innerWidth = 1440;
globalThis.innerHeight = 900;
globalThis.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.location = dom.window.location;
globalThis.localStorage = dom.window.localStorage;

/* 서버는 없는 셈 친다 — /v1/health 가 실패하면 팝업은 데모 답으로 떨어진다.
   착장 생성만 성공으로 흉내 내어 결과 이미지가 들어온 화면을 본다. */
const FAKE_PNG = 'data:image/png;base64,iVBORw0KGgo=';
let fitBody = null;
globalThis.fetch = async (u, opt) => {
  const url = String(u);
  if (url.includes('/v1/virtual-fitting')) {
    fitBody = JSON.parse((opt && opt.body) || '{}');
    /* 태그를 청했으면 두 번째로 보낸 상품에 점 하나 (vton.locate 흉내) */
    const body = JSON.stringify({ ok: true, image: FAKE_PNG, size: '2480x3312',
      tags: fitBody.tags ? [{ index: 1, x: .4, y: .55 }] : [] });
    return { ok: true, text: async () => body, json: async () => JSON.parse(body) };
  }
  if (url.includes('/v1/fit-classify')) {
    const body = JSON.stringify({ ok: true, categories: [] });
    return { ok: true, text: async () => body, json: async () => JSON.parse(body) };
  }
  throw new Error('offline');            /* isUp() 실패 → 데모 답 */
};

let pass = 0, fail = 0;
const t = async (n, f) => {
  try { await f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; }
};
const wait = (ms = 0) => new Promise(r => setTimeout(r, ms));

await import(`${F}/main.js`);
const CP = await import(`${F}/home/static/js/chat_popup.js`);
const CHAT_API = await import(`${F}/home/static/js/chat_api.js`);
const { youtubeVideoId } = await import(`${F}/home/static/js/chat_video.js`);
const P  = await import(`${F}/account/static/js/profile.js`);
P.AUTH.in = true;                        /* 로그인 관문을 지난 상태로 둔다 */

const thread = () => document.querySelector('#cpThread');
const click = (el) => el.dispatchEvent(new dom.window.MouseEvent('click', {bubbles:true}));

await t('챗봇 원인 템플릿의 영상 근거를 썸네일·인앱 재생·전체화면·YouTube 링크로 표시한다', () => {
  const video='https://www.youtube.com/watch?v=dQw4w9WgXcQ';
  const html=CHAT_API.reportHTML({blocks:[{type:'generative_report',slot:'full',template:'why',title:'원인',modules:[{
    id:'why',kind:'evidence',presentation:'hero',span:12,block:{type:'timeline',term:'플리스 재킷',window:2,
      points:[{d:'2026-10-02',m:2},{d:'2026-10-03',m:4}],spikes:[],
      evidence:[{src:'유튜브',kind:'영상',body:'착장 영상',url:video,at:'2026-10-03'}]}}]}]});
  thread().innerHTML=html;
  const card=thread().querySelector('.tlCard--video .chatVideo');
  assert.ok(card,'영상 근거 카드가 없다');
  assert.match(card.querySelector('img').src,/i\.ytimg\.com\/vi\/dQw4w9WgXcQ\/hqdefault\.jpg/);
  assert.equal(card.querySelector('iframe'),null,'클릭 전에 외부 플레이어를 로드했다');
  assert.equal(card.querySelector('.chatVideoActions a').href,video);
  let fullscreenCalled=false;
  card.requestFullscreen=()=>{ fullscreenCalled=true; return Promise.resolve(); };
  click(card.querySelector('[data-chat-video-fullscreen]'));
  assert.ok(fullscreenCalled,'전체화면 버튼이 동작하지 않는다');
  click(card.querySelector('[data-chat-video-play]'));
  const frame=card.querySelector('iframe');
  assert.ok(frame,'화면 안에서 플레이어가 열리지 않았다');
  assert.match(frame.src,/youtube-nocookie\.com\/embed\/dQw4w9WgXcQ\?autoplay=1/);
  assert.ok(frame.hasAttribute('allowfullscreen'));
  assert.equal(card.querySelector('.chatVideoActions a').href,video,'원본 이동 링크가 유지되어야 한다');
});

await t('같은 영상의 설명·댓글은 썸네일 하나에 묶고, 재생하면 카드 폭으로 펼친다', () => {
  const v='https://www.youtube.com/watch?v=dQw4w9WgXcQ';
  const other='https://youtu.be/aaaaaaaaaaa';
  const html=CHAT_API.reportHTML({blocks:[{type:'generative_report',slot:'full',template:'why',title:'원인',modules:[{
    id:'why',kind:'evidence',presentation:'hero',span:12,block:{type:'timeline',term:'플리스 재킷',window:2,
      points:[{d:'2026-10-02',m:2},{d:'2026-10-03',m:4}],spikes:[],
      evidence:[
        {src:'커뮤니티',kind:'POST',body:'가볍고 따뜻해요',url:'https://community.example.com/p/1',at:'2026-09-27'},
        {src:'유튜브',kind:'COMMENT',body:'셔츠랑 둘 다 샀어요',url:v+'&lc=abc',at:'2026-09-28'},
        {src:'유튜브',kind:'DESCRIPTION',body:'가을 필수 아우터',url:v,at:'2026-09-28'},
        {src:'유튜브',kind:'COMMENT',body:'셔츠랑 둘 다 샀어요',url:v,at:'2026-09-28'},
        {src:'유튜브',kind:'DESCRIPTION',body:'다른 영상',url:other,at:'2026-09-29'},
      ]}}]}]});
  thread().innerHTML=html;
  const videos=[...thread().querySelectorAll('.chatVideo')];
  assert.equal(videos.length,2,'같은 영상은 카드 하나여야 한다');
  assert.equal(thread().querySelectorAll('.tlCard').length,3,'근거 묶음은 세 개여야 한다');
  const first=videos[0];
  assert.equal(first.dataset.videoId,'dQw4w9WgXcQ');
  assert.equal(first.querySelectorAll('img').length,1);
  const notes=[...first.querySelectorAll('.chatVideoNotes li')];
  assert.equal(notes.length,2,'중복 문장은 한 번만 남겨야 한다');
  assert.deepEqual(notes.map(li=>li.querySelector('.chatVideoTag').textContent),['설명','댓글'],'설명이 댓글보다 먼저 와야 한다');
  assert.match(first.querySelector('.chatVideoCount').textContent,/근거 2건/);
  assert.equal(first.querySelector('.chatVideoNo').textContent,'02','번호는 묶은 뒤 순서를 따라야 한다');
  click(first.querySelector('[data-chat-video-play]'));
  assert.ok(first.classList.contains('isPlaying'),'재생하면 카드가 펼쳐져야 한다');
  assert.match(first.querySelector('iframe').title,/가을 필수 아우터/);
});

await t('링크 템플릿에서 같은 영상이 두 번 오면 한 번만 그린다', () => {
  const html=CHAT_API.reportHTML({blocks:[{type:'links',slot:'full',items:[
    {url:'https://youtu.be/dQw4w9WgXcQ',title:'영상 추천'},
    {url:'https://www.youtube.com/watch?v=dQw4w9WgXcQ',title:'같은 영상'},
    {url:'https://magazine.example.com/story',title:'웹매거진'},
  ]}]});
  thread().innerHTML=html;
  assert.equal(thread().querySelectorAll('.chatVideo').length,1);
  assert.equal(thread().querySelector('.rank .row .n').textContent,'02','중복을 뺀 뒤 번호를 다시 매겨야 한다');
});

await t('링크 템플릿은 유효한 영상만 플레이어로 바꾸고 매거진 링크는 유지한다', () => {
  const html=CHAT_API.reportHTML({blocks:[{type:'links',slot:'full',items:[
    {url:'https://youtu.be/dQw4w9WgXcQ',title:'영상 추천'},
    {url:'https://magazine.example.com/story',title:'웹매거진'},
    {url:'https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ',title:'가짜 영상'},
  ]}]});
  thread().innerHTML=html;
  assert.equal(thread().querySelectorAll('.chatVideo').length,1);
  assert.equal(thread().querySelectorAll('.rank .row[data-href]').length,2);
  assert.match(thread().textContent,/웹매거진/);
  assert.equal(youtubeVideoId('https://youtu.be/x'),null);
  assert.equal(youtubeVideoId('https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ'),null);
});

await t('사진 관찰값이 다음 요청의 history에 그대로 남는다', () => {
  const visual = {
    item: '미디 스커트', colors: ['블랙'], materials: ['광택 있는 직물로 보임'],
    silhouette: ['미디 길이'], details: ['밑단 레이스'], uncertainties: ['혼용률 미확인']
  };
  const got = CP.cpHistoryFor({messages: [
    {role: 'me', text: '이거 어때?'},
    {role: 'ai', turn: {q: '이거 어때?', intent: 'vision.salmal', terms: [], visual}},
    {role: 'ai', pending: true},
  ]});
  assert.equal(got.length, 1, '완료된 사진 턴 하나만 보내야 한다');
  assert.deepEqual(got[0].visual, visual);
});

/* ── 내 말풍선 아래 아이콘 줄 ───────────────────────────── */
CP.openChatWith('트렌드 TOP 10 알려줘', null, { fresh: true });
await wait(30);

await t('내 말풍선에 재전송·수정·복사 아이콘이 함께 붙는다', () => {
  const acts = thread().querySelector('.msg.me .cpMeActs');
  assert.ok(acts, '아이콘 줄이 없다');
  assert.ok(acts.querySelector('[data-resend]'), '재전송이 없다');
  assert.ok(acts.querySelector('[data-again]'), '수정이 없다');
  assert.ok(acts.querySelector('[data-copy]'), '복사가 없다');
  assert.equal(acts.querySelectorAll('svg').length, 3, '아이콘은 셋이다');
});

await t('재전송은 같은 질문을 한 턴 더 쌓는다', async () => {
  const before = thread().querySelectorAll('.msg.me').length;
  click(thread().querySelector('.msg.me [data-resend]'));
  await wait(30);
  const after = [...thread().querySelectorAll('.msg.me')];
  assert.equal(after.length, before + 1, '턴이 늘지 않았다');
  assert.match(after[after.length - 1].textContent, /트렌드 TOP 10 알려줘/);
});

/* ── 마지막 질문 그 자리에서 고치기 (2026-09-14) ───────────
   예전에는 연필이 글을 입력창으로 되돌렸다 — 눈이 화면 아래로 내려가고,
   무엇을 고치는 중인지 말풍선 쪽에는 표시가 없었다. */
await t('수정 연필은 마지막 질문에만 붙는다', () => {
  const mine = [...thread().querySelectorAll('.msg.me')];
  assert.ok(mine.length >= 2, '질문이 둘 이상 있어야 본다');
  assert.equal(mine[0].querySelector('[data-again]'), null,
               '중간 질문에도 연필이 붙었다 — 고치면 뒤 대화가 날아간다');
  assert.ok(mine[mine.length - 1].querySelector('[data-again]'), '마지막에 연필이 없다');
  assert.ok(mine[0].querySelector('[data-resend]'), '재전송은 모든 질문에 남아야 한다');
  assert.ok(mine[0].querySelector('[data-copy]'), '복사는 모든 질문에 남아야 한다');
});

await t('연필을 누르면 말풍선이 그 자리에서 입력칸이 된다', async () => {
  document.querySelector('#cpInput').value = '';
  const mine = [...thread().querySelectorAll('.msg.me')];
  click(mine[mine.length - 1].querySelector('[data-again]'));
  await wait(20);
  const box = thread().querySelector('.msg.me.editing .cpEditIn');
  assert.ok(box, '고치는 칸이 안 열렸다');
  assert.equal(box.value, '트렌드 TOP 10 알려줘');
  assert.ok(thread().querySelector('[data-edit-save]'), '저장이 없다');
  assert.ok(thread().querySelector('[data-edit-cancel]'), '취소가 없다');
  assert.equal(document.querySelector('#cpInput').value, '', '입력창으로 샜다');
});

await t('수정 입력칸은 원문 말풍선 크기를 잡는 복제 문장을 사용한다', () => {
  const edit = thread().querySelector('.msg.me.editing');
  const box = edit&&edit.querySelector('.cpEditIn');
  const sizer = edit&&edit.querySelector('.cpEditSizer');
  assert.ok(box&&sizer, '말풍선 크기를 유지할 sizer가 없다');
  assert.equal(sizer.textContent, box.value, 'sizer와 수정 원문이 다르다');
  assert.match(popupCss, /\.cpEditBox\{[\s\S]*?width:max-content;max-width:62%/,
               '수정 상자가 원래 말풍선처럼 내용 폭을 따르지 않는다');
  assert.match(popupCss, /\.cpEditSizer,\.cpEditIn\{[\s\S]*?padding:12px 17px[\s\S]*?font-size:14px/,
               '수정 글꼴·여백이 팝업 말풍선과 다르다');
});

await t('취소하면 원래 말풍선으로 돌아온다', async () => {
  click(thread().querySelector('[data-edit-cancel]'));
  await wait(20);
  assert.equal(thread().querySelector('.msg.me.editing'), null, '고치는 칸이 남아 있다');
  const mine = [...thread().querySelectorAll('.msg.me')];
  assert.match(mine[mine.length - 1].textContent, /트렌드 TOP 10 알려줘/);
});

await t('저장하면 고친 질문으로 다시 묻고 그 뒤 답변은 지워진다', async () => {
  const store = () => CP.cpStore().convos.find(c => c.id === CP.cpStore().activeId);
  const mine = [...thread().querySelectorAll('.msg.me')];
  click(mine[mine.length - 1].querySelector('[data-again]'));
  await wait(20);
  const before = store().messages.length;
  thread().querySelector('.cpEditIn').value = '발레코어 지금 사도 될까?';
  click(thread().querySelector('[data-edit-save]'));
  await wait(80);
  /* 고친 질문과 새 답이 옛 자리를 그대로 쓴다 — 턴 수가 늘지 않는다 */
  assert.equal(store().messages.length, before, `턴 수가 ${store().messages.length} 로 어긋났다`);
  const last = [...thread().querySelectorAll('.msg.me')].pop();
  assert.match(last.textContent, /발레코어 지금 사도 될까\?/);
  assert.equal(thread().querySelector('.msg.me.editing'), null);
});

await t('고치는 칸에서 Esc 는 팝업까지 닫지 않는다', async () => {
  const mine = [...thread().querySelectorAll('.msg.me')];
  click(mine[mine.length - 1].querySelector('[data-again]'));
  await wait(20);
  thread().querySelector('.cpEditIn')
    .dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await wait(20);
  assert.equal(thread().querySelector('.msg.me.editing'), null, 'Esc 로 안 닫혔다');
  assert.ok(document.querySelector('#cpOverlay').classList.contains('on'),
            '팝업까지 같이 닫혔다');
});

/* ── 착장 위젯 ──────────────────────────────────────────── */
CP.openChatWith('이거 입혀줘', null, { fresh: true, images: [FAKE_PNG] });
await wait(60);

await t('칸은 넣은 사진 수만큼만 열린다 (2026-09-14)', async () => {
  const slots = thread().querySelectorAll('.cpFit .cpFitSlot:not(.addSlot)');
  assert.equal(slots.length, 1, `사진 한 장인데 칸이 ${slots.length}개다`);
  assert.ok(thread().querySelector('.cpFit [data-vf-add]'), '칸 늘리기 ＋ 가 없다');
  /* 종류는 칸 아래 이름을 눌러 펼치는 판에서 고른다 (2026-10-01) — Auto 가 맨 앞 */
  click(thread().querySelector('[data-vf-kind="0"]')); await wait(10);
  const names = [...thread().querySelectorAll('.cpFitSheet [data-vf-kindpick]')]
    .map(b => b.textContent.trim());
  assert.deepEqual(names, ['Auto','아우터','상의','하의','원피스(셋업)','신발','양말','모자','벨트','안경']);
  click(thread().querySelector('.cpFitSheetHead [data-vf-kind]')); await wait(10);
  assert.equal(thread().querySelector('.cpFitSheet'), null, '닫기를 눌러도 판이 남아 있다');
});

await t('모델 고르기가 칸보다 위에 선다 — Female · Male 두 장', async () => {
  const setup = thread().querySelector('.cpFitSetup');
  const models = setup.querySelector('.cpFitModels'), items = setup.querySelector('.cpFitItems');
  assert.ok(models.compareDocumentPosition(items) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING,
            '모델이 칸 아래에 있다');
  assert.deepEqual([...models.querySelectorAll('[data-vf-model]')].map(b => b.textContent), ['Female', 'Male']);
  click(models.querySelector('[data-vf-model="man"]')); await wait(10);
  assert.ok(thread().querySelector('.cpFitModels.m-man [data-vf-model="man"].on'), 'Male 이 골라지지 않았다');
  click(thread().querySelector('[data-vf-generate]')); await wait(60);
  assert.equal(fitBody.model_id, 'man');
  click(thread().querySelector('[data-vf-model="woman"]')); await wait(10);
});

await t('＋ 는 칸을 한 개씩 늘리고, × 는 칸째로 뺀다', async () => {
  const n = () => thread().querySelectorAll('.cpFit .cpFitSlot:not(.addSlot)').length;
  click(thread().querySelector('[data-vf-add]')); await wait(10);
  assert.equal(n(), 2, '＋ 를 눌러도 칸이 늘지 않았다');
  click(thread().querySelector('[data-vf-add]')); await wait(10);
  assert.equal(n(), 3);
  const del = thread().querySelectorAll('[data-vf-remove]');
  click(del[del.length - 1]); await wait(10);
  assert.equal(n(), 2, '× 를 눌러도 칸이 줄지 않았다');
  assert.equal(thread().querySelector('.cpFitClothesHead span').textContent, '2 / 9');
});

await t('칸은 아홉(서버 MAX_ITEMS)에서 멈추고 ＋ 가 사라진다', async () => {
  for (let i = 0; i < 12; i++) {
    const add = thread().querySelector('[data-vf-add]');
    if (!add) break;
    click(add); await wait(5);
  }
  assert.equal(thread().querySelectorAll('.cpFit .cpFitSlot:not(.addSlot)').length, 9);
  assert.equal(thread().querySelector('[data-vf-add]'), null, '아홉 칸인데 ＋ 가 남아 있다');
  /* 뒤 시험이 한 칸짜리를 기대하므로 되돌린다 */
  for (let i = 0; i < 8; i++) {
    const del = thread().querySelectorAll('[data-vf-remove]');
    click(del[del.length - 1]); await wait(5);
  }
  assert.equal(thread().querySelectorAll('.cpFit .cpFitSlot:not(.addSlot)').length, 1);
});

await t('판에서 고른 종류가 칸 이름 · 배지가 되고 생성 요청에 실린다', async () => {
  click(thread().querySelector('[data-vf-kind="0"]')); await wait(10);
  click(thread().querySelector('[data-vf-kindpick="0|모자"]')); await wait(10);
  assert.equal(thread().querySelector('.cpFitSheet'), null, '고른 뒤에도 판이 남아 있다');
  const cap = thread().querySelector('[data-vf-kind="0"]');
  assert.equal(cap.textContent.trim(), '모자');
  assert.equal(cap.classList.contains('auto'), false);
  click(thread().querySelector('[data-vf-generate]'));
  await wait(60);
  assert.equal(fitBody.items[0].category, '모자');
  /* Auto 로 되돌리면 서버가 사진을 보고 정한다 */
  click(thread().querySelector('[data-vf-kind="0"]')); await wait(10);
  click(thread().querySelector('[data-vf-kindpick="0|자동 분류"]')); await wait(10);
  assert.equal(thread().querySelector('[data-vf-kind="0"]').textContent.trim(), 'Auto');
  click(thread().querySelector('[data-vf-generate]')); await wait(60);
  assert.equal(fitBody.items[0].category, '자동 분류');
});

/* 2026-10-01 시안 C — 옵션은 결과 아래 독에 늘 보인다(서랍 없음).
   아우터 · 상의는 버튼 하나로 Open ↔ Close, 핏은 그림 세 칸, 레이어드는 On/Off. */
await t('독에는 아우터 · 상의 Open/Close, 핏 세 칸, 레이어드, 엔진 둘, 입혀보기가 선다', () => {
  const dock = thread().querySelector('.cpFitOutput .cpFitDock');
  assert.ok(dock, '독이 없다');
  assert.equal(thread().querySelector('[data-vf-opts]'), null, '옛 옵션 서랍 버튼이 남아 있다');
  assert.deepEqual([...dock.querySelectorAll('[data-vf-flip]')].map(b => b.textContent.trim()),
    ['아우터 Open', '상의 Open']);
  assert.deepEqual([...dock.querySelectorAll('[data-vf-slide="fit"]')].map(b => b.getAttribute('aria-label')),
    ['오버핏', '정핏', '슬림핏']);
  assert.equal(dock.querySelector('[data-vf-slide="fit"].on').dataset.vfVal, 'regular');
  assert.match(dock.querySelector('.cpDockFit>span').textContent, /핏 · 정핏/);
  const layer = dock.querySelector('[data-vf-opt="outer_layered"]');
  assert.equal(layer.getAttribute('role'), 'switch');
  assert.equal(layer.textContent.trim(), '레이어드 Off');
  assert.deepEqual([...dock.querySelectorAll('[data-vf-slide="engine"]')].map(b => b.textContent.trim()),
    ['고화질', '빠르게']);
  assert.ok(dock.querySelector('.cpDockGo[data-vf-generate]'), '입혀보기 버튼이 독에 없다');
});

await t('옵션을 눌러도 대화가 맨 아래로 튀지 않는다 (2026-09-14)', async () => {
  const wrap = document.querySelector('#cpThreadWrap');
  /* jsdom 에는 레이아웃이 없어 scrollHeight 가 0이다 — 값을 세워 두고 본다 */
  Object.defineProperty(wrap, 'scrollHeight', { value: 4000, configurable: true });
  wrap.scrollTop = 1200;
  click(thread().querySelector('[data-vf-opt="outer_layered"]'));
  await wait(10);
  assert.equal(wrap.scrollTop, 1200, `보던 자리가 ${wrap.scrollTop} 로 튀었다`);
  click(thread().querySelector('[data-vf-opt="outer_layered"]'));  /* 되돌린다 */
  await wait(10);
});

/* 2026-10-02 — 옵션을 바꿀 때마다 대화 전체를 다시 그려 왼쪽 사진들이 깜빡였다.
   이제 위젯 안에서 달라진 곳만 고친다 — 사진 <img> 는 같은 요소로 남아야 한다. */
await t('옵션 · 엔진 · 모델 · 종류 판을 바꿔도 사진 요소는 다시 만들어지지 않는다', async () => {
  const imgs = () => [...thread().querySelectorAll('.cpFitModels img, .cpFitItemImg')];
  const before = imgs();
  const say = thread().querySelector('.msg.ai .say');
  assert.ok(before.length >= 3, '모델 · 옷 사진이 없다');
  for (const sel of ['[data-vf-flip="outer"]', '[data-vf-slide="fit"][data-vf-val="over"]',
                     '[data-vf-opt="outer_layered"]', '[data-vf-slide="engine"][data-vf-val="flare"]',
                     '[data-vf-model="man"]', '[data-vf-kind="0"]']) {
    click(thread().querySelector(sel)); await wait(10);
  }
  const after = imgs();
  assert.equal(after.length, before.length);
  after.forEach((img, i) => assert.equal(img, before[i], `${i}번째 사진이 새 요소로 바뀌었다`));
  assert.equal(thread().querySelector('.msg.ai .say'), say, '답변 말풍선까지 다시 그렸다');
  assert.ok(thread().querySelector('.cpFitModels.m-man'), 'Male 로 안 바뀌었다');
  assert.ok(thread().querySelector('.cpFitSheet'), '종류 판이 안 열렸다');
  /* 되돌린다 */
  for (const sel of ['.cpFitSheetHead [data-vf-kind]', '[data-vf-model="woman"]',
                     '[data-vf-slide="engine"][data-vf-val="sunburst"]', '[data-vf-opt="outer_layered"]',
                     '[data-vf-slide="fit"][data-vf-val="regular"]', '[data-vf-flip="outer"]']) {
    click(thread().querySelector(sel)); await wait(10);
  }
  assert.equal(thread().querySelector('.cpFitSheet'), null);
});

await t('아무것도 안 만지면 열어 입기 · 정핏 · 고화질로 나간다', async () => {
  click(thread().querySelector('[data-vf-generate]'));
  await wait(60);
  assert.deepEqual(fitBody.options,
    {outer_layered:false, outer_open:true, outer_closed:false, top_open:true, top_closed:false,
     fit_over:false, fit_slim:false});
  assert.equal(fitBody.engine, 'sunburst');
});

const cellOf = (group, val) =>
  thread().querySelector('[data-vf-slide="' + group + '"][data-vf-val="' + val + '"]');
const flipOf = (group) => thread().querySelector('[data-vf-flip="' + group + '"]');

await t('Open/Close 는 누를 때마다 뒤집히고, 둘이 같이 켜지지 않는다', async () => {
  click(thread().querySelector('[data-vf-opt="outer_layered"]')); await wait(10);
  assert.equal(thread().querySelector('[data-vf-opt="outer_layered"]').textContent.trim(), '레이어드 On');
  click(flipOf('outer')); await wait(10);
  assert.equal(flipOf('outer').textContent.trim(), '아우터 Close');
  click(flipOf('top')); await wait(10);
  click(thread().querySelector('[data-vf-generate]'));
  await wait(60);
  assert.equal(fitBody.options.outer_layered, true);
  assert.equal(fitBody.options.outer_closed, true);
  assert.equal(fitBody.options.outer_open, false, '열기와 여미기가 같이 켜졌다');
  assert.equal(fitBody.options.top_closed, true);
  assert.equal(fitBody.options.top_open, false);
  click(flipOf('outer')); await wait(10);     /* 다시 누르면 Open */
  assert.equal(flipOf('outer').textContent.trim(), '아우터 Open');
  click(flipOf('top')); await wait(10);
  click(thread().querySelector('[data-vf-opt="outer_layered"]')); await wait(10);
});

await t('핏은 세 칸 중 하나 — 오버핏 · 정핏(이름 없음) · 슬림핏', async () => {
  const fitOpts = async (val) => {
    click(cellOf('fit', val)); await wait(10);
    click(thread().querySelector('[data-vf-generate]')); await wait(60);
    return [fitBody.options.fit_over, fitBody.options.fit_slim];
  };
  assert.deepEqual(await fitOpts('over'), [true, false]);
  /* 고른 칸을 다시 눌러도 그대로다 */
  assert.deepEqual(await fitOpts('over'), [true, false]);
  assert.deepEqual(await fitOpts('slim'), [false, true]);
  assert.match(thread().querySelector('.cpDockFit>span').textContent, /핏 · 슬림핏/);
  assert.deepEqual(await fitOpts('regular'), [false, false]);
  assert.equal(cellOf('fit', 'regular').getAttribute('aria-checked'), 'true');
});

await t('생성 방식 — 빠르게(Flare)를 고르면 그대로 요청에 실리고 엔진 표시가 바뀐다', async () => {
  const tag = () => thread().querySelector('.cpFitEngineTag').textContent.trim();
  assert.equal(tag(), 'SUNBURST');
  click(cellOf('engine', 'flare')); await wait(10);
  assert.equal(tag(), 'FLARE');
  /* 고른 칸을 다시 눌러도 그대로다 — 두 버튼은 라디오다 */
  click(cellOf('engine', 'flare')); await wait(10);
  assert.equal(tag(), 'FLARE');
  click(thread().querySelector('[data-vf-generate]')); await wait(60);
  assert.equal(fitBody.engine, 'flare');
  /* 결과 아래에 무엇으로 몇 초 걸렸는지 — 옛 서버는 engine 을 안 돌려줘서 고화질로 적힌다 */
  assert.match(thread().querySelector('.cpFitMade').textContent, /^고화질 \(SUNBURST\) · \d+초$/);
  click(cellOf('engine', 'sunburst')); await wait(10);
  assert.equal(tag(), 'SUNBURST');
});

await t('설정 칸을 접으면 모델 · 옷이 작은 네모로 남고, 누르면 다시 펼친다', async () => {
  const sec = () => thread().querySelector('.cpFit');
  click(thread().querySelector('.cpFitSideBtn')); await wait(10);
  assert.ok(sec().classList.contains('side-closed'), '접히지 않았다');
  assert.equal(sec().querySelector('.cpFitModels'), null, '접혔는데 모델 사진이 그대로다');
  const sq = [...sec().querySelectorAll('.cpFitMini .cpMiniSq')];
  /* 모델 하나 · 옷 칸 하나 · 칸 추가 하나 */
  assert.equal(sq.length, 3);
  assert.ok(sq[0].classList.contains('model'));
  assert.ok(sq[2].classList.contains('add'));
  assert.ok(sec().querySelector('.cpFitDock'), '접어도 독은 남아야 한다');
  click(sq[1]); await wait(10);
  assert.equal(sec().classList.contains('side-closed'), false, '네모를 눌러도 펼쳐지지 않았다');
  assert.ok(sec().querySelector('.cpFitModels'));
});

await t('결과가 나오면 이미지 저장 버튼이 붙는다', () => {
  const a = thread().querySelector('.cpFitDl');
  assert.ok(a, '저장 버튼이 없다');
  assert.equal(a.getAttribute('href'), FAKE_PNG);
  assert.match(a.getAttribute('download'), /\.png$/);
});

/* 4K 로 올리면서 결과를 webp 로 받게 됐다(vton.OUTPUT_FORMAT). 저장 이름만
   .png 로 박혀 있으면 내려받은 파일이 이름과 속이 다르다. (2026-09-14) */
await t('저장 파일 확장자는 서버가 보낸 형식을 따른다', async () => {
  const m = CP.cpStore().convos.find(c => c.messages.some(x => x.fit))
    .messages.filter(x => x.fit).pop();
  const was = { result: m.fit.result, format: m.fit.format };
  m.fit.result = 'data:image/webp;base64,UklGRg=='; m.fit.format = 'webp';
  CP.cpRenderThread({ keepScroll: true });
  await wait(10);
  assert.match(thread().querySelector('.cpFitDl').getAttribute('download'), /\.webp$/);
  /* format 을 안 보내던 옛 대화는 data URL 에서 읽어 낸다 */
  m.fit.format = '';
  CP.cpRenderThread({ keepScroll: true });
  await wait(10);
  assert.match(thread().querySelector('.cpFitDl').getAttribute('download'), /\.webp$/);
  Object.assign(m.fit, was);
  CP.cpRenderThread({ keepScroll: true });
  await wait(10);
});

/* ── 리포트 저장 · 공유 ─────────────────────────────────────
   진짜 리포트는 서버가 붙여 준다. 여기서는 카드 마크업만 스레드에 넣고
   버튼이 실제로 배선돼 있는지(눌렀을 때 아무 일도 안 일어나지 않는지)를 본다.
   jsdom 에는 canvas 가 없어 이미지 저장까지는 갈 수 없다 — 그래서 공유 쪽의
   '마지막 수단'(클립보드)이 실패했을 때 사용자에게 말하는지를 확인한다. */
const API = await import(`${F}/home/static/js/chat_api.js`);

await t('리포트 카드 머리줄에 공유·저장 버튼이 붙는다', () => {
  const card = API.reportHTML({ blocks: [{ type: 'rank', slot: 'full', title: 'TOP',
    rows: [{ k: '자켓', v: '86', up: true }] }] });
  assert.match(card, /data-rp-share/);
  assert.match(card, /data-rp-save/);
  const say = thread().querySelector('.msg.ai .say');
  say.parentElement.insertAdjacentHTML('beforeend', card);
});

await t('공유를 누르면 결과를 말한다 (조용히 끝나지 않는다)', async () => {
  click(thread().querySelector('[data-rp-share]'));
  await wait(60);
  const toast = document.querySelector('#cpToast');
  assert.ok(toast, '알림 한 줄이 없다');
  assert.ok(toast.textContent.trim().length > 0, '알림이 비어 있다');
});

/* ── 칸이 늘어도 결과 칸은 안 늘어난다 (2026-09-14) ────────
   jsdom 에는 레이아웃이 없어 실제 높이는 잴 수 없다. 대신 (1) 높이를 정하는
   쪽이 살아 있는지와 (2) 레이아웃이 없을 때 0 을 물고 칸을 접어 버리지
   않는지를 본다. 이 둘이 깨지면 아홉 칸까지 늘렸을 때 왼쪽이 길어지고
   .cpFitGrid(align-items:stretch) 때문에 오른쪽 검은 칸까지 같이 늘어난다. */
await t('칸 목록은 스크롤이 걸려 있고 타일은 정사각형이다', () => {
  const css = fs.readFileSync(new URL('../home/static/css/chat_popup.css', import.meta.url), 'utf8');
  const rule = css.match(/\.cpFitItems\{[^}]*\}/s);
  assert.ok(rule, '.cpFitItems 규칙이 없다');
  assert.match(rule[0], /overflow-y:\s*auto/, '스크롤이 걸려 있지 않다');
  const tile = css.match(/\.cpFitItem\{[^}]*\}/s);
  assert.match(tile[0], /aspect-ratio:\s*1/, '타일이 정사각형이 아니다');
});

await t('두 줄 상한은 실제로 잰 한 줄 높이로 잡는다', () => {
  const box = thread().querySelector('.cpFitItems');
  assert.ok(box, '칸 목록이 없다');
  /* 레이아웃이 없으면(offsetHeight 0) 손대지 않는다 — 0 을 쓰면 칸이 접힌다 */
  assert.equal(box.style.maxHeight, '', '높이를 못 쟀는데 값을 박았다');
  /* 한 줄이 100px 인 척하고 다시 재게 한다: 2줄 + 간격 10 + 비침 18 = 228 */
  const slot = box.querySelector('.cpFitSlot:not(.addSlot)');
  Object.defineProperty(slot, 'offsetHeight', { value: 100, configurable: true });
  CP.cpFitSizeItems(thread());
  assert.equal(box.style.maxHeight, '228px', `상한이 ${box.style.maxHeight} 로 잡혔다`);
  box.style.maxHeight = '';
});

/* ── 대화 목록 줄 메뉴 (2026-09-14) ───────────────────────
   연필·휴지통 두 버튼을 ⋮ 하나로 모았다. 고정·이름 변경·삭제가 거기서 나온다. */
const list = () => document.querySelector('#cpList');
const menu = () => document.querySelector('#cpMenu');

await t('대화 줄에는 ⋮ 하나만 있고 연필·휴지통은 없다', () => {
  CP.cpRenderList();
  assert.ok(list().querySelector('.cpKebab[data-menu]'), '⋮ 가 없다');
  assert.equal(list().querySelector('.cpEdit'), null, '연필이 남아 있다');
  assert.equal(list().querySelector('.cpDel'), null, '휴지통이 남아 있다');
});

await t('⋮ 를 누르면 고정·이름 변경·삭제가 뜬다', () => {
  CP.cpOpenMenu(list().querySelector('.cpKebab[data-menu]'));
  const items = [...menu().querySelectorAll('[data-mi]')].map(b => b.dataset.mi);
  assert.deepEqual(items, ['pin', 'rename', 'del']);
  assert.equal(menu().hidden, false);
});

await t('삭제는 한 번 더 묻는다 — 바로 지우지 않는다', async () => {
  const before = CP.cpStore().convos.length;
  click(menu().querySelector('[data-mi="del"]'));
  await wait(10);
  assert.equal(CP.cpStore().convos.length, before, '묻지도 않고 지웠다');
  assert.ok(menu().querySelector('[data-mi="del-yes"]'), '확인 줄이 없다');
  click(menu().querySelector('[data-mi="cancel"]'));
  await wait(10);
  assert.equal(CP.cpStore().convos.length, before);
});

await t('고정한 대화는 목록 맨 위로 올라간다', async () => {
  const s = CP.cpStore();
  assert.ok(s.convos.length >= 2, '대화가 둘 이상 있어야 본다');
  const last = s.convos[s.convos.length - 1];
  CP.cpOpenMenu(list().querySelector('.cpKebab[data-menu="' + last.id + '"]'));
  click(menu().querySelector('[data-mi="pin"]'));
  await wait(10);
  assert.equal(CP.cpStore().convos[0].id, last.id, '고정했는데 위로 안 갔다');
  assert.ok(list().querySelector('.cpItemRow.pinned'), '고정 표시가 없다');
});

await t('메뉴에 적어 둔 글쇠(P·R·D)가 실제로 먹는다', async () => {
  const s = CP.cpStore();
  const target = s.convos.find(c => !c.pinned) || s.convos[0];
  CP.cpOpenMenu(list().querySelector('.cpKebab[data-menu="' + target.id + '"]'));
  const was = !!target.pinned;
  document.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'p', bubbles: true }));
  await wait(10);
  assert.equal(!!CP.cpStore().convos.find(c => c.id === target.id).pinned, !was, 'P 가 안 먹는다');
  /* D 는 바로 지우지 않고 확인 줄을 연다 */
  CP.cpOpenMenu(list().querySelector('.cpKebab[data-menu="' + target.id + '"]'));
  const before = CP.cpStore().convos.length;
  document.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'd', bubbles: true }));
  await wait(10);
  assert.equal(CP.cpStore().convos.length, before, 'D 가 묻지도 않고 지웠다');
  assert.ok(menu().querySelector('[data-mi="del-yes"]'), 'D 로 확인 줄이 안 열렸다');
  click(menu().querySelector('[data-mi="cancel"]'));
  await wait(10);
});

await t('바깥을 누르면 메뉴가 닫힌다', async () => {
  CP.cpOpenMenu(list().querySelector('.cpKebab[data-menu]'));
  assert.equal(menu().hidden, false);
  click(document.body);
  await wait(10);
  assert.equal(menu().hidden, true, '메뉴가 떠 있다');
});

/* ── Virtual Try On 단독 진입 (2026-09-18) ──────────────
   질문을 먼저 보내지 않아도 팝업 버튼이 빈 착장을 연다. */
await t('팝업 왼쪽 하단에만 Virtual Try On 버튼이 있다', () => {
  assert.equal(document.querySelector('#homeVtonQuick'), null, '홈 챗바 위 버튼이 남아 있다');
  assert.ok(document.querySelector('#cpVtonQuick'), '팝업 버튼이 없다');
  assert.match(popupCss, /\.cpOverlay\.sm \.cpVtonQuick\{display:flex/,
               '팝업 버튼이 살말 모드에서 보이지 않는다');
});

await t('질문 없이 바로 빈 착장 위젯을 연다', async () => {
  CP.openVirtualTryOn();
  await wait(340);
  const c = CP.cpStore().convos.find(x => x.id === CP.cpStore().activeId);
  assert.equal(c.title, 'Virtual Try On');
  assert.equal(c.transient, true, '저장될 수 없는 착장 상태가 대화 기록으로 남는다');
  assert.equal(c.messages.some(m => m.role === 'me'), false, '질문 메시지가 자동으로 생겼다');
  assert.ok(thread().querySelector('.cpFit'), '착장 위젯이 없다');
  assert.equal(thread().querySelectorAll('.cpFitSlot:not(.addSlot)').length, 1,
               '첫 사진을 넣을 빈 칸이 하나여야 한다');
  assert.equal(document.querySelector('#cpOverlay').classList.contains('sm'), true,
               '살말 팝업으로 열리지 않았다');
});

await t('팝업 버튼이 독립 착장을 연다 — 살!말? 대화 안이면 이 대화/새 대화를 먼저 묻는다', async () => {
  const count = () => CP.cpStore().convos.length;
  const where = () => document.querySelector('#cpWhere');
  const before = count();
  click(document.querySelector('#cpVtonQuick'));
  await wait(40);
  const asked = !where().hidden;
  if (asked) {
    assert.equal(count(), before, '고르기 전에는 아무것도 만들지 않는다');
    click(where().querySelector('[data-where="new"]'));
    await wait(40);
  }
  assert.equal(count(), before + 1, '팝업 버튼이 새 착장을 열지 않았다');
  /* 이제 살!말? 대화 안 — 다시 누르면 묻고, '이 대화에서' 는 대화를 늘리지 않는다 */
  const c = CP.cpStore().convos.find(x => x.id === CP.cpStore().activeId);
  const fits = () => c.messages.filter(m => m.fit).length;
  const had = fits();
  click(document.querySelector('#cpVtonQuick'));
  await wait(40);
  assert.equal(where().hidden, false, '살!말? 대화 안에서는 어디서 열지 묻는다');
  assert.match(where().textContent, /이 대화에서/);
  click(where().querySelector('[data-where="here"]'));
  await wait(40);
  assert.equal(where().hidden, true);
  assert.equal(count(), before + 1, '이 대화에서 열면 대화가 늘지 않는다');
  assert.equal(fits(), had + 1, '이 대화 아래에 착장 칸이 하나 더 열린다');
  /* × 는 취소 */
  click(document.querySelector('#cpVtonQuick')); await wait(20);
  click(where().querySelector('[data-where="close"]')); await wait(20);
  assert.equal(fits(), had + 1);
  assert.equal(count(), before + 1);
});

/* 챗봇이 고른 연출이 슬라이드에 그대로 선다 (2026-10-01).
   서버 build_fit 은 켠 이름만 돌려준다 — 안 고른 묶음은 기본 칸(열어 입기 · 정핏)이다. */
await t('챗봇이 고른 연출(top_closed)은 상의 슬라이드를 여며 입기로 세운다', () => {
  const f = CP.cpFitFromServer({ items: [{ slot: '상의', image: 'https://image.msscdn.net/a.jpg' }],
                                 options: ['top_closed'] }, '');
  assert.equal(f.options.top_closed, true);
  assert.equal(f.options.top_open, false);
  assert.equal(f.options.outer_open, true, '안 고른 아우터가 기본(열어 입기)이 아니다');
  assert.deepEqual([f.options.fit_over, f.options.fit_slim], [false, false]);
  /* 둘 다 켜져 온 옛 값은 고른 칸 하나로 정리된다 — 모순된 지시가 나가지 않는다 */
  const g = CP.cpFitFromServer({ items: [], options: ['outer_open', 'outer_closed'] }, '');
  assert.equal(Number(g.options.outer_open) + Number(g.options.outer_closed), 1);
});

await t('저장된 성별이 VTON 기본 모델을 고르고, 상품 출처 링크가 착장 카드에 나온다', () => {
  P.ME.gender='MALE';
  const fit=CP.cpFitFromServer({items:[{
    slot:'상의',image:'https://image.msscdn.net/a.jpg',name:'트랙 재킷',
    brand:'아디다스',source:'MUSINSA',source_label:'무신사',
    url:'https://www.musinsa.com/products/123',
  }]},'이 코디로 입혀보기');
  assert.equal(fit.model,'man');
  const c=CP.cpNewConvo();
  c.messages.push({role:'ai',html:'',fit});
  CP.cpRenderThread();
  assert.equal(thread().querySelector('.cpFitProductName').textContent,'트랙 재킷');
  /* ① 칸 사진 위 판매처 배지 · ② 코디 상품 줄의 카드가 판매처로 간다 (2026-10-02) */
  assert.equal(thread().querySelector('.cpFitItem .cpFitSrcTag').textContent,'무신사');
  const link=thread().querySelector('.cpFitLookCard');
  assert.equal(link.href,'https://www.musinsa.com/products/123');
  assert.match(link.textContent,/아디다스/);
  assert.match(link.textContent,/무신사 ↗/);
  assert.equal(link.rel,'noopener noreferrer');
  const unsafe=CP.cpFitFromServer({items:[{slot:'상의',image:'https://image.msscdn.net/a.jpg',
    name:'의심 상품',url:'javascript:alert(1)'}]},'');
  assert.equal(unsafe.items[0].url,'');
  /* 판매처 없는 사진(직접 올린 것)은 코디 상품 줄에 오르지 않는다 */
  const mine=CP.cpNewConvo();
  mine.messages.push({role:'ai',html:'',fit:CP.cpFitFromServer({items:[{slot:'상의',image:'https://image.msscdn.net/a.jpg'}]},'')});
  CP.cpRenderThread();
  assert.equal(thread().querySelector('.cpFitLook'),null);
  assert.equal(thread().querySelector('.cpFitSrcTag'),null);
  P.ME.gender='FEMALE';
  assert.equal(CP.cpFitFromServer({items:[]},'').model,'woman');
  assert.equal(CP.cpFitFromServer({items:[]},'Female 코디').model,'woman');
  assert.equal(CP.cpFitFromServer({items:[]},'Male 코디').model,'man');
  assert.equal(CP.cpFitFromServer({items:[],gender:'MALE'},'이 코디로 입혀보기').model,'man');
  /* 데이트 상대는 입을 사람이 아니다 — "여자친구랑 데이트" 를 FEMALE 로 읽지 않는다 */
  P.ME.gender='MALE';
  assert.equal(CP.cpFitFromServer({items:[]},'주말에 여자친구랑 데이트할 때 입을 옷').model,'man');
  assert.equal(CP.cpFitFromServer({items:[]},'여친이랑 데이트 코디').model,'man');
  P.ME.gender='FEMALE';
  assert.equal(CP.cpFitFromServer({items:[]},'남자친구랑 전시회 갈 때 입을 옷').model,'woman');
  P.ME.gender='';
});

await t('③ 결과 사진 위 태그 — 판매처 상품만 점이 찍히고, 누르면 카드가 열린다', async () => {
  const fit=CP.cpFitFromServer({items:[
    {slot:'아우터',image:'https://image.msscdn.net/a.jpg',name:'릴렉스드 블레이저',brand:'무신사 스탠다드',
     source:'MUSINSA',source_label:'무신사',url:'https://www.musinsa.com/products/1'},
    {slot:'신발',image:'https://image.msscdn.net/b.jpg',name:'더비 슈즈',brand:'로맨틱무브',
     source:'MUSINSA',source_label:'무신사',url:'https://www.musinsa.com/products/2'},
  ]},'');
  fit.result='data:image/webp;base64,eA=='; fit.size='2480x3312';
  /* 서버 태그는 보낸 순서(index) — 화면은 칸 번호(item)로 바꿔 둔다. 겹친 점은 비켜 선다. */
  fit.tags=[{item:0,x:.5,y:.35},{item:1,x:.5,y:.36}];
  const c=CP.cpNewConvo();
  c.messages.push({role:'ai',html:'',fit});
  CP.cpRenderThread();
  const shot=thread().querySelector('.cpFitShot');
  assert.match(shot.getAttribute('style'),/aspect-ratio:2480 \/ 3312/);
  const dots=[...thread().querySelectorAll('.cpFitTag')];
  assert.equal(dots.length,2);
  const marks=[...thread().querySelectorAll('.cpFitTagMark')];
  assert.notEqual(marks[0].style.top,marks[1].style.top,'겹친 점은 비켜 선다');
  /* 카드는 점마다 미리 있되(마우스오버로 뜬다) 고정된 것(.on)은 아직 없다 */
  assert.equal(thread().querySelectorAll('.cpFitTagCard').length,2);
  assert.equal(thread().querySelector('.cpFitTagMark.on'),null);
  click(dots[0]); await wait(10);
  const card=thread().querySelector('.cpFitTagMark.on .cpFitTagCard');
  assert.match(card.textContent,/릴렉스드 블레이저/);
  assert.match(card.textContent,/무신사 스탠다드 · 무신사/);
  assert.equal(card.querySelector('a').href,'https://www.musinsa.com/products/1');
  assert.equal(card.querySelector('a').rel,'noopener noreferrer');
  assert.equal(thread().querySelector('[data-vf-tag="0"]').getAttribute('aria-expanded'),'true');
  /* 사진을 누르면 고정이 풀린다 */
  click(thread().querySelector('.cpFitResult')); await wait(10);
  assert.equal(thread().querySelector('.cpFitTagMark.on'),null);
  assert.match(thread().querySelector('.cpFitLookHead').textContent,/사진에 올리면/);
});

await t('③ 생성 요청은 이름과 태그 요청을 싣고, 서버 태그(보낸 순서)를 칸 번호로 옮긴다', async () => {
  const fit=CP.cpFitFromServer({items:[
    {slot:'상의',image:'https://image.msscdn.net/a.jpg',name:'옥스퍼드 셔츠',source_label:'무신사',url:'https://www.musinsa.com/products/1'},
    {slot:'신발',image:'https://image.msscdn.net/b.jpg',name:'더비 슈즈',source_label:'무신사',url:'https://www.musinsa.com/products/2'},
  ]},'');
  fit.items.splice(1,0,{category:'하의',image:'',imageUrl:'',auto:false});   /* 빈 칸이 사이에 있다 */
  const c=CP.cpNewConvo();
  c.messages.push({role:'ai',html:'',fit});
  CP.cpRenderThread();
  click(thread().querySelector('[data-vf-generate]')); await wait(60);
  assert.equal(fitBody.tags,true);
  assert.deepEqual(fitBody.items.map(x=>x.name),['옥스퍼드 셔츠','더비 슈즈']);
  const dot=thread().querySelector('.cpFitTag');
  assert.equal(dot.dataset.vfTag,'2','보낸 순서 1번 = 칸 2번(빈 칸을 건너뛴다)');
  /* 판매처 없는 사진만이면 태그를 청하지 않는다 — vision 한 번을 아낀다 */
  const own=CP.cpFitFromServer({items:[{slot:'상의',image:'https://image.msscdn.net/a.jpg'}]},'');
  const c2=CP.cpNewConvo();
  c2.messages.push({role:'ai',html:'',fit:own});
  CP.cpRenderThread();
  click(thread().querySelector('[data-vf-generate]')); await wait(60);
  assert.equal(fitBody.tags,false);
  assert.equal(thread().querySelector('.cpFitTag'),null);
});

await t('결과 뒤 다른 룩 제안 — 상황을 잇고, 보여 준 상품과 근거 기사를 서버에 알린다', async () => {
  const fit=CP.cpFitFromServer({items:[
    {slot:'상의',image:'https://image.msscdn.net/a.jpg',name:'옥스퍼드 셔츠',source_label:'무신사',
     url:'https://www.musinsa.com/products/11',product_source_id:'11'},
  ],styles:['미니멀'],occasion:'친구 결혼식 하객',
   ref:{title:'블레이저 하객룩',who:'보그',url:'https://www.vogue.co.kr/g'}},'');
  assert.equal(fit.occasion,'친구 결혼식 하객');
  assert.equal(fit.ref.url,'https://www.vogue.co.kr/g');
  const c=CP.cpNewConvo();
  c.messages.push({role:'ai',html:'',fit});
  CP.cpRenderThread();
  /* 근거 기사는 '참고한 코디' 로 링크된다 */
  const ref=thread().querySelector('.cpFitRef');
  assert.equal(ref.href,'https://www.vogue.co.kr/g');
  assert.match(ref.textContent,/참고한 코디/);
  assert.equal(thread().querySelector('.cpFitNext'),null,'결과 전에는 묻지 않는다');
  click(thread().querySelector('[data-vf-generate]')); await wait(60);
  const next=thread().querySelector('.cpFitNext');
  assert.match(next.textContent,/친구 결혼식 하객 다른 룩도 추천해 드릴까요\?/);
  const msg=c.messages.find(m=>m.fit===fit);
  assert.match(msg.turn.next,/다른 룩도 추천해 드릴까요/,'"응" 만 쳐도 이어지게 기록에 남는다');
  const mem=CP.cpFitMemory(c);
  assert.deepEqual(mem.refs,['https://www.vogue.co.kr/g']);
  assert.equal(mem.occasion,'친구 결혼식 하객');
  assert.ok(mem.seen.includes('https://www.musinsa.com/products/11'));
  /* '다른 룩 추천' 은 같은 상황으로 이 대화에 새 질문을 보낸다 */
  click(thread().querySelector('[data-vf-more="look"]')); await wait(30);
  const asked=c.messages.filter(m=>m.role==='me').map(m=>m.text);
  assert.ok(asked.includes('친구 결혼식 하객 다른 룩도 추천해줘'), asked.join(' / '));
  /* 사진 직접 올린 위젯(서버 코디 아님)에는 묻지 않는다 */
  const own=CP.cpNewConvo();
  own.messages.push({role:'ai',html:'',fit:{...CP.cpFitFromServer({items:[]},''),fromServer:false,result:'data:image/png;base64,eA=='}});
  CP.cpRenderThread();
  assert.equal(thread().querySelector('.cpFitNext'),null);
});

await t('답 아래 [입혀보기] 는 한 번에 반응한다 — 열린 착장 칸을 접지 않고 바로 만든다', async () => {
  fitBody=null;
  const fit=CP.cpFitFromServer({items:[{slot:'상의',image:'https://image.msscdn.net/a.jpg',name:'셔츠',
    url:'https://www.musinsa.com/products/31'}],styles:['미니멀']},'');
  const c=CP.cpNewConvo();
  c.messages.push({role:'me',text:'데이트룩'});
  c.messages.push({role:'ai',html:'<p>코디</p>',fit,actionsHtml:
    '<div class="act"><button class="pill ghost actBtn" data-virtual-fit="1"><span>입혀보기</span></button></div>'});
  CP.cpRenderThread();
  assert.ok(thread().querySelector('.cpFit'),'답과 함께 칸이 열려 있다');
  click(thread().querySelector('[data-virtual-fit]')); await wait(60);
  assert.ok(thread().querySelector('.cpFit'),'첫 누름에 칸이 닫히면 안 된다');
  assert.ok(fitBody&&fitBody.items.length===1,'첫 누름에 바로 만든다');
  /* 이미 만든 뒤에는 다시 만들지 않는다 — 칸만 보여 준다 */
  fitBody=null;
  click(thread().querySelector('[data-virtual-fit]')); await wait(30);
  assert.equal(fitBody,null);
  assert.ok(thread().querySelector('.cpFit'));
});

await t('답하는 중에 들어온 질문은 끊지 않고 대기열에 넣었다가, 답이 끝나면 이어서 묻는다', async () => {
  CP.openChatWith('발레코어 요즘 어때?', null, {fresh:true});
  const c=CP.cpStore().convos.find(x=>x.id===CP.cpStore().activeId);
  /* 첫 답이 도는 중 — 칩을 누르거나 새로 친 질문 */
  CP.openChatWith('그럼 비슷한 스타일은?', null);
  assert.equal(CP.cpQueueSize(),1,'바로 보내지 않고 기다린다');
  const box=document.querySelector('#cpQueue');
  assert.equal(box.hidden,false);
  assert.match(box.textContent,/그럼 비슷한 스타일은\?/);
  assert.deepEqual(c.messages.filter(m=>m.role==='me').map(m=>m.text),['발레코어 요즘 어때?'],
    '대기 중인 질문은 아직 대화에 들어가지 않는다');
  /* 첫 답이 끝나면 이어서 묻는다 */
  for(let i=0;i<40&&CP.cpQueueSize();i++) await wait(30);
  await wait(200);
  assert.equal(CP.cpQueueSize(),0);
  assert.equal(box.hidden,true);
  assert.deepEqual(c.messages.filter(m=>m.role==='me').map(m=>m.text),
    ['발레코어 요즘 어때?','그럼 비슷한 스타일은?']);
  /* × 로 빼면 묻지 않는다 */
  CP.openChatWith('하나', null);
  CP.openChatWith('뺄 질문', null);
  click(document.querySelector('#cpQueue [data-q-drop]'));
  assert.equal(CP.cpQueueSize(),0);
  await wait(400);
  assert.ok(!c.messages.some(m=>m.text==='뺄 질문'));
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
