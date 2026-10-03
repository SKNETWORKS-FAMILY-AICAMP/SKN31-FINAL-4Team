/* 상품 사진 주소를 온전하게 만든다.
 *
 * 왜 필요한가 (2026-09-22 실측) —
 *   commerce.product_source.thumbnail_url 72,352건 중 27,424건이 호스트 없는
 *   상대 경로다(thumbnails/images/goods_img/...). 수집기가 무신사 경로를 베이스
 *   없이 적어 둔 자리다. 그대로 내보내면 브라우저가 우리 도메인 기준으로 읽어
 *   상품 카드 사진이 안 뜬다 — 전체의 38%다.
 *
 *   ★ 기준은 수집기가 원본이다(backend/collection/musinsa/constants.py
 *     IMAGE_BASE_URL). 여기서 새로 정하지 않는다.
 *   ★ 모르는 모양에는 아무 호스트도 붙이지 않는다 — 엉뚱한 사진이 걸리는 것보다
 *     빈 자리가 낫다.
 *
 * 같은 규칙이 두 곳에 더 있다. 고칠 때 같이 고친다:
 *   · backend/apps/api/images.py  — Django (로컬·중계 경로)
 *   · ChatBot/app/fit.py          — 챗봇이 코디에 담을 상품을 고를 때
 */

/* 소스 코드(수집기 constants 의 SOURCE_CODE) → 사진 베이스 주소 */
const IMAGE_BASE = {
  MUSINSA: 'https://image.msscdn.net',
  MUSINSA_USED: 'https://image.msscdn.net',
};
/* 상대 경로로 인정할 모양. 이 밖은 주소로 만들지 않는다. */
const RELATIVE_HINTS = ['thumbnails/images/', 'images/goods_img/', 'goods_img/'];

export function absoluteImageUrl(url, source) {
  const text = String(url == null ? '' : url).trim();
  if (!text) return null;
  if (/^https?:\/\//i.test(text)) return text;
  if (text.startsWith('//')) return 'https:' + text;
  const path = text.replace(/^\/+/, '');
  if (!RELATIVE_HINTS.some((hint) => path.startsWith(hint))) return null;
  const base = IMAGE_BASE[String(source || '').toUpperCase()]
    /* 소스를 모를 때는 모양으로 가른다 — goods_img 는 무신사 경로다. */
    || (path.includes('goods_img/') ? IMAGE_BASE.MUSINSA : '');
  return base ? base + '/' + path : null;
}
