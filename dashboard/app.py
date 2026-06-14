import sys
sys.path.insert(0, '/home/vision/projects/people-analytics')

from flask import Flask, render_template_string, jsonify, request
from shared.database import (
    get_traffic_summary,
    get_unique_visitors,
    get_demographics_summary,
    get_hourly_traffic_pattern,
    get_dwell_summary,
    get_attention_summary,
)
from shared.config import DASHBOARD_HOST, DASHBOARD_PORT, FACE_CAMERA_ID

app = Flask(__name__)

VALID_PERIODS = ('day', 'week', 'month')


@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/summary')
def api_summary():
    period = request.args.get('period', 'day')
    if period not in VALID_PERIODS:
        period = 'day'

    traffic = get_traffic_summary(period)
    unique_visitors = {r['period_label']: r['unique_visitors'] for r in get_unique_visitors(period)}
    dwell = {r['period_label']: r for r in get_dwell_summary(period, camera_id=FACE_CAMERA_ID)}
    attention = {r['period_label']: r for r in get_attention_summary(period)}

    trend = []
    for row in traffic:
        label = row['period_label']
        attn = attention.get(label, {'attention_ratio': 0, 'sample_count': 0})
        dwell_row = dwell.get(label, {'avg_dwell': 0, 'avg_attentive_dwell': 0})
        trend.append({
            'period_label':    label,
            'total_count':     row['total_count'],
            'avg_count':       row['avg_count'],
            'peak_count':      row['peak_count'],
            'unique_visitors': unique_visitors.get(label, 0),
            'avg_dwell':       dwell_row['avg_dwell'],
            'attention_ratio': attn['attention_ratio'],
            'attentive_dwell': dwell_row['avg_attentive_dwell'],
        })

    # Demographics for the most recent period only
    demo_rows = get_demographics_summary(period)
    latest_label = trend[-1]['period_label'] if trend else None
    demographics = [r for r in demo_rows if r['period_label'] == latest_label]

    return jsonify({
        'period':        period,
        'trend':         trend,
        'demographics':  demographics,
        'hourly_pattern': get_hourly_traffic_pattern(days=30),
    })


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Field Activity Log</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  :root {
    --bg:       #1b1f23;
    --panel:    #232830;
    --line:     #343b45;
    --text:     #e8e6e1;
    --text-dim: #9aa0a8;
    --accent:   #c1714a;
    --accent2:  #5a8a82;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'IBM Plex Sans', sans-serif;
    -webkit-font-smoothing: antialiased;
  }

  .wrap {
    max-width: 1100px;
    margin: 0 auto;
    padding: 32px 24px 64px;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    flex-wrap: wrap;
    gap: 16px;
    border-bottom: 1px solid var(--line);
    padding-bottom: 20px;
    margin-bottom: 28px;
  }

  .title-block .eyebrow {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.12em;
    color: var(--accent);
    text-transform: uppercase;
    margin-bottom: 6px;
  }

  .title-block h1 {
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }

  .title-block .sub {
    font-size: 13px;
    color: var(--text-dim);
    margin-top: 4px;
    font-family: 'IBM Plex Mono', monospace;
  }

  .period-toggle {
    display: flex;
    border: 1px solid var(--line);
    border-radius: 6px;
    overflow: hidden;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
  }

  .period-toggle button {
    background: transparent;
    border: none;
    color: var(--text-dim);
    padding: 8px 18px;
    cursor: pointer;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    transition: background 0.15s, color 0.15s;
  }

  .period-toggle button + button {
    border-left: 1px solid var(--line);
  }

  .period-toggle button.active {
    background: var(--accent);
    color: #1b1f23;
  }

  .period-toggle button:hover:not(.active) {
    color: var(--text);
    background: #2c323b;
  }

  .section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin: 36px 0 14px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .section-label::after {
    content: "";
    flex: 1;
    height: 1px;
    background: var(--line);
  }

  .stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1px;
    background: var(--line);
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
  }

  .stat-cell {
    background: var(--panel);
    padding: 18px 20px;
  }

  .stat-cell .value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 30px;
    font-weight: 500;
    line-height: 1.1;
  }

  .stat-cell .value .unit {
    font-size: 14px;
    color: var(--text-dim);
    margin-left: 4px;
  }

  .stat-cell .label {
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 6px;
    letter-spacing: 0.02em;
  }

  .panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 20px;
  }

  .panel-grid {
    display: grid;
    grid-template-columns: 1.4fr 1fr;
    gap: 16px;
  }

  @media (max-width: 760px) {
    .panel-grid { grid-template-columns: 1fr; }
  }

  .panel h2 {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 14px;
  }

  canvas { max-width: 100%; }

  .heatmap {
    display: flex;
    gap: 2px;
    margin-top: 6px;
  }

  .heatmap .cell {
    flex: 1;
    height: 48px;
    border-radius: 3px;
    background: var(--accent2);
    position: relative;
    transition: opacity 0.15s;
  }

  .heatmap .cell:hover {
    opacity: 0.7;
  }

  .heatmap .cell .tip {
    position: absolute;
    bottom: 56px;
    left: 50%;
    transform: translateX(-50%);
    background: #11141a;
    border: 1px solid var(--line);
    color: var(--text);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 4px;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.15s;
  }

  .heatmap .cell:hover .tip {
    opacity: 1;
  }

  .heatmap-labels {
    display: flex;
    justify-content: space-between;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 8px;
  }

  .demo-table {
    width: 100%;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    border-collapse: collapse;
  }

  .demo-table th {
    text-align: left;
    font-weight: 500;
    color: var(--text-dim);
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.06em;
    padding: 6px 8px;
    border-bottom: 1px solid var(--line);
  }

  .demo-table td {
    padding: 7px 8px;
    border-bottom: 1px solid #2a303a;
  }

  .demo-table tr:last-child td { border-bottom: none; }

  .demo-table .bar-cell {
    width: 40%;
  }

  .demo-bar {
    height: 8px;
    border-radius: 2px;
    background: var(--accent2);
  }

  .empty-note {
    color: var(--text-dim);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    padding: 12px 0;
  }

  footer {
    margin-top: 40px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    text-align: center;
  }
