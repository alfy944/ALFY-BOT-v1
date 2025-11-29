import time
import requests
import os
import logging
from datetime import datetime
from fastapi import FastAPI
from threading import Thread
from pybit.unified_trading import HTTP
from pydantic import BaseModel

# --- CONFIGURAZIONE ---
SLEEP_INTERVAL = 900  # 15 Minuti
MASTER_AI_URL = "http://master-ai-agent:8000"
TARGET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Precisione decimali per Qty e Prezzo (SL/TP)
QTY_PRECISION = {"BTCUSDT": 3, "ETHUSDT": 2, "SOLUSDT": 1}
PRICE_PRECISION = {"BTCUSDT": 1, "ETHUSDT": 2, "SOLUSDT": 3}

# --- GESTIONE RISCHIO ---
DEFAULT_SL_PERCENT = 0.02  # 2% di movimento prezzo contro
DEFAULT_TP_PERCENT = 0.06  # 6% di movimento prezzo a favore (R:R 1:3)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PositionManager")
app = FastAPI()

# LOGS
management_logs = [] 
equity_history = [] 

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

session = None
try:
    session = HTTP(testnet=IS_TESTNET, api_key=API_KEY, api_secret=API_SECRET)
except: pass

class CloseRequest(BaseModel):
    symbol: str

def add_log(title, message, status="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {title}: {message}")
    management_logs.insert(0, {"id": int(time.time()*1000), "time": timestamp, "pair": title, "action": message, "status": status})
    if len(management_logs) > 100: management_logs.pop()

def get_wallet_data():
    if not session: return 0.0, []
    bal = 0.0
    pos = []
    try:
        r = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        if r['retCode'] == 0:
            bal = float(r['result']['list'][0]['coin'][0]['walletBalance'])
        r2 = session.get_positions(category="linear", settleCoin="USDT")
        if r2['retCode'] == 0:
            for p in r2['result']['list']:
                if float(p['size']) > 0:
                    pos.append({
                        "symbol": p['symbol'],
                        "side": p['side'],
                        "size": float(p['size']),
                        "entry_price": float(p['avgPrice']),
                        "leverage": float(p['leverage']),
                        "pnl": float(p['unrealisedPnl']),
                        "stop_loss": float(p.get('stopLoss', 0)),
                        "take_profit": float(p.get('takeProfit', 0))
                    })
    except: pass
    return bal, pos

def get_price(sym):
    try:
        r = session.get_tickers(category="linear", symbol=sym)
        return float(r['result']['list'][0]['markPrice'])
    except: return 0.0

def calculate_sl_tp(entry_price, direction, sl_pct, tp_pct, precision):
    """Calcola prezzi esatti per SL e TP in base alla direzione"""
    if direction == "long":
        sl = entry_price * (1 - sl_pct)
        tp = entry_price * (1 + tp_pct)
    else: # short
        sl = entry_price * (1 + sl_pct)
        tp = entry_price * (1 - tp_pct)
    
    return round(sl, precision), round(tp, precision)

