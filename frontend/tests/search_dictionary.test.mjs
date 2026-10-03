/* 세부 검색 — 사전(RDS)과 네 칸 독립 필터가 지금 방식대로 도는지 실제로 눌러 본다.
 *
 * ── 2026-09-16 다시 씀 ───────────────────────────────────────
 * 예전 시험은 "스타일 › 종류 › 브랜드 › 아이템명" 을 위에서부터 좁히는
 * 단계식 팝업(#fsC0 button[data-lv], FS.sel, FS.attr)을 기준으로 짜여 있었다.
 * 2026-09-09 에 네 칸이 서로 독립된 필터(FS.pick)로 바뀌면서 14건이 늘 실패했다.
 * 지금 방식에 맞춰 다시 쓴다.
 *
 * 여기서 지키려는 것
 *   ① 사전에만 있는 말이 검색된다 (박아 둔 목록을 덮지 않고 얹는다)
 *   ② STYLE 칸은 핵심 스타일 10종만 — 상품이 0건이어도 0 으로 남는다
 *   ③ 서버 후보가 있으면 그것만, 못 받으면 박아 둔 목록이라고 밝힌다
 *   ④ 네 칸은 독립 필터 — 칩으로 쌓이고 하나만 뗄 수 있다
 *   ⑤ 색·디테일·TPO 같은 속성도 조건으로 걸리고 조회 대상이 된다
 *   ⑥ 할인률·리세일·수명주기는 조건을 고르면 빈 화면을 벗어난다
 *
 * 돌리는 법:  node tests/search_dictionary.test.mjs      (jsdom 필요)
 */
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const F = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://localhost:5173/' });
for (const k of ['window','document','Element','SVGElement','getComputedStyle','Node',
                 'HTMLElement','CustomEvent','KeyboardEvent','MouseEvent'])
  globalThis[k] = k === 'window' ? dom.window : dom.window[k];
/* notify.js 가 본문 진입을 기다릴 때 쓴다 — 전역에 없으면 import 단계에서 통째로 죽는다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
globalThis.cancelAnimationFrame = (h) => clearTimeout(h);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
globalThis.scrollTo = () => {};
globalThis.innerWidth = 1280; globalThis.innerHeight = 800;
globalThis.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.location = dom.window.location;
globalThis.localStorage = dom.window.localStorage;

/* ── 서버 흉내 ──────────────────────────────────────────────
   /api/dictionary 는 진짜 모양 그대로.
   ★ '발레코어' 는 박아 둔 목록에도 있다 — 덮이면 안 된다.
   ★ '블랙' 은 색이다 — 단계가 아니라 속성으로 걸려야 한다.
   /api/facets 는 백엔드가 주는 모양 그대로 — STYLE 은 핵심 10종, 0건 포함. */
const DICT = [
  { label: '키르시',   facet: '브랜드', kind: 'brand', en: 'KIRSH'  },
  { label: '엄브로',   facet: '브랜드', kind: 'brand', en: 'UMBRO'  },
  { label: '미니멀',   facet: '스타일', kind: 'term',  en: 'minimal'},
  { label: '발레코어', facet: '스타일', kind: 'term',  en: 'balletcore' },
  { label: '블랙',     facet: '색',     kind: 'term',  en: 'black'  },
  { label: '롱 슬리브', facet: '아이템', kind: 'term',  en: ''       },
  { label: '레이온',   facet: '소재',   kind: 'term',  en: 'rayon'  },
];
const CORE = ['고프코어','블록코어','바이크코어','놈코어','애슬레저','클래식','아메카지','그런지','페미닌','스트릿웨어'];
const FACETS = {
  status: 'ok', narrowed: true, matched: 1300, products: 8971,
  data: {
    style: [
      { label: '고프코어', count: 122 }, { label: '블록코어', count: 104 }, { label: '클래식', count: 86 },
      { label: '스트릿웨어', count: 51 }, { label: '애슬레저', count: 30 }, { label: '그런지', count: 19 },
      { label: '페미닌', count: 17 }, { label: '아메카지', count: 8 },
      { label: '바이크코어', count: 0 }, { label: '놈코어', count: 0 },
    ].map((o) => ({ ...o, core: true })),
    kind: [{ label: '스니커즈', count: 40 }],
    brand: [{ label: '살로몬', count: 30 }],
    item: [{ label: 'XT-6', count: 3 }],
  },
};
let dictCalls = 0, facetMode = 'ok', asked = [];
const reply = (obj) => { const body = JSON.stringify(obj);
  return { ok: true, status: 200, text: async () => body, json: async () => JSON.parse(body) }; };
