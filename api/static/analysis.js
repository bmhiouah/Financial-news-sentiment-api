// Analysis page — slicer + Plotly charts

const API = "";
let allSymbols = [];
let selected = new Set();
let currentReturnType = "daily";
let lastOptimization = null;  // remember optimize() result so user can re-run with best params

const COLORS = { positive: "#2ca02c", negative: "#d62728", neutral: "#7f7f7f" };

window.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadAvailableSymbols();
  await loadDateRange();
});

// ---------- events ----------
function bindEvents() {
  document.getElementById("search").addEventListener("input", e => renderList(e.target.value));
  document.getElementById("select-all").addEventListener("click", () => {
    allSymbols.forEach(s => selected.add(s));
    renderList(document.getElementById("search").value);
    loadAll();
  });
  document.getElementById("clear-selection").addEventListener("click", () => {
    selected.clear();
    renderList(document.getElementById("search").value);
    clearAllCharts();
  });
  document.querySelectorAll(".rt-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".rt-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentReturnType = btn.dataset.rt;
      if (selected.size > 0) loadDistribution();
    });
  });
  document.getElementById("bt-run").addEventListener("click", runBacktest);
  document.getElementById("bt-optimize").addEventListener("click", runOptimize);
  document.querySelectorAll('input[name="param-src"]').forEach(r => {
    r.addEventListener("change", () => {
      if (r.checked && r.value === "best" && lastOptimization) {
        fillParamsFromBest();
      }
    });
  });
}

// ---------- data loading ----------
async function loadAvailableSymbols() {
  const el = document.getElementById("loading-equities");
  try {
    const resp = await fetch(`${API}/analysis/available-symbols`);
    const data = await resp.json();
    allSymbols = data.symbols;
    document.getElementById("total-count").textContent = data.count;
    renderList("");
    // pre-select all if dataset is small (matches notebook behaviour)
    if (data.count <= 10) {
      allSymbols.forEach(s => selected.add(s));
      renderList("");
    }
    el.style.display = "none";
  } catch (e) {
    el.textContent = `Error loading symbols: ${e.message}`;
    el.style.color = "#e53e3e";
    return;
  }
  // Load charts separately so a chart failure never hides the equity list
  loadAll();
}

async function loadDateRange() {
  try {
    const resp = await fetch(`${API}/analysis/date-range`);
    const data = await resp.json();
    document.getElementById("date-range").textContent =
      data.min_date && data.max_date ? `${data.min_date} → ${data.max_date}` : "no data";
  } catch (e) { /* non-fatal */ }
}

function symbolParams() {
  return [...selected].map(s => `symbols=${encodeURIComponent(s)}`).join("&");
}

async function loadAll() {
  if (selected.size === 0) return;
  // Run each loader independently so a failure in one chart doesn't block
  // the others (Promise.all would reject on the first failure).
  await Promise.allSettled([
    loadDistribution(),
    loadCorrelation(),
    loadPriceSentiment(),
  ]);
}

function clearAllCharts() {
  document.getElementById("corr-table").innerHTML = "";
  Plotly.purge("price-sentiment");
  Plotly.purge("distribution");
  document.getElementById("bt-plot").innerHTML = "";
  document.getElementById("bt-summary").innerHTML = "";
  document.getElementById("opt-card").style.display = "none";
  lastOptimization = null;
}

// ---------- correlation ----------
async function loadCorrelation() {
  const params = [...selected].map(s => `symbol=${encodeURIComponent(s)}`).join("&");
  const resp = await fetch(`${API}/analysis/correlation?${params}`);
  const data = await resp.json();
  renderCorrelationTable(data.rows);
}

// ---------- price + sentiment ----------
async function loadPriceSentiment() {
  const resp = await fetch(`${API}/analysis/price-sentiment?${symbolParams()}`);
  const series = await resp.json();
  renderPriceSentiment(series);
}

// ---------- distribution ----------
async function loadDistribution() {
  const resp = await fetch(`${API}/analysis/distribution?${symbolParams()}&return_type=${currentReturnType}`);
  const data = await resp.json();
  renderDistribution(data);
}

// ---------- backtest ----------
function getBacktestSymbol() {
  // backtest needs exactly one symbol; if user selected multiple, take the first
  // (the symbol dropdown is kept in sync so this is consistent)
  const sel = document.getElementById("bt-symbol");
  return sel.value || [...selected][0];
}

function refreshBacktestSymbolDropdown() {
  const sel = document.getElementById("bt-symbol");
  const previousValue = sel.value;
  sel.innerHTML = [...selected].map(s => `<option value="${s}">${s}</option>`).join("");
  if ([...selected].includes(previousValue)) sel.value = previousValue;
}

