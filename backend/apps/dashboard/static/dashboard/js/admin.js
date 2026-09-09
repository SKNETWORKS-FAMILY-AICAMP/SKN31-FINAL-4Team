document.addEventListener("DOMContentLoaded", () => {
    const currentPath = window.location.pathname;

    document.querySelectorAll(".sidebar-nav a").forEach((link) => {
        const href = link.getAttribute("href");

        if (href && href !== "/" && currentPath.startsWith(href)) {
            link.style.background = "#222";
            link.style.color = "#fff";
            link.style.fontWeight = "700";
        }
    });
});

// ==========================================
// Collection Run detail toggle
// ==========================================

document.querySelectorAll("[data-run-toggle]").forEach((button) => {

    button.addEventListener("click", () => {

        const runId =
            button.dataset.runToggle;

        const detail =
            document.getElementById(
                `run-detail-${runId}`
            );

        if (!detail) {
            return;
        }

        detail.classList.toggle(
            "is-open"
        );
    });

});


// ==========================================
// Duration calculator
// ==========================================

document.querySelectorAll(".duration-value").forEach((element) => {

    const startValue =
        element.dataset.start;

    const endValue =
        element.dataset.end;

    if (!startValue || !endValue) {
        return;
    }

    const start =
        new Date(startValue);

    const end =
        new Date(endValue);

    let seconds =
        Math.floor(
            (end - start) / 1000
        );

    if (seconds < 0) {
        element.textContent = "-";
        return;
    }


    const hours =
        Math.floor(seconds / 3600);

    seconds %= 3600;


    const minutes =
        Math.floor(seconds / 60);

    seconds %= 60;


    if (hours > 0) {

        element.textContent =
            `${hours}h ${minutes}m`;

    } else if (minutes > 0) {

        element.textContent =
            `${minutes}m ${seconds}s`;

    } else {

        element.textContent =
            `${seconds}s`;

    }

});

document.querySelectorAll("[data-target-toggle]").forEach((button) => {

    button.addEventListener("click", () => {

        const targetId =
            button.dataset.targetToggle;

        const detail =
            document.getElementById(
                `target-detail-${targetId}`
            );

        if (!detail) {
            return;
        }

        detail.classList.toggle(
            "is-open"
        );
    });

});


/* ============================================================
   브랜드 코드 자동 정규화
   ------------------------------------------------------------
   원래 이 파일 끝에 <script> 태그로 감싼 채 들어 있었다.
   .js 파일 안의 <script> 는 문법 오류라 파일 전체가 파싱되지 않아
   위쪽 타겟 토글까지 동작하지 않는 상태였다. (2026-09-09 수정)

   대상도 id="brand_code" 로 잡혀 있었으나 실제 입력란 id 는
   new-brand-code 라서 매칭되지 않았다. name 기준으로 변경했다.

   서버(create_brand_from_source)에서도 같은 정규화를 하므로
   여기서는 입력 중 확인용이다.
   ============================================================ */

document.addEventListener("DOMContentLoaded", function () {

    const inputs = document.querySelectorAll('input[name="brand_code"]');

    inputs.forEach(function (input) {

        input.addEventListener("blur", function () {

            let value = (input.value || "").trim();

            if (!value) {
                return;
            }

            value = value
                .toUpperCase()
                .replace(/\s+/g, "_")
                .replace(/-+/g, "_")
                .replace(/_{2,}/g, "_");

            if (!value.startsWith("BRAND_")) {
                value = "BRAND_" + value;
            }

            input.value = value;
        });

    });

});
