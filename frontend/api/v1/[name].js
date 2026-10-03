/* /api/v1/chat · /api/v1/feedback · /api/v1/fit-classify · /api/v1/health · /api/v1/magazines
 *
 * 챗봇 쪽 네 주소를 **함수 하나**로 받는다.
 * 버셀 Hobby 요금제는 배포 하나에 서버리스 함수가 12개까지라, 파일마다 따로 두면
 * 13개가 되어 배포가 막힌다(2026-09-17). 실제 처리 코드는 api/_v1/ 에 그대로 있다.
 * 밑줄(_)로 시작하는 폴더는 버셀이 함수로 세지 않는다.
 *
 * virtual-fitting 은 오래 걸려(maxDuration 300) 따로 둔다.
 * 같은 폴더에서는 정적 파일 이름(virtual-fitting.js)이 [name] 보다 먼저 잡힌다.
 */
import chat from '../_v1/chat.js';
import feedback from '../_v1/feedback.js';
import fitClassify from '../_v1/fit-classify.js';
import health from '../_v1/health.js';
import magazines from '../_v1/magazines.js';

const ROUTES = { chat, feedback, 'fit-classify': fitClassify, health, magazines };

/* ★ 챗봇 답변은 챗봇 쪽 시간 예산(최대 45+15초)보다 길게 열어 둔다 (2026-09-18).
     예전 30초는 링크 질문 예산(33초)보다도 짧아, 끝나기 전에 버셀이 끊을 수 있었다.
     vercel.json 의 같은 값과 맞춘다. */
export const config = { runtime: 'nodejs', maxDuration: 120 };

export default async function handler(req, res) {
  const url = new URL(req.url, 'http://x');
  const name = url.pathname.replace(/^\/api\/v1\//, '').split('/')[0];
  const route = ROUTES[name];
  if (!route) {
    res.statusCode = 404;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    return res.end(JSON.stringify({ status: 'error', reason: `없는 주소입니다: /api/v1/${name}`, data: null }));
  }
  return route(req, res);
}