function readBacktestParams() {
  return {
    initial_capital: parseFloat(document.getElementById("bt-initial").value),
    trade_size: parseFloat(document.getElementById("bt-trade-size").value),
    stop_loss: parseFloat(document.getElementById("bt-stop-loss").value),
    stop_win: parseFloat(document.getElementById("bt-stop-win").value),
    buy_threshold: parseFloat(document.getElementById("bt-buy").value),
    sell_threshold: parseFloat(document.getElementById("bt-sell").value),
  };
}

function fillParamsFromBest() {
  if (!lastOptimization) return;
  const b = lastOptimization.best;
  document.getElementById("bt-stop-loss").value = b.stop_loss;
  document.getElementById("bt-stop-win").value = b.stop_win;
  document.getElementById("bt-buy").value = b.buy_threshold;
  document.getElementById("bt-sell").value = b.sell_threshold;
  // also bring initial capital + trade size from the optimization run
  document.getElementById("bt-initial").value = lastOptimization.initial_capital || 100;
  document.getElementById("bt-trade-size").value = lastOptimization.trade_size || 20;
}

async function runBacktest() {
  if (selected.size === 0) { alert("Select at least one equity first."); return; }
  refreshBacktestSymbolDropdown();
  const symbol = getBacktestSymbol();
  const params = readBacktestParams();
  const summary = document.getElementById("bt-summary");
  summary.innerHTML = `<div class="loading">Running backtest for <b>${symbol}</b>...</div>`;
  Plotly.purge("bt-plot");
  try {
    const resp = await fetch(`${API}/backtest/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, params }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || resp.statusText);
    renderBacktestSummary(data);
    renderBacktestPlot(data);
  } catch (e) {
    summary.innerHTML = `<div class="status error" style="display:block;">${e.message}</div>`;
  }
}

async function runOptimize() {
  if (selected.size === 0) { alert("Select at least one equity first."); return; }
  refreshBacktestSymbolDropdown();
  const symbol = getBacktestSymbol();
  const card = document.getElementById("opt-card");
  card.style.display = "block";
  document.getElementById("opt-top10").innerHTML = `<div class="loading">Optimising <b>${symbol}</b>...</div>`;
  Plotly.purge("opt-heatmap");
  const body = {
    symbol,
    train_days: 30,
    initial_capital: parseFloat(document.getElementById("bt-initial").value),
    trade_size: parseFloat(document.getElementById("bt-trade-size").value),
  };
  try {
    const resp = await fetch(`${API}/backtest/optimize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || resp.statusText);
    lastOptimization = { ...data, initial_capital: body.initial_capital, trade_size: body.trade_size };
    renderTopTrialsTable(data);
    renderOptimPnlHeatmap(data);
    // auto-fill params with best so the user can hit "Run Backtest" right away
    if (document.querySelector('input[name="param-src"]:checked').value === "best") {
      fillParamsFromBest();
    }
  } catch (e) {
    document.getElementById("opt-top10").innerHTML = `<div class="status error" style="display:block;">${e.message}</div>`;
  }
}

// ---------- rendering ----------
function renderList(filter) {
  const container = document.getElementById("equity-list");
  const ql = (filter || "").toLowerCase();
  const filtered = ql ? allSymbols.filter(s => s.toLowerCase().includes(ql)) : allSymbols;
  container.innerHTML = filtered.map(s => `
    <label class="equity-item">
      <input type="checkbox" data-symbol="${s}" ${selected.has(s) ? "checked" : ""}>
      <span class="equity-symbol">${s}</span>
    </label>
  `).join("");
  container.querySelectorAll("input[type=checkbox]").forEach(cb => {
    cb.addEventListener("change", () => {
      const sym = cb.dataset.symbol;
      if (cb.checked) selected.add(sym); else selected.delete(sym);
      document.getElementById("selected-count").textContent = selected.size;
      refreshBacktestSymbolDropdown();
      loadAll();
    });
  });
  document.getElementById("selected-count").textContent = selected.size;
  refreshBacktestSymbolDropdown();
}

function fmt(v) { return v == null ? "N/A" : v.toFixed(3); }

function renderCorrelationTable(rows) {
  if (!rows.length) {
    document.getElementById("corr-table").innerHTML = "<p class='loading'>No data for selected symbols.</p>";
    return;
  }
  const html = `
    <table class="corr-table">
      <thead><tr><th>Symbol</th><th>Daily</th><th>Weekly</th><th>Monthly</th><th>N</th></tr></thead>
      <tbody>
        ${rows.map(r => `
          <tr>
            <td><b>${r.symbol}</b></td>
            <td class="${corrClass(r.daily)}">${fmt(r.daily)}</td>
            <td class="${corrClass(r.weekly)}">${fmt(r.weekly)}</td>
            <td class="${corrClass(r.monthly)}">${fmt(r.monthly)}</td>
            <td>${r.n}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  document.getElementById("corr-table").innerHTML = html;
}

