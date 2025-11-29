"""
Trading Dashboard v7.6 - PERSISTENT CHART & ANCHOR
"""
import os
import time
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="Mitragliere Dashboard", version="7.6.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

POS_URL = os.getenv("POSITION_MANAGER_URL", "http://position-manager-agent:8000")
AI_URL = os.getenv("MASTER_AI_URL", "http://master-ai-agent:8000")
DATA_FILE = "chart_history.json"

# --- GESTIONE MEMORIA SU FILE ---
def load_history():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f: return json.load(f)
    except: pass
    # Se non esiste, struttura vuota
    return {"start_equity": None, "history": []}

def save_history(data):
    try:
        with open(DATA_FILE, "w") as f: json.dump(data, f)
    except: pass

# Carichiamo la memoria all'avvio
chart_memory = load_history()

# --- UTILS ---
async def safe_get(client, url, default):
    try:
        r = await client.get(url, timeout=2.0)
        if r.status_code == 200: return r.json()
    except: pass
    return default

@app.get("/api/wallet")
async def gw():
    global chart_memory
    async with httpx.AsyncClient() as c:
        # 1. Dati attuali
        bal_data = await safe_get(c, f"{POS_URL}/get_wallet_balance", {"balance": 0})
        balance = float(bal_data.get("balance", 0))
        pos_list = await safe_get(c, f"{POS_URL}/get_open_positions", [])
        
        total_unrealized_pnl = sum(float(p.get("pnl", 0)) for p in pos_list)
        
        # Calcolo Margine Usato (Stima)
        used_margin = sum((float(p.get("size", 0)) * float(p.get("entry_price", 0))) / 5 for p in pos_list)
        
        current_equity = balance + total_unrealized_pnl
        available = balance - used_margin
        if available < 0: available = 0

        # --- LOGICA GRAFICO ---
        # Se è la prima volta in assoluto, settiamo il "Punto Fermo" (Baseline)
        if chart_memory["start_equity"] is None and current_equity > 0:
            chart_memory["start_equity"] = current_equity
            print(f"BASELINE FISSATA A: {current_equity}")

        timestamp = time.strftime("%H:%M") # Salviamo per minuto per non intasare
        
        # Aggiungiamo punto al grafico (solo se è cambiato minuto o lista vuota)
        should_add = False
        if not chart_memory["history"]: should_add = True
        elif chart_memory["history"][-1]["ts"] != timestamp: should_add = True
        
        if should_add and current_equity > 0:
            chart_memory["history"].append({
                "ts": timestamp, 
                "equity": round(current_equity, 2),
                "baseline": chart_memory["start_equity"] # Salviamo il riferimento
            })
            # Limitiamo a 2000 punti (circa 2 giorni minuto per minuto)
            if len(chart_memory["history"]) > 2000: chart_memory["history"].pop(0)
            
            # SALVATAGGIO SU DISCO
            save_history(chart_memory)

        return {
            "equity": round(current_equity, 2),
            "availableToWithdraw": round(available, 2),
            "pnl_open": round(total_unrealized_pnl, 2)
        }

@app.get("/api/stats")
async def gs():
    async with httpx.AsyncClient() as c: 
        pos_list = await safe_get(c, f"{POS_URL}/get_open_positions", [])
        current_pnl = sum(float(p.get("pnl", 0)) for p in pos_list)
        return {"total_pnl": round(current_pnl, 2), "win_rate": 0}

@app.get("/api/positions")
async def gp():
    async with httpx.AsyncClient() as c: 
        raw_list = await safe_get(c, f"{POS_URL}/get_open_positions", [])
        return {"active": raw_list}

@app.get("/api/ai")
async def gai():
    async with httpx.AsyncClient() as c: return await safe_get(c, f"{AI_URL}/latest_reasoning", {})

@app.get("/api/mgmt")
async def gmgmt():
    async with httpx.AsyncClient() as c: 
        raw_logs = await safe_get(c, f"{POS_URL}/management_logs", [])
        fixed_logs = []
        for l in raw_logs:
            pair = l.get("pair") or l.get("symbol") or "SYS"
            action = l.get("action") or l.get("details") or "..."
            fixed_logs.append({"time": l.get("time",""), "pair": pair, "action": action})
        return {"logs": fixed_logs}

