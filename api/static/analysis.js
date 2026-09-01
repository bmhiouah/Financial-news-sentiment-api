// Analysis page — slicer + Plotly charts

const API = "";
let allSymbols = [];
let selected = new Set();     // holds at most ONE symbol (single-equity page)
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
    // Single-equity page: pre-select the first symbol so the page isn't empty.
    if (allSymbols.length > 0) selected = new Set([allSymbols[0]]);
    renderList("");
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
    loadPriceSentiment(),
  ]);
}

function clearAllCharts() {
  Plotly.purge("price-sentiment");
  Plotly.purge("distribution");
  Plotly.purge("correlation-bars");
  document.getElementById("bt-plot").innerHTML = "";
  document.getElementById("bt-summary").innerHTML = "";
  document.getElementById("opt-card").style.display = "none";
  lastOptimization = null;
  clearComparison();
}

// Comparison panel (Simple vs Benchmark) — cleared whenever the result would
// refer to a symbol that is no longer selected.
function clearComparison() {
  Plotly.purge("cmp-curve");
  const curve = document.getElementById("cmp-curve");
  if (curve) curve.innerHTML = "";
  const summary = document.getElementById("cmp-summary");
  if (summary) summary.innerHTML = "";
  const heat = document.getElementById("cmp-heatmap");
  if (heat) heat.innerHTML = "";
}

// ---------- price + sentiment ----------
async function loadPriceSentiment() {
  const resp = await fetch(`${API}/analysis/price-sentiment?${symbolParams()}`);
  const series = await resp.json();
  renderPriceSentiment(series);
}

// ---------- distribution (heatmaps) + correlation bars (driven by same data) ----------
async function loadDistribution() {
  const resp = await fetch(`${API}/analysis/distribution?${symbolParams()}&return_type=${currentReturnType}`);
  const data = await resp.json();
  renderDistributionHeatmaps(data);
  renderCorrelationBars(data);
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
  if (selected.size === 0) { alert("Select one equity first."); return; }
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
    // Same symbol + same params -> the benchmark comparison.
    await runComparison(symbol, params);
  } catch (e) {
    summary.innerHTML = `<div class="status error" style="display:block;">${e.message}</div>`;
    clearComparison();
  }
}

