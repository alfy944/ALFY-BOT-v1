"""
Learning Agent v1.0 - Trade Analysis & Pattern Recognition
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pybit.unified_trading import HTTP

app = FastAPI(title="Learning Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
session = HTTP(testnet=TESTNET, api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
ANALYSIS_FILE = os.path.join(DATA_DIR, "trade_analysis.json")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons_learned.json")
STATS_FILE = os.path.join(DATA_DIR, "trading_stats.json")
ANALYSIS_INTERVAL = int(os.getenv("LEARNING_INTERVAL", "3600"))

def log_print(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "i", "WARN": "!", "ERROR": "X", "SUCCESS": "OK", "LEARN": "L"}.get(level, "-")
    print("[{}] [{}] {}".format(ts, prefix, msg), flush=True)

def safe_float(value, default=0.0):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except:
        return default

def fetch_closed_trades(days_back=30):
    all_trades = []
    try:
        start_time = int((datetime.now() - timedelta(days=days_back)).timestamp() * 1000)
        cursor = ""
        while True:
            params = {"category": "linear", "limit": 100}
            if cursor:
                params["cursor"] = cursor
            r = session.get_closed_pnl(**params)
            if r["retCode"] != 0:
                break
            trades = r["result"].get("list", [])
            if not trades:
                break
            for trade in trades:
                trade_time = int(trade.get("updatedTime", 0))
                if trade_time < start_time:
                    return all_trades
                all_trades.append({
                    "symbol": trade.get("symbol"),
                    "side": trade.get("side"),
                    "qty": safe_float(trade.get("qty")),
                    "entry_price": safe_float(trade.get("avgEntryPrice")),
                    "exit_price": safe_float(trade.get("avgExitPrice")),
                    "closed_pnl": safe_float(trade.get("closedPnl")),
                    "leverage": safe_float(trade.get("leverage")),
                    "created_time": trade.get("createdTime"),
                    "updated_time": trade.get("updatedTime")
                })
            cursor = r["result"].get("nextPageCursor", "")
            if not cursor:
                break
    except Exception as e:
        log_print("Exception fetching trades: {}".format(e), "ERROR")
    return all_trades

def analyze_trade(trade):
    entry = trade["entry_price"]
    exit_price = trade["exit_price"]
    side = trade["side"]
    pnl = trade["closed_pnl"]
    if side == "Buy":
        pct_move = ((exit_price - entry) / entry) * 100 if entry > 0 else 0
    else:
        pct_move = ((entry - exit_price) / entry) * 100 if entry > 0 else 0
    is_win = pnl > 0
    result = dict(trade)
    result["pct_move"] = round(pct_move, 2)
    result["is_win"] = is_win
    result["pnl_category"] = "WIN" if is_win else "LOSS"
    return result

def calculate_statistics(analyzed_trades):
    if not analyzed_trades:
        return {"error": "No trades to analyze"}
    
    stats = {
        "total_trades": len(analyzed_trades),
        "total_pnl": 0,
        "wins": 0,
        "losses": 0,
        "by_symbol": {},
        "by_side": {}
    }
    wins_pnl = []
    losses_pnl = []
    
    for trade in analyzed_trades:
        pnl = trade["closed_pnl"]
        symbol = trade["symbol"]
        side = trade["side"]
        stats["total_pnl"] += pnl
        
        if trade["is_win"]:
            stats["wins"] += 1
            wins_pnl.append(pnl)
        else:
            stats["losses"] += 1
            losses_pnl.append(abs(pnl))
        
        if symbol not in stats["by_symbol"]:
            stats["by_symbol"][symbol] = {"trades": 0, "wins": 0, "pnl": 0}
        stats["by_symbol"][symbol]["trades"] += 1
        stats["by_symbol"][symbol]["pnl"] += pnl
        if trade["is_win"]:
            stats["by_symbol"][symbol]["wins"] += 1
        
        if side not in stats["by_side"]:
            stats["by_side"][side] = {"trades": 0, "wins": 0, "pnl": 0}
        stats["by_side"][side]["trades"] += 1
        stats["by_side"][side]["pnl"] += pnl
        if trade["is_win"]:
            stats["by_side"][side]["wins"] += 1
    
    total = stats["total_trades"]
    stats["win_rate"] = round((stats["wins"] / total) * 100, 1) if total > 0 else 0
    stats["avg_win"] = round(sum(wins_pnl) / len(wins_pnl), 2) if wins_pnl else 0
    stats["avg_loss"] = round(sum(losses_pnl) / len(losses_pnl), 2) if losses_pnl else 0
    total_loss = sum(losses_pnl)
    stats["profit_factor"] = round(sum(wins_pnl) / total_loss, 2) if total_loss > 0 else 0
    stats["total_pnl"] = round(stats["total_pnl"], 2)
    
    for symbol in stats["by_symbol"]:
        s = stats["by_symbol"][symbol]
        s["win_rate"] = round((s["wins"] / s["trades"]) * 100, 1) if s["trades"] > 0 else 0
        s["pnl"] = round(s["pnl"], 2)
    
    for side in stats["by_side"]:
        s = stats["by_side"][side]
        s["win_rate"] = round((s["wins"] / s["trades"]) * 100, 1) if s["trades"] > 0 else 0
        s["pnl"] = round(s["pnl"], 2)
    
    return stats

def generate_lessons(stats):
    lessons = {
        "generated_at": datetime.now().isoformat(),
        "summary": "",
        "best_performing": [],
        "worst_performing": [],
        "recommendations": [],
        "avoid": []
    }
    
    if "error" in stats:
        lessons["summary"] = "Non ci sono abbastanza trade per generare lezioni."
        return lessons
    
    lessons["summary"] = "Analizzati {} trade. Win rate: {}%. PnL totale: ${}".format(
        stats["total_trades"], stats["win_rate"], stats["total_pnl"]
    )
    
    for symbol, data in stats["by_symbol"].items():
        if data["trades"] >= 3:
            item = {
                "symbol": symbol,
                "win_rate": data["win_rate"],
                "trades": data["trades"],
                "pnl": data["pnl"]
            }
            if data["win_rate"] >= 60:
                lessons["best_performing"].append(item)
            elif data["win_rate"] <= 40:
                lessons["worst_performing"].append(item)
    
    lessons["best_performing"].sort(key=lambda x: x["win_rate"], reverse=True)
    lessons["worst_performing"].sort(key=lambda x: x["win_rate"])
    
    if stats["win_rate"] < 50:
        lessons["recommendations"].append("Win rate sotto 50% - aumenta la confidence minima")
    
    if stats["avg_loss"] > stats["avg_win"] * 1.5:
        lessons["recommendations"].append("Perdite troppo grandi - stringi gli stop loss")
    
    if "Buy" in stats["by_side"] and "Sell" in stats["by_side"]:
        buy_wr = stats["by_side"]["Buy"]["win_rate"]
        sell_wr = stats["by_side"]["Sell"]["win_rate"]
        if buy_wr > sell_wr + 15:
            lessons["recommendations"].append("LONG performano meglio ({}% vs {}%)".format(buy_wr, sell_wr))
        elif sell_wr > buy_wr + 15:
            lessons["recommendations"].append("SHORT performano meglio ({}% vs {}%)".format(sell_wr, buy_wr))
    
    for item in lessons["worst_performing"][:3]:
        if item["win_rate"] <= 35:
            lessons["avoid"].append("{} (win rate: {}%)".format(item["symbol"], item["win_rate"]))
    
    return lessons

def generate_ai_context(lessons, stats):
    if "error" in stats or stats.get("total_trades", 0) < 5:
        return ""
    
    parts = []
    parts.append("=== HISTORICAL PERFORMANCE ===")
    parts.append("Win rate: {}% | Profit factor: {}".format(stats["win_rate"], stats["profit_factor"]))
    
    if lessons.get("best_performing"):
        best_list = []
        for s in lessons["best_performing"][:3]:
            best_list.append("{}({}%)".format(s["symbol"], s["win_rate"]))
        parts.append("BEST: " + ", ".join(best_list))
    
    if lessons.get("avoid"):
        parts.append("AVOID: " + ", ".join(lessons["avoid"]))
    
    if lessons.get("recommendations"):
        parts.append("TIPS: " + "; ".join(lessons["recommendations"][:2]))
    
    return "\n".join(parts)

async def run_analysis():
    log_print("Starting trade analysis...", "LEARN")
    trades = fetch_closed_trades(days_back=30)
    log_print("Fetched {} closed trades".format(len(trades)), "LEARN")
    
    if not trades:
        log_print("No trades found", "WARN")
        return None
    
    analyzed = [analyze_trade(t) for t in trades]
    stats = calculate_statistics(analyzed)
    lessons = generate_lessons(stats)
    ai_context = generate_ai_context(lessons, stats)
    
    try:
        with open(ANALYSIS_FILE, "w") as f:
            json.dump(analyzed, f, indent=2)
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)
        lessons["ai_context"] = ai_context
        with open(LESSONS_FILE, "w") as f:
            json.dump(lessons, f, indent=2)
        log_print("Analysis complete. Win rate: {}%, PnL: ${}".format(stats["win_rate"], stats["total_pnl"]), "SUCCESS")
    except Exception as e:
        log_print("Error saving: {}".format(e), "ERROR")
    
    return stats

async def analysis_loop():
    log_print("Learning Agent started - Interval: {}s".format(ANALYSIS_INTERVAL), "INFO")
    await run_analysis()
    while True:
        await asyncio.sleep(ANALYSIS_INTERVAL)
        await run_analysis()

@app.get("/health")
def health():
    return {"status": "ok", "service": "learning-agent", "version": "1.0.0"}

@app.get("/stats")
def get_stats():
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return {"error": "No stats yet"}

@app.get("/lessons")
def get_lessons_endpoint():
    try:
        if os.path.exists(LESSONS_FILE):
            with open(LESSONS_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return {"error": "No lessons yet"}

@app.get("/ai_context")
def get_ai_context_endpoint():
    try:
        if os.path.exists(LESSONS_FILE):
            with open(LESSONS_FILE, "r") as f:
                data = json.load(f)
                return {"context": data.get("ai_context", "")}
    except:
        pass
    return {"context": ""}

@app.post("/refresh")
async def refresh():
    stats = await run_analysis()
    if stats:
        return {"status": "ok", "win_rate": stats.get("win_rate")}
    return {"status": "error"}

@app.on_event("startup")
async def startup():
    log_print("Learning Agent starting...", "INFO")
    asyncio.create_task(analysis_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