</style>
</head>
<body>
<div class="wrap">

  <header>
    <div class="title-block">
      <div class="eyebrow">Site Activity Log</div>
      <h1>People Analytics</h1>
      <div class="sub" id="rangeLabel">Loading range&hellip;</div>
    </div>
    <div class="period-toggle" id="periodToggle">
      <button data-period="day" class="active">Day</button>
      <button data-period="week">Week</button>
      <button data-period="month">Month</button>
    </div>
  </header>

  <div class="stat-grid" id="statGrid">
    <!-- filled by JS -->
  </div>

  <div class="section-label">Foot traffic &amp; dwell</div>
  <div class="panel">
    <h2>Average occupancy &amp; unique visitors over time</h2>
    <canvas id="trafficChart" height="90"></canvas>
  </div>

  <div class="section-label">Hourly pattern (last 30 days)</div>
  <div class="panel">
    <h2>Average activity by hour of day</h2>
    <div class="heatmap" id="heatmap"></div>
    <div class="heatmap-labels">
      <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
    </div>
  </div>

  <div class="section-label">Demographics &amp; attention</div>
  <div class="panel-grid">
    <div class="panel">
      <h2 id="demoTitle">Demographic mix</h2>
      <table class="demo-table" id="demoTable">
        <thead>
          <tr><th>Gender</th><th>Age group</th><th class="bar-cell">Share</th><th>Count</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
    <div class="panel">
      <h2>Attention ratio over time</h2>
      <canvas id="attentionChart" height="160"></canvas>
    </div>
  </div>

  <footer>Data refreshes on load &middot; switch ranges above</footer>
</div>

<script>
let trafficChart, attentionChart;
let currentPeriod = 'day';

const RANGE_LABELS = {
  day:   'Daily totals, last 30 days',
  week:  'Weekly totals, last 12 weeks',
  month: 'Monthly totals, last 12 months',
};

function fmtLabel(period, label) {
  if (period === 'day') {
    const d = new Date(label + 'T00:00:00');
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }
  if (period === 'week') {
    return label.replace(/^\\d{4}-W/, 'Wk ');
  }
  if (period === 'month') {
    const [y, m] = label.split('-');
    const d = new Date(parseInt(y), parseInt(m) - 1, 1);
    return d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' });
  }
  return label;
}

function initCharts() {
  const opts = {
    responsive: true,
    plugins: { legend: { labels: { color: '#e8e6e1', font: { family: 'IBM Plex Mono', size: 11 } } } },
    scales: {
      x: { ticks: { color: '#9aa0a8', font: { family: 'IBM Plex Mono', size: 11 } }, grid: { color: '#343b45' } },
      y: { ticks: { color: '#9aa0a8', font: { family: 'IBM Plex Mono', size: 11 } }, grid: { color: '#343b45' }, beginAtZero: true }
    }
  };

  trafficChart = new Chart(document.getElementById('trafficChart'), {
    type: 'bar',
    data: {
      labels: [],
      datasets: [
        { label: 'Avg. occupancy', data: [], backgroundColor: '#c1714a', borderRadius: 3, order: 2 },
        { label: 'Unique visitors', data: [], type: 'line', borderColor: '#5a8a82', backgroundColor: '#5a8a82', tension: 0.3, order: 1, yAxisID: 'y' }
      ]
    },
    options: opts
  });

  attentionChart = new Chart(document.getElementById('attentionChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Attention ratio',
        data: [],
        borderColor: '#c1714a',
        backgroundColor: 'rgba(193,113,74,0.12)',
        fill: true,
        tension: 0.3
      }]
    },
    options: {
      ...opts,
      scales: {
        ...opts.scales,
        y: { ...opts.scales.y, min: 0, max: 1, ticks: { ...opts.scales.y.ticks, callback: v => (v*100) + '%' } }
      }
    }
  });
}

