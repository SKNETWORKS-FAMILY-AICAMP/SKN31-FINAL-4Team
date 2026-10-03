/* POST /api/v1/feedback — 답변 하나에 대한 도움됨/아쉬움을 챗봇 서버로 넘긴다.
 * 무엇이 자주 틀리는지 알 방법이 이것뿐이다(2026-09-13). */

import { clientIp } from '../_lib/client_ip.js';

export const config = { runtime: 'nodejs', maxDuration: 30 };

export default async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, {
    ok: false, message: 'POST 요청만 지원합니다.',
  });

  const backend = (process.env.CHAT_BACKEND_URL || '').replace(/\/+$/, '');
  if (!backend) return json(res, 503, {
    ok: false, message: '서버 주소가 설정되지 않았습니다.',
  });

  let body;
  try {
    body = await readBody(req);
  } catch (error) {
    return json(res, error && error.code === 'TOO_LARGE' ? 413 : 400, {
      ok: false,
      message: error && error.code === 'TOO_LARGE'
        ? '보낸 내용이 너무 큽니다.'
        : '보낸 내용을 읽지 못했습니다.',
    });
  }

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (process.env.CHAT_BACKEND_TOKEN) {
      headers['X-FEEDiT-Token'] = process.env.CHAT_BACKEND_TOKEN;
    }
    { const ip = clientIp(req); if (ip && process.env.CHAT_BACKEND_TOKEN) headers['X-FEEDiT-Client-IP'] = ip; }
    const forwarded = req.headers && (req.headers['x-forwarded-for'] || req.headers['x-real-ip']);
    if (forwarded) headers['X-Forwarded-For'] = String(forwarded).split(',')[0].trim();

    const upstream = await fetch(backend + '/v1/feedback', {
      method: 'POST', headers, body,
    });
    const raw = await upstream.text();
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      return json(res, 502, {
        ok: false,
        message: `서버가 올바른 응답을 보내지 않았습니다 (HTTP ${upstream.status}).`,
      });
    }
    return json(res, upstream.status, payload);
  } catch (error) {
    return json(res, 502, {
      ok: false,
      message: `서버에 연결하지 못했습니다: ${String(error && error.message || error).slice(0, 120)}`,
    });
  }
}

function readBody(req) {
  if (req.body != null) {
    const value = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    if (Buffer.byteLength(value) > 4_000_000) return Promise.reject(tooLarge());
    return Promise.resolve(value || '{}');
  }
  return new Promise((resolve, reject) => {
    let value = '';
    req.on('data', chunk => {
      value += chunk;
      if (Buffer.byteLength(value) > 4_000_000) reject(tooLarge());
    });
    req.on('end', () => resolve(value || '{}'));
    req.on('error', reject);
  });
}

function tooLarge() {
  const error = new Error('request too large');
  error.code = 'TOO_LARGE';
  return error;
}

function json(res, status, payload) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(payload));
}