function corrClass(v) {
  if (v == null) return "";
  if (v > 0.3) return "corr-pos-strong";
  if (v > 0) return "corr-pos";
  if (v < -0.3) return "corr-neg-strong";
  if (v < 0) return "corr-neg";
  return "";
}

function renderPriceSentiment(series) {
  if (!series.length) {
    Plotly.purge("price-sentiment");
    document.getElementById("price-sentiment").innerHTML = "<p class='loading'>No price data for selected symbols.</p>";
    return;
  }
  const traces = [];
  for (const s of series) {
    traces.push({
      x: s.points.map(p => p.date),
      y: s.points.map(p => p.close),
      mode: "lines",
      name: s.symbol,
      line: { width: 2 },
      type: "scatter",
      hovertemplate: `<b>${s.symbol}</b><br>%{x|%Y-%m-%d}<br>Close: %{y:.2f}<extra></extra>`,
    });
    const withSent = s.points
      .map((p, i) => ({ ...p, idx: i }))
      .filter(p => p.sentiment_score != null);
    if (withSent.length) {
      traces.push({
        x: withSent.map(p => p.date),
        y: withSent.map(p => p.close),
        mode: "markers",
        name: `${s.symbol} sentiment`,
        marker: {
          size: withSent.map(p => Math.max(6, Math.min(25, Math.abs(p.sentiment_score) * 30))),
          color: withSent.map(p => COLORS[p.sentiment_label] || COLORS.neutral),
          line: { width: 1, color: "black" },
          opacity: 0.9,
        },
        text: withSent.map(p => p.headline || ""),
        customdata: withSent.map(p => [p.sentiment_label, p.sentiment_score]),
        hovertemplate: `<b>${s.symbol}</b> %{x|%Y-%m-%d}<br>Close: %{y:.2f}<br>Sentiment: %{customdata[0]} (%{customdata[1]:.2f})<br><i>%{text}</i><extra></extra>`,
      });
    }
  }
  const layout = {
    title: "Price + News Sentiment by Equity",
    xaxis: { title: "Date" },
    yaxis: { title: "Close Price" },
    hovermode: "closest",
    height: Math.max(400, 80 * series.length + 300),
    legend: { orientation: "h", y: -0.15 },
  };
  Plotly.newPlot("price-sentiment", traces, layout, { responsive: true });
}

function renderDistribution(data) {
  const el = document.getElementById("distribution");
  if (!data.rows.length) {
    Plotly.purge(el);
    el.innerHTML = "<p class='loading'>Not enough data for distribution plot (need >= 5 sentiment observations per symbol).</p>";
    return;
  }
  // Build n rows x 2 columns: heatmap (col 1) + correlation bars (col 2) per symbol.
  // We assign explicit xaxis/yaxis IDs to each trace so Plotly places them
  // in the right cell of the grid.  This is the approach from the official
  // plotly.js docs (https://plotly.com/javascript/subplots/) and works with
  // the standard `plotly.min.js` bundle (no `makeSubplots` import needed).
  const n = data.rows.length;
  const traces = [];
  for (let idx = 0; idx < n; idx++) {
    const r = data.rows[idx];
    const xa = `x${idx * 2 + 1}`;  // x1, x3, x5, ...
    const xb = `x${idx * 2 + 2}`;  // x2, x4, x6, ...
    const ya = `y${idx * 2 + 1}`;
    const yb = `y${idx * 2 + 2}`;
    traces.push({
      type: "heatmap",
      z: r.heatmap_z,
      x: r.heatmap_x_labels,
      y: r.heatmap_y_labels,
      colorscale: "Blues",
      showscale: false,
      xaxis: xa, yaxis: ya,
      hovertemplate: "Score: %{x}<br>Return: %{y}<br>Pct: %{z:.1f}%<extra></extra>",
    });
    traces.push({
      type: "bar",
      x: r.correlation.map(c => c.name),
      y: r.correlation.map(c => c.value ?? 0),
      marker: { color: ["#1f77b4", "#ff7f0e", "#2ca02c"] },
      text: r.correlation.map(c => c.value == null ? "N/A" : c.value.toFixed(3)),
      textposition: "outside",
      xaxis: xb, yaxis: yb,
      showlegend: false,
      hovertemplate: "%{x}: %{y:.3f}<extra></extra>",
    });
  }
  const layout = {
    title: { text: `Distribution & Correlation by Equity (return = ${data.return_type})` },
    grid: { rows: n, columns: 2, pattern: "independent" },
    showlegend: false,
    height: Math.max(400, 240 * n + 100),
    margin: { l: 70, r: 30, t: 60, b: 50 },
  };
  // Configure axes: per-cell titles via xaxis{N} keys
  for (let idx = 0; idx < n; idx++) {
    const isLast = idx === n - 1;
    const xa = `xaxis${idx * 2 + 1}`;
    const xb = `xaxis${idx * 2 + 2}`;
    const ya = `yaxis${idx * 2 + 1}`;
    const yb = `yaxis${idx * 2 + 2}`;
    layout[xa] = {
      tickangle: -45, tickfont: { size: 9 },
      title: isLast ? { text: "FinBERT score bucket" } : undefined,
    };
    layout[ya] = {
      tickfont: { size: 9 },
      title: isLast ? { text: "Log return bucket" } : undefined,
    };
    layout[xb] = {
      tickfont: { size: 9 },
      title: isLast ? { text: "Return type" } : undefined,
    };
    layout[yb] = {
      range: [-1, 1],
      title: isLast ? { text: "Correlation" } : undefined,
    };
  }
  Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false });
}

