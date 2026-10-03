/* 사진 질문이 챗봇 서버에 닿지도 못하고 멈추던 문제 (2026-10-02).
 *   원인: 버셀 중계(api/_v1/chat.js)의 본문 상한이 200,000자라, 1280px 사진 한 장만
 *         붙어도 넘었다. 게다가 거절 안내를 { text } 로 보내 화면(delta 를 읽음)에는
 *         빈 말풍선으로 보였다.
 *   돌리는 법:  node tests/chat_relay_image.test.mjs
 */
import assert from 'node:assert/strict';
import { Readable } from 'node:stream';

const { default: chat, MAX_BODY_BYTES } = await import('../api/_v1/chat.js');

function fakeReq(body) {
  const r = Readable.from([Buffer.from(body)]);
  r.method = 'POST';
  return r;
}
function fakeRes() {
  const out = { chunks: [], headers: {}, ended: false, statusCode: 200 };
  out.setHeader = (k, v) => { out.headers[k] = v; };
  out.write = (c) => { out.chunks.push(String(c)); return true; };
  out.end = (c) => { if (c) out.chunks.push(String(c)); out.ended = true; };
  return out;
}
function events(res) {
  return res.chunks.join('').split('\n\n').filter(Boolean).map((blk) => {
    const ev = (blk.match(/^event: (.+)$/m) || [])[1];
    const data = JSON.parse((blk.match(/^data: (.+)$/m) || [])[1] || 'null');
    return { ev, data };
  });
}

let passed = 0, failed = 0;
async function t(name, fn) {
  try { await fn(); passed++; console.log('✅ ' + name); }
  catch (e) { failed++; console.log('❌ ' + name + '\n   ' + (e && e.stack || e)); }
}

const photo = 'data:image/jpeg;base64,' + 'A'.repeat(420_000);   // 1280px JPEG 한 장 크기

await t('사진 한 장(약 42만 자)이 붙은 질문도 챗봇 서버로 그대로 넘긴다', async () => {
  process.env.CHAT_BACKEND_URL = 'http://chat.test';
  let sent = null;
  globalThis.fetch = async (url, init) => {
    sent = { url, body: init.body };
    const enc = new TextEncoder();
    const stream = new ReadableStream({ start(c) {
      c.enqueue(enc.encode('event: done\ndata: {"ok":true}\n\n')); c.close(); } });
    return { ok: true, status: 200, body: stream };
  };
  const body = JSON.stringify({ question: '이거 어때?', images: [photo] });
  const res = fakeRes();
  await chat(fakeReq(body), res);
  assert.ok(sent, '챗봇 서버로 보내지 않았다');
  assert.equal(sent.url, 'http://chat.test/v1/chat');
  assert.equal(JSON.parse(sent.body).images[0].length, photo.length);
  assert.ok(res.ended);
});

await t('상한을 넘으면 사유를 error 이벤트로 알린다 — 빈 말풍선이 아니다', async () => {
  process.env.CHAT_BACKEND_URL = 'http://chat.test';
  let called = false;
  globalThis.fetch = async () => { called = true; throw new Error('불리면 안 된다'); };
  const big = 'x'.repeat(MAX_BODY_BYTES + 10);
  const res = fakeRes();
  await chat(fakeReq(JSON.stringify({ question: 'q', images: ['data:image/jpeg;base64,' + big] })), res);
  assert.equal(called, false);
  const evs = events(res);
  const err = evs.find((e) => e.ev === 'error');
  assert.ok(err && /사진/.test(err.data.message), JSON.stringify(evs));
  assert.equal(err.data.reason, 'IMAGE_TOO_LARGE');
  assert.equal(evs.at(-1).ev, 'done');
});

await t('서버 미연결 안내는 화면이 읽는 delta 로 보낸다', async () => {
  delete process.env.CHAT_BACKEND_URL;
  const res = fakeRes();
  await chat(fakeReq('{"question":"q"}'), res);
  const text = events(res).find((e) => e.ev === 'text');
  assert.ok(text && /챗봇 서버/.test(text.data.delta), JSON.stringify(text));
});

console.log(`\n${passed}개 통과 · ${failed}개 실패`);
if (failed) process.exit(1);
