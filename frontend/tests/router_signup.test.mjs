/* 로그인 화면의 회원가입 링크가 인트로로 되돌아가지 않고 가입 화면을 연다.
 * 실제 index.html 과 라우터를 jsdom 에서 함께 실행해 SPA 전환을 검증한다. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root = new URL('..', import.meta.url).href.replace(/\/$/, '');
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost:5173/' });

for(const key of [
  'window','document','Element','SVGElement','getComputedStyle','Node','HTMLElement',
  'KeyboardEvent','MouseEvent','CustomEvent'
]) globalThis[key] = key === 'window' ? dom.window : dom.window[key];

/* notify.js 가 본문을 기다릴 때 쓴다 — jsdom 전역에 없어서 이 시험들이 통째로 죽어 있었다 */
globalThis.MutationObserver=dom.window.MutationObserver||class{observe(){} disconnect(){} takeRecords(){return []}};
globalThis.requestAnimationFrame = fn => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = id => clearTimeout(id);
globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);
globalThis.location = dom.window.location;
globalThis.history = dom.window.history;
globalThis.localStorage = dom.window.localStorage;
globalThis.innerWidth = 1440;
globalThis.innerHeight = 900;
globalThis.matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
globalThis.scrollTo = () => {};
globalThis.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
globalThis.fetch = async () => { throw new Error('이 테스트에서는 네트워크를 사용하지 않습니다.'); };

await import(`${root}/main.js`);
const router = await import(`${root}/app_shell/static/js/router.js`);

document.getElementById('jumpBtn').click();
router.goView('login');

const signupLink = document.querySelector('#v-login a[data-v="signup"]');
const click = new dom.window.MouseEvent('click', { bubbles:true, cancelable:true });
signupLink.dispatchEvent(click);

assert.equal(click.defaultPrevented, true, 'href="#" 기본 이동을 취소해야 한다');
assert.equal(router.curView, 'signup', '현재 화면이 회원가입이어야 한다');
assert.ok(document.getElementById('v-signup').classList.contains('on'), '회원가입 화면이 보여야 한다');
assert.ok(!document.getElementById('v-login').classList.contains('on'), '로그인 화면은 닫혀야 한다');
assert.ok(document.body.classList.contains('mainmode'), '인트로 화면으로 빠지면 안 된다');

console.log('✅ 로그인 → 회원가입 SPA 경로가 정상입니다.');
process.exit(0);
