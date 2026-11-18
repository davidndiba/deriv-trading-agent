"""The dashboard's HTML/JS, kept as a plain string rather than a
templating engine — no new dependency, and the page is simple enough
(a handful of cards, an SVG equity curve, a table) not to need one.
Fetches the existing read-only JSON endpoints client-side; it cannot
place, approve, or reject a trade — see api/main.py's module docstring.
"""

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deriv Trading Agent</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 24px;
         background: #0b0f14; color: #e6e6e6; max-width: 960px; }
  h1 { font-size: 1.25rem; margin: 0 0 4px; }
  .sub { color: #8a93a1; margin-bottom: 20px; font-size: 0.9rem; }
  .cards { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #262c36; border-radius: 8px;
          padding: 14px 18px; min-width: 150px; flex: 1 1 150px; }
  .card .label { font-size: 0.72rem; color: #8a93a1; text-transform: uppercase;
                 letter-spacing: 0.04em; }
  .card .value { font-size: 1.6rem; font-weight: 600; margin-top: 4px; }
  .pos { color: #3fb950; }
  .neg { color: #f85149; }
  select { background: #161b22; color: #e6e6e6; border: 1px solid #262c36;
           border-radius: 6px; padding: 6px 10px; font-size: 0.9rem; }
  a.csv-link { color: #58a6ff; text-decoration: none; font-size: 0.85rem; margin-left: 12px; }
  a.csv-link:hover { text-decoration: underline; }
  .audit { color: #d29922; font-weight: 600; }
  .corr-strong { font-weight: 600; }
  svg { background: #161b22; border: 1px solid #262c36; border-radius: 8px;
        width: 100%; height: 180px; display: block; }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.85rem; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #262c36; }
  th { color: #8a93a1; font-weight: 500; }
  .section-title { margin-top: 28px; margin-bottom: 8px; font-size: 1rem; }
  .note { font-size: 0.78rem; color: #8a93a1; margin-top: 4px; }
</style>
</head>
<body>
  <h1>Deriv Trading Agent</h1>
  <div class="sub">
    Read-only — nothing on this page can place, approve, or reject a trade.
    <select id="env"><option value="demo">demo</option><option value="live">live</option></select>
    <a class="csv-link" id="csvLink" href="/trades.csv?env=demo" download>Download CSV</a>
  </div>

  <div class="cards">
    <div class="card"><div class="label">Today's P&amp;L</div><div class="value" id="pnlToday">—</div></div>
    <div class="card"><div class="label">Closed trades (shown)</div><div class="value" id="closedCount">—</div></div>
    <div class="card"><div class="label">Win rate</div><div class="value" id="winRate">—</div></div>
    <div class="card"><div class="label">Open positions</div><div class="value" id="openCount">—</div></div>
  </div>

  <div class="section-title">Equity curve (cumulative profit, closed trades, oldest to newest)</div>
  <svg id="equityChart" viewBox="0 0 800 180" preserveAspectRatio="none"></svg>
  <div class="note" id="equityNote"></div>

  <div class="section-title">Recent trades</div>
  <table>
    <thead><tr><th>Symbol</th><th>Direction</th><th>Status</th><th>Stake</th><th>Profit</th><th>Opened</th></tr></thead>
    <tbody id="tradesBody"></tbody>
  </table>

  <div class="section-title">Recent backtests</div>
  <table>
    <thead><tr><th>Symbol</th><th>Label</th><th>Closed</th><th>Win rate</th><th>Avg R</th><th>Max DD (R)</th><th></th></tr></thead>
    <tbody id="backtestsBody"></tbody>
  </table>
  <div class="note" id="backtestsNote"></div>

  <div class="section-title">Correlation matrix</div>
  <table>
    <thead><tr><th>Pair</th><th>Correlation</th></tr></thead>
    <tbody id="correlationBody"></tbody>
  </table>
  <div class="note" id="correlationNote"></div>

<script>
const SVG_NS = "http://www.w3.org/2000/svg";

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(url + " -> " + res.status);
  return res.json();
}

function fmtMoney(n) {
  const sign = n >= 0 ? "+" : "";
  return sign + "$" + n.toFixed(2);
}

function renderEquityCurve(trades) {
  const svg = document.getElementById("equityChart");
  const note = document.getElementById("equityNote");
  svg.innerHTML = "";

  const closed = trades.filter(t => t.status === "won" || t.status === "lost").slice().reverse();
  if (closed.length === 0) {
    note.textContent = "No closed trades yet.";
    return;
  }
  note.textContent = closed.length + " closed trade(s) plotted.";

  let running = 0;
  const points = closed.map(t => (running += (t.profit || 0)));
  const lo = Math.min(0, ...points);
  const hi = Math.max(0, ...points);
  const span = (hi - lo) || 1;
  const w = 800, h = 180, pad = 10;
  const coords = points.map((v, i) => {
    const x = pad + (i / Math.max(1, points.length - 1)) * (w - 2 * pad);
    const y = h - pad - ((v - lo) / span) * (h - 2 * pad);
    return x + "," + y;
  });

  const poly = document.createElementNS(SVG_NS, "polyline");
  poly.setAttribute("points", coords.join(" "));
  poly.setAttribute("fill", "none");
  poly.setAttribute("stroke", points[points.length - 1] >= 0 ? "#3fb950" : "#f85149");
  poly.setAttribute("stroke-width", "2");
  svg.appendChild(poly);
}

function renderTradesTable(trades) {
  const body = document.getElementById("tradesBody");
  body.innerHTML = "";
  trades.slice(0, 50).forEach(t => {
    const tr = document.createElement("tr");
    const profit = t.profit == null ? "—" : fmtMoney(t.profit);
    const cls = (t.profit || 0) >= 0 ? "pos" : "neg";
    tr.innerHTML =
      "<td>" + t.symbol + "</td>" +
      "<td>" + t.direction + "</td>" +
      "<td>" + t.status + "</td>" +
      "<td>$" + t.stake.toFixed(2) + "</td>" +
      "<td class=\\"" + cls + "\\">" + profit + "</td>" +
      "<td>" + (t.opened_at || "").replace("T", " ").slice(0, 19) + "</td>";
    body.appendChild(tr);
  });
}

function renderBacktestsTable(backtests) {
  const body = document.getElementById("backtestsBody");
  const note = document.getElementById("backtestsNote");
  body.innerHTML = "";
  if (backtests.length === 0) {
    note.textContent = "No backtests logged yet — run one of the run_phase{2,7,9,10,12}_*.py scripts.";
    return;
  }
  note.textContent = backtests.length + " backtest run(s) shown.";
  backtests.slice(0, 30).forEach(b => {
    const tr = document.createElement("tr");
    const auditFlag = b.needs_audit ? '<span class="audit">*** audit</span>' : "";
    tr.innerHTML =
      "<td>" + b.symbol + "</td>" +
      "<td>" + (b.label || "—") + "</td>" +
      "<td>" + b.closed_trades + "</td>" +
      "<td>" + (b.win_rate * 100).toFixed(1) + "%</td>" +
      "<td>" + b.avg_r_multiple.toFixed(2) + "</td>" +
      "<td>" + b.max_drawdown_r.toFixed(2) + "</td>" +
      "<td>" + auditFlag + "</td>";
    body.appendChild(tr);
  });
}

function renderCorrelationTable(correlation) {
  const body = document.getElementById("correlationBody");
  const note = document.getElementById("correlationNote");
  body.innerHTML = "";
  const pairs = correlation.pairs || [];
  if (pairs.length === 0) {
    note.textContent = "No correlation matrix logged yet — run run_phase17_correlation_matrix.py.";
    return;
  }
  note.textContent = "Computed at " + (correlation.computed_at || "unknown") + ".";
  pairs
    .slice()
    .sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation))
    .forEach(p => {
      const tr = document.createElement("tr");
      const strong = Math.abs(p.correlation) >= 0.7 ? "corr-strong" : "";
      const cls = p.correlation >= 0 ? "pos" : "neg";
      tr.innerHTML =
        "<td>" + p.symbol_a + " / " + p.symbol_b + "</td>" +
        "<td class=\\"" + cls + " " + strong + "\\">" + p.correlation.toFixed(3) + "</td>";
      body.appendChild(tr);
    });
}

async function refresh() {
  const env = document.getElementById("env").value;
  document.getElementById("csvLink").href = "/trades.csv?env=" + env;
  try {
    const [trades, pnl, backtests, correlation] = await Promise.all([
      fetchJSON("/trades?env=" + env + "&limit=200"),
      fetchJSON("/trades/pnl/today?env=" + env),
      fetchJSON("/backtests?limit=30"),
      fetchJSON("/correlation"),
    ]);
    const closed = trades.filter(t => t.status === "won" || t.status === "lost");
    const wins = closed.filter(t => t.status === "won").length;
    const open = trades.filter(t => t.status === "open").length;

    const pnlEl = document.getElementById("pnlToday");
    pnlEl.textContent = fmtMoney(pnl.realized_pnl_today);
    pnlEl.className = "value " + (pnl.realized_pnl_today >= 0 ? "pos" : "neg");
    document.getElementById("closedCount").textContent = closed.length;
    document.getElementById("winRate").textContent =
      closed.length ? ((wins / closed.length) * 100).toFixed(1) + "%" : "—";
    document.getElementById("openCount").textContent = open;

    renderEquityCurve(trades);
    renderTradesTable(trades);
    renderBacktestsTable(backtests);
    renderCorrelationTable(correlation);
  } catch (err) {
    console.error("dashboard refresh failed", err);
  }
}

document.getElementById("env").addEventListener("change", refresh);
refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
"""