def execute_decision(decision):
    sym = decision.get("symbol") + "USDT"
    op = decision.get("operation", "hold").lower()
    direct = decision.get("direction", "").lower()
    lev = int(decision.get("leverage", 1))
    size_pct = float(decision.get("target_portion_of_balance", 0.0))
    reason = decision.get("reason", "")

    logger.info(f"EXEC: {sym} -> {op.upper()} ({reason[:40]}...)")
    
    if op == "hold": return

    bal, positions = get_wallet_data()
    my_pos = next((p for p in positions if p['symbol'] == sym), None)

    # --- CHIUSURA ---
    if op == "close" and my_pos:
        try:
            side = "Sell" if my_pos['side'] == "Buy" else "Buy"
            session.place_order(category="linear", symbol=sym, side=side, orderType="Market", qty=str(my_pos['size']), reduceOnly=True)
            add_log(sym, f"CLOSED {my_pos['side']} (AI)", "success")
        except Exception as e: add_log(sym, f"Close Fail: {e}", "error")

    # --- APERTURA con SL/TP ---
    elif op == "open" and not my_pos:
        try:
            session.set_leverage(category="linear", symbol=sym, buyLeverage=str(lev), sellLeverage=str(lev))
        except: pass
        
        bal, _ = get_wallet_data()
        price = get_price(sym)
        if price == 0 or bal < 10: return

        # 1. Calcola Quantità
        amount = (bal * size_pct * lev * 0.95) / price
        qty_prec = QTY_PRECISION.get(sym, 3)
        qty = f"{amount:.{qty_prec}f}"
        
        # 2. Calcola SL e TP
        # Adattiamo la percentuale alla leva: più leva = stop loss più stretto per non bruciare tutto
        # Esempio: Leva 10 -> SL 1% (invece di 2%)
        adjusted_sl = DEFAULT_SL_PERCENT / (lev / 2) if lev > 2 else DEFAULT_SL_PERCENT
        adjusted_tp = DEFAULT_TP_PERCENT / (lev / 2) if lev > 2 else DEFAULT_TP_PERCENT
        
        price_prec = PRICE_PRECISION.get(sym, 2)
        sl_price, tp_price = calculate_sl_tp(price, direct, adjusted_sl, adjusted_tp, price_prec)
        
        side = "Buy" if direct == "long" else "Sell"
        
        add_log(sym, f"Opening {direct.upper()} x{lev} | SL: {sl_price} TP: {tp_price}", "info")

        try:
            r = session.place_order(
                category="linear", 
                symbol=sym, 
                side=side, 
                orderType="Market", 
                qty=qty,
                stopLoss=str(sl_price),
                takeProfit=str(tp_price)
            )
            if r['retCode'] == 0: 
                add_log(sym, f"OPENED {direct.upper()} with SL/TP", "success")
            else: 
                add_log(sym, f"Open Rejected: {r['retMsg']}", "error")
        except Exception as e: 
            add_log(sym, f"Open Fail: {e}", "error")

def trading_cycle():
    add_log("SYSTEM", "Smart Batch Engine Started (15m Cycle)", "success")
    while True:
        try:
            bal, pos = get_wallet_data()
            equity_history.append({"time": datetime.now().strftime("%H:%M"), "equity": bal})
            if len(equity_history) > 50: equity_history.pop(0)
            
            payload = {
                "symbols": TARGET_SYMBOLS,
                "portfolio": {"balance_usd": bal, "open_positions": pos}
            }
            
            add_log("AI", "Calling Rizzo Master Brain (Batch)...", "info")
            resp = requests.post(f"{MASTER_AI_URL}/execute_batch_strategy", json=payload, timeout=180)
            
            if resp.status_code == 200:
                data = resp.json()
                trades = data.get("trades", []) 
                if not trades: add_log("AI", "Rizzo says: NO TRADES for now.", "info")
                for trade in trades: execute_decision(trade)
            else:
                add_log("AI", f"API Error: {resp.status_code}", "error")
            
            add_log("SYSTEM", f"Cycle Done. Sleeping 15m...", "info")
            time.sleep(SLEEP_INTERVAL)
            
        except Exception as e:
            add_log("CRASH", f"{e}", "error")
            time.sleep(60)

@app.on_event("startup")
def startup():
    Thread(target=trading_cycle, daemon=True).start()

# --- ENDPOINTS API ---
@app.get("/health")
def health(): return {"status": "active"}

@app.get("/management_logs")
def logs(): return management_logs

@app.get("/get_wallet_balance")
def api_balance(): 
    b, _ = get_wallet_data()
    return {"balance": b}

@app.get("/get_open_positions")
def api_positions():
    _, p = get_wallet_data()
    return p

@app.get("/equity_history")
def api_equity(): return equity_history

@app.post("/close_position")
def manual_close(req: CloseRequest):
    symbol = req.symbol
    add_log("MANUAL", f"Manually closing {symbol}...", "warning")
    
    if not session: return {"status": "error", "message": "No Session"}
    
    _, positions = get_wallet_data()
    target = next((p for p in positions if p['symbol'] == symbol), None)
    
    if target:
        try:
            side = "Sell" if target['side'] == "Buy" else "Buy"
            resp = session.place_order(category="linear", symbol=symbol, side=side, orderType="Market", qty=str(target['size']), reduceOnly=True)
            if resp['retCode'] == 0:
                add_log("MANUAL", f"Closed {symbol} successfully", "success")
                return {"status": "closed", "symbol": symbol}
            else:
                return {"status": "error", "message": resp['retMsg']}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Position not found"}

@app.post("/manage_active_positions")
def manage_compat(): return {"status": "ok"}
