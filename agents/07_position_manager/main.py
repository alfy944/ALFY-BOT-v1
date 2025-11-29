import os
import math
import json
import time
import asyncio
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from pybit.unified_trading import HTTP

app = FastAPI()

# --- CONFIGURAZIONE STRATEGIA ---
AI_URL = os.getenv("MASTER_AI_URL", "http://master-ai-agent:8000")
MAX_ALLOCATION = 0.20       # Max capitale per trade
DEFAULT_SL_PCT = 0.02       # 2% Stop Loss (Sicurezza se l'AI non lo specifica)
DEFAULT_TP_PCT = 0.05       # 5% Take Profit (Target base)
TRAILING_TRIGGER = 0.015    # Se profitto > 1.5%, attiva trailing
STATS_FILE = "stats.json"
HISTORY_FILE = "equity_history.json"
MANAGEMENT_LOGS = []
BOT_START_TIME = int(time.time()) * 1000

# --- CONNESSIONE BYBIT ---
client = HTTP(
    testnet=os.getenv("BYBIT_TESTNET")=="true",
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET")
)

# --- MODELLI DATI ---
class Order(BaseModel):
    symbol: str; side: str; leverage: int; size_pct: float
class CloseRequest(BaseModel):
    symbol: str

# --- UTILS ---
def safe_float(val):
    try: return float(val)
    except: return 0.0

def round_step_size(quantity, step_size):
    if step_size == 0: return quantity
    return math.floor(quantity / step_size) * step_size

def load_json(f, d):
    if os.path.exists(f):
        try: 
            with open(f) as file: return json.load(file)
        except: pass
    return d

def save_json(f, d):
    try: 
        with open(f, 'w') as file: json.dump(d, file)
    except: pass

# --- CICLI AUTOMATICI (IL MOTORE) ---
@app.on_event("startup")
async def startup():
    # 1. Ciclo di Trading (Analisi -> Esecuzione con SL/TP)
    asyncio.create_task(trading_loop())
    # 2. Ciclo di Sincronizzazione Dati (Per Dashboard)
    asyncio.create_task(data_sync_loop())
    # 3. Ciclo di Trailing Stop (Gestione Dinamica)
    asyncio.create_task(trailing_stop_loop())

async def trading_loop():
    print(">>> SYSTEM ONLINE: WAITING FOR OPPORTUNITIES...")
    while True:
        try:
            # A. Recupera Dati Mercato Reali
            symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
            market_data = {}
            for sym in symbols:
                try:
                    t = client.get_tickers(category='linear', symbol=sym)['result']['list'][0]
                    market_data[sym] = {
                        'price': float(t['lastPrice']),
                        'change_24h': float(t['price24hPcnt']),
                        'volume_24h': float(t['volume24h']),
                        'turnover_24h': float(t['turnover24h'])
                    }
                except: pass

            # B. Invia al Cervello (Master AI)
            # L'AI usa GPT/Claude per analizzare trend, sentiment e strategia Rizzo
            try:
                r = requests.post(f"{AI_URL}/analyze", json={'raw_data': market_data}, timeout=15)
                decisions = r.json()
            except Exception as e:
                print(f"AI Connection Error: {e}")
                decisions = {}

            # C. Esecuzione Ordini INTELLIGENTE
            if decisions:
                for sym, dec in decisions.items():
                    action = dec.get('decision', 'HOLD')
                    
                    if action in ['OPEN_LONG', 'OPEN_SHORT']:
                        # Verifica se siamo già dentro
                        is_open = False
                        try:
                            curr = client.get_positions(category='linear', symbol=sym)['result']['list'][0]
                            if float(curr['size']) > 0: is_open = True
                        except: pass
                        
                        if not is_open:
                            print(f">>> ESECUZIONE STRATEGIA: {action} su {sym}")
                            # ESEGUE L'ORDINE CON PROTEZIONI
                            do_open_position(
                                symbol=sym, 
                                side='Buy' if 'LONG' in action else 'Sell',
                                leverage=dec.get('leverage', 5),
                                size_pct=dec.get('size_pct', 0.15)
                            )
                            
        except Exception as e:
            print(f"Trading Loop Error: {e}")
        
        await asyncio.sleep(60) # Analisi ogni 60 secondi

async def trailing_stop_loop():
    """Gestisce le posizioni aperte spostando lo SL a profitto"""
    global MANAGEMENT_LOGS
    while True:
        try:
            pos_data = api_positions().get("active", [])
            for p in pos_data:
                entry = p['entry_price']
                mark = p['mark_price']
                curr_sl = p['sl']
                side = p['side']
                sym = p['symbol']
                size = p['size']
                
                # Calcolo ROI%
                if entry > 0:
                    roi = (mark - entry)/entry if side == "Buy" else (entry - mark)/entry
                    
                    # SE PROFITTO > TRIGGER (es. 1.5%), SPOSTA SL A BE (Break Even) + piccolo profitto
                    if roi > TRAILING_TRIGGER:
                        new_sl = entry * 1.005 if side == "Buy" else entry * 0.995
                        
                        should_update = False
                        if side == "Buy" and new_sl > curr_sl: should_update = True
                        if side == "Sell" and (curr_sl == 0 or new_sl < curr_sl): should_update = True
                        
                        if should_update:
                            try:
                                client.set_trading_stop(category="linear", symbol=sym, stopLoss=str(round(new_sl, 4)))
                                
                                log_entry = {
                                    "time": int(time.time()),
                                    "symbol": sym,
                                    "details": f"Trailing Stop attivato a {new_sl:.2f} (ROI: {roi*100:.2f}%)",
                                    "locked_profit": "SECURED"
                                }
                                MANAGEMENT_LOGS.insert(0, log_entry)
                                if len(MANAGEMENT_LOGS)>50: MANAGEMENT_LOGS.pop()
                            except: pass
        except: pass
        await asyncio.sleep(10)

