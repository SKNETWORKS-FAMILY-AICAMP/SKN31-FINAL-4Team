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