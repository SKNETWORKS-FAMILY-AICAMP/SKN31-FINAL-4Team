"""상품 사진 주소를 온전하게 만든다.

왜 필요한가 (2026-09-22 실측) —
  `commerce.product_source.thumbnail_url` 72,352건 중 **27,424건이 호스트가 없는
  상대 경로**다(`thumbnails/images/goods_img/...`). 수집기가 무신사 경로를 베이스
  없이 적어 둔 자리다. 그대로 내보내면 브라우저가 우리 도메인 기준으로 읽어
  상품 카드 사진이 뜨지 않는다 — 전체의 38%다.

    image.msscdn.net                 24,251
    cf.product-image.s3.zigzag.kr    18,268
    d3ha2047wt6x28.cloudfront.net     1,353
    kream-phinf.pstatic.net             655
    (호스트 없음 · 상대 경로)         27,424

  ★ 기준은 수집기가 원본이다 — backend/collection/musinsa/constants.py 의
    IMAGE_BASE_URL. 여기서 새로 정하지 않는다.
  ★ 모르는 모양에는 아무 호스트도 붙이지 않는다. 앞에 우리 도메인이나 남의
    CDN 을 붙이면 엉뚱한 사진이 상품 카드에 걸린다 — 빈 값이 낫다.

같은 규칙이 두 곳에 더 있다. 고칠 때 같이 고친다:
  · frontend/api/_lib/image.js   — Vercel 함수(배포된 화면이 실제로 쓰는 길)
  · ChatBot/app/fit.py           — 챗봇이 코디에 담을 상품을 고를 때
"""
from __future__ import annotations

# 소스 코드(collection/*/constants.py SOURCE_CODE) → 사진 베이스 주소
IMAGE_BASE = {
    "MUSINSA": "https://image.msscdn.net",
    "MUSINSA_USED": "https://image.msscdn.net",
}
# 상대 경로로 인정할 모양. 이 밖은 주소로 만들지 않는다.
RELATIVE_HINTS = ("thumbnails/images/", "images/goods_img/", "goods_img/")


def absolute_image_url(url: str | None, source: str = "") -> str | None:
    """상대 경로면 베이스를 붙여 돌려준다. 못 만들면 None (빈 자리로 남긴다)."""
    text = str(url or "").strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("//"):
        return "https:" + text
    path = text.lstrip("/")
    if not path.startswith(RELATIVE_HINTS):
        return None
    base = IMAGE_BASE.get(str(source or "").upper())
    if not base:
        # 소스를 모를 때는 모양으로 가른다 — goods_img 는 무신사 경로다.
        base = IMAGE_BASE["MUSINSA"] if "goods_img/" in path else ""
    return f"{base}/{path}" if base else None