@app.get("/api/history")
async def ghist():
    # Restituisce la memoria persistente
    return {"history": chart_memory["history"], "start": chart_memory["start_equity"]}

@app.post("/api/close_position")
async def cp(request: Request):
    try:
        data = await request.json()
        async with httpx.AsyncClient() as c:
            return (await c.post(f"{POS_URL}/close_position", json=data)).json()
    except Exception as e: return {"error": str(e)}

DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <title>MITRAGLIERE // V7.6</title>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=JetBrains+Mono:wght@400;700&family=Orbitron:wght@900&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { --neon-green: #00ff9d; --neon-red: #ff2a6d; --neon-blue: #00f3ff; --card-bg: rgba(12, 18, 24, 0.95); }
        body { background-color: #050505; color: #e0e0e0; font-family: 'Rajdhani', sans-serif; margin: 0; padding: 20px; min-height: 100vh; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #333; padding-bottom: 15px; }
        .logo { font-family: 'Orbitron'; font-size: 2rem; color: var(--neon-green); text-shadow: 0 0 15px rgba(0,255,157,0.3); }
        .status { font-family: 'JetBrains Mono'; font-size: 0.8rem; color: #888; border: 1px solid #333; padding: 5px 10px; border-radius: 4px; }
        .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
        .col-2 { grid-column: span 2; } .col-4 { grid-column: span 4; }
        .card { background: var(--card-bg); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; }
        .label { font-size: 0.75rem; color: #888; text-transform: uppercase; font-weight: 700; margin-bottom: 5px; }
        .val { font-family: 'JetBrains Mono'; font-size: 2.2rem; font-weight: 700; color: white; }
        .green { color: var(--neon-green); } .red { color: var(--neon-red); } .blue { color: var(--neon-blue); }
        .terminal { font-family: 'JetBrains Mono'; font-size: 0.75rem; height: 200px; overflow-y: auto; background: rgba(0,0,0,0.3); padding: 10px; border: 1px solid #222; }
        .log-entry { margin-bottom: 5px; border-bottom: 1px solid #222; padding-bottom: 5px; }
        .btn-kill { border: 1px solid var(--neon-red); color: var(--neon-red); background: transparent; padding: 5px; cursor: pointer; font-weight: bold; }
        @media(max-width: 900px) { .grid { grid-template-columns: 1fr; } .col-2, .col-4 { grid-column: span 1; } }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">MITRAGLIERE <span style="font-size:1rem; opacity:0.5; color:white;">// V7.6</span></div>
        <div class="status" id="sys-status">INIT...</div>
    </div>
    <div class="grid">
        <div class="card"><div class="label">NET EQUITY</div><div class="val" id="equity">----</div></div>
        <div class="card"><div class="label">AVAILABLE</div><div class="val blue" id="avail">----</div></div>
        <div class="card"><div class="label">SESSION PNL (OPEN)</div><div class="val" id="pnl">----</div></div>
        <div class="card"><div class="label">WIN RATE</div><div class="val green" id="wr">----</div></div>
        <div class="card col-4">
            <div class="label">ACTIVE ENGAGEMENTS</div>
            <div id="pos-box" style="display:flex; gap:10px; flex-wrap:wrap; margin-top:10px;">Scanning...</div>
        </div>
        <div class="card col-2"><div class="label">AI LOGS</div><div class="terminal" id="ai-box">...</div></div>
        <div class="card col-2"><div class="label">MANAGEMENT</div><div class="terminal" id="mgmt-box">...</div></div>
        <div class="card col-4"><div class="label">EQUITY HISTORY (BASE: <span id="base-val">---</span>)</div><div style="height:250px"><canvas id="chart"></canvas></div></div>
    </div>
    <script>
        let chart = null;
        const sysStatus = document.getElementById('sys-status');
        
        try {
            if (typeof Chart !== 'undefined') {
                const ctx = document.getElementById('chart').getContext('2d');
                chart = new Chart(ctx, { 
                    type: 'line', 
                    data: { 
                        labels: [], 
                        datasets: [
                            { label: 'Current Equity', data: [], borderColor: '#00ff9d', tension: 0.2, borderWidth: 2 },
                            { label: 'Baseline', data: [], borderColor: '#333', borderDash: [5, 5], borderWidth: 1, pointRadius: 0 } 
                        ] 
                    }, 
                    options: { responsive: true, maintainAspectRatio: false, plugins:{legend:{display:true, labels:{color:'#666'}}}, scales:{x:{display:true, grid:{display:false}, ticks:{color:'#444'}}, y:{grid:{color:'#222'}, ticks:{color:'#666'}}} } 
                });
            }
        } catch (e) {}
        
        async function update() {
            try {
                const r = await fetch('/api/wallet');
                const w = await r.json();
                document.getElementById('equity').innerText = '$' + (w.equity||0).toFixed(2);
                document.getElementById('avail').innerText = '$' + (w.availableToWithdraw||0).toFixed(2);
                sysStatus.innerText = "SYSTEM ONLINE"; sysStatus.style.color = "#00ff9d";
            } catch(e) { sysStatus.innerText = "CONN ERROR"; sysStatus.style.color = "#ff2a6d"; }

            try {
                const s = await fetch('/api/stats').then(r=>r.json());
                const pnl = s.total_pnl || 0;
                const pnlEl = document.getElementById('pnl');
                pnlEl.innerText = (pnl>=0?'+':'') + '$' + pnl.toFixed(2);
                pnlEl.className = `val ${pnl>=0?'green':'red'}`;
            } catch(e) {}

            try {
                const p = await fetch('/api/positions').then(r=>r.json());
                const pos = p.active || [];
                const pb = document.getElementById('pos-box');
                if(pos.length === 0) pb.innerHTML = '<span style="color:#555">NO POSITIONS</span>';
                else {
                    pb.innerHTML = pos.map(x => `
                        <div style="border:1px solid ${x.pnl>=0?'#00ff9d':'#ff2a6d'}; padding:10px; border-radius:5px;">
                            <b>${x.symbol}</b> ${x.side} <br>
                            <span style="font-size:1.2rem; color:${x.pnl>=0?'#00ff9d':'#ff2a6d'}">${x.pnl.toFixed(2)}$</span>
                            <button class="btn-kill" onclick="closePos('${x.symbol}')">CLOSE</button>
                        </div>
                    `).join('');
                }
            } catch(e) {}
            
            try {
                const mgmt = await fetch('/api/mgmt').then(r=>r.json());
                if(mgmt.logs) document.getElementById('mgmt-box').innerHTML = mgmt.logs.map(l=>`<div class="log-entry"><small>${l.time}</small> <b style="color:#00ff9d">${l.pair}</b>: ${l.action}</div>`).join('');
                const ai = await fetch('/api/ai').then(r=>r.json());
                if(ai.decisions) {
                     let h=''; for(const [k,v] of Object.entries(ai.decisions)) h+=`<div class="log-entry"><b style="color:#00f3ff">${k}</b>: ${v.decision}<br><small>${v.reasoning}</small></div>`;
                     document.getElementById('ai-box').innerHTML = h;
                }
            } catch(e) {}

            // UPDATE CHART PERSISTENTE
            try {
                if(chart) {
                    const h = await fetch('/api/history').then(r=>r.json());
                    if(h.history && h.history.length>0) {
                        chart.data.labels = h.history.map(x=>x.ts);
                        chart.data.datasets[0].data = h.history.map(x=>x.equity);
                        
                        // Linea di base (Baseline)
                        const startEq = h.start || h.history[0].equity;
                        document.getElementById('base-val').innerText = '$'+startEq.toFixed(2);
                        chart.data.datasets[1].data = new Array(h.history.length).fill(startEq);

                        chart.update();
                    }
                }
            } catch(e) {}
        }
        window.closePos = async (sym) => { if(confirm('Close '+sym+'?')) await fetch('/api/close_position', {method:'POST', body:JSON.stringify({symbol:sym})}); };
        setInterval(update, 3000); // Aggiorna ogni 3 secondi
        update();
    </script>
</body>
</html>'''
@app.get("/", response_class=HTMLResponse)
async def dashboard(): return DASHBOARD_HTML
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
