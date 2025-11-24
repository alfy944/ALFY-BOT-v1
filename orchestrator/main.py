import asyncio
import httpx
import schedule
import time
import os
from datetime import datetime, timezone

# --- CONFIGURAZIONE ---
SYMBOLS_TO_ANALYZE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", 
    "DOGEUSDT", "BNBUSDT", "LTCUSDT", "MATICUSDT", "DOTUSDT"
]

TECHNICAL_ANALYZER_AGENT_URL = os.getenv("TECHNICAL_ANALYZER_URL", "http://technical-analyzer-agent:8000")
FIBONACCI_AGENT_URL = os.getenv("FIBONACCI_AGENT_URL", "http://fibonacci-cyclical-agent:8000")
GANN_AGENT_URL = os.getenv("GANN_AGENT_URL", "http://gann-analyzer-agent:8000")
NEWS_SENTIMENT_AGENT_URL = os.getenv("NEWS_SENTIMENT_AGENT_URL", "http://news-sentiment-agent:8000")
MASTER_AI_AGENT_URL = os.getenv("MASTER_AI_AGENT_URL", "http://master-ai-agent:8000")
POSITION_MANAGER_AGENT_URL = os.getenv("POSITION_MANAGER_AGENT_URL", "http://position-manager-agent:8000")

async def make_request(client, url, method='get', json=None):
    try:
        if method == 'get': resp = await client.get(url, timeout=60.0)
        else: resp = await client.post(url, json=json, timeout=60.0)
        if resp.status_code == 200: return resp.json()
        return None
    except Exception as e:
        print(f"❌ Errore {url}: {e}")
        return None

async def get_all_data(client, symbol):
    print(f"   1. Raccolta Dati per {symbol}...")
    results = await asyncio.gather(
        make_request(client, f"{TECHNICAL_ANALYZER_AGENT_URL}/analyze_multi_tf", 'post', {"symbol": symbol, "timeframes": ["15", "240"]}),
        make_request(client, f"{FIBONACCI_AGENT_URL}/analyze_fibonacci", 'post', {"crypto_symbol": symbol}),
        make_request(client, f"{GANN_AGENT_URL}/analyze_gann", 'post', {"symbol": symbol}),
        make_request(client, f"{NEWS_SENTIMENT_AGENT_URL}/analyze_market_data/{symbol}")
    )
    tech = results[0] or {}
    return (
        (tech.get("data") or {}).get("15", {}),
        (tech.get("data") or {}).get("240", {}),
        results[1] or {},
        results[2] or {},
        results[3] or {}
    )

async def execute_trade(client, symbol, decision_data):
    decision = decision_data.get("decision")
    setup = decision_data.get("trade_setup", {})
    if not setup: return

    side = "Buy" if decision == "OPEN_LONG" else "Sell"
    print(f"   ⚡ INVIO ORDINE: {side} {symbol}...")

    payload = {
        "symbol": symbol,
        "side": side,
        "leverage": 5, 
        "stop_loss": setup.get("stop_loss"),
        "take_profit": setup.get("take_profit"),
        "size_pct": setup.get("size_pct", 0.2)
    }
    
    resp = await make_request(client, f"{POSITION_MANAGER_AGENT_URL}/open_position", 'post', payload)
    if resp and resp.get("status") == "executed":
        print(f"   ✅ ORDINE PIAZZATO! ID: {resp.get('order_id')}")
    else:
        print(f"   ❌ ERRORE ORDINE: {resp}")

async def scan_market():
    print(f"\n--- 🕒 {datetime.now(timezone.utc).strftime('%H:%M:%S')} | INIZIO SCANSIONE ---")
    
    async with httpx.AsyncClient() as client:
        # 1. Trailing Stop
        await make_request(client, f"{POSITION_MANAGER_AGENT_URL}/manage", 'post', {"positions": []})

        # 2. Check Posizioni Aperte
        open_pos = []
        pos_data = await make_request(client, f"{POSITION_MANAGER_AGENT_URL}/get_open_positions")
        if pos_data: open_pos = pos_data.get("open_positions", [])
        print(f"ℹ️ Posizioni Aperte: {open_pos}")

        # 3. Analisi
        for symbol in SYMBOLS_TO_ANALYZE:
            if symbol in open_pos:
                print(f"⏩ Salto {symbol} (Già aperto)")
                continue

            print(f"\n🔎 Analizzo {symbol}...")
            tech_15, tech_4h, fib, gann, news = await get_all_data(client, symbol)
            
            if not (tech_4h and fib):
                print("   ⚠️ Dati incompleti.")
                continue

            ai_payload = {
                "symbol": symbol,
                "tech_data": {"data": {"15": tech_15, "240": tech_4h}},
                "fib_data": fib, "gann_data": gann, "sentiment_data": news
            }
            
            decision_resp = await make_request(client, f"{MASTER_AI_AGENT_URL}/decide", 'post', ai_payload)
            
            if decision_resp:
                dec = decision_resp.get("decision")
                print(f"   👉 AI DECISION: {dec}")
                
                if dec in ["OPEN_LONG", "OPEN_SHORT"]:
                    await execute_trade(client, symbol, decision_resp)
            
            await asyncio.sleep(2)

    print("--- ✅ FINE SCANSIONE ---")

def job(): asyncio.run(scan_market())

if __name__ == "__main__":
    print("🚀 Orchestrator v3.1 Ready")
    job()
    schedule.every(15).minutes.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)