// ---------- strategy comparison (Simple vs Benchmark) ----------
async function runComparison(symbol, params) {
  const box = document.getElementById("cmp-summary");
  box.innerHTML = `<div class="loading">Comparing strategies on <b>${symbol}</b>...</div>`;
  Plotly.purge("cmp-curve");
  document.getElementById("cmp-heatmap").innerHTML = "";
  try {
    const resp = await fetch(`${API}/backtest/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, params }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || resp.statusText);
    renderComparisonHeatmap(data);
    renderComparisonSummary(data);
    renderComparisonCurve(data);
  } catch (e) {
    box.innerHTML = `<div class="status error" style="display:block;">${e.message}</div>`;
  }
}

// Formats a metric fraction/ratio for display.
function fmtMetric(key, v) {
  if (v == null || !isFinite(v)) return "—";
  if (key === "sharpe_ratio") return (v >= 0 ? "+" : "") + v.toFixed(2);
  return (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + "%";
}

// 4 metrics (rows) x 2 strategies (cols). The better value on each row is
// highlighted; for Max Drawdown the less negative value is the better one.
function renderComparisonHeatmap(data) {
  const strategies = data.strategies;
  const rows = data.metric_keys.map((key, i) => {
    const values = strategies.map(s => s.metrics[key]);
    const best = Math.max(...values);
    const allEqual = values.every(v => v === values[0]);
    const cells = strategies.map((s, j) => {
      const isBest = !allEqual && values[j] === best;
      const cls = allEqual ? "cmp-tie" : (isBest ? "cmp-win" : "cmp-lose");
      const badge = isBest ? '<span class="cmp-star">★</span>' : "";
      return `<td class="cmp-cell ${cls}">${badge}${fmtMetric(key, values[j])}</td>`;
    }).join("");
    return `<tr><th scope="row">${data.metric_labels[i]}</th>${cells}</tr>`;
  }).join("");

  const head = strategies.map(s => `<th>${escapeHtml(s.name)}</th>`).join("");
  document.getElementById("cmp-heatmap").innerHTML = `
    <table class="cmp-table">
      <thead><tr><th>Metric</th>${head}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="cmp-legend">
      <span class="cmp-star">★</span> marks the better value on each metric.
      Max Drawdown is shown as a negative number, so a <b>smaller loss</b> is better.
      Both strategies use the same data, window and starting capital; Buy &amp; Hold is fully
      invested, while the Simple Strategy only deploys <b>trade size</b> when a signal fires.
    </p>
  `;
}

function renderComparisonSummary(data) {
  const cards = data.strategies.map(s => {
    const ret = s.final_capital - s.initial_capital;
    const cls = ret >= 0 ? "pnl-pos" : "pnl-neg";
    return `
      <div class="cmp-chip">
        <div class="cmp-chip-name">${escapeHtml(s.name)}</div>
        <div class="cmp-chip-value ${cls}">${s.final_capital.toFixed(2)}</div>
        <div class="cmp-chip-meta">
          final capital · <span class="${cls}">${ret >= 0 ? "+" : ""}${ret.toFixed(2)}</span>
          · ${s.n_trades} closed trade${s.n_trades === 1 ? "" : "s"}
        </div>
      </div>
    `;
  }).join("");

  // Annualised figures are unstable on a short window — say so rather than
  // letting a 2-month CAGR be read as a yearly expectation.
  const shortWindow = data.n_days > 0 && data.n_days < 120;
  const warn = shortWindow ? `
    <p class="cmp-warning">
      Window is only <b>${data.n_days} trading days</b> (${data.start} → ${data.end}).
      CAGR and Sharpe are annualised, so treat them as indicative only.
    </p>` : "";

  document.getElementById("cmp-summary").innerHTML = `
    <div class="cmp-chips">${cards}</div>
    ${warn}
  `;
}

function renderComparisonCurve(data) {
  const colors = ["#1f77b4", "#ff7f0e"];
  const traces = data.strategies.map((s, i) => ({
    x: s.curve.map(p => p.date),
    y: s.curve.map(p => p.value),
    type: "scatter",
    mode: "lines",
    name: s.name,
    line: { width: 2.5, color: colors[i % colors.length] },
    hovertemplate: `<b>${escapeHtml(s.name)}</b><br>%{x|%Y-%m-%d}<br>Value: %{y:.2f}<extra></extra>`,
  }));

  const base = data.strategies[0] ? data.strategies[0].initial_capital : 100;
  const layout = {
    title: `${data.symbol}: equity curve — Simple vs Benchmark`,
    xaxis: { title: "Date" },
    yaxis: { title: "Portfolio value" },
    hovermode: "x unified",
    height: 420,
    legend: { orientation: "h", y: -0.2 },
    margin: { t: 60, l: 60, r: 20, b: 60 },
    shapes: [{
      type: "line", xref: "paper", yref: "y",
      x0: 0, x1: 1, y0: base, y1: base,
      line: { color: "#a0aec0", dash: "dash", width: 1 },
    }],
  };
  Plotly.newPlot("cmp-curve", traces, layout, { responsive: true });
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
  // Single-equity selection: radios sharing one name, so picking a symbol
  // replaces the previous one instead of adding to it.
  container.innerHTML = filtered.map(s => `
    <label class="equity-item">
      <input type="radio" name="equity" data-symbol="${s}" ${selected.has(s) ? "checked" : ""}>
      <span class="equity-symbol">${s}</span>
    </label>
  `).join("");
  container.querySelectorAll("input[type=radio]").forEach(rb => {
    rb.addEventListener("change", () => {
      selected = new Set([rb.dataset.symbol]);
      renderList(document.getElementById("search").value);
      refreshBacktestSymbolDropdown();
      clearComparison();
      loadAll();
    });
  });
  document.getElementById("selected-count").textContent = selected.size;
  refreshBacktestSymbolDropdown();
}

function fmt(v) { return v == null ? "N/A" : v.toFixed(3); }

function renderPriceSentiment(series) {
  if (!series.length) {
    Plotly.purge("price-sentiment");
    document.getElementById("price-sentiment").innerHTML = "<p class='loading'>No price data for selected symbols.</p>";
    return;
  }
  const traces = [];
  // Track which trace index is a sentiment marker so the click handler
  // can tell lines from markers.
  const markerTraceIdx = new Set();
  for (let i = 0; i < series.length; i++) {
    const s = series[i];
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
      const traceIdx = traces.length;
      markerTraceIdx.add(traceIdx);
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
        customdata: withSent.map(p => [s.symbol, p.sentiment_label, p.sentiment_score]),
        hovertemplate: `<b>${s.symbol}</b> %{x|%Y-%m-%d}<br>Close: %{y:.2f}<br>Sentiment: %{customdata[1]} (%{customdata[2]:.2f})<br><i>%{text}</i><extra></extra>`,
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

  // Click handler: only respond to clicks on sentiment marker traces
  const el = document.getElementById("price-sentiment");
  el.on("plotly_click", (ev) => {
    if (!ev.points || !ev.points.length) return;
    const pt = ev.points[0];
    if (!markerTraceIdx.has(pt.curveNumber)) return;  // ignore line clicks
    const symbol = pt.customdata && pt.customdata[0];
    const date = pt.x;
    if (symbol && date) loadNewsForDay(symbol, date);
  });
  // Reset the news panel on each redraw
  resetNewsPanel();
}

// ---------- news panel (click handler on Price + Sentiment) ----------
function resetNewsPanel() {
  const panel = document.getElementById("news-panel");
  if (panel) {
    panel.innerHTML = `<div class="news-panel-empty">Click a sentiment marker to see the news for that day.</div>`;
  }
}

const newsCache = new Map();

async function loadNewsForDay(symbol, date) {
  const panel = document.getElementById("news-panel");
  panel.innerHTML = `<div class="news-panel-empty">Loading news for ${symbol}…</div>`;
  const cacheKey = symbol;
  let allNews;
  if (newsCache.has(cacheKey)) {
    allNews = newsCache.get(cacheKey);
  } else {
    try {
      const resp = await fetch(`${API}/analysis/news?symbol=${encodeURIComponent(symbol)}`);
      const data = await resp.json();
      allNews = data.items || [];
      newsCache.set(cacheKey, allNews);
    } catch (e) {
      panel.innerHTML = `<div class="status error" style="display:block;">Failed to load news: ${e.message}</div>`;
      return;
    }
  }
  // Filter to the clicked date
  const dateStr = String(date).slice(0, 10);
  const items = allNews.filter(n => String(n.date).slice(0, 10) === dateStr);
  renderNewsPanel(symbol, dateStr, items);
}

function renderNewsPanel(symbol, dateStr, items) {
  const panel = document.getElementById("news-panel");
  if (!items.length) {
    panel.innerHTML = `
      <h4>${symbol} — ${dateStr}</h4>
      <div class="news-meta">No news found for this date.</div>
    `;
    return;
  }
  const html = `
    <h4>${symbol} — ${dateStr}</h4>
    <div class="news-meta">${items.length} headline${items.length > 1 ? 's' : ''}</div>
    ${items.map(n => {
      const label = (n.sentiment_label || 'neutral').toLowerCase();
      const labelCls = label === 'positive' ? 'label-pos' : label === 'negative' ? 'label-neg' : 'label-neu';
      const score = n.finbert_score != null ? n.finbert_score.toFixed(2) : '—';
      const cleanText = n.text ? cleanNewsText(n.text) : '';
      return `
        <div class="news-item">
          <div class="headline">${escapeHtml(n.headline || '(no headline)')}</div>
          <div class="meta">
            <span>${escapeHtml(n.source || 'unknown')}</span>
            <span class="${labelCls}">${label} (${score})</span>
          </div>
          ${cleanText ? `<div class="summary">${escapeHtml(cleanText)}</div>` : ''}
        </div>
      `;
    }).join('')}
  `;
  panel.innerHTML = html;
}

// Strip HTML tags, decode entities, remove boilerplate, keep only the core text.
function cleanNewsText(raw) {
  if (!raw) return '';
  let text = String(raw);
  // Strip HTML tags
  text = text.replace(/<[^>]+>/g, ' ');
  // Decode common HTML entities
  text = text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&#\d+;/g, '');
  // Remove boilerplate / promotional patterns
  const boilerplate = [
    /Read Also:.*$/gim,
    /Photo Courtesy:.*$/gim,
    /\[.*?\]\([^)]+\)/g,         // markdown links [text](url)
    /https?:\/\/\S+/g,           // raw URLs
  ];
  for (const pat of boilerplate) {
    text = text.replace(pat, '');
  }
  // Collapse whitespace
  text = text.replace(/\s+/g, ' ').trim();
  // Take only the first 2 sentences (core news content)
  const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
  text = sentences.slice(0, 2).join('').trim();
  if (text.length > 400) {
    text = text.slice(0, 400).trim();
    const lastSpace = text.lastIndexOf(' ');
    if (lastSpace > 200) text = text.slice(0, lastSpace) + '…';
  }
  return text;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ---------- distribution heatmaps (with percentage text on each cell) ----------
function renderDistributionHeatmaps(data) {
  const el = document.getElementById("distribution");
  if (!data.rows.length) {
    Plotly.purge(el);
    el.innerHTML = "<p class='loading'>Not enough data for distribution plot (need >= 5 sentiment observations per symbol).</p>";
    return;
  }
  // One heatmap per symbol, stacked vertically.  Each cell shows the % of data
  // points in that bucket (text overlay), matching notebooks/demo.ipynb.
  // We use the original range labels ("0.123 to 0.456") and a tall figure
  // (450px per row, like the notebook) so they fit without overlapping.
  const n = data.rows.length;
  const traces = [];
  for (let idx = 0; idx < n; idx++) {
    const r = data.rows[idx];
    const xa = `x${idx + 1}`;
    const ya = `y${idx + 1}`;
    // Build percentage text for each cell (e.g. "12.3%" or "0.0%"), matching
    // notebooks/demo.ipynb which shows the percentage on every cell.
    const text = r.heatmap_z.map(row => row.map(v => v.toFixed(1) + "%"));
    traces.push({
      type: "heatmap",
      z: r.heatmap_z,
      x: r.heatmap_x_labels,
      y: r.heatmap_y_labels,
      // Custom white-to-blue colorscale (matches plotly.py's "Blues" but
      // defined explicitly).  Darkest stop is rgb(49, 130, 189) — clearly
      // "dark blue" but not near-black, so the percentage text stays readable
      // and the max cell doesn't visually dominate the plot.
      colorscale: [
        [0.0,  "rgb(247, 251, 255)"],
        [0.125, "rgb(222, 235, 247)"],
        [0.25,  "rgb(198, 219, 239)"],
        [0.375, "rgb(173, 205, 231)"],
        [0.5,   "rgb(148, 191, 223)"],
        [0.625, "rgb(123, 177, 215)"],
        [0.75,  "rgb(98, 163, 207)"],
        [0.875, "rgb(73, 149, 199)"],
        [1.0,   "rgb(49, 130, 189)"],
      ],
      zmin: 0,                    // 0% maps to white
      // zmax intentionally NOT set: Plotly auto-scales to the actual data
      // maximum, so the gradient always spans the full data range.  If we
      // hard-coded zmax: 100, most cells would look pale (since the data
      // max is usually ~10-20%).
      showscale: idx === 0,
      colorbar: idx === 0 ? { title: { text: "%" }, len: 0.4, y: 0.8 } : undefined,
      xaxis: xa, yaxis: ya,
      text: text,
      texttemplate: "%{text}",
      textfont: { size: 9, color: "black" },
      hovertemplate: `Score: %{x}<br>Return: %{y}<br>Pct: %{z:.1f}%<extra></extra>`,
    });
  }
  const layout = {
    title: { text: `Distribution by Equity (return = ${data.return_type})` },
    grid: { rows: n, columns: 1, pattern: "independent" },
    showlegend: false,
    height: Math.max(400, 200 * n + 80),
    margin: { l: 110, r: 30, t: 60, b: 50 },
  };
  for (let idx = 0; idx < n; idx++) {
    const isLast = idx === n - 1;
    const xa = `xaxis${idx + 1}`;
    const ya = `yaxis${idx + 1}`;
    layout[xa] = {
      tickangle: -45,
      tickfont: { size: 9 },
      automargin: true,
      title: isLast ? { text: "FinBERT score bucket" } : undefined,
    };
    layout[ya] = {
      tickfont: { size: 9 },
      automargin: true,
      title: isLast ? { text: "Log return bucket" } : undefined,
    };
  }
  Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false });
}

// ---------- correlation bars per symbol ----------
function renderCorrelationBars(data) {
  const el = document.getElementById("correlation-bars");
  if (!data.rows.length) {
    Plotly.purge(el);
    el.innerHTML = "<p class='loading'>No correlation data for selected symbols.</p>";
    return;
  }
  const n = data.rows.length;
  const traces = [];
  for (let idx = 0; idx < n; idx++) {
    const r = data.rows[idx];
    const xa = `x${idx + 1}`;
    const ya = `y${idx + 1}`;
    traces.push({
      type: "bar",
      x: r.correlation.map(c => c.name),
      y: r.correlation.map(c => c.value ?? 0),
      marker: { color: ["#1f77b4", "#ff7f0e", "#2ca02c"] },
      text: r.correlation.map(c => c.value == null ? "N/A" : c.value.toFixed(3)),
      textposition: "outside",
      xaxis: xa, yaxis: ya,
      showlegend: false,
      hovertemplate: "%{x}: %{y:.3f}<extra></extra>",
    });
  }
  const layout = {
    title: { text: "Correlation by Equity" },
    grid: { rows: n, columns: 1, pattern: "independent" },
    showlegend: false,
    height: Math.max(300, 160 * n + 80),
    margin: { l: 60, r: 30, t: 60, b: 40 },
  };
  for (let idx = 0; idx < n; idx++) {
    const isLast = idx === n - 1;
    const ya = `yaxis${idx + 1}`;
    layout[ya] = { range: [-1, 1], title: isLast ? { text: "Correlation" } : undefined };
    layout[`xaxis${idx + 1}`] = { title: isLast ? { text: "Return type" } : undefined };
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
