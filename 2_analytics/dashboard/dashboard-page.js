// Browser-only setup shared by index.html, sleep.html and training.html.
// Load after Chart.js and dashboard-utils.js.

const API_BASE = "http://127.0.0.1:8000";

const COLOR_RECOVERY = "#199e70";
const COLOR_SLEEP = "#9085e9";
const COLOR_STRAIN = "#e66767";
const COLOR_WEATHER = "#4a9fd8";
const CATEGORICAL = ["#6fd6b0", "#4fb3bf", "#9ad0f5", "#b9a7f0", "#f2c48d", "#ee9fb5", "#b5e48c", "#7aa6c2"];
const OTHER_COLOR = "#898781";
const GRID_COLOR = "#2c2c2a";
const TICK_COLOR = "#898781";

Chart.defaults.color = TICK_COLOR;
Chart.defaults.font.family = "'Roobert', 'Inter', sans-serif";

const TOOLTIP_STYLE = {
    backgroundColor: "#1a1a19",
    titleColor: "#fff",
    bodyColor: "#fff",
};

function fmtDate(d) {
    return new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function fetchJson(path) {
    return fetch(`${API_BASE}${path}`).then((response) => {
        if (!response.ok) throw new Error(`${path} returned ${response.status}`);
        return response.json();
    });
}

function showLoadError() {
    document.querySelector(".topNav").insertAdjacentHTML("afterend", "<p class='error pageError'>Dashboard data could not be loaded.</p>");
}

// Calls onChange(period) whenever a period button inside the container is clicked.
function wirePeriodToggle(container, onChange) {
    container.querySelectorAll(".toggleBtn").forEach((button) => {
        button.addEventListener("click", () => {
            container.querySelectorAll(".toggleBtn").forEach((other) => other.classList.remove("active"));
            button.classList.add("active");
            onChange(button.dataset.period);
        });
    });
}

function activePeriod(container) {
    return container.querySelector(".toggleBtn.active").dataset.period;
}
