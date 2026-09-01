// Financial Sentiment Pipeline - Frontend

const API = "";  // same origin

let allEquities = [];
let selected = new Set();
let filtered = [];

// ---------- init ----------
window.addEventListener("DOMContentLoaded", async () => {
  setDefaultDates();
  await loadEquities();
  bindEvents();
});

function setDefaultDates() {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 30);
  document.getElementById("start-date").value = toIso(start);
  document.getElementById("end-date").value = toIso(end);
}

function toIso(d) { return d.toISOString().slice(0, 10); }

// ---------- equities ----------
async function loadEquities() {
  const status = document.getElementById("loading-equities");
  status.textContent = "Loading equities...";
  try {
    const resp = await fetch(`${API}/equities/symbols?limit=10000`);
    const data = await resp.json();
    allEquities = data.items;
    filtered = allEquities;
    document.getElementById("total-count").textContent = data.total;
    renderList();
    status.style.display = "none";
  } catch (e) {
    status.textContent = `Error loading equities: ${e.message}`;
    status.style.color = "#e53e3e";
  }
}

function renderList() {
  const container = document.getElementById("equity-list");
  const slice = filtered.slice(0, 500);
  container.innerHTML = slice.map(e => `
    <label class="equity-item">
      <input type="checkbox" data-symbol="${e.symbol}" ${selected.has(e.symbol) ? "checked" : ""}>
      <span class="equity-symbol">${e.symbol}</span>
      <span class="equity-name">${e.name || ""}</span>
    </label>
  `).join("");
  container.querySelectorAll("input[type=checkbox]").forEach(cb => {
    cb.addEventListener("change", () => {
      const sym = cb.dataset.symbol;
      if (cb.checked) selected.add(sym); else selected.delete(sym);
      updateCount();
    });
  });
  updateCount();
}

function updateCount() {
  document.getElementById("selected-count").textContent = selected.size;
}

function applySearch(q) {
  if (!q) { filtered = allEquities; }
  else {
    const ql = q.toLowerCase();
    filtered = allEquities.filter(e =>
      e.symbol.toLowerCase().includes(ql) ||
      (e.name || "").toLowerCase().includes(ql)
    );
  }
  renderList();
}

// ---------- events ----------
function bindEvents() {
  document.getElementById("search").addEventListener("input", e => applySearch(e.target.value));

  document.getElementById("select-all").addEventListener("click", () => {
    filtered.forEach(e => selected.add(e.symbol));
    renderList();
  });

  document.getElementById("clear-selection").addEventListener("click", () => {
    selected.clear();
    renderList();
  });

  document.querySelectorAll(".preset").forEach(btn => {
    btn.addEventListener("click", () => {
      const days = parseInt(btn.dataset.days);
      const end = new Date();
      const start = new Date();
      start.setDate(end.getDate() - days);
      document.getElementById("start-date").value = toIso(start);
      document.getElementById("end-date").value = toIso(end);
    });
  });

  document.getElementById("run-pipeline").addEventListener("click", runPipeline);
}

// ---------- run pipeline ----------
async function runPipeline() {
  const status = document.getElementById("run-status");
  const btn = document.getElementById("run-pipeline");

  if (selected.size === 0) {
    showStatus(status, "error", "Please select at least one equity.");
    return;
  }
  const startDate = document.getElementById("start-date").value;
  const endDate = document.getElementById("end-date").value;
  if (!startDate || !endDate) {
    showStatus(status, "error", "Please pick a start and end date.");
    return;
  }
  if (endDate < startDate) {
    showStatus(status, "error", "End date must be on or after start date.");
    return;
  }

  const sources = [];
  if (document.getElementById("source-openbb").checked) sources.push("openbb");
  if (document.getElementById("source-finnhub").checked) sources.push("finnhub");
  if (sources.length === 0) {
    showStatus(status, "error", "Pick at least one news source.");
    return;
  }

  const body = {
    symbols: [...selected],
    start_date: startDate,
    end_date: endDate,
    sources: sources,
    analyze: document.getElementById("analyze").checked,
    force_refresh: document.getElementById("force-refresh").checked,
    finnhub_sources: ["CNBC"],
  };

  btn.disabled = true;
  showStatus(status, "info", `Running pipeline for ${selected.size} symbol(s)... this can take a few minutes.`);

  try {
    const resp = await fetch(`${API}/pipeline/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || resp.statusText);

    const detail = Object.entries(data.results)
      .map(([name, s]) => `${name}: fetched=${s.fetched} saved=${s.saved} scored=${s.scored}`)
      .join(" | ");
    showStatus(status, "success", `${data.summary}  (${detail})`);
  } catch (e) {
    showStatus(status, "error", `Pipeline failed: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
}

function showStatus(el, type, msg) {
  el.className = `status ${type}`;
  el.textContent = msg;
}