globalThis.fetch = async (u) => {
  const url = decodeURIComponent(String(u));
  asked.push(url);
  if (url.includes('/api/dictionary')) {
    dictCalls++;
    return reply({ status: 'ok', data: DICT, total: DICT.length });
  }
  if (url.includes('/api/facets')) {
    if (facetMode === 'down') throw new Error('ECONNREFUSED');
    return reply(FACETS);
  }
  return reply({ status: 'empty', reason: '적재 전입니다.' });
};

let pass = 0, fail = 0;
const t = async (n, f) => {
  try { await f(); console.log('✅', n); pass++; }
  catch (e) { console.log('❌', n, '\n   ', e.message); fail++; }
};
const wait = (ms = 30) => new Promise((r) => setTimeout(r, ms));

/* ★ 진짜 진입점부터 — 모듈 평가 순서를 실제 브라우저와 같게 맞춘다 */
await import(`${F}/main.js`);
const S = await import(`${F}/style/static/js/search.js`);
const RH = await import(`${F}/trend/static/js/render_helpers.js`);
const D = await import(`${F}/trend/static/js/dispatch.js`);
await wait();   // main.js 가 trBuild() → fsLoadDictionary() 를 이미 태웠다

const FIDX_OF = (f, label) => S.FIDX.filter((o) => o.f === f && o.label === label);
const colBtns = (lv) => Array.from(document.querySelectorAll('#fsC' + lv + ' button[data-fv]'));
const labelOf = (b) => b.querySelector('.fsOptTx').textContent;
const countOf = (b) => { const i = b.querySelector('i'); return i ? Number(i.textContent) : null; };
const hintOf = (lv) => (document.querySelector('#fsC' + lv + ' .hint') || {}).textContent || '';
const click = (el) => el.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
const stateText = () => document.getElementById('fsState').textContent;

/* ══ ① 사전 ══════════════════════════════════════════════════ */
await t('키르시·미니멀은 박아 둔 목록에 없다 (사전이 필요한 이유)', () => {
  for (const q of ['키르시', '엄브로', '미니멀', '롱 슬리브', '레이온', '블랙']) {
    const hard = S.FIDX.filter((o) => o.label === q && o.src !== 'db');
    assert.equal(hard.length, 0, q + ' 이 원래부터 박혀 있으면 이 시험은 무의미하다');
  }
});

await t('★ 사전을 한 번만 받아서 없던 말만 더한다 (아이템 → 종류 칸)', () => {
  assert.equal(dictCalls, 1, '사전을 ' + dictCalls + '번 불렀다');
  const axis = { 아이템: '종류' };
  for (const row of DICT) {
    const f = axis[row.facet] || row.facet;
    assert.equal(FIDX_OF(f, row.label).length, 1, row.label + ' 이 ' + f + ' 축에 한 줄이어야 한다');
  }
});

await t('★ 사전에만 있던 말이 이제 검색된다', () => {
  for (const [q, f] of [['키르시','브랜드'], ['엄브로','브랜드'], ['미니멀','스타일']]) {
    const hit = S.fsMatch(q);
    assert.ok(hit.length, q + ' 이 안 걸린다');
    assert.equal(hit[0].f, f, q + ' 축이 ' + hit[0].f);
  }
  assert.equal(FIDX_OF('브랜드', '키르시')[0].src, 'db', '어디서 온 말인지 남아야 한다');
});

await t('박아 둔 말은 사전에 덮이지 않고, 두 줄로 늘지 않는다', () => {
  const b = FIDX_OF('스타일', '발레코어');
  assert.equal(b.length, 1);
  assert.equal(b[0].src, undefined);
});

await t('다시 불러도 서버를 또 부르지 않는다', async () => {
  const before = S.FIDX.length;
  const r2 = await S.fsLoadDictionary();
  assert.equal(r2.cached, true, JSON.stringify(r2));
  assert.equal(dictCalls, 1);
  assert.equal(S.FIDX.length, before, '항목이 늘어나면 중복이다');
});

