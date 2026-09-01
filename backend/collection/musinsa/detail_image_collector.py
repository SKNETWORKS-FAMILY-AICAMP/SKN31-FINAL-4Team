from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright


OCR_SECTIONS = {
    "INTRO",
    "FABRIC",
    "DETAIL",
}


SECTION_RULES = {
    "FABRIC": [
        "원단",
        "소재",
        "fabric",
        "material",
        "materials",
        "fabric info",
    ],

    "DETAIL": [
        "디테일",
        "detail",
        "details",
        "product detail",
    ],

    "INTRO": [
        "인트로",
        "intro",
        "상품설명",
        "description",
        "product info",
        "productinfo",
        "information",
    ],

    "MODEL": [
        "모델컷",
        "모델",
        "착용",
        "착장",
        "wearing",
        "model",
        "lookbook",
        "look book",
    ],

    "CARE": [
        "세탁",
        "washing",
        "laundry",
        "care",
    ],

    "NOTICE": [
        "공지",
        "notice",
        "guide",
    ],

    "BRAND": [
        "브랜드홍보",
        "brand story",
        "brandstory",
    ],

    "INFLUENCER": [
        "인플루언서",
        "influencer",
    ],
}


class MusinsaDetailImageCollector:

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 60_000,
        scroll_wait_ms: int = 700,
        max_scrolls: int = 40,
    ):
        self.headless = headless
        self.timeout = timeout
        self.scroll_wait_ms = scroll_wait_ms
        self.max_scrolls = max_scrolls

    # --------------------------------------------------
    # Scroll
    # --------------------------------------------------

    def _scroll_to_bottom(
        self,
        page,
    ) -> None:

        previous_height = 0

        for _ in range(
            self.max_scrolls
        ):

            current_height = (
                page.evaluate(
                    "document.body.scrollHeight"
                )
            )

            if (
                current_height
                == previous_height
            ):
                break

            previous_height = (
                current_height
            )

            page.evaluate(
                """
                window.scrollTo(
                    0,
                    document.body.scrollHeight
                )
                """
            )

            page.wait_for_timeout(
                self.scroll_wait_ms
            )

    # --------------------------------------------------
    # DOM image collection
    # --------------------------------------------------

    def _collect_all_images(
        self,
        page,
    ) -> list[dict]:

        return page.locator(
            "img"
        ).evaluate_all(
            """
            imgs => imgs.map((img, index) => {

                const rect =
                    img.getBoundingClientRect();

                return {
                    index,

                    src:
                        img.currentSrc ||
                        img.src ||
                        img.getAttribute("data-src") ||
                        img.getAttribute("data-original") ||
                        "",

                    alt:
                        img.alt || "",

                    width:
                        img.naturalWidth || 0,

                    height:
                        img.naturalHeight || 0,

                    renderedWidth:
                        rect.width || 0,

                    renderedHeight:
                        rect.height || 0,

                    y:
                        rect.top +
                        window.scrollY
                };
            })
            """
        )

    # --------------------------------------------------
    # URL decode
    # --------------------------------------------------

    def _decode_image_metadata(
        self,
        image_url: str,
    ) -> dict:

        decoded_url = unquote(
            image_url
        )

        parsed = urlparse(
            decoded_url
        )

        filename = PurePosixPath(
            parsed.path
        ).name

        return {
            "image_url": image_url,
            "decoded_url": decoded_url,
            "filename": filename,
        }

    # --------------------------------------------------
    # Section classifier
    # --------------------------------------------------

    def _classify_section(
        self,
        filename: str,
        alt: str = "",
    ) -> str:

        text = (
            f"{filename} {alt}"
            .lower()
            .replace("_", " ")
            .replace("-", " ")
        )

        for (
            section,
            keywords,
        ) in SECTION_RULES.items():

            if any(
                keyword.lower()
                in text
                for keyword
                in keywords
            ):
                return section

        return "UNKNOWN"

    # --------------------------------------------------
    # Noise filtering
    # --------------------------------------------------

    def _is_noise_image(
        self,
        image: dict,
    ) -> bool:

        src = (
            image.get(
                "src",
                "",
            )
            or ""
        ).lower()

        noise_patterns = [
            "/data/estimate/",
            "/snap/",
            "/community/",
            "/cms/",
            "/mfile_s01/_simbols/",
            "/mfile_s01/_brand/",
            "size_type",
            "goodsdetail/banner",
        ]

        return any(
            pattern in src
            for pattern
            in noise_patterns
        )

    def _is_gallery_image(
        self,
        image: dict,
    ) -> bool:

        src = (
            image.get(
                "src",
                "",
            )
            or ""
        ).lower()

        return (
            "/goods_img/" in src
            or "/prd_img/" in src
        )

    # --------------------------------------------------
    # Candidate filtering
    # --------------------------------------------------

    def _is_detail_candidate(
        self,
        image: dict,
    ) -> bool:

        if self._is_noise_image(
            image
        ):
            return False

        if self._is_gallery_image(
            image
        ):
            return False

        width = image.get(
            "width",
            0,
        )

        height = image.get(
            "height",
            0,
        )

        rendered_width = (
            image.get(
                "renderedWidth",
                0,
            )
        )

        if width < 400:
            return False

        if height < 300:
            return False

        if rendered_width < 400:
            return False

        return True

    # --------------------------------------------------
    # Fallback OCR candidate
    # --------------------------------------------------

    def _select_fallback_ocr_images(
        self,
        detail_images: list[dict],
        max_images: int = 3,
    ) -> list[dict]:

        candidates = []

        for image in detail_images:

            width = image.get(
                "width",
                0,
            )

            height = image.get(
                "height",
                0,
            )

            # 너무 작은 상세 이미지 제외
            if width < 800:
                continue

            if height < 1000:
                continue

            # 모델컷/룩북일 가능성이 높은
            # 지나치게 긴 이미지는 일단 제외
            if height > 12_000:
                continue

            candidate = dict(
                image
            )

            candidate[
                "original_section_type"
            ] = candidate.get(
                "section_type",
                "UNKNOWN",
            )

            # SectionOCR에서 INTRO 정책 사용
            candidate[
                "section_type"
            ] = "INTRO"

            candidate[
                "fallback_selected"
            ] = True

            candidate[
                "ocr_required"
            ] = True

            candidates.append(
                candidate
            )

        candidates.sort(
            key=lambda item: (
                item.get(
                    "y",
                    0,
                )
            )
        )

        return candidates[
            :max_images
        ]

    # --------------------------------------------------
    # Public
    # --------------------------------------------------

    def collect(
        self,
        product_url: str,
    ) -> dict:

        print(
            f"[MusinsaDetailImageCollector] "
            f"open: {product_url}"
        )

        with sync_playwright() as p:

            browser = (
                p.chromium.launch(
                    headless=self.headless
                )
            )

            page = browser.new_page(
                viewport={
                    "width": 1440,
                    "height": 1600,
                }
            )

            try:

                page.goto(
                    product_url,
                    wait_until=(
                        "domcontentloaded"
                    ),
                    timeout=self.timeout,
                )

                page.wait_for_timeout(
                    2000
                )

                self._scroll_to_bottom(
                    page
                )

                page.wait_for_timeout(
                    1200
                )

                all_images = (
                    self._collect_all_images(
                        page
                    )
                )

            finally:
                browser.close()

        detail_images = []

        seen = set()

        for image in all_images:

            src = (
                image.get(
                    "src",
                    "",
                )
                or ""
            ).strip()

            if not src:
                continue

            if src in seen:
                continue

            seen.add(
                src
            )

            if not (
                self._is_detail_candidate(
                    image
                )
            ):
                continue

            metadata = (
                self._decode_image_metadata(
                    src
                )
            )

            section_type = (
                self._classify_section(
                    filename=metadata[
                        "filename"
                    ],

                    alt=image.get(
                        "alt",
                        "",
                    ),
                )
            )

            detail_images.append(
                {
                    **image,
                    **metadata,

                    "section_type": (
                        section_type
                    ),

                    "ocr_required": (
                        section_type
                        in OCR_SECTIONS
                    ),

                    "fallback_selected": (
                        False
                    ),
                }
            )

        # 페이지 위 -> 아래 순서
        detail_images.sort(
            key=lambda item: (
                item.get(
                    "y",
                    0,
                )
            )
        )

        # --------------------------------------------------
        # Normal OCR targets
        # --------------------------------------------------

        ocr_images = [
            image
            for image
            in detail_images
            if image[
                "ocr_required"
            ]
        ]

        # --------------------------------------------------
        # Debug
        # --------------------------------------------------

        print(
            "\n"
            "[MusinsaDetailImageCollector] "
            "DETAIL IMAGES"
        )

        for i, image in enumerate(
            detail_images
        ):

            print(
                f"{i:02d} | "
                f"{image['section_type']:10s} | "
                f"{image.get('width', 0)}x"
                f"{image.get('height', 0)} | "
                f"{image.get('filename', '')}"
            )

        # --------------------------------------------------
        # Fallback
        # --------------------------------------------------

        if not ocr_images:

            print(
                "\n"
                "[MusinsaDetailImageCollector] "
                "NO DECODED OCR SECTION"
            )

            print(
                "[MusinsaDetailImageCollector] "
                "fallback candidate selection..."
            )

            ocr_images = (
                self._select_fallback_ocr_images(
                    detail_images,
                    max_images=3,
                )
            )

        # --------------------------------------------------
        # OCR target log
        # --------------------------------------------------

        print(
            "\n"
            "[MusinsaDetailImageCollector] "
            f"OCR TARGETS="
            f"{len(ocr_images)}"
        )

        for image in ocr_images:

            fallback = (
                " FALLBACK"
                if image.get(
                    "fallback_selected"
                )
                else ""
            )

            print(
                f" -> "
                f"[{image['section_type']}]"
                f"{fallback} | "
                f"{image.get('width', 0)}x"
                f"{image.get('height', 0)} | "
                f"{image.get('filename', '')}"
            )

        return {
            "product_url": (
                product_url
            ),

            "detail_image_count": (
                len(
                    detail_images
                )
            ),

            "ocr_image_count": (
                len(
                    ocr_images
                )
            ),

            "detail_images": (
                detail_images
            ),

            "ocr_images": (
                ocr_images
            ),
        }