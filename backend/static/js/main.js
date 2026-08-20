document.addEventListener("DOMContentLoaded", () => {
    initJobFilters();
    initTrendChart();
    initAutoDismissToasts();
});

function initJobFilters() {
    const table = document.querySelector("#jobsTable");
    if (!table) return;

    const rows = [...table.querySelectorAll("tbody tr.clickable-row")];
    const search = document.querySelector("#jobSearch");
    const source = document.querySelector("#filterSource");
    const status = document.querySelector("#filterStatus");
    const reset = document.querySelector("#filterReset");
    const count = document.querySelector("#jobCount");

    const apply = () => {
        const q = (search?.value || "").trim().toLowerCase();
        const sourceValue = source?.value || "";
        const statusValue = status?.value || "";
        let visible = 0;

        rows.forEach((row) => {
            const text = row.textContent.toLowerCase();
            const target = (row.dataset.target || "").toLowerCase();
            const rowSource = row.dataset.source || "";
            const rowStatus = row.dataset.status || "";

            const searchOK = !q || text.includes(q) || target.includes(q);
            const sourceOK = !sourceValue || rowSource === sourceValue;
            const statusOK = !statusValue || rowStatus === statusValue;
            const show = searchOK && sourceOK && statusOK;

            row.hidden = !show;
            if (show) visible += 1;
        });

        if (count) count.textContent = `표시 ${visible}건 / 전체 ${rows.length}건`;
    };

    search?.addEventListener("input", apply);
    source?.addEventListener("change", apply);
    status?.addEventListener("change", apply);
    reset?.addEventListener("click", () => {
        if (search) search.value = "";
        if (source) source.value = "";
        if (status) status.value = "";
        apply();
    });

    apply();
}

function initTrendChart() {
    const canvas = document.querySelector("#trendChart");
    const dataNode = document.querySelector("#trend-data");
    if (!canvas || !dataNode || typeof Chart === "undefined") return;

    let payload;
    try {
        payload = JSON.parse(dataNode.textContent);
    } catch (error) {
        console.warn("trend-data JSON parse failed", error);
        return;
    }

    new Chart(canvas, {
        type: "line",
        data: {
            labels: payload.labels || [],
            datasets: [
                {
                    label: "전체 실행",
                    data: payload.totals || [],
                    tension: 0.35,
                },
                {
                    label: "성공",
                    data: payload.successes || [],
                    tension: 0.35,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: { legend: { position: "bottom" } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        },
    });
}

function initAutoDismissToasts() {
    document.querySelectorAll(".toast").forEach((toast) => {
        window.setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(-6px)";
            toast.style.transition = "opacity .2s ease, transform .2s ease";
            window.setTimeout(() => toast.remove(), 220);
        }, 3500);
    });
}