function renderStats(trend) {
  const grid = document.getElementById('statGrid');
  if (!trend.length) {
    grid.innerHTML = '<div class="stat-cell"><div class="empty-note">No data yet for this range.</div></div>';
    return;
  }
  const latest = trend[trend.length - 1];
  const cells = [
    { value: latest.avg_count.toFixed(1), unit: '', label: 'Avg. occupancy' },
    { value: latest.unique_visitors, unit: '', label: 'Unique visitors' },
    { value: latest.peak_count, unit: '', label: 'Peak count' },
    { value: latest.avg_dwell.toFixed(1), unit: 's', label: 'Avg. dwell time' },
    { value: (latest.attention_ratio * 100).toFixed(0), unit: '%', label: 'Attention ratio' },
    { value: latest.attentive_dwell.toFixed(1), unit: 's', label: 'Avg. attentive time' },
  ];
  grid.innerHTML = cells.map(c => `
    <div class="stat-cell">
      <div class="value">${c.value}<span class="unit">${c.unit}</span></div>
      <div class="label">${c.label}</div>
    </div>
  `).join('');
}

function renderTrafficChart(trend, period) {
  trafficChart.data.labels = trend.map(r => fmtLabel(period, r.period_label));
  trafficChart.data.datasets[0].data = trend.map(r => r.avg_count);
  trafficChart.data.datasets[1].data = trend.map(r => r.unique_visitors);
  trafficChart.update();
}

function renderAttentionChart(trend, period) {
  attentionChart.data.labels = trend.map(r => fmtLabel(period, r.period_label));
  attentionChart.data.datasets[0].data = trend.map(r => r.attention_ratio);
  attentionChart.update();
}

function renderHeatmap(hourly) {
  const max = Math.max(1, ...hourly.map(h => h.avg_count));
  const el = document.getElementById('heatmap');
  el.innerHTML = hourly.map(h => {
    const intensity = h.avg_count / max;
    const opacity = 0.12 + intensity * 0.88;
    const hh = String(h.hour).padStart(2, '0') + ':00';
    return `<div class="cell" style="opacity:${opacity.toFixed(2)}">
      <div class="tip">${hh} &middot; ${h.avg_count.toFixed(1)} avg</div>
    </div>`;
  }).join('');
}

function renderDemographics(demographics, period, latestLabel) {
  const tbody = document.querySelector('#demoTable tbody');
  const title = document.getElementById('demoTitle');
  const table = document.getElementById('demoTable');
  const panel = table.parentElement;
  const existingNote = panel.querySelector('.empty-note');

  if (!demographics.length) {
    tbody.innerHTML = '';
    title.textContent = 'Demographic mix';
    table.style.display = 'none';
    if (!existingNote) {
      const note = document.createElement('div');
      note.className = 'empty-note';
      note.textContent = 'No demographic samples for this period yet.';
      panel.appendChild(note);
    }
    return;
  }

  table.style.display = '';
  if (existingNote) existingNote.remove();

  title.textContent = 'Demographic mix \u2014 ' + fmtLabel(period, latestLabel);

  const total = demographics.reduce((s, d) => s + d.count, 0);
  const sorted = [...demographics].sort((a, b) => b.count - a.count);

  tbody.innerHTML = sorted.map(d => {
    const pct = total ? (d.count / total * 100) : 0;
    return `<tr>
      <td>${d.gender || '\u2014'}</td>
      <td>${d.age_group || '\u2014'}</td>
      <td class="bar-cell"><div class="demo-bar" style="width:${pct.toFixed(1)}%"></div></td>
      <td>${d.count}</td>
    </tr>`;
  }).join('');
}

function update(period) {
  fetch('/api/summary?period=' + period)
    .then(r => r.json())
    .then(data => {
      document.getElementById('rangeLabel').textContent = RANGE_LABELS[period] || '';
      renderStats(data.trend);
      renderTrafficChart(data.trend, period);
      renderAttentionChart(data.trend, period);
      renderHeatmap(data.hourly_pattern);
      const latestLabel = data.trend.length ? data.trend[data.trend.length - 1].period_label : null;
      renderDemographics(data.demographics, period, latestLabel);
    });
}

document.getElementById('periodToggle').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  document.querySelectorAll('#periodToggle button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentPeriod = btn.dataset.period;
  update(currentPeriod);
});

initCharts();
update(currentPeriod);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print(f"[Dashboard] Starting at http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)
