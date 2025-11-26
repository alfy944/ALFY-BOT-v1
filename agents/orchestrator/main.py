"""
Orchestrator v2.1 (PRODUCTION OPTIMIZED)
========================================
OTTIMIZZAZIONE: Chiama /refresh_all sul Sentiment Agent UNA VOLTA
per scan invece di una chiamata per ogni crypto.
"""

import asyncio
import httpx
import schedule
import time
import os
from datetime import datetime, timezone

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "BNBUSDT", "LTCUSDT", "MATICUSDT", "DOTUSDT"]
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "15"))
TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "90"))
DELAY = float(os.getenv("INTER_SYMBOL_DELAY", "2"))

TECH_URL = os.getenv("TECHNICAL_ANALYZER_URL", "http://technical-analyzer-agent:8000")
FIB_URL = os.getenv("FIBONACCI_AGENT_URL", "http://fibonacci-cyclical-agent:8000")
GANN_URL = os.getenv("GANN_AGENT_URL", "http://gann-analyzer-agent:8000")
SENT_URL = os.getenv("NEWS_SENTIMENT_AGENT_URL", "http://news-sentiment-agent:8000")
AI_URL = os.getenv("MASTER_AI_AGENT_URL", "http://master-ai-agent:8000")
POS_URL = os.getenv("POSITION_MANAGER_AGENT_URL", "http://position-manager-agent:8000")

os.makedirs("/app/logs", exist_ok=True)

def log(msg: str, lvl: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "SUCCESS": "✅", "TRADE": "💰", "CACHE": "💾"}.get(lvl, "📝")
    print(f"[{ts}] {prefix} {msg}")

async def req(client, url, method='get', data=None, desc=""):
    try:
        r = await (client.get(url, timeout=TIMEOUT) if method == 'get' else client.post(url, json=data, timeout=TIMEOUT))
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        log(f"{desc} error: {e}", "WARN")
        return None

async def refresh_sentiment_cache(client) -> bool:
    log("Refreshing sentiment cache (single API call)...", "CACHE")
    result = await req(client, f"{SENT_URL}/refresh_all", 'post', {}, "Sentiment Refresh")
    if result and result.get("status") == "refreshed":
        log(f"Sentiment cache refreshed: {result.get('symbols_updated', 0)} symbols", "CACHE")
        return True
    log("Sentiment cache refresh failed", "WARN")
    return False

async def collect_data(client, symbol):
    log(f"Collecting data for {symbol}...")
    results = await asyncio.gather(
        req(client, f"{TECH_URL}/analyze_multi_tf", 'post', {"symbol": symbol, "timeframes": ["15", "60", "240"]}, "Tech"),
        req(client, f"{FIB_URL}/analyze_fibonacci", 'post', {"crypto_symbol": symbol}, "Fib"),
        req(client, f"{GANN_URL}/analyze_gann", 'post', {"symbol": symbol}, "Gann"),
        req(client, f"{SENT_URL}/analyze_market_data/{symbol}", 'get', None, "Sent"),
        return_exceptions=True
    )
    return tuple(r if isinstance(r, dict) else {} for r in results)

async def execute_trade(client, symbol, decision_data) -> bool:
    setup = decision_data.get("trade_setup", {})
    if not setup: return False
    side = "Buy" if decision_data.get("decision") == "OPEN_LONG" else "Sell"
    sl, tp = setup.get("stop_loss") or setup.get("sl"), setup.get("take_profit") or setup.get("tp")
    if not sl or not tp: return False
    payload = {"symbol": symbol, "side": side, "leverage": setup.get("leverage", 5), "stop_loss": float(sl), "take_profit": float(tp), "size_pct": setup.get("size_pct", 0.15)}
    log(f"Sending order: {side} {symbol}, SL={sl}, TP={tp}", "TRADE")
    result = await req(client, f"{POS_URL}/open_position", 'post', payload, "Position")
    if result and result.get("status") == "executed":
        log(f"ORDER EXECUTED: {side} {symbol} | ID: {result.get('order_id')}", "SUCCESS")
        return True
    log(f"Order failed: {result}", "ERROR")
    return False

async def scan_market():
    start_time = datetime.now(timezone.utc)
    log("=" * 60)
    log("MARKET SCAN STARTED (GPT-5.1 Engine)")
    log("=" * 60)
    stats = {"symbols_analyzed": 0, "trades_opened": 0, "errors": 0}
    
    async with httpx.AsyncClient() as client:
        # STEP 1: Refresh sentiment cache (UNA chiamata API per tutte le crypto)
        await refresh_sentiment_cache(client)
        
        # STEP 2: Gestione posizioni
        await req(client, f"{POS_URL}/manage", 'post', {}, "Manage")
        pos_data = await req(client, f"{POS_URL}/get_open_positions", 'get', None, "Positions")
        open_positions = pos_data.get("open_positions", []) if pos_data else []
        log(f"Open positions: {', '.join(open_positions) if open_positions else 'None'}")
        
        # STEP 3: Analizza ogni symbol
        for symbol in SYMBOLS:
            log(f"\n{'─' * 40}")
            log(f"Analyzing {symbol}...")
            if symbol in open_positions:
                log("Skipping (position open)")
                continue
            try:
                tech, fib, gann, sent = await collect_data(client, symbol)
                if not tech.get("data"):
                    log("Insufficient data", "WARN")
                    stats["errors"] += 1
                    continue
                if sent.get("from_cache"):
                    log(f"  Sentiment from cache (age: {sent.get('cache_age_seconds', 0)}s)")
                decision = await req(client, f"{AI_URL}/decide", 'post', {"symbol": symbol, "tech_data": tech, "fib_data": fib, "gann_data": gann, "sentiment_data": sent}, "AI")
                if decision:
                    stats["symbols_analyzed"] += 1
                    dec, score = decision.get("decision", "?"), decision.get("confidence_score", 0)
                    reason = (decision.get("logic_log") or [""])[0][:80]
                    log(f"AI: {dec} (confidence: {score})")
                    if reason: log(f"  {reason}...")
                    if dec in ["OPEN_LONG", "OPEN_SHORT"]:
                        if await execute_trade(client, symbol, decision):
                            stats["trades_opened"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                log(f"Error: {e}", "ERROR")
                stats["errors"] += 1
            await asyncio.sleep(DELAY)
    
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    log(f"\n{'=' * 60}")
    log(f"SCAN COMPLETED in {duration:.1f}s", "SUCCESS")
    log(f"  Analyzed: {stats['symbols_analyzed']} | Trades: {stats['trades_opened']} | Errors: {stats['errors']}")
    log(f"  API calls saved: ~{len(SYMBOLS) - 1} (sentiment batch)")
    log("=" * 60)

def run_scan():
    try: asyncio.run(scan_market())
    except Exception as e: log(f"Scan failed: {e}", "ERROR")

if __name__ == "__main__":
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║          TRADING SYSTEM ORCHESTRATOR v2.1                    ║
    ║                  Powered by GPT-5.1                          ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  OPTIMIZATIONS:                                              ║
    ║  ✓ Async HTTP (httpx)                                        ║
    ║  ✓ Sentiment batch fetch (1 API call for all)                ║
    ║  ✓ 15-min cache for sentiment                                ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  Scan Interval: {SCAN_INTERVAL} minutes                                   ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    log(f"Symbols: {', '.join(SYMBOLS)}")
    run_scan()
    schedule.every(SCAN_INTERVAL).minutes.do(run_scan)
    log(f"Next scan in {SCAN_INTERVAL} minutes")
    while True:
        schedule.run_pending()
        time.sleep(1)