/* ══ ② ③ STYLE 칸 — 핵심 10종 ═══════════════════════════════ */
D.trRender('resale');       // 공통 세부 검색이 쓰이는 탭 (할인률은 상품 전용 후보)
S.fsBuild();

await t('★ 서버 후보: STYLE 칸은 핵심 10종만, 0건도 0 으로 남는다', async () => {
  facetMode = 'ok'; S.fsReset();
  await S.fsLoadFacets();
  const names = colBtns(0).map(labelOf);
  assert.deepEqual([...names].sort(), [...CORE].sort(), names.join(','));
  const bike = colBtns(0).find((b) => labelOf(b) === '바이크코어');
  assert.equal(countOf(bike), 0, '0건이어도 숫자 0 이 보여야 한다');
  assert.ok(bike.classList.contains('zero'), '0건은 흐리게 구분된다');
  assert.equal(countOf(colBtns(0).find((b) => labelOf(b) === '고프코어')), 122);
  assert.ok(!names.includes('캐주얼') && !names.includes('발레코어'), '핵심이 아닌 스타일이 섞였다');
  assert.equal(stateText(), '', '정상 응답이면 불필요한 상태 문구를 띄우지 않는다');
});

await t('★ 서버를 못 봐도 STYLE 칸은 같은 10종이고, 그 사실을 적는다', async () => {
  facetMode = 'down'; S.fsReset();
  await S.fsLoadFacets();
  const names = colBtns(0).map(labelOf);
  /* 2026-09-23 부터 세부 검색의 모든 칸은 가나다순 (search.js 칸 정렬) */
  assert.deepEqual(names, [...CORE].sort((a,b)=>a.localeCompare(b,'ko-KR')), names.join(','));
  assert.ok(colBtns(0).every((b) => countOf(b) === null), '서버가 세지 않은 숫자를 만들면 안 된다');
  assert.ok(!names.includes('미니멀'), '사전 스타일을 섞으면 안 된다');
  assert.match(stateText(), /박아 둔 목록/);
  assert.ok(S.FS_CORE_STYLES.length === 10);
});

/* ══ ④ 네 칸은 독립 필터 ═════════════════════════════════════ */
await t('스타일을 고르면 칩이 생기고, 박아 둔 계층 안에서 카테고리가 좁혀진다', async () => {
  facetMode = 'down'; S.fsReset();
  click(colBtns(0).find((b) => labelOf(b) === '고프코어'));
  assert.deepEqual(S.FS.pick['스타일'], ['고프코어']);
  assert.ok(document.getElementById('fsPicked').textContent.includes('고프코어'));
  const kinds = colBtns(2).map(labelOf);
  assert.deepEqual(kinds, ['카고 팬츠', '테크 셸', '트레일 러너', '플리스'], kinds.join(','));   /* 가나다순 */
  await wait(250);   // 뒤따라 도는 후보 요청이 상태를 덮어도 칩은 그대로여야 한다
  assert.deepEqual(S.FS.pick['스타일'], ['고프코어']);
});

await t('★ 스타일은 한 번에 하나만 선택되고 새 선택이 이전 선택을 바꾼다', async () => {
  facetMode = 'ok'; S.fsReset(); await S.fsLoadFacets();
  click(colBtns(0).find((b) => labelOf(b) === '고프코어'));
  click(colBtns(0).find((b) => labelOf(b) === '아메카지'));
  assert.deepEqual(S.FS.pick['스타일'], ['아메카지']);
  assert.equal(document.querySelectorAll('#fsPicked [data-drop^="스타일|"]').length, 1);
});

await t('계층이 없는 핵심 스타일(바이크코어)을 고르면 "후보 없음" 을 사실대로 적는다', async () => {
  facetMode = 'down'; S.fsReset(); await S.fsLoadFacets();
  click(colBtns(0).find((b) => labelOf(b) === '바이크코어'));
  assert.equal(colBtns(1).length, 0);
  assert.match(hintOf(1), /아직 후보가 없습니다/);
  await wait(250);
});

await t('칸끼리 겹쳐 걸리고, 칩 하나만 뗄 수 있다', async () => {
  facetMode = 'ok'; S.fsReset(); await S.fsLoadFacets();
  click(colBtns(0).find((b) => labelOf(b) === '고프코어'));
  click(colBtns(1).find((b) => labelOf(b) === '살로몬'));
  assert.deepEqual(S.FS.pick, { 스타일: ['고프코어'], 브랜드: ['살로몬'] });
  const x = document.querySelector('#fsPicked [data-drop="스타일|고프코어"]');
  assert.ok(x, '뗄 단추가 있어야 한다');
  click(x);
  assert.deepEqual(S.FS.pick, { 브랜드: ['살로몬'] }, '스타일만 빠져야 한다');
  await wait(250);
});