async def data_sync_loop():
    """Tiene aggiornati i dati per la Dashboard"""
    while True:
        try:
            bal = get_balance_internal()
            if bal['equity'] > 0:
                h = load_json(HISTORY_FILE, [])
                h.append({"ts": int(time.time()), "equity": bal['equity']})
                save_json(HISTORY_FILE, h[-2000:])
            
            r = client.get_closed_pnl(category="linear", limit=50)
            if r.get('result'):
                trades = [t for t in r['result']['list'] if int(t['updatedTime']) > BOT_START_TIME]
                wins = sum(1 for t in trades if safe_float(t['closedPnl']) > 0)
                pnl = sum(safe_float(t['closedPnl']) for t in trades)
                wr = (wins/len(trades)*100) if len(trades)>0 else 0
                save_json(STATS_FILE, {"total_pnl": round(pnl, 2), "win_rate": round(wr, 1)})
        except: pass
        await asyncio.sleep(30)

# --- FUNZIONI ESECUTIVE (ORDER BLOCK) ---
def get_balance_internal():
    try:
        r = client.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        if r['retCode']==0 and r['result']['list']:
            c = r['result']['list'][0]['coin'][0]
            eq = safe_float(c.get('equity'))
            av = safe_float(c.get('availableToWithdraw'))
            # Fix Smart Balance se available è buggato
            if eq > 0 and av == 0: av = eq - 2.0 
            return {"equity": eq, "availableToWithdraw": av}
    except: pass
    return {"equity":0.0, "availableToWithdraw":0.0}

def do_open_position(symbol, side, leverage, size_pct):
    try:
        # 1. Check Fondi
        bal = get_balance_internal()
        if bal['availableToWithdraw'] < 5: return
        
        # 2. Configura Leva
        try: client.set_leverage(category="linear", symbol=symbol, buyLeverage=str(leverage), sellLeverage=str(leverage))
        except: pass

        # 3. Calcola Quantità
        ticker = client.get_tickers(category="linear", symbol=symbol)
        price = safe_float(ticker['result']['list'][0]['lastPrice'])
        
        trade_amt = bal['availableToWithdraw'] * min(size_pct, MAX_ALLOCATION) * leverage
        
        # Rispetta i filtri di quantità di Bybit
        instr = client.get_instruments_info(category="linear", symbol=symbol)
        qty_step = float(instr['result']['list'][0]['lotSizeFilter']['qtyStep'])
        min_qty = float(instr['result']['list'][0]['lotSizeFilter']['minOrderQty'])
        
        raw_qty = trade_amt / price
        qty = max(min_qty, round_step_size(raw_qty, qty_step))

        # 4. CALCOLA SL e TP (Cruciale per strategia Rizzo)
        # Se Side è Buy: SL sotto, TP sopra. Se Sell: SL sopra, TP sotto.
        sl_price = price * (1 - DEFAULT_SL_PCT) if side == "Buy" else price * (1 + DEFAULT_SL_PCT)
        tp_price = price * (1 + DEFAULT_TP_PCT) if side == "Buy" else price * (1 - DEFAULT_TP_PCT)

        # 5. INVIA ORDINE COMPLETO
        client.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            stopLoss=str(round(sl_price, 4)),
            takeProfit=str(round(tp_price, 4))
        )
        print(f">>> ORDINE APERTO: {symbol} {side} x{leverage} | SL: {sl_price:.2f} TP: {tp_price:.2f}")
        
    except Exception as e:
        print(f"Order Failed: {e}")

# --- API ENDPOINTS ---
@app.get("/get_wallet_balance")
def api_balance(): return get_balance_internal()
@app.get("/stats")
def api_stats(): return load_json(STATS_FILE, {})
@app.get("/equity_history")
def api_hist(): return {"history": load_json(HISTORY_FILE, [])}
@app.get("/management_logs")
def api_logs(): return {"logs": MANAGEMENT_LOGS}
@app.get("/get_open_positions")
def api_positions():
    try:
        r = client.get_positions(category="linear", settleCoin="USDT")
        active = []
        for p in r['result']['list']:
            if safe_float(p['size']) > 0:
                active.append({
                    "symbol": p['symbol'], "side": p['side'], "size": p['size'],
                    "entry_price": safe_float(p['avgPrice']), "mark_price": safe_float(p['markPrice']),
                    "pnl": safe_float(p['unrealisedPnl']), "leverage": p['leverage'], "sl": safe_float(p['stopLoss'])
                })
        return {"active": active}
    except: return {"active": []}

@app.post("/close_position")
def close_pos(r: CloseRequest):
    try:
        pos = client.get_positions(category="linear", symbol=r.symbol)['result']['list'][0]
        if float(pos['size']) > 0:
            side = "Sell" if pos['side']=="Buy" else "Buy"
            client.place_order(category="linear", symbol=r.symbol, side=side, qty=pos['size'], orderType="Market", reduceOnly=True)
            return {"status": "closed"}
    except Exception as e: return {"error": str(e)}
    
@app.post("/open_position")
def api_open(o: Order):
    do_open_position(o.symbol, o.side, o.leverage, o.size_pct)
    return {"status": "ok"}
