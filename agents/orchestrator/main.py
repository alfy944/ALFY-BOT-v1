import asyncio, httpx, time
from datetime import datetime

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
URLS = {
    "tech": "http://technical-analyzer-agent:8000",
    "fc": "http://forecaster-agent:8000",
    "fib": "http://fibonacci-cyclical-agent:8000",
    "gann": "http://gann-analyzer-agent:8000",
    "sent": "http://news-sentiment-agent:8000",
    "pos": "http://position-manager-agent:8000",
    "ai": "http://master-ai-agent:8000"
}

async def manage_cycle():
    async with httpx.AsyncClient() as c:
        try:
            r = await c.post(f"{URLS['pos']}/manage_active_positions")
            logs = r.json().get('actions', [])
            if logs: print(f"🛡️ PROTECTION: {logs}")
        except: pass

async def analysis_cycle():
    print(f"\n[{datetime.now().strftime('%H:%M')}] 🧠 AI SCAN START")
    async with httpx.AsyncClient(timeout=60) as c:
        # 1. Global Data + POSIZIONI APERTE
        glob = await asyncio.gather(
            c.get(f"{URLS['pos']}/get_wallet_balance"),
            c.get(f"{URLS['sent']}/global_sentiment"),
            c.get(f"{URLS['pos']}/get_open_positions"), # <-- CHIEDIAMO COSA E' APERTO
            return_exceptions=True
        )
        portfolio = glob[0].json() if not isinstance(glob[0], Exception) else {}
        fg = glob[1].json() if not isinstance(glob[1], Exception) else {}
        # Lista delle crypto già aperte (es. ['BTCUSDT'])
        open_pos_data = glob[2].json() if not isinstance(glob[2], Exception) else {"active": []}
        active_symbols = open_pos_data.get("active", [])
        
        print(f"ℹ️  Portfolio: {portfolio.get('equity', '0')}$ | Active: {active_symbols}")

        # 2. Assets Data
        assets = {}
        for s in SYMBOLS:
            try:
                tech_r = await c.post(f"{URLS['tech']}/analyze_multi_tf", json={"symbol": s})
                tech = tech_r.json()
                price = tech.get('price', 0)
                
                r = await asyncio.gather(
                    c.post(f"{URLS['fc']}/forecast", json={"symbol": s}),
                    c.post(f"{URLS['fib']}/analyze_fibonacci", json={"crypto_symbol": s}),
                    c.post(f"{URLS['gann']}/analyze_gann", json={"price": price}),
                    return_exceptions=True
                )
                assets[s] = {
                    "tech": tech,
                    "fc": r[0].json() if not isinstance(r[0], Exception) else {},
                    "fib": r[1].json() if not isinstance(r[1], Exception) else {},
                    "gann": r[2].json() if not isinstance(r[2], Exception) else {}
                }
            except Exception as e: print(f"Err {s}: {e}")

        # 3. AI Decision
        payload = {
            "global_data": {"fg": fg, "portfolio": portfolio, "already_open": active_symbols}, 
            "assets_data": assets
        }
        
        try:
            resp = await c.post(f"{URLS['ai']}/decide_batch", json=payload)
            dec = resp.json()
            print(f"🤖 Analysis: {dec.get('analysis')}")
            
            for d in dec.get('decisions', []):
                sym = d['symbol']
                action = d['action']
                
                # --- FILTRO: SE GIA' APERTO, SALTA ---
                if sym in active_symbols:
                    print(f"⚠️ SKIP {sym}: Position already open.")
                    continue
                
                if action in ["OPEN_LONG", "OPEN_SHORT"]:
                    print(f"🔥 EXECUTING: {sym} {action} (Lev {d['leverage']}x)")
                    
                    # Esegui Ordine
                    ord_resp = await c.post(f"{URLS['pos']}/open_position", json={
                        "symbol": sym,
                        "side": "Buy" if "LONG" in action else "Sell",
                        "leverage": d['leverage'],
                        "size_pct": d['size_pct']
                    })
                    
                    # --- STAMPA RISULTATO ESATTO (DEBUG) ---
                    print(f"👉 BYBIT RESPONSE: {ord_resp.json()}")

        except Exception as e: print(f"AI Err: {e}")

async def main_loop():
    last_scan = 0
    SCAN_INTERVAL = 900 
    while True:
        now = time.time()
        await manage_cycle()
        if now - last_scan > SCAN_INTERVAL:
            await analysis_cycle()
            last_scan = now
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main_loop())