function renderBacktestSummary(data) {
  const pnlClass = data.pnl >= 0 ? "pnl-pos" : "pnl-neg";
  const html = `
    <h3>${data.symbol}: backtest result</h3>
    <div class="kv"><span>Final capital</span><b>${data.final_capital.toFixed(2)}</b></div>
    <div class="kv"><span>Initial capital</span><b>${data.initial_capital.toFixed(2)}</b></div>
    <div class="kv"><span>P&amp;L</span><b class="${pnlClass}">${data.pnl >= 0 ? "+" : ""}${data.pnl.toFixed(2)}</b></div>
    <div class="kv"><span>Signals</span><b>${data.signals}</b></div>
    <div class="kv"><span>Closed trades</span><b>${data.closed_trades}</b></div>
  `;
  document.getElementById("bt-summary").innerHTML = html;
}

function renderBacktestPlot(data) {
  const x = data.points.map(p => p.date);
  const cap = data.points.map(p => p.capital);
  const virt = data.points.map(p => p.virtual_capital);
  const long = data.points.map(p => p.open_long);
  const short = data.points.map(p => -p.open_short);

  const capTrace = {
    x, y: virt, type: "scatter", mode: "lines+markers",
    name: "virtual_capital",
    line: { color: "#1f77b4", width: 2 },
    marker: {
      size: 8,
      color: data.points.map(p => p.open_long - p.open_short),
      colorscale: "RdBu", cmin: -3, cmax: 3, showscale: false,
      line: { width: 1, color: "black" },
    },
    xaxis: "x", yaxis: "y",
    customdata: data.points.map(p => [p.open_long, p.open_short]),
    hovertemplate: "Date %{x|%Y-%m-%d}<br>Virtual %{y:.2f}<br>Open L %{customdata[0]}  Open S %{customdata[1]}<extra></extra>",
  };
  const longTrace = { x, y: long, type: "bar", name: "open_long", marker: { color: "#2ca02c", opacity: 0.85 }, xaxis: "x2", yaxis: "y2" };
  const shortTrace = { x, y: short, type: "bar", name: "open_short", marker: { color: "#d62728", opacity: 0.85 }, xaxis: "x2", yaxis: "y2" };

  const layout = {
    title: `${data.symbol}: Virtual capital & open trade counts`,
    barmode: "overlay",
    grid: { rows: 2, columns: 1, pattern: "independent" },
    height: 650,
    hovermode: "x unified",
    legend: { orientation: "h", y: 1.05 },
    shapes: [{ type: "line", xref: "x", yref: "y", x0: x[0], x1: x[x.length - 1], y0: data.initial_capital, y1: data.initial_capital, line: { color: "gray", dash: "dash" } }],
    margin: { t: 60, l: 60, r: 20, b: 40 },
  };
  layout.xaxis = { anchor: "y" };
  layout.yaxis = { title: "Virtual capital ($)", domain: [0.4, 1] };
  layout.xaxis2 = { anchor: "y2" };
  layout.yaxis2 = { title: "Open long (+) / short (-)", zeroline: true, domain: [0, 0.32] };

  Plotly.newPlot("bt-plot", [capTrace, longTrace, shortTrace], layout, { responsive: true });
}

