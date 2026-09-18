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
document.addEventListener("DOMContentLoaded", () => {
    const currentPath = window.location.pathname;

    document.querySelectorAll(".sidebar-nav a").forEach((link) => {
        const href = link.getAttribute("href");

        if (
            href &&
            href !== "/" &&
            currentPath.startsWith(href)
        ) {
            link.style.background = "#222";
            link.style.color = "#fff";
            link.style.fontWeight = "700";
        }
    });
});


// ==========================================
// Collection Run detail toggle
// ==========================================

document
    .querySelectorAll("[data-run-toggle]")
    .forEach((button) => {

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

document
    .querySelectorAll(".duration-value")
    .forEach((element) => {

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
            Math.floor(
                seconds / 3600
            );

        seconds %= 3600;

        const minutes =
            Math.floor(
                seconds / 60
            );

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


// ==========================================
// Collection Target detail toggle
// ==========================================

document
    .querySelectorAll("[data-target-toggle]")
    .forEach((button) => {

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


// ==========================================
// FEEDIT 브랜드 코드 자동 생성
// ==========================================
//
// english_name 을 기준으로:
//
// FOETO
// -> BRAND_FOETO
//
// Ghost Republic
// -> BRAND_GHOST_REPUBLIC
//
// GOLDEN BEAR
// -> BRAND_GOLDEN_BEAR
//
// A.P.C.
// -> BRAND_APC
//
// 실제 최종 검증/생성은 서버에서도 다시 수행한다.
// ==========================================

function generateBrandCode(englishName) {

    if (!englishName) {
        return "";
    }

    let value = englishName
        .trim()
        .toUpperCase()

        // 공백 / - / / / & 를 underscore 로
        .replace(/[\s\-\/&]+/g, "_")

        // 영문 / 숫자 / underscore 외 제거
        .replace(/[^A-Z0-9_]/g, "")

        // 중복 underscore 제거
        .replace(/_+/g, "_")

        // 앞뒤 underscore 제거
        .replace(/^_+|_+$/g, "");

    if (!value) {
        return "";
    }

    return `BRAND_${value}`;
}


// ==========================================
// 신규 FEEDIT 브랜드 코드 동기화
// ==========================================

function syncBrandCode() {

    const englishNameInput =
        document.getElementById(
            "new-brand-en"
        );

    const brandCodeInput =
        document.getElementById(
            "new-brand-code"
        );

    if (
        !englishNameInput ||
        !brandCodeInput
    ) {
        return;
    }

    brandCodeInput.value =
        generateBrandCode(
            englishNameInput.value
        );
}


// ==========================================
// 영문 브랜드명 변경 시 코드 실시간 갱신
// ==========================================

document.addEventListener(
    "DOMContentLoaded",
    () => {

        const englishNameInput =
            document.getElementById(
                "new-brand-en"
            );

        if (!englishNameInput) {
            return;
        }

        englishNameInput.addEventListener(
            "input",
            syncBrandCode
        );

        // 초기값이 이미 존재할 수도 있으므로
        // 로딩 시 한 번 실행
        syncBrandCode();
    }
);