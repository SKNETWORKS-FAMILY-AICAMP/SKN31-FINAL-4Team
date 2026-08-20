console.log("[FEEDIT] crawler.js loaded");

/* =========================================================
   CSS Variable
========================================================= */

function getCssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();

  return value || fallback;
}

/* =========================================================
   JSON
========================================================= */

function readJson(id) {
  const element = document.getElementById(id);

  if (!element) {
    return null;
  }

  try {
    return JSON.parse(element.textContent);
  } catch (error) {
    console.error(`[FEEDIT] JSON parse failed: ${id}`, error);
    return null;
  }
}

/* =========================================================
   Job Search / Filter
========================================================= */

function initJobFilter({
  tableId = "jobsTable",
  searchId = "jobSearch",
  sourceId = "filterSource",
  statusId = "filterStatus",
  resetId = "filterReset",
  countId = "jobCount",
} = {}) {
  const table = document.getElementById(tableId);

  if (!table) {
    return;
  }

  const rows = Array.from(table.querySelectorAll("tbody tr[data-status]"));

  const searchInput = document.getElementById(searchId);
  const sourceSelect = document.getElementById(sourceId);
  const statusSelect = document.getElementById(statusId);
  const resetButton = document.getElementById(resetId);
  const countElement = document.getElementById(countId);

  function applyFilter() {
    const keyword = (searchInput?.value || "").trim().toLowerCase();

    const selectedSource = sourceSelect?.value || "";
    const selectedStatus = statusSelect?.value || "";

    let visibleCount = 0;

    rows.forEach((row) => {
      const rowText = (row.textContent || "").toLowerCase();
      const rowSource = row.dataset.source || "";
      const rowStatus = row.dataset.status || "";

      const matchesKeyword = !keyword || rowText.includes(keyword);

      const matchesSource =
        !sourceSelect || !selectedSource || rowSource === selectedSource;

      const matchesStatus =
        !statusSelect || !selectedStatus || rowStatus === selectedStatus;

      const visible = matchesKeyword && matchesSource && matchesStatus;

      row.hidden = !visible;

      if (visible) {
        visibleCount += 1;
      }
    });

    if (countElement) {
      if (
        keyword ||
        (sourceSelect && selectedSource) ||
        (statusSelect && selectedStatus)
      ) {
        countElement.textContent = `검색 결과 ${visibleCount}건 / 전체 ${rows.length}건`;
      } else {
        countElement.textContent = `전체 ${rows.length}건`;
      }
    }
  }

  searchInput?.addEventListener("input", applyFilter);

  sourceSelect?.addEventListener("change", applyFilter);

  statusSelect?.addEventListener("change", applyFilter);

  resetButton?.addEventListener("click", () => {
    if (searchInput) {
      searchInput.value = "";
    }

    if (sourceSelect) {
      sourceSelect.value = "";
    }

    if (statusSelect) {
      statusSelect.value = "";
    }

    applyFilter();

    searchInput?.focus();
  });

  applyFilter();
}

/* =========================================================
   Trend Chart
========================================================= */

/*
지원하는 두 데이터 형태

1) Dashboard
[
    {"label": "08/12", "count": 3},
    {"label": "08/13", "count": 5}
]

2) MUSINSA Detail
{
    "labels": ["08/12", "08/13"],
    "success": [3, 4],
    "failed": [0, 1]
}
*/

function normalizeTrendData(data) {
  if (Array.isArray(data)) {
    return {
      labels: data.map((item) => item.label),
      datasets: [
        {
          label: "실행 작업",
          data: data.map((item) => Number(item.count || 0)),
        },
      ],
    };
  }

  if (data && Array.isArray(data.labels)) {
    return {
      labels: data.labels,
      datasets: [
        {
          label: "SUCCESS",
          data: (data.success || data.success_jobs || []).map((value) =>
            Number(value || 0),
          ),
        },
        {
          label: "FAILED",
          data: (data.failed || data.failed_jobs || []).map((value) =>
            Number(value || 0),
          ),
        },
      ],
    };
  }

  return null;
}

function renderTrendChart(canvasId = "trendChart", dataId = "trend-data") {
  const canvas = document.getElementById(canvasId);
  const rawData = readJson(dataId);

  if (!canvas || !rawData || !window.Chart) {
    return;
  }

  const normalized = normalizeTrendData(rawData);

  if (!normalized) {
    return;
  }

  const brandColor = getCssVar("--brand", "#171717");

  const successColor = getCssVar("--success", "#15803d");

  const dangerColor = getCssVar("--danger", "#dc2626");

  const palette = [brandColor, successColor, dangerColor];

  const datasets = normalized.datasets.map((dataset, index) => ({
    ...dataset,
    borderColor: palette[index] || brandColor,
    backgroundColor: "rgba(23, 23, 23, 0.04)",
    fill: false,
    tension: 0.35,
    borderWidth: 2,
    pointRadius: 3,
    pointBackgroundColor: palette[index] || brandColor,
  }));

  new Chart(canvas, {
    type: "line",

    data: {
      labels: normalized.labels,
      datasets,
    },

    options: {
      responsive: true,
      maintainAspectRatio: false,

      interaction: {
        mode: "index",
        intersect: false,
      },

      plugins: {
        legend: {
          display: datasets.length > 1,
        },
      },

      scales: {
        x: {
          grid: {
            display: false,
          },
        },

        y: {
          beginAtZero: true,

          ticks: {
            precision: 0,
          },

          grid: {
            color: "#f0f0f0",
          },
        },
      },
    },
  });
}

/* =========================================================
   Status Donut
========================================================= */

function renderStatusDonut(
  canvasId = "statusDonut",
  dataId = "status-counts",
  centerValueId = "statusDonutCenter",
) {
  const canvas = document.getElementById(canvasId);
  const data = readJson(dataId);

  if (!canvas || !data || !window.Chart) {
    return;
  }

  const labels = ["SUCCESS", "FAILED", "RUNNING", "PENDING"];

  const values = labels.map((label) => Number(data[label] || 0));

  const colors = [
    getCssVar("--success", "#15803d"),
    getCssVar("--danger", "#dc2626"),
    getCssVar("--warning", "#a16207"),
    "#a3a3a3",
  ];

  const total = values.reduce((sum, value) => sum + value, 0);

  const successRate = total ? Math.round((values[0] / total) * 1000) / 10 : 0;

  new Chart(canvas, {
    type: "doughnut",

    data: {
      labels,

      datasets: [
        {
          data: values,
          backgroundColor: colors,
          borderWidth: 0,
        },
      ],
    },

    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "72%",

      plugins: {
        legend: {
          display: false,
        },
      },
    },
  });

  const centerElement = document.getElementById(centerValueId);

  if (centerElement) {
    centerElement.textContent = `${successRate}%`;
  }
}

/* =========================================================
   Confirm Form
========================================================= */

function initConfirmForms() {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.dataset.confirm;

      if (message && !window.confirm(message)) {
        event.preventDefault();
      }
    });
  });
}

/* =========================================================
   Page Init
========================================================= */

document.addEventListener("DOMContentLoaded", () => {
  initJobFilter();

  renderTrendChart();

  renderStatusDonut();

  initConfirmForms();
});