function renderTopTrialsTable(data) {
  const top = data.top_trials;
  const rows = top.map((t, i) => {
    const pnlCls = t.pnl >= 0 ? "pnl-pos" : "pnl-neg";
    return `
      <tr class="${i === 0 ? 'best' : ''}">
        <td>${i === 0 ? "★" : i + 1}</td>
        <td>${t.stop_loss}</td>
        <td>${t.stop_win}</td>
        <td>${t.buy_threshold}</td>
        <td>${t.sell_threshold}</td>
        <td class="${pnlCls}">${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}</td>
        <td>${t.final_capital.toFixed(2)}</td>
        <td>${t.n_signals}</td>
        <td>${t.n_trades}</td>
      </tr>
    `;
  }).join("");
  const html = `
    <p class="hint">
      <b>Optimizer</b> trained on the <b>oldest 30 days</b> of available data:
      <b>${data.start} → ${data.end}</b><br>
      <b>Backtest</b> (when you hit "Run Backtest") evaluates those params on the
      <b>full dataset</b>: <b>${data.full_data_start} → ${data.full_data_end}</b>
      &middot; ${data.all_trials.length} total trials &middot; best P&amp;L = <b class="${data.best.pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}">${data.best.pnl >= 0 ? "+" : ""}${data.best.pnl.toFixed(2)}</b>
    </p>
    <table class="trial-table">
      <thead><tr><th>#</th><th>stop_loss</th><th>stop_win</th><th>buy</th><th>sell</th><th>P&amp;L</th><th>Final</th><th>Signals</th><th>Trades</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  document.getElementById("opt-top10").innerHTML = html;
}

function renderOptimPnlHeatmap(data) {
  // The stop_loss values from the optimizer are not evenly spaced (they come from
  // a coarse + refine grid), so plotting them directly on a numeric y-axis makes
  // Plotly render unequal-height cells that overlap.  We map them to evenly
  // spaced integer indices and override the tick labels with the real values.
  const swVals = data.pnl_grid_x;
  const slVals = data.pnl_grid_y;
  const nRows = slVals.length;
  const nCols = swVals.length;

  // Z matrix: rows = stop_loss, cols = stop_win.  Replace null with null
  // (Plotly treats null as a gap).
  const z = data.pnl_grid_z.map(row => row.map(v => v == null ? null : v));
  const text = data.pnl_grid_z.map(row => row.map(v => v == null ? "" : (v >= 0 ? "+" : "") + v.toFixed(1)));

  // Reverse rows for the y-axis so the smallest stop_loss is at the bottom
  // (matches the notebook's P&L heatmap orientation).
  const yIdx = [...Array(nRows).keys()].map(i => nRows - 1 - i);
  const yLabels = [...slVals].reverse();
  const zRev = yIdx.map(i => z[i]);
  const textRev = yIdx.map(i => text[i]);

  // cell size on the x axis must be larger than the gap between values; we use
  // a numeric x with extra padding by passing '' x labels and tickvals.
  const xTickVals = [...Array(nCols).keys()];
  const trace = {
    type: "heatmap",
    z: zRev,
    x: xTickVals,
    y: [...Array(nRows).keys()],
    colorscale: "RdYlGn", zmid: 0,
    text: textRev,
    texttemplate: "%{text}",
    textfont: { size: 12 },
    xgap: 3, ygap: 3,
    hovertemplate: "stop_win=%{customdata}<br>stop_loss=%{ycustomdata}<br>P&L=%{z:+.2f}<extra></extra>",
    customdata: zRev.map(row => row.map(_ => "")),
    showscale: true,
    colorbar: { title: "P&L" },
  };
  // Build per-cell customdata for the tooltip (stop_win, stop_loss)
  trace.customdata = zRev.map((row, i) => row.map((_, j) => swVals[j]));
  trace.ycustomdata = zRev.map((row, i) => row.map((_, j) => yLabels[i]));

  const layout = {
    title: `P&L across (stop_loss, stop_win) at best buy=${data.best.buy_threshold}, sell=${data.best.sell_threshold}`,
    xaxis: {
      title: "stop_win",
      tickmode: "array",
      tickvals: xTickVals,
      ticktext: swVals.map(v => v.toString()),
      side: "bottom",
    },
    yaxis: {
      title: "stop_loss",
      tickmode: "array",
      tickvals: [...Array(nRows).keys()],
      ticktext: yLabels.map(v => v.toString()),
      autorange: "reversed",
    },
    height: Math.max(400, 50 * nRows + 120),
    width: Math.max(600, 80 * nCols + 160),
    margin: { l: 90, r: 40, t: 70, b: 70 },
  };
  Plotly.newPlot("opt-heatmap", [trace], layout, { responsive: true, displayModeBar: true });
}
