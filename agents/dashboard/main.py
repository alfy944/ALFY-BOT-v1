"""
Trading Dashboard v2.0 - Modern Real-Time Interface
"""

import os
import json
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="Trading Dashboard", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

POSITION_MANAGER_URL = os.getenv("POSITION_MANAGER_URL", "http://position-manager-agent:8000")
MASTER_AI_URL = os.getenv("MASTER_AI_URL", "http://master-ai-agent:8000")
LEARNING_AGENT_URL = os.getenv("LEARNING_AGENT_URL", "http://learning-agent:8000")

@app.get("/api/wallet")
async def get_wallet():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{POSITION_MANAGER_URL}/get_wallet_balance")
            if r.status_code == 200:
                return r.json()
    except:
        pass
    return {"equity": 0, "available": 0, "live_pnl": 0}

@app.get("/api/positions")
async def get_positions():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{POSITION_MANAGER_URL}/get_open_positions")
            if r.status_code == 200:
                return r.json()
    except:
        pass
    return {"open_positions": [], "details": [], "count": 0}

@app.get("/api/decisions")
async def get_decisions():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{MASTER_AI_URL}/latest_decisions")
            if r.status_code == 200:
                return r.json()
    except:
        pass
    return {}

@app.get("/api/stats")
async def get_stats():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{LEARNING_AGENT_URL}/stats")
            if r.status_code == 200:
                return r.json()
    except:
        pass
    return {"error": "Learning Agent offline"}

@app.get("/api/equity_history")
async def get_equity_history():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{POSITION_MANAGER_URL}/equity_history")
            if r.status_code == 200:
                return r.json()
    except:
        pass
    return {"history": []}

@app.get("/api/system_status")
async def get_system_status():
    agents = {
        "position_manager": POSITION_MANAGER_URL,
        "master_ai": MASTER_AI_URL,
        "learning_agent": LEARNING_AGENT_URL
    }
    status = {}
    async with httpx.AsyncClient(timeout=3) as client:
        for name, url in agents.items():
            try:
                r = await client.get(f"{url}/health")
                status[name] = "online" if r.status_code == 200 else "error"
            except:
                status[name] = "offline"
    return status

@app.get("/health")
def health():
    return {"status": "ok", "service": "dashboard", "version": "2.0.0"}

DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mitragliere Bot V2 - Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a25;
            --bg-card-hover: #22222f;
            --border-color: #2a2a3a;
            --text-primary: #ffffff;
            --text-secondary: #8b8b9e;
            --text-muted: #5a5a6e;
            --accent-green: #00ff88;
            --accent-red: #ff4757;
            --accent-blue: #3b82f6;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Space Grotesk', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: 
                radial-gradient(circle at 20% 80%, rgba(0, 255, 136, 0.03) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(59, 130, 246, 0.03) 0%, transparent 50%);
            pointer-events: none;
            z-index: -1;
        }
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .logo { display: flex; align-items: center; gap: 1rem; }
        .logo-icon {
            width: 48px; height: 48px;
            background: linear-gradient(135deg, #00ff88 0%, #00cc6a 100%);
            border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.5rem;
            box-shadow: 0 0 30px rgba(0, 255, 136, 0.3);
        }
        .logo-text h1 {
            font-size: 1.5rem; font-weight: 700;
            background: linear-gradient(135deg, #00ff88 0%, #00cc6a 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .logo-text span { font-size: 0.75rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }
        .header-status { display: flex; align-items: center; gap: 1.5rem; }
        .status-indicator { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-secondary); }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-green); animation: pulse 2s infinite; }
        .status-dot.offline { background: var(--accent-red); }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .time-display { font-family: 'JetBrains Mono', monospace; font-size: 0.875rem; color: var(--text-muted); }
        .container { max-width: 1800px; margin: 0 auto; padding: 2rem; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 1.5rem; }
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            transition: all 0.3s ease;
        }
        .card:hover { background: var(--bg-card-hover); border-color: var(--accent-green); transform: translateY(-2px); }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
        .card-title { font-size: 0.875rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; }
        .card-icon { font-size: 1.25rem; }
        .metric-value { font-size: 2.5rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; line-height: 1; margin-bottom: 0.5rem; }
        .metric-value.positive { color: var(--accent-green); }
        .metric-value.negative { color: var(--accent-red); }
        .metric-change { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-secondary); }
        .chart-container { height: 300px; position: relative; }
        .chart-controls { display: flex; gap: 0.5rem; }
        .chart-btn {
            padding: 0.5rem 1rem;
            border: 1px solid var(--border-color);
            background: transparent;
            color: var(--text-secondary);
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .chart-btn:hover, .chart-btn.active { background: var(--accent-green); color: var(--bg-primary); border-color: var(--accent-green); }
        .positions-table { width: 100%; border-collapse: collapse; }
        .positions-table th { text-align: left; padding: 1rem; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; border-bottom: 1px solid var(--border-color); }
        .positions-table td { padding: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.875rem; border-bottom: 1px solid var(--border-color); }
        .positions-table tr:hover { background: var(--bg-secondary); }
        .side-badge { padding: 0.25rem 0.75rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .side-badge.long { background: rgba(0, 255, 136, 0.15); color: var(--accent-green); }
        .side-badge.short { background: rgba(255, 71, 87, 0.15); color: var(--accent-red); }
        .decisions-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
        .decision-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 12px; padding: 1rem; transition: all 0.3s ease; }
        .decision-card:hover { border-color: var(--accent-blue); }
        .decision-card.long { border-left: 3px solid var(--accent-green); }
        .decision-card.short { border-left: 3px solid var(--accent-red); }
        .decision-card.hold { border-left: 3px solid var(--text-muted); }
        .decision-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
        .decision-symbol { font-size: 1.125rem; font-weight: 700; }
        .decision-action { padding: 0.25rem 0.75rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .decision-action.long { background: linear-gradient(135deg, #00ff88 0%, #00cc6a 100%); color: var(--bg-primary); }
        .decision-action.short { background: linear-gradient(135deg, #ff4757 0%, #cc3a47 100%); color: white; }
        .decision-action.hold { background: var(--border-color); color: var(--text-secondary); }
        .confidence-bar { height: 4px; background: var(--bg-primary); border-radius: 2px; margin: 0.75rem 0; overflow: hidden; }
        .confidence-fill { height: 100%; background: var(--accent-blue); border-radius: 2px; transition: width 0.5s ease; }
        .decision-reasoning { font-size: 0.75rem; color: var(--text-muted); line-height: 1.5; max-height: 60px; overflow: hidden; }
        .decision-setup { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color); }
        .setup-item { text-align: center; }
        .setup-label { font-size: 0.625rem; color: var(--text-muted); text-transform: uppercase; }
        .setup-value { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; font-weight: 600; }
        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
        .stat-item { text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px; }
        .stat-value { font-size: 1.5rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
        .stat-label { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem; }
        .loading { display: flex; justify-content: center; align-items: center; height: 100px; }
        .loading-spinner { width: 40px; height: 40px; border: 3px solid var(--border-color); border-top-color: var(--accent-green); border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .empty-state { text-align: center; padding: 3rem; color: var(--text-muted); }
        .empty-state-icon { font-size: 3rem; margin-bottom: 1rem; }
        .col-3 { grid-column: span 3; }
        .col-4 { grid-column: span 4; }
        .col-6 { grid-column: span 6; }
        .col-8 { grid-column: span 8; }
        .col-12 { grid-column: span 12; }
        @media (max-width: 1200px) { .dashboard-grid > * { grid-column: span 6 !important; } }
        @media (max-width: 768px) { .container { padding: 1rem; } .dashboard-grid > * { grid-column: span 12 !important; } .stats-grid { grid-template-columns: repeat(2, 1fr); } }
    </style>
</head>
<body>
    <header class="header">
        <div class="logo">
            <div class="logo-icon">🚀</div>
            <div class="logo-text">
                <h1>MITRAGLIERE BOT V2</h1>
                <span>Multi-Agent AI Trading System</span>
            </div>
        </div>
        <div class="header-status">
            <div class="status-indicator">
                <div class="status-dot" id="system-status"></div>
                <span id="system-status-text">Connecting...</span>
            </div>
            <div class="time-display" id="current-time"></div>
        </div>
    </header>
    <main class="container">
        <div class="dashboard-grid">
            <div class="card col-3">
                <div class="card-header"><span class="card-title">Equity Totale</span><span class="card-icon">💰</span></div>
                <div class="metric-value" id="equity-value">$0.00</div>
                <div class="metric-change" id="equity-change"><span>--</span></div>
            </div>
            <div class="card col-3">
                <div class="card-header"><span class="card-title">PnL Live</span><span class="card-icon">📊</span></div>
                <div class="metric-value" id="pnl-value">$0.00</div>
                <div class="metric-change" id="pnl-positions"><span>0 posizioni aperte</span></div>
            </div>
            <div class="card col-3">
                <div class="card-header"><span class="card-title">Win Rate</span><span class="card-icon">🎯</span></div>
                <div class="metric-value positive" id="winrate-value">0%</div>
                <div class="metric-change" id="winrate-trades"><span>0 trades totali</span></div>
            </div>
            <div class="card col-3">
                <div class="card-header"><span class="card-title">Profit Factor</span><span class="card-icon">📈</span></div>
                <div class="metric-value" id="pf-value">0.00</div>
                <div class="metric-change" id="pf-ratio"><span>Avg Win / Avg Loss</span></div>
            </div>
            <div class="card col-8">
                <div class="card-header">
                    <span class="card-title">Equity Curve</span>
                    <div class="chart-controls">
                        <button class="chart-btn" data-period="24h">24H</button>
                        <button class="chart-btn" data-period="7d">7D</button>
                        <button class="chart-btn" data-period="30d">30D</button>
                        <button class="chart-btn active" data-period="all">ALL</button>
                    </div>
                </div>
                <div class="chart-container"><canvas id="equity-chart"></canvas></div>
            </div>
            <div class="card col-4">
                <div class="card-header"><span class="card-title">Statistiche</span><span class="card-icon">📉</span></div>
                <div class="stats-grid">
                    <div class="stat-item"><div class="stat-value" id="stat-wins">0</div><div class="stat-label">Wins</div></div>
                    <div class="stat-item"><div class="stat-value" id="stat-losses">0</div><div class="stat-label">Losses</div></div>
                    <div class="stat-item"><div class="stat-value" id="stat-avg-win">$0</div><div class="stat-label">Avg Win</div></div>
                    <div class="stat-item"><div class="stat-value" id="stat-avg-loss">$0</div><div class="stat-label">Avg Loss</div></div>
                </div>
                <div style="margin-top: 1.5rem;">
                    <div class="card-title" style="margin-bottom: 0.75rem;">Best Performers</div>
                    <div id="best-performers"></div>
                </div>
            </div>
            <div class="card col-12">
                <div class="card-header"><span class="card-title">Posizioni Aperte</span><span class="card-icon">⚡</span></div>
                <div id="positions-container"><div class="loading"><div class="loading-spinner"></div></div></div>
            </div>
            <div class="card col-12">
                <div class="card-header"><span class="card-title">Decisioni AI</span><span class="card-icon">🧠</span></div>
                <div class="decisions-grid" id="decisions-container"><div class="loading"><div class="loading-spinner"></div></div></div>
            </div>
        </div>
    </main>
    <script>
        let equityChart = null;
        let chartData = [];
        document.addEventListener('DOMContentLoaded', () => {
            initChart();
            updateTime();
            setInterval(updateTime, 1000);
            fetchAllData();
            setInterval(fetchAllData, 15000);
            document.querySelectorAll('.chart-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.chart-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    updateChartPeriod(btn.dataset.period);
                });
            });
        });
        function updateTime() { document.getElementById('current-time').textContent = new Date().toLocaleString('it-IT'); }
        function initChart() {
            const ctx = document.getElementById('equity-chart').getContext('2d');
            equityChart = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'Equity', data: [], borderColor: '#00ff88', backgroundColor: 'rgba(0, 255, 136, 0.1)', fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#5a5a6e' } }, y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#5a5a6e', callback: v => '$' + v.toFixed(2) } } } }
            });
        }
        async function fetchAllData() { await Promise.all([fetchWallet(), fetchPositions(), fetchDecisions(), fetchStats(), fetchEquityHistory()]); updateSystemStatus(); }
        async function fetchWallet() {
            try {
                const r = await fetch('/api/wallet');
                const data = await r.json();
                document.getElementById('equity-value').textContent = '$' + (data.equity || 0).toFixed(2);
                const pnl = data.live_pnl || 0;
                const pnlEl = document.getElementById('pnl-value');
                pnlEl.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2);
                pnlEl.className = 'metric-value ' + (pnl >= 0 ? 'positive' : 'negative');
            } catch (e) { console.error(e); }
        }
        async function fetchPositions() {
            try {
                const r = await fetch('/api/positions');
                const data = await r.json();
                const positions = data.details || [];
                document.getElementById('pnl-positions').innerHTML = '<span>' + positions.length + ' posizioni aperte</span>';
                const container = document.getElementById('positions-container');
                if (positions.length === 0) { container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div><p>Nessuna posizione aperta</p></div>'; return; }
                let html = '<table class="positions-table"><thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>PnL</th><th>Lev</th></tr></thead><tbody>';
                positions.forEach(pos => {
                    const pnl = pos.pnl || 0;
                    html += '<tr><td><strong>' + pos.symbol + '</strong></td><td><span class="side-badge ' + (pos.side === 'Buy' ? 'long' : 'short') + '">' + (pos.side === 'Buy' ? 'LONG' : 'SHORT') + '</span></td><td>' + pos.size + '</td><td>' + parseFloat(pos.entry_price).toFixed(4) + '</td><td>' + parseFloat(pos.mark_price).toFixed(4) + '</td><td class="' + (pnl >= 0 ? 'positive' : 'negative') + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2) + '</td><td>' + pos.leverage + 'x</td></tr>';
                });
                html += '</tbody></table>';
                container.innerHTML = html;
            } catch (e) { console.error(e); }
        }
        async function fetchDecisions() {
            try {
                const r = await fetch('/api/decisions');
                const data = await r.json();
                const container = document.getElementById('decisions-container');
                if (Object.keys(data).length === 0) { container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🤔</div><p>In attesa...</p></div>'; return; }
                const sorted = Object.entries(data).sort((a, b) => (b[1].decision === 'HOLD' ? 0 : 1) - (a[1].decision === 'HOLD' ? 0 : 1));
                let html = '';
                sorted.forEach(([symbol, dec]) => {
                    const decision = dec.decision || 'HOLD';
                    const confidence = dec.confidence_score || 0;
                    const reasoning = dec.reasoning || '';
                    const setup = dec.trade_setup || {};
                    let cardClass = 'hold', actionClass = 'hold', actionText = 'HOLD';
                    if (decision === 'OPEN_LONG') { cardClass = 'long'; actionClass = 'long'; actionText = '🟢 LONG'; }
                    else if (decision === 'OPEN_SHORT') { cardClass = 'short'; actionClass = 'short'; actionText = '🔴 SHORT'; }
                    html += '<div class="decision-card ' + cardClass + '"><div class="decision-header"><span class="decision-symbol">' + symbol + '</span><span class="decision-action ' + actionClass + '">' + actionText + '</span></div><div class="confidence-bar"><div class="confidence-fill" style="width: ' + confidence + '%"></div></div><div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Confidence: ' + confidence + '%</div><div class="decision-reasoning">' + reasoning.substring(0, 150) + '...</div>';
                    if (setup && setup.entry) { html += '<div class="decision-setup"><div class="setup-item"><div class="setup-label">Entry</div><div class="setup-value">' + setup.entry + '</div></div><div class="setup-item"><div class="setup-label">SL</div><div class="setup-value" style="color: var(--accent-red)">' + setup.stop_loss + '</div></div><div class="setup-item"><div class="setup-label">TP</div><div class="setup-value" style="color: var(--accent-green)">' + setup.take_profit + '</div></div></div>'; }
                    html += '</div>';
                });
                container.innerHTML = html;
            } catch (e) { console.error(e); }
        }
        async function fetchStats() {
            try {
                const r = await fetch('/api/stats');
                const data = await r.json();
                if (data.error) return;
                document.getElementById('winrate-value').textContent = (data.win_rate || 0) + '%';
                document.getElementById('winrate-trades').innerHTML = '<span>' + (data.total_trades || 0) + ' trades</span>';
                const pf = data.profit_factor || 0;
                const pfEl = document.getElementById('pf-value');
                pfEl.textContent = pf.toFixed(2);
                pfEl.className = 'metric-value ' + (pf >= 1 ? 'positive' : 'negative');
                document.getElementById('stat-wins').textContent = data.wins || 0;
                document.getElementById('stat-losses').textContent = data.losses || 0;
                document.getElementById('stat-avg-win').textContent = '$' + (data.avg_win || 0).toFixed(2);
                document.getElementById('stat-avg-loss').textContent = '$' + (data.avg_loss || 0).toFixed(2);
                const bySymbol = data.by_symbol || {};
                const best = Object.entries(bySymbol).filter(([_, v]) => v.trades >= 3).sort((a, b) => b[1].win_rate - a[1].win_rate).slice(0, 3);
                let bestHtml = '';
                best.forEach(([symbol, stats]) => { bestHtml += '<div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid var(--border-color);"><span>' + symbol + '</span><span style="color: var(--accent-green)">' + stats.win_rate + '%</span></div>'; });
                document.getElementById('best-performers').innerHTML = bestHtml || '<p style="color: var(--text-muted)">Non abbastanza dati</p>';
            } catch (e) { console.error(e); }
        }
        async function fetchEquityHistory() {
            try {
                const r = await fetch('/api/equity_history');
                const data = await r.json();
                chartData = data.history || [];
                updateChartPeriod('all');
            } catch (e) { console.error(e); }
        }
        function updateChartPeriod(period) {
            if (!chartData.length) return;
            const now = Date.now() / 1000;
            let cutoff = 0;
            if (period === '24h') cutoff = now - 86400;
            else if (period === '7d') cutoff = now - 604800;
            else if (period === '30d') cutoff = now - 2592000;
            const filtered = chartData.filter(d => d.ts >= cutoff);
            equityChart.data.labels = filtered.map(d => new Date(d.ts * 1000).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }));
            equityChart.data.datasets[0].data = filtered.map(d => d.equity);
            if (filtered.length >= 2) {
                const color = filtered[filtered.length - 1].equity >= filtered[0].equity ? '#00ff88' : '#ff4757';
                equityChart.data.datasets[0].borderColor = color;
            }
            equityChart.update();
        }
        async function updateSystemStatus() {
            try {
                const r = await fetch('/api/system_status');
                const data = await r.json();
                const allOnline = Object.values(data).every(s => s === 'online');
                document.getElementById('system-status').className = 'status-dot' + (allOnline ? '' : ' offline');
                document.getElementById('system-status-text').textContent = allOnline ? 'Sistema Online' : 'Alcuni agenti offline';
            } catch (e) {
                document.getElementById('system-status').className = 'status-dot offline';
                document.getElementById('system-status-text').textContent = 'Connessione persa';
            }
        }
    </script>
</body>
</html>'''

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
