from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = (
    "https://www.musinsa.com/main/musinsa/ranking"
    "?storeCode=musinsa"
    "&sectionId=199"
    "&contentsId="
    "&categoryCode=000"
    "&subPan=product"
)

OUTPUT_PATH = Path(__file__).resolve().parent / "constants_generated.py"


# ============================================================
# Browser
# ============================================================


def create_driver():

    options = Options()

    options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")

    options.add_argument(
        "--user-agent="
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    )

    return webdriver.Chrome(options=options)


def wait_page(driver):

    WebDriverWait(
        driver,
        15,
    ).until(lambda d: d.execute_script("return document.readyState") == "complete")

    # React 렌더링 대기
    time.sleep(2)


# ============================================================
# category id 정규화
# ============================================================


def normalize_category_id(
    raw_value: str | None,
) -> str | None:
    """
    예:

    001|001010
        -> 001010

    002|002001
        -> 002001

    001000
        -> 001000
    """

    if not raw_value:
        return None

    raw_value = raw_value.strip()

    if "|" in raw_value:

        raw_value = raw_value.split("|")[-1].strip()

    if not raw_value.isdigit():
        return None

    return raw_value


# ============================================================
# 현재 화면의 category button 탐색
# ============================================================


def discover_category_buttons(
    driver,
):

    result = {}

    elements = driver.find_elements(
        By.CSS_SELECTOR,
        "button[data-category-id]",
    )

    for element in elements:

        raw_category_id = element.get_attribute("data-category-id")

        category_code = normalize_category_id(raw_category_id)

        if not category_code:
            continue

        # ★ 무신사 DOM에서 직접 제공
        category_name = (element.get_attribute("data-category-name") or "").strip()

        # 혹시 속성이 비어있으면
        # 버튼 텍스트 fallback
        if not category_name:

            category_name = (element.text or "").strip()

        if not category_name:

            category_name = (element.get_attribute("textContent") or "").strip()

        result[category_code] = {
            "name": category_name,
            "raw_id": raw_category_id,
        }

    return result


# ============================================================
# DEBUG
# ============================================================


def print_categories(
    categories,
):

    print("\n=================================")

    print(f"발견된 category button: " f"{len(categories)}개")

    print("=================================")

    for code, item in sorted(categories.items()):

        print(f"{code:<8} " f"{item['name']:<25} " f"raw={item['raw_id']}")


# ============================================================
# 1개 카테고리 페이지 접근
# ============================================================


def build_category_url(
    category_code: str,
):

    return (
        "https://www.musinsa.com/"
        "main/musinsa/ranking"
        "?storeCode=musinsa"
        "&sectionId=199"
        "&contentsId="
        f"&categoryCode={category_code}"
        "&subPan=product"
    )


# ============================================================
# 최초 전체 페이지 탐색
# ============================================================


def discover_initial_categories(
    driver,
):

    driver.get(BASE_URL)

    wait_page(driver)

    return discover_category_buttons(driver)


# ============================================================
# 대분류 추출
# ============================================================


def discover_main_categories(
    categories,
):
    """
    대분류 전체 버튼:

    001000
    002000
    003000

    형태 사용.
    """

    result = {}

    for code, item in categories.items():

        if len(code) == 6 and code.endswith("000"):

            result[code] = item["name"]

    return result


# ============================================================
# 상세 카테고리 탐색
# ============================================================


def discover_subcategories(
    driver,
    main_code,
):

    driver.get(build_category_url(main_code))

    wait_page(driver)

    categories = discover_category_buttons(driver)

    prefix = main_code[:3]

    children = {}

    for code, item in categories.items():

        if len(code) != 6:
            continue

        if not code.startswith(prefix):
            continue

        if code == main_code:
            continue

        children[code] = item["name"]

    return children


# ============================================================
# Python 파일 생성
# ============================================================


def write_constants(
    main_categories,
    subcategories,
):

    lines = []

    lines.append('"""')

    lines.append("AUTO GENERATED MUSINSA LIVE CATEGORIES")

    lines.append("직접 수정하지 마세요.")

    lines.append('"""')

    lines.append("")
    lines.append("")

    # ========================================================
    # MAIN
    # ========================================================

    lines.append("MUSINSA_LIVE_CATEGORIES = {")

    for code, name in sorted(main_categories.items()):

        lines.append(f'    "{code}": {name!r},')

    lines.append("}")

    lines.append("")
    lines.append("")

    # ========================================================
    # SUB
    # ========================================================

    lines.append("MUSINSA_LIVE_SUBCATEGORIES = {")

    for main_code, children in sorted(subcategories.items()):

        lines.append(f'    "{main_code}": {{')

        for code, name in sorted(children.items()):

            lines.append(f'        "{code}": {name!r},')

        lines.append("    },")

    lines.append("}")

    lines.append("")

    OUTPUT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(f"\n생성 완료: {OUTPUT_PATH}")


# ============================================================
# MAIN
# ============================================================


def main():

    driver = create_driver()

    try:

        # ----------------------------------------------------
        # 1. 최초 페이지
        # ----------------------------------------------------

        initial = discover_initial_categories(driver)

        print_categories(initial)

        main_categories = discover_main_categories(initial)

        print("\n========== 대분류 ==========")

        for code, name in sorted(main_categories.items()):

            print(
                code,
                name,
            )

        # ----------------------------------------------------
        # 2. 각 대분류 상세 탐색
        # ----------------------------------------------------

        subcategories = {}

        for (
            main_code,
            main_name,
        ) in sorted(main_categories.items()):

            print("\n" f"===== {main_name} " f"({main_code}) 탐색 =====")

            children = discover_subcategories(
                driver,
                main_code,
            )

            subcategories[main_code] = children

            for code, name in sorted(children.items()):

                print(f"  {code:<8} {name}")

        # ----------------------------------------------------
        # 3. 파일 생성
        # ----------------------------------------------------

        write_constants(
            main_categories,
            subcategories,
        )

    finally:

        driver.quit()


if __name__ == "__main__":
    main()
