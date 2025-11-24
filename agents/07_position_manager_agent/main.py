import os
import json
import time
import math
import asyncio
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from pybit.unified_trading import HTTP

app = FastAPI(title="Position Manager (Full Logic + 96h History)")

# --- CONFIGURAZIONE ---
session = HTTP(
    testnet=False, 
    api_key=os.getenv("BYBIT_API_KEY"), 
    api_secret=os.getenv("BYBIT_API_SECRET")
)
MASTER_AI_URL = os.getenv("MASTER_AI_AGENT_URL", "http://master-ai-agent:8000")

# Gestione Cartelle Dati
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
HISTORY_FILE = os.path.join(DATA_DIR, "equity_history.json")
LAST_CHECKED_TRADE_TIME = 0 

# --- MODELLI DATI ---
class Position(BaseModel):
    symbol: str; side: str; entry_price: float; stop_loss: float = 0.0
class ManageRequest(BaseModel):
    positions: List[Position] = [] 
class Action(BaseModel):
    action: str; symbol: str; new_stop_loss: float; message: str
class OrderRequest(BaseModel):
    symbol: str; side: str; leverage: int = 5; stop_loss: float; take_profit: float; size_pct: float = 0.2

# ==============================================================================
# 1. TIME MACHINE: RICOSTRUZIONE STORICO 96 ORE
# ==============================================================================
def rebuild_history_if_empty():
    """Se lo storico è vuoto, lo ricostruisce scaricando i trade passati"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                # Se abbiamo già un po' di dati (es. > 5 punti), non serve ricostruire
                if len(data) > 5: return 
        except: pass

    print("⏳ TIME MACHINE: Ricostruzione storico ultime 96 ore...")
    try:
        # 1. Saldo Attuale
        w_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        current_equity = float(w_resp['result']['list'][0]['coin'][0]['equity'])
        
        # 2. Scarica PnL realizzati (limit 100 copre bene gli ultimi giorni)
        pnl_resp = session.get_closed_pnl(category="linear", limit=100)
        trades = []
        if pnl_resp['retCode'] == 0:
            trades = pnl_resp['result']['list']
        
        # Ordina dal più recente al più vecchio per il calcolo a ritroso
        trades.sort(key=lambda x: int(x['updatedTime']), reverse=True)
        
        history_points = []
        running_equity = current_equity
        
        # Aggiungi il punto "ADESSO"
        now_ts = int(time.time())
        history_points.append({
            "ts": now_ts,
            "date": datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d %H:%M"),
            "equity": running_equity
        })
        
        # Limite 96 ore fa
        limit_ts = now_ts - (96 * 3600)
        
        for t in trades:
            ts = int(t['updatedTime']) / 1000
            if ts < limit_ts: break # Ci fermiamo a 96 ore fa
            
            pnl = float(t['closedPnl'])
            # Stima fee se non presente (circa 0.06% taker)
            fee = float(t['qty']) * float(t['avgExitPrice']) * 0.0006 
            net_change = pnl - fee
            
            # CALCOLO INVERSO: Se oggi ho 100 e ho guadagnato 10, ieri avevo 90.
            running_equity -= net_change 
            
            history_points.append({
                "ts": int(ts),
                "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
                "equity": running_equity
            })
            
        # Punto finale (96 ore fa) piatto se non ci sono altri trade
        if len(history_points) < 2:
             history_points.append({
                "ts": int(limit_ts),
                "date": datetime.fromtimestamp(limit_ts).strftime("%Y-%m-%d %H:%M"),
                "equity": running_equity
            })

        # Riordina cronologicamente per il grafico (Vecchio -> Nuovo)
        history_points.sort(key=lambda x: x['ts'])
        
        with open(HISTORY_FILE, "w") as f:
            json.dump(history_points, f)
            
        print(f"✅ Storico ricostruito: {len(history_points)} punti.")
            
    except Exception as e:
        print(f"⚠️ Errore ricostruzione storico: {e}")

def save_equity_snapshot():
    try:
        resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        if resp['retCode'] == 0:
            equity = float(resp['result']['list'][0]['coin'][0]['equity'])
            entry = {"ts": int(time.time()), "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "equity": equity}
            
            history = []
            if os.path.exists(HISTORY_FILE):
                try:
                    with open(HISTORY_FILE, "r") as f: history = json.load(f)
                except: pass
            
            history.append(entry)
            # Filtra doppi vicini (<60s)
            if len(history) > 1 and (history[-1]['ts'] - history[-2]['ts'] < 60):
                history.pop()
                history.append(entry)

            if len(history) > 2000: history = history[-2000:]
            with open(HISTORY_FILE, "w") as f: json.dump(history, f)
    except: pass

# ==============================================================================
# 2. LOGICA DI TRADING & REPORTER
# ==============================================================================

async def report_closed_trades():
    global LAST_CHECKED_TRADE_TIME
    if LAST_CHECKED_TRADE_TIME == 0:
        LAST_CHECKED_TRADE_TIME = int(time.time()) * 1000

    while True:
        try:
            resp = session.get_closed_pnl(category="linear", limit=10)
            if resp['retCode'] == 0:
                trades = resp['result']['list']
                trades.sort(key=lambda x: int(x['updatedTime']))
                
                for t in trades:
                    update_time = int(t['updatedTime'])
                    if update_time > LAST_CHECKED_TRADE_TIME:
                        symbol = t['symbol']
                        pnl = float(t['closedPnl'])
                        exit_price = float(t['avgExitPrice'])
                        try:
                            requests.post(f"{MASTER_AI_URL}/learn", json={"symbol": symbol, "pnl": pnl, "close_price": exit_price, "reason": "TP/SL Hit"}, timeout=5)
                        except: pass
                        LAST_CHECKED_TRADE_TIME = update_time
                        save_equity_snapshot() # Salva equity al chiudersi di un trade
        except: pass
        await asyncio.sleep(60)

# Helpers
instrument_rules_cache = {}
def get_instrument_rules(symbol):
    if symbol in instrument_rules_cache: return instrument_rules_cache[symbol]
    try:
        resp = session.get_instruments_info(category="linear", symbol=symbol)
        if resp['retCode'] == 0:
            i = resp['result']['list'][0]
            rules = {"tick_size": float(i['priceFilter']['tickSize']), "qty_step": float(i['lotSizeFilter']['qtyStep']), "min_qty": float(i['lotSizeFilter']['minOrderQty'])}
            instrument_rules_cache[symbol] = rules
            return rules
    except: pass
    return {"tick_size": 0.01, "qty_step": 0.001, "min_qty": 0.001}

def round_value(v, s): return v if s == 0 else math.floor(v * (1/s)) / (1/s)

def calculate_atr_stop(symbol, side, entry_price):
    try:
        resp = session.get_kline(category="linear", symbol=symbol, interval='60', limit=30)
        if resp['retCode'] != 0: return 0.0
        df = pd.DataFrame(resp['result']['list'], columns=['t','o','h','l','c','v','to'])
        for c in ['h','l','c']: df[c] = df[c].astype(float)
        df['tr'] = df[['h','l','c']].apply(lambda x: max(x['h']-x['l'], abs(x['h']-x['c']), abs(x['l']-x['c'])), axis=1)
        atr = df['tr'].rolling(window=14).mean().iloc[-1]
        return (entry_price - (atr * 2.5)) if side == "Buy" else (entry_price + (atr * 2.5))
    except: return 0.0

# ==============================================================================
# 3. ENDPOINTS API
# ==============================================================================

@app.get("/health")
def health_check(): return {"status": "ok"}

@app.get("/get_wallet_balance")
def get_wallet_balance():
    try:
        w_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        equity = 0.0; available = 0.0
        if w_resp['retCode'] == 0:
            c = w_resp['result']['list'][0]['coin'][0]
            equity = float(c['equity']); available = float(c['walletBalance'])
        
        # CALCOLO LIVE PNL (Somma posizioni aperte)
        live_pnl = 0.0
        p_resp = session.get_positions(category="linear", settleCoin="USDT")
        if p_resp['retCode'] == 0:
            for p in p_resp['result']['list']:
                if float(p['size']) > 0: live_pnl += float(p['unrealisedPnl'])

        return {"equity": equity, "available": available, "live_pnl": live_pnl}
    except Exception as e: return {"equity": 0, "available": 0, "live_pnl": 0, "error": str(e)}

@app.get("/get_history")
def get_history(period: str = "all"):
    # Prova a caricare il file
    if not os.path.exists(HISTORY_FILE): return []
    try:
        with open(HISTORY_FILE, "r") as f: data = json.load(f)
        now = int(time.time())
        m = {"day": 86400, "week": 604800, "month": 2592000}
        if period in m:
            limit = now - m[period]
            data = [x for x in data if x['ts'] >= limit]
        return data
    except: return []

@app.get("/get_open_positions")
def get_open_positions():
    try:
        resp = session.get_positions(category="linear", settleCoin="USDT")
        open_positions = []; details = []
        if resp['retCode'] == 0:
            for p in resp['result']['list']:
                if float(p['size']) > 0:
                    open_positions.append(p['symbol'])
                    details.append({
                        "symbol": p['symbol'], "side": p['side'], "size": float(p['size']),
                        "entry_price": float(p['avgPrice']), "mark_price": float(p['markPrice']),
                        "pnl": float(p['unrealisedPnl']), "leverage": p['leverage']
                    })
        return {"open_positions": open_positions, "details": details}
    except: return {"open_positions": [], "details": []}

@app.post("/manage", response_model=List[Action])
def manage_positions(request: ManageRequest):
    to_check = request.positions
    if not to_check:
        try:
            r = session.get_positions(category="linear", settleCoin="USDT")
            if r['retCode']==0: 
                to_check = [Position(symbol=p['symbol'], side=p['side'], entry_price=float(p['avgPrice']), stop_loss=float(p['stopLoss']) if p['stopLoss'] else 0.0) for p in r['result']['list'] if float(p['size'])>0]
        except: pass
    actions = []
    for pos in to_check:
        sl_calc = calculate_atr_stop(pos.symbol, pos.side, pos.entry_price)
        if sl_calc == 0: continue
        rules = get_instrument_rules(pos.symbol)
        new_sl = round_value(sl_calc, rules['tick_size'])
        upd = False
        if pos.side == "Buy" and new_sl > pos.stop_loss and (new_sl - pos.stop_loss) > (rules['tick_size']*5): upd = True
        elif pos.side == "Sell" and (pos.stop_loss == 0 or new_sl < pos.stop_loss) and (pos.stop_loss==0 or (pos.stop_loss - new_sl) > (rules['tick_size']*5)): upd = True
        if upd:
            try:
                session.set_trading_stop(category="linear", symbol=pos.symbol, stopLoss=str(new_sl), positionIdx=0)
                actions.append(Action(action="update_sl", symbol=pos.symbol, new_stop_loss=new_sl, message="SL updated"))
            except: pass
    return actions

@app.post("/open_position")
def open_position(order: OrderRequest):
    try:
        w = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        eq = float(w['result']['list'][0]['coin'][0]['walletBalance'])
        tick = session.get_tickers(category="linear", symbol=order.symbol)
        price = float(tick['result']['list'][0]['lastPrice'])
        qty_raw = (eq * order.size_pct * order.leverage) / price
        rules = get_instrument_rules(order.symbol)
        qty = round_value(qty_raw, rules['qty_step'])
        if qty < rules['min_qty']: return {"status": "error", "msg": "Qty too small"}
        sl = round_value(order.stop_loss, rules['tick_size'])
        tp = round_value(order.take_profit, rules['tick_size'])
        resp = session.place_order(category="linear", symbol=order.symbol, side=order.side, orderType="Market", qty=str(qty), stopLoss=str(sl), takeProfit=str(tp))
        if resp['retCode'] == 0:
            save_equity_snapshot()
            return {"status": "executed", "order_id": resp['result']['orderId']}
        return {"status": "error", "msg": resp['retMsg']}
    except Exception as e: return {"status": "error", "msg": str(e)}

# ==============================================================================
# 4. STARTUP
# ==============================================================================
@app.on_event("startup")
async def startup_event():
    # 1. Ricostruisci storico se manca
    rebuild_history_if_empty()
    
    # 2. Avvia loops
    asyncio.create_task(report_closed_trades())
    async def equity_loop():
        while True:
            save_equity_snapshot()
            await asyncio.sleep(900)
    asyncio.create_task(equity_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
