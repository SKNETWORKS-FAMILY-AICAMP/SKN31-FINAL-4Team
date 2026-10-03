/* 손님 IP — 챗봇 서버의 분당 횟수 제한을 사람마다 세게 한다 (2026-10-02).
 *
 * 왜 따로 보내나: 버셀 함수가 챗봇 서버를 부르면, 서버 앞 nginx 는 X-Forwarded-For 를
 * '버셀 함수의 IP' 로 덮어쓴다. 그래서 30명이 동시에 쓰면 전원이 IP 몇 개로 묶여
 * 분당 20회 제한을 같이 나눠 썼다(기수 테스트의 '질문이 너무 잦습니다' · 렉).
 * 버셀이 받은 손님 IP 를 별도 머리글로 넘긴다. 챗봇 서버는 공유 토큰이 맞는 요청에서만
 * 이 머리글을 믿는다 — 밖에서 지어 보내도 토큰이 없으면 무시된다(server.py _client_ip).
 */
export function clientIp(req) {
  const h = (req && req.headers) || {};
  const first = String(h['x-forwarded-for'] || '').split(',')[0].trim();
  const ip = first || String(h['x-real-ip'] || '').trim();
  return /^[0-9a-fA-F:.]{3,45}$/.test(ip) ? ip : '';
}