/* ══ ⑤ 속성 ═════════════════════════════════════════════════ */
await t('★ 검색창에서 색을 고르면 속성 조건으로 걸리고 칩이 남는다', () => {
  S.fsReset();
  const hit = S.fsMatch('블랙');
  assert.ok(hit.length && hit[0].f === '색', JSON.stringify(hit[0]));
  const inp = document.getElementById('fsInput');
  inp.value = '블랙';
  inp.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  inp.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  assert.deepEqual(S.FS.pick['색'], ['블랙'], JSON.stringify(S.FS.pick));
  assert.ok(document.getElementById('fsChips').textContent.includes('블랙'));
});

await t('★ 조회 대상 — 없으면 빈 문자열, 속성만 있어도 대상, 더 구체적인 것이 이긴다', () => {
  S.FS.pick = {};
  assert.equal(RH.fsItem(), '');
  S.FS.pick = { 색: ['블랙'] };
  assert.equal(RH.fsItem(), '블랙');
  S.FS.pick = { 색: ['블랙'], 브랜드: ['키르시'] };
  assert.equal(RH.fsItem(), '키르시');
});

await t('★ 화면 제목은 대표 용어 하나가 아니라 고른 검색 조건 전체를 적는다', () => {
  S.FS.pick = { 스타일: ['아메카지'], 종류: ['재킷'] };
  assert.equal(RH.fsSelectionLabel(), '아메카지 · 재킷');
});

await t('★ 리세일·수명주기도 할인률과 같은 검색 축 순서와 이름을 쓴다', () => {
  for (const id of ['resale', 'life']) {
    D.trRender(id);
    assert.deepEqual(S.getFsCols().map(c => [c.head, c.param]), [
      ['STYLE', 'style'], ['브랜드', 'brand'], ['카테고리', 'kind'], ['상품명', 'item'],
    ]);
  }
});

/* ══ ⑥ 할인률은 개별 상품 ID, 리세일·수명주기는 기존 사전 검색 ══ */
await t('★ 할인률은 브랜드 필터만으로 조회하지 않고 상품 ID를 기다린다', async () => {
  S.FS.pick = { 브랜드: ['엄브로'] };
  S.FS.stockItem = null;
  asked = [];
  D.trRender('stock');
  assert.match(document.getElementById('trBody').textContent, /할인률을 볼 상품을 고르세요/);
  assert.ok(!asked.some(u => u.includes('/api/discount?')), '상품 선택 전 지표를 요청하지 않는다');
  S.fsStockSelect({id:17,label:'엄브로 상품',thumb:'https://img.example/17.jpg'});
  D.trRender('stock');
  assert.ok(asked.some(u => u.includes('/api/discount?source_id=17')));
});
/* 나머지 두 탭의 사전 검색 방식은 바뀌지 않는다. */
for (const [id, name, brand] of [['resale', '리세일', '엄브로'], ['life', '수명주기', '엄브로']]) {
  await t(`★ ${name} — 사전 브랜드를 고르면 빈 화면을 벗어나 조회를 시작한다`, async () => {
    S.FS.pick = {};
    D.trRender(id);
    assert.match(document.getElementById('trBody').textContent, /먼저 볼 대상을 고르세요/);

    asked = [];
    S.FS.pick = { 브랜드: [brand] };
    D.trRender(id);
    const body = document.getElementById('trBody').textContent;
    assert.ok(!/먼저 볼 대상을 고르세요/.test(body), '고른 뒤에도 빈 화면이다');
    const api = { stock: '/api/discount', resale: '/api/resale', life: '/api/lifecycle' }[id];
    assert.ok(asked.some((u) => u.includes(api) && u.includes('brand=' + brand)),
      api + ' 를 고른 조건으로 불러야 한다: ' + asked.join(' | '));
    await wait(40);
    assert.match(document.getElementById('trBody').textContent, /측정 불가|적재 전입니다/,
      '서버가 비었다고 하면 그 사유를 그려야 한다');
  });
}

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail ? 1 : 0);
