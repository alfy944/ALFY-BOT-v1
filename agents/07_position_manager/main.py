import os
import ccxt
import json
import time
import requests
import httpx
from decimal import Decimal, ROUND_DOWN
from datetime import datetime
from typing import Optional, Any, Dict, Tuple
from fastapi import FastAPI
from pydantic import BaseModel
from threading import Thread, Lock

app = FastAPI()

# =========================================================
# CONFIG
# =========================================================
HISTORY_FILE = os.getenv("HISTORY_FILE", "equity_history.json")

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

# Se usi Hedge Mode su Bybit (posizioni long/short contemporanee),
# metti BYBIT_HEDGE_MODE=true. Se non sei sicuro, lascialo false.
HEDGE_MODE = os.getenv("BYBIT_HEDGE_MODE", "false").lower() == "true"
BYBIT_POSITION_MODE = os.getenv("BYBIT_POSITION_MODE", "oneway").lower()
BYBIT_FORCE_POSITION_IDX = os.getenv("BYBIT_FORCE_POSITION_IDX", "false").lower() == "true"
BYBIT_ENFORCE_ONEWAY = os.getenv("BYBIT_ENFORCE_ONEWAY", "true").lower() == "true"

# --- PARAMETRI TRAILING STOP DINAMICO (ATR-BASED) ---
TRAILING_ACTIVATION_PCT = float(os.getenv("TRAILING_ACTIVATION_PCT", "0.018"))  # 1.8% (leveraged ROI fraction)
ATR_MULTIPLIER_DEFAULT = float(os.getenv("ATR_MULTIPLIER_DEFAULT", "2.5"))
ATR_MULTIPLIERS = {
    "BTC": 2.0,
    "ETH": 2.0,
    "SOL": 3.0,
    "DOGE": 3.5,
    "PEPE": 4.0,
}
TECHNICAL_ANALYZER_URL = os.getenv("TECHNICAL_ANALYZER_URL", "http://01_technical_analyzer:8000").strip()
FALLBACK_TRAILING_PCT = float(os.getenv("FALLBACK_TRAILING_PCT", "0.025"))  # 2.5%
DEFAULT_INITIAL_SL_PCT = float(os.getenv("DEFAULT_INITIAL_SL_PCT", "0.04"))  # 4%
BREAK_EVEN_R = float(os.getenv("BREAK_EVEN_R", "0.9"))
TIME_STOP_MINUTES = int(os.getenv("TIME_STOP_MINUTES", "14"))
PARTIAL_TP_PCT = float(os.getenv("PARTIAL_TP_PCT", "0.5"))
PARTIAL_TP_R = float(os.getenv("PARTIAL_TP_R", "0.8"))
TRAILING_ATR_MULTIPLIER = float(os.getenv("TRAILING_ATR_MULTIPLIER", "1.1"))
ENTRY_ORDER_TYPE = os.getenv("ENTRY_ORDER_TYPE", "limit").lower()

# --- PARAMETRI AI REVIEW / REVERSE ---
ENABLE_AI_REVIEW = os.getenv("ENABLE_AI_REVIEW", "true").lower() == "true"
MASTER_AI_URL = os.getenv("MASTER_AI_URL", "http://04_master_ai_agent:8000").strip()

WARNING_THRESHOLD = float(os.getenv("WARNING_THRESHOLD", "-0.08"))
AI_REVIEW_THRESHOLD = float(os.getenv("AI_REVIEW_THRESHOLD", "-0.12"))
REVERSE_THRESHOLD = float(os.getenv("REVERSE_THRESHOLD", "-0.15"))
HARD_STOP_THRESHOLD = float(os.getenv("HARD_STOP_THRESHOLD", "-0.20"))

REVERSE_COOLDOWN_MINUTES = int(os.getenv("REVERSE_COOLDOWN_MINUTES", "30"))
REVERSE_LEVERAGE = float(os.getenv("REVERSE_LEVERAGE", "5.0"))
reverse_cooldown_tracker: Dict[str, float] = {}

# --- COOLDOWN CONFIGURATION ---
# Direzione specifica (long/short) dopo close: default 60 minuti
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "60"))
COOLDOWN_PNL_THRESHOLD_PCT = float(os.getenv("COOLDOWN_PNL_THRESHOLD_PCT", "5.0"))
COOLDOWN_FILE = os.getenv("COOLDOWN_FILE", "/data/closed_cooldown.json")

# --- AI DECISIONS FILE ---
AI_DECISIONS_FILE = os.getenv("AI_DECISIONS_FILE", "/data/ai_decisions.json")

# --- LEARNING AGENT ---
LEARNING_AGENT_URL = os.getenv("LEARNING_AGENT_URL", "http://10_learning_agent:8000").strip()
DEFAULT_SIZE_PCT = float(os.getenv("DEFAULT_SIZE_PCT", "0.15"))

file_lock = Lock()
position_risk_meta: Dict[str, dict] = {}

# =========================================================
# HELPERS
# =========================================================
def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

def to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "" or s.lower() == "none":
            return default
        return float(s)
    except Exception:
        return default

def symbol_base(symbol: str) -> str:
    """
    Estrae l'asset base: "BTC" da:
    - "BTC/USDT:USDT"
    - "BTC/USDT"
    - "BTCUSDT"
    """
    s = str(symbol).strip()
    if ":" in s:
        s = s.split(":")[0]
    s = s.replace("/", "")
    s = s.replace("USDT", "")
    return s.upper()

def bybit_symbol_id(symbol: str) -> str:
    """
    Converte in formato Bybit id: "BTCUSDT"
    """
    s = str(symbol).strip()
    if ":" in s:
        s = s.split(":")[0]
    s = s.replace("/", "")
    s = s.upper()
    if not s.endswith("USDT"):
        # se ci arriva "BTC", aggiungiamo USDT
        s = f"{s}USDT"
    return s

def ccxt_symbol_from_id(exchange_obj, sym_id: str) -> Optional[str]:
    """
    Trova il simbolo CCXT (tipo "BTC/USDT:USDT") a partire dall'id (tipo "BTCUSDT")
    """
    try:
        for m in exchange_obj.markets.values():
            if m.get("id") == sym_id and m.get("linear", False):
                return m.get("symbol")
    except Exception:
        pass
    return None

def normalize_position_side(side_raw: str) -> Optional[str]:
    """
    Normalizza verso 'long' / 'short'
    """
    s = (side_raw or "").lower().strip()
    if s in ("long", "buy"):
        return "long"
    if s in ("short", "sell"):
        return "short"
    return None

def side_to_order_side(direction: str) -> str:
    """
    'long' -> 'buy'
    'short' -> 'sell'
    """
    return "buy" if direction == "long" else "sell"

def direction_to_position_idx(direction: str) -> int:
    """
    Bybit Hedge Mode:
      long  -> positionIdx 1
      short -> positionIdx 2
    One-way:
      0
    """
    if not use_position_idx():
        return 0
    return 1 if direction == "long" else 2

def should_use_position_idx() -> bool:
    return (
        HEDGE_MODE
        and BYBIT_POSITION_MODE == "hedge"
        and BYBIT_FORCE_POSITION_IDX
        and not BYBIT_ENFORCE_ONEWAY
    )

POSITION_IDX_ENABLED = should_use_position_idx()

def use_position_idx() -> bool:
    return POSITION_IDX_ENABLED

def disable_position_idx(reason: str) -> None:
    global POSITION_IDX_ENABLED
    if POSITION_IDX_ENABLED:
        POSITION_IDX_ENABLED = False
        print(f"⚠️ positionIdx disabilitato: {reason}")

def strip_position_idx(params: dict) -> dict:
    if BYBIT_ENFORCE_ONEWAY or BYBIT_POSITION_MODE != "hedge":
        params.pop("positionIdx", None)
    return params

def get_position_idx_from_position(p: dict) -> int:
    """
    Se Bybit/CCXT riporta positionIdx in info, usalo.
    Altrimenti usa la modalità HEDGE_MODE.
    """
    info = p.get("info", {}) or {}
    idx = info.get("positionIdx", None)
    idx_f = int(to_float(idx, 0))
    if idx_f in (0, 1, 2):
        return idx_f
    side_dir = normalize_position_side(p.get("side", ""))
    if side_dir:
        return direction_to_position_idx(side_dir)
    return 0

# =========================================================
# JSON MEMORY (thread-safe)
# =========================================================
def load_json(path: str, default=None):
    if default is None:
        default = []
    with file_lock:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

def save_json(path: str, data):
    ensure_parent_dir(path)
    with file_lock:
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

# =========================================================
# EXCHANGE SETUP
# =========================================================
exchange = None
if API_KEY and API_SECRET:
    try:
        exchange = ccxt.bybit({
            "apiKey": API_KEY,
            "secret": API_SECRET,
            "options": {
                "defaultType": "swap",
                "adjustForTimeDifference": True,
            },
        })
        if IS_TESTNET:
            exchange.set_sandbox_mode(True)
        exchange.load_markets()
        print(f"🔌 Position Manager: Connesso (Testnet: {IS_TESTNET}) | HedgeMode: {HEDGE_MODE}")
    except Exception as e:
        print(f"⚠️ Errore Connessione: {e}")
else:
    print("⚠️ BYBIT_API_KEY/BYBIT_API_SECRET mancanti: exchange non inizializzato")

# =========================================================
# BACKGROUND: EQUITY HISTORY LOOP
# =========================================================
def record_equity_loop():
    while True:
        if exchange:
            try:
                bal = exchange.fetch_balance(params={"type": "swap"})
                usdt = bal.get("USDT", {}) or {}
                real_bal = to_float(usdt.get("total", 0), 0.0)

                pos = exchange.fetch_positions(None, params={"category": "linear"})
                upnl = sum([to_float(p.get("unrealizedPnl"), 0.0) for p in pos])

                hist = load_json(HISTORY_FILE, default=[])
                hist.append({
                    "timestamp": datetime.now().isoformat(),
                    "real_balance": real_bal,
                    "live_equity": real_bal + upnl,
                })
                if len(hist) > 4000:
                    hist = hist[-4000:]
                save_json(HISTORY_FILE, hist)
            except Exception:
                pass

        time.sleep(60)

Thread(target=record_equity_loop, daemon=True).start()

# =========================================================
# MODELS
# =========================================================
class OrderRequest(BaseModel):
    symbol: str
    side: str = "buy"          # buy/sell/long/short
    leverage: float = 1.0
    size_pct: float = 0.0      # frazione del free USDT (es. 0.15)
    sl_pct: float = 0.0        # frazione (es. 0.04)

class CloseRequest(BaseModel):
    symbol: str

# =========================================================
# LEARNING AGENT
# =========================================================
def record_closed_trade(
    symbol: str,
    side: str,
    entry_price: float,
    exit_price: float,
    pnl_pct: float,
    leverage: float,
    size_pct: float,
    duration_minutes: int,
    market_conditions: Optional[dict] = None
):
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(
                f"{LEARNING_AGENT_URL}/record_trade",
                json={
                    "timestamp": datetime.now().isoformat(),
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl_pct": pnl_pct,
                    "leverage": leverage,
                    "size_pct": size_pct,
                    "duration_minutes": duration_minutes,
                    "market_conditions": market_conditions or {},
                },
            )
            if r.status_code == 200:
                print(f"📚 Trade recorded for learning: {symbol} {side} PnL={pnl_pct:.2f}%")
    except Exception as e:
        print(f"⚠️ Failed to record trade for learning: {e}")

def record_trade_for_learning(
    symbol: str,
    side_raw: str,
    entry_price: float,
    exit_price: float,
    leverage: float,
    duration_minutes: int,
    market_conditions: Optional[dict] = None
):
    try:
        side_dir = normalize_position_side(side_raw) or "long"
        asset = symbol_base(symbol)

        pnl_raw = 0.0
        if entry_price > 0:
            if side_dir == "long":
                pnl_raw = (exit_price - entry_price) / entry_price
            else:
                pnl_raw = (entry_price - exit_price) / entry_price

        pnl_pct = pnl_raw * leverage * 100.0

        record_closed_trade(
            symbol=asset,
            side=side_dir,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl_pct=pnl_pct,
            leverage=leverage,
            size_pct=DEFAULT_SIZE_PCT,
            duration_minutes=duration_minutes,
            market_conditions=market_conditions or {},
        )
    except Exception as e:
        print(f"⚠️ Errore in record_trade_for_learning: {e}")

# =========================================================
# ATR FUNCTIONS
# =========================================================
def get_market_risk_data(symbol: str) -> Dict[str, Any]:
    try:
        clean_id = bybit_symbol_id(symbol)  # BTCUSDT
        with httpx.Client(timeout=5.0) as client:
            r = client.post(f"{TECHNICAL_ANALYZER_URL}/analyze_multi_tf", json={"symbol": clean_id})
            if r.status_code == 200:
                d = r.json() or {}
                return {
                    "atr": to_float(d.get("details", {}).get("atr") or d.get("atr")),
                    "price": to_float(d.get("price")),
                    "momentum_exit": (d.get("momentum_exit") or {}),
                    "trend": d.get("trend"),
                    "macd_hist": to_float(d.get("macd_hist"), None),
                    "rsi": to_float(d.get("rsi"), None),
                    "ema_20": to_float((d.get("details", {}) or {}).get("ema_20"), None),
                }
    except Exception:
        pass
    return {"atr": None, "price": None, "momentum_exit": {}}

def get_trailing_distance_pct(symbol: str, mark_price: float) -> float:
    data = get_market_risk_data(symbol)
    atr, price = data.get("atr"), data.get("price")
    if atr and price and price > 0:
        base = symbol_base(symbol)
        mult = float(ATR_MULTIPLIERS.get(base, ATR_MULTIPLIER_DEFAULT))
        pct = min(0.08, max(0.01, (atr * mult) / price))
        print(f"📊 ATR {symbol}: {atr:.6f}, mult={mult}, trailing={pct*100:.2f}%")
        return pct

    print(f"⚠️ ATR unavailable for {symbol}, using fallback {FALLBACK_TRAILING_PCT*100:.2f}%")
    return FALLBACK_TRAILING_PCT

# =========================================================
# TRAILING LOGIC (ATR-BASED)
# =========================================================
def check_and_update_trailing_stops():
    if not exchange:
        return

    try:
        positions = exchange.fetch_positions(None, params={"category": "linear"})

        for p in positions:
            qty = to_float(p.get("contracts"), 0.0)
            if qty == 0:
                continue

            symbol = p.get("symbol", "")
            if not symbol:
                continue

            try:
                market_id = exchange.market(symbol).get("id") or bybit_symbol_id(symbol)
            except Exception:
                market_id = bybit_symbol_id(symbol)

            side_dir = normalize_position_side(p.get("side", ""))
            if not side_dir:
                continue

            entry_price = to_float(p.get("entryPrice"), 0.0)
            mark_price = to_float(p.get("markPrice"), 0.0)
            if entry_price <= 0 or mark_price <= 0:
                continue

            info = p.get("info", {}) or {}
            sl_current = to_float(info.get("stopLoss") or p.get("stopLoss"), 0.0)

            leverage = max(1.0, to_float(p.get("leverage"), 1.0))

            if side_dir == "long":
                roi_raw = (mark_price - entry_price) / entry_price
            else:
                roi_raw = (entry_price - mark_price) / entry_price
            roi = roi_raw * leverage

            sym_id = bybit_symbol_id(symbol)
            risk_data = get_market_risk_data(symbol)
            atr = risk_data.get("atr")
            momentum_exit = risk_data.get("momentum_exit") or {}
            ema_20 = to_float(risk_data.get("ema_20"), 0.0)

            # Momentum-based soft exit (2/3 conditions)
            if momentum_exit.get(side_dir):
                print(f"⏱️ Momentum exit triggered for {symbol} ({side_dir}) - closing position")
                execute_close_position(symbol)
                continue

            # Track initial SL distance per symbol for 1R calculations
            meta = position_risk_meta.get(sym_id, {})
            initial_sl_price = meta.get("initial_sl")
            if not initial_sl_price or abs(meta.get("entry_price", 0) - entry_price) > 0.5:
                base_sl = sl_current
                if base_sl == 0.0:
                    if atr:
                        base_sl = entry_price - (atr * 1.2) if side_dir == "long" else entry_price + (atr * 1.2)
                    else:
                        base_sl = entry_price * (1 - DEFAULT_INITIAL_SL_PCT) if side_dir == "long" else entry_price * (1 + DEFAULT_INITIAL_SL_PCT)
                position_risk_meta[sym_id] = {
                    "entry_price": entry_price,
                    "initial_sl": base_sl,
                    "entry_ts": time.time(),
                    "partial_tp_taken": False,
                }
                initial_sl_price = base_sl

            if not initial_sl_price:
                initial_sl_price = sl_current

            risk_distance = 0.0
            if initial_sl_price and entry_price:
                risk_distance = (entry_price - initial_sl_price) if side_dir == "long" else (initial_sl_price - entry_price)

            # Time stop: close if trade stalls after N minutes
            entry_ts = position_risk_meta.get(sym_id, {}).get("entry_ts", time.time())
            elapsed_minutes = (time.time() - entry_ts) / 60.0
            profit_distance = (mark_price - entry_price) if side_dir == "long" else (entry_price - mark_price)
            if risk_distance > 0 and elapsed_minutes >= TIME_STOP_MINUTES:
                if profit_distance < (risk_distance * 0.2):
                    print(f"⏱️ Time-stop triggered for {symbol} ({side_dir}) after {elapsed_minutes:.1f}m")
                    execute_close_position(symbol)
                    continue

            # Partial take profit at 1R
            if risk_distance > 0 and not position_risk_meta.get(sym_id, {}).get("partial_tp_taken"):
                if profit_distance >= (risk_distance * PARTIAL_TP_R):
                    try:
                        target_market = exchange.market(symbol)
                        info = target_market.get("info", {}) or {}
                        lot_filter = info.get("lotSizeFilter", {}) or {}
                        qty_step = to_float(lot_filter.get("qtyStep") or (target_market.get("limits", {}).get("amount", {}) or {}).get("min"), 0.001)
                        min_qty = to_float(lot_filter.get("minOrderQty") or qty_step, qty_step)
                        partial_qty = max(qty * PARTIAL_TP_PCT, min_qty)
                        partial_qty = float(exchange.amount_to_precision(symbol, partial_qty))
                        if partial_qty >= min_qty:
                            close_side = "sell" if side_dir == "long" else "buy"
                            params = {"category": "linear", "reduceOnly": True}
                            if use_position_idx():
                                params["positionIdx"] = get_position_idx_from_position(p)
                            params = strip_position_idx(params)
                            exchange.create_order(symbol, "market", close_side, partial_qty, params=params)
                            position_risk_meta[sym_id]["partial_tp_taken"] = True
                            print(f"✅ Partial TP {symbol} {side_dir}: {partial_qty} @ {profit_distance:.6f}")
                    except Exception as e:
                        print(f"⚠️ Partial TP failed for {symbol}: {e}")

            # Break-even: lock stop to entry after 1R
            new_sl_price = None
            if risk_distance > 0:
                if profit_distance >= (risk_distance * BREAK_EVEN_R):
                    target_be = entry_price
                    if side_dir == "long":
                        if sl_current == 0.0 or target_be > sl_current:
                            new_sl_price = target_be
                    else:
                        if sl_current == 0.0 or target_be < sl_current:
                            new_sl_price = target_be
                    position_risk_meta[sym_id]["breakeven_reached"] = True

            # Trailing ATR after break-even
            if (position_risk_meta.get(sym_id, {}).get("breakeven_reached") or sl_current == entry_price) and atr:
                trailing_target = mark_price - (atr * TRAILING_ATR_MULTIPLIER) if side_dir == "long" else mark_price + (atr * TRAILING_ATR_MULTIPLIER)
                if side_dir == "long":
                    if sl_current == 0.0 or trailing_target > sl_current:
                        new_sl_price = max(new_sl_price or 0, trailing_target)
                else:
                    if sl_current == 0.0 or trailing_target < sl_current:
                        new_sl_price = trailing_target if new_sl_price is None else min(new_sl_price, trailing_target)

                # Structure-aware trailing using EMA20 as dynamic support/resistance
                if ema_20 > 0 and atr:
                    if side_dir == "long":
                        structure_sl = ema_20 - (atr * 0.2)
                        if sl_current == 0.0 or structure_sl > sl_current:
                            new_sl_price = max(new_sl_price or 0, structure_sl)
                    else:
                        structure_sl = ema_20 + (atr * 0.2)
                        if sl_current == 0.0 or structure_sl < sl_current:
                            new_sl_price = structure_sl if new_sl_price is None else min(new_sl_price, structure_sl)

            # Fallback trailing distance if ATR unavailable but break-even reached
            if new_sl_price is None and (position_risk_meta.get(sym_id, {}).get("breakeven_reached") or sl_current == entry_price):
                trailing_distance = get_trailing_distance_pct(symbol, mark_price)
                if side_dir == "long":
                    target_sl = mark_price * (1 - trailing_distance)
                    if sl_current == 0.0 or target_sl > sl_current:
                        new_sl_price = target_sl
                else:
                    target_sl = mark_price * (1 + trailing_distance)
                    if sl_current == 0.0 or target_sl < sl_current:
                        new_sl_price = target_sl

            if not new_sl_price:
                continue

            price_str = exchange.price_to_precision(symbol, new_sl_price)
            position_idx = get_position_idx_from_position(p) if use_position_idx() else 0

            print(
                f"🏃 SL UPDATE {symbol} ROI={roi*100:.2f}% "
                f"SL {sl_current} -> {price_str} (ATR={atr})"
                f"{f' idx={position_idx}' if use_position_idx() else ''}"
            )

            try:
                req = {
                    "category": "linear",
                    "symbol": market_id,
                    "tpslMode": "Full",
                    "stopLoss": price_str,
                }
                if use_position_idx():
                    req["positionIdx"] = position_idx
                req = strip_position_idx(req)
                exchange.private_post_v5_position_trading_stop(req)
                print("✅ SL Aggiornato con successo su Bybit")
            except Exception as api_err:
                print(f"❌ Errore API Bybit (trading_stop): {api_err}")

    except Exception as e:
        print(f"⚠️ Trailing logic error: {e}")

# =========================================================
# AI DECISIONS PERSISTENCE
# =========================================================
def save_ai_decision(decision_data: dict):
    try:
        ensure_parent_dir(AI_DECISIONS_FILE)
        decisions = load_json(AI_DECISIONS_FILE, default=[])

        decisions.append({
            "timestamp": datetime.now().isoformat(),
            "symbol": decision_data.get("symbol"),
            "action": decision_data.get("action"),
            "leverage": decision_data.get("leverage", 0),
            "size_pct": decision_data.get("size_pct", 0),
            "rationale": decision_data.get("rationale", ""),
            "analysis_summary": decision_data.get("analysis_summary", ""),
            "roi_pct": decision_data.get("roi_pct", 0),
            "source": "position_manager",
        })

        decisions = decisions[-100:]
        save_json(AI_DECISIONS_FILE, decisions)

    except Exception as e:
        print(f"⚠️ Error saving AI decision: {e}")

def request_reverse_analysis(symbol: str, position_data: dict) -> Optional[dict]:
    try:
        sym_id = bybit_symbol_id(symbol)
        response = requests.post(
            f"{MASTER_AI_URL}/analyze_reverse",
            json={
                "symbol": sym_id,
                "current_position": position_data,
            },
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()

        print(f"⚠️ Reverse analysis failed: HTTP {response.status_code}")
        return None

    except requests.exceptions.Timeout:
        print(f"⚠️ Reverse analysis timeout for {symbol}")
        return None
    except Exception as e:
        print(f"⚠️ Reverse analysis error: {e}")
        return None

# =========================================================
# CLOSE / REVERSE EXECUTION
# =========================================================
def execute_close_position(symbol: str) -> bool:
    if not exchange:
        return False

    try:
        # accetta sia CCXT symbol sia id
        sym_id = bybit_symbol_id(symbol)
        sym_ccxt = ccxt_symbol_from_id(exchange, sym_id) or symbol
        positions = exchange.fetch_positions([sym_ccxt], params={"category": "linear"})

        position = None
        for p in positions:
            if to_float(p.get("contracts"), 0.0) > 0:
                position = p
                break

        if not position:
            print(f"⚠️ Nessuna posizione aperta per {symbol}")
            return False

        entry_price = to_float(position.get("entryPrice"), 0.0)
        mark_price = to_float(position.get("markPrice"), entry_price)
        leverage = max(1.0, to_float(position.get("leverage"), 1.0))
        side_dir = normalize_position_side(position.get("side", "")) or "long"

        position_idx = get_position_idx_from_position(position) if use_position_idx() else 0

        if entry_price > 0:
            pnl_raw = (mark_price - entry_price) / entry_price if side_dir == "long" else (entry_price - mark_price) / entry_price
        else:
            pnl_raw = 0.0
        pnl_pct = pnl_raw * leverage * 100.0

        size = to_float(position.get("contracts"), 0.0)
        close_side = "sell" if side_dir == "long" else "buy"

        print(f"🔒 Chiudo posizione {sym_ccxt}: {side_dir} size={size} idx={position_idx}")

        params = {"category": "linear", "reduceOnly": True}
        if use_position_idx():
            params["positionIdx"] = position_idx
        params = strip_position_idx(params)

        exchange.create_order(sym_ccxt, "market", close_side, size, params=params)

        record_trade_for_learning(
            symbol=sym_id,
            side_raw=side_dir,
            entry_price=entry_price,
            exit_price=mark_price,
            leverage=leverage,
            duration_minutes=0,
            market_conditions={},
        )

        # Cooldown (solo se PnL supera la soglia)
        try:
            if abs(pnl_pct) >= COOLDOWN_PNL_THRESHOLD_PCT:
                ensure_parent_dir(COOLDOWN_FILE)
                cooldowns = load_json(COOLDOWN_FILE, default={})

                direction_key = f"{sym_id}_{side_dir}"  # long/short
                now_ts = time.time()
                cooldowns[direction_key] = now_ts
                cooldowns[sym_id] = now_ts

                save_json(COOLDOWN_FILE, cooldowns)
                print(f"💾 Cooldown salvato per {direction_key} (PnL {pnl_pct:.2f}%)")
            else:
                print(f"ℹ️ Cooldown non applicato: PnL {pnl_pct:.2f}% < {COOLDOWN_PNL_THRESHOLD_PCT}%")
        except Exception as e:
            print(f"⚠️ Errore salvataggio cooldown: {e}")

        print(f"✅ Posizione {sym_ccxt} chiusa con successo | PnL={pnl_pct:.2f}%")
        return True

    except Exception as e:
        print(f"❌ Errore chiusura posizione {symbol}: {e}")
        return False

def execute_reverse(symbol: str, current_side_raw: str, recovery_size_pct: float) -> bool:
    if not exchange:
        return False

    try:
        sym_id = bybit_symbol_id(symbol)
        sym_ccxt = ccxt_symbol_from_id(exchange, sym_id) or symbol

        current_dir = normalize_position_side(current_side_raw) or "long"
        new_dir = "short" if current_dir == "long" else "long"
        new_side = side_to_order_side(new_dir)

        # chiudi prima
        if not execute_close_position(sym_ccxt):
            return False

        time.sleep(1)

        bal = exchange.fetch_balance(params={"type": "swap"})
        free_balance = to_float((bal.get("USDT", {}) or {}).get("free", 0.0), 0.0)
        price = to_float(exchange.fetch_ticker(sym_ccxt).get("last"), 0.0)
        if price <= 0:
            print("❌ Prezzo non valido per reverse")
            return False

        cost = max(free_balance * recovery_size_pct, 10.0)
        leverage = REVERSE_LEVERAGE

        target_market = exchange.market(sym_ccxt)
        info = target_market.get("info", {}) or {}
        lot_filter = info.get("lotSizeFilter", {}) or {}
        qty_step = to_float(lot_filter.get("qtyStep") or (target_market.get("limits", {}).get("amount", {}) or {}).get("min"), 0.001)
        min_qty = to_float(lot_filter.get("minOrderQty") or qty_step, qty_step)

        qty_raw = (cost * leverage) / price
        d_qty = Decimal(str(qty_raw))
        d_step = Decimal(str(qty_step))
        steps = (d_qty / d_step).to_integral_value(rounding=ROUND_DOWN)
        final_qty_d = steps * d_step
        if final_qty_d < Decimal(str(min_qty)):
            final_qty_d = Decimal(str(min_qty))
        final_qty = float("{:f}".format(final_qty_d.normalize()))

        # set leverage
        try:
            exchange.set_leverage(int(leverage), sym_ccxt, params={"category": "linear"})
        except Exception as e:
            print(f"⚠️ Impossibile impostare leva (ccxt): {e}")

        # SL iniziale
        sl_pct = DEFAULT_INITIAL_SL_PCT
        sl_price = price * (1 - sl_pct) if new_dir == "long" else price * (1 + sl_pct)
        sl_str = exchange.price_to_precision(sym_ccxt, sl_price)

        pos_idx = direction_to_position_idx(new_dir)

        print(
            f"🔄 REVERSE {sym_ccxt}: {current_dir} -> {new_dir}, "
            f"size={recovery_size_pct*100:.1f}%, qty={final_qty}, idx={pos_idx}"
        )

        params = {"category": "linear", "stopLoss": sl_str}
        if use_position_idx():
            params["positionIdx"] = pos_idx
        params = strip_position_idx(params)

        res = exchange.create_order(sym_ccxt, "market", new_side, final_qty, params=params)
        print(f"✅ Reverse eseguito con successo: {res.get('id')}")
        return True

    except Exception as e:
        print(f"❌ Errore durante reverse: {e}")
        return False

# =========================================================
# AUTO-COOLDOWN FROM CLOSED PNL
# =========================================================
def check_recent_closes_and_save_cooldown():
    if not exchange:
        return

    try:
        res = exchange.private_get_v5_position_closed_pnl({
            "category": "linear",
            "limit": 20,
        })

        if not res or res.get("retCode") != 0:
            return

        items = (res.get("result", {}) or {}).get("list", []) or []
        current_time = time.time()

        ensure_parent_dir(COOLDOWN_FILE)
        cooldowns = load_json(COOLDOWN_FILE, default={})

        changed = False

        for item in items:
            close_time_ms = int(to_float(item.get("updatedTime"), 0))
            close_time_sec = close_time_ms / 1000.0

            if (current_time - close_time_sec) > 600:
                continue

            symbol_raw = (item.get("symbol") or "").upper()  # es: BTCUSDT
            side = (item.get("side") or "").lower()          # buy/sell

            direction = "long" if side == "buy" else "short"
            direction_key = f"{symbol_raw}_{direction}"

            existing_time = to_float(cooldowns.get(direction_key), 0.0)
            if close_time_sec > existing_time:
                avg_entry_price = to_float(item.get("avgEntryPrice"), 0.0)
                closed_pnl = to_float(item.get("closedPnl"), 0.0)
                leverage = max(1.0, to_float(item.get("leverage"), 1.0))
                qty = to_float(item.get("qty"), 0.0)
                pnl_pct = None
                if avg_entry_price > 0 and qty > 0:
                    pnl_pct = (closed_pnl / (avg_entry_price * qty)) * leverage * 100.0

                if pnl_pct is not None and abs(pnl_pct) >= COOLDOWN_PNL_THRESHOLD_PCT:
                    cooldowns[direction_key] = close_time_sec
                    cooldowns[symbol_raw] = close_time_sec
                    changed = True
                    print(f"💾 Cooldown auto-salvato per {direction_key} (PnL {pnl_pct:.2f}%)")
                else:
                    print("ℹ️ Cooldown auto non applicato: PnL sotto soglia o non calcolabile")

                # learning record
                try:
                    entry_price = to_float(item.get("avgEntryPrice"), 0.0)
                    exit_price = to_float(item.get("avgExitPrice"), 0.0)
                    leverage = max(1.0, to_float(item.get("leverage"), 1.0))

                    created_time_ms = int(to_float(item.get("createdTime"), close_time_ms))
                    duration_minutes = int((close_time_ms - created_time_ms) / 1000 / 60)

                    record_trade_for_learning(
                        symbol=symbol_raw,
                        side_raw=direction,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        leverage=leverage,
                        duration_minutes=duration_minutes,
                        market_conditions={"closed_by": "bybit_sl_tp"},
                    )
                except Exception as e:
                    print(f"⚠️ Errore recording auto-closed trade: {e}")

        if changed:
            save_json(COOLDOWN_FILE, cooldowns)

    except Exception as e:
        print(f"⚠️ Errore check chiusure recenti: {e}")

# =========================================================
# SMART REVERSE SYSTEM
# =========================================================
def check_smart_reverse():
    if not ENABLE_AI_REVIEW or not exchange:
        return

    try:
        positions = exchange.fetch_positions(None, params={"category": "linear"})
        wallet_bal = exchange.fetch_balance(params={"type": "swap"})
        wallet_balance = to_float((wallet_bal.get("USDT", {}) or {}).get("total", 0.0), 0.0)
        if wallet_balance <= 0:
            return

        for p in positions:
            size = to_float(p.get("contracts"), 0.0)
            if size == 0:
                continue

            symbol = p.get("symbol", "")
            entry_price = to_float(p.get("entryPrice"), 0.0)
            mark_price = to_float(p.get("markPrice"), 0.0)
            side_dir = normalize_position_side(p.get("side", ""))  # long/short
            pnl_dollars = to_float(p.get("unrealizedPnl"), 0.0)

            if not symbol or entry_price <= 0 or mark_price <= 0 or not side_dir:
                continue

            leverage = max(1.0, to_float(p.get("leverage"), 1.0))

            roi_raw = (mark_price - entry_price) / entry_price if side_dir == "long" else (entry_price - mark_price) / entry_price
            roi = roi_raw * leverage  # fraction (e.g. -0.12 => -12%)

            sym_id = bybit_symbol_id(symbol)

            if roi <= HARD_STOP_THRESHOLD:
                print(f"🛑 HARD STOP: {symbol} {side_dir.upper()} ROI={roi*100:.2f}% - Chiusura immediata!")
                execute_close_position(symbol)
                continue

            if roi <= REVERSE_THRESHOLD:
                last_reverse_time = reverse_cooldown_tracker.get(sym_id, 0.0)
                now = time.time()
                if (now - last_reverse_time) < (REVERSE_COOLDOWN_MINUTES * 60):
                    minutes_left = int((REVERSE_COOLDOWN_MINUTES * 60 - (now - last_reverse_time)) / 60)
                    print(f"⏳ Reverse cooldown attivo per {symbol}: {minutes_left} minuti rimanenti")
                    continue

                print(f"⚠️ REVERSE TRIGGER: {symbol} {side_dir.upper()} ROI={roi*100:.2f}% - Chiedo conferma AI...")

                position_data = {
                    "side": side_dir,
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "roi_pct": roi,
                    "size": size,
                    "pnl_dollars": pnl_dollars,
                    "leverage": leverage,
                    "wallet_balance": wallet_balance,
                }

                analysis = request_reverse_analysis(symbol, position_data)

                if analysis:
                    action = (analysis.get("action") or "HOLD").upper()
                    rationale = analysis.get("rationale", "No rationale")
                    confidence = to_float(analysis.get("confidence"), 0.0)
                    recovery_size_pct = to_float(analysis.get("recovery_size_pct"), 0.15)

                    print(f"🤖 AI REVERSE DECISION for {symbol}: {action} (confidence: {confidence:.0f}%)")
                    print(f"   Rationale: {rationale}")

                    save_ai_decision({
                        "symbol": sym_id,
                        "action": action,
                        "rationale": rationale,
                        "analysis_summary": f"REVERSE TRIGGER | ROI: {roi*100:.2f}% | Confidence: {confidence:.0f}%",
                        "roi_pct": roi * 100,
                        "leverage": leverage,
                        "size_pct": (recovery_size_pct * 100) if action == "REVERSE" else 0,
                    })

                    action_to_execute = action
                    if action == "REVERSE":
                        market_context = get_market_risk_data(symbol)
                        trend = (market_context.get("trend") or "").upper()
                        macd_hist = to_float(market_context.get("macd_hist"), 0.0)
                        rsi_val = to_float(market_context.get("rsi"), 50.0)

                        trend_flip = (trend == "BEARISH" and side_dir == "long") or (trend == "BULLISH" and side_dir == "short")
                        macd_alignment = (macd_hist < 0 and side_dir == "long") or (macd_hist > 0 and side_dir == "short")
                        rsi_alignment = (rsi_val < 45 and side_dir == "long") or (rsi_val > 55 and side_dir == "short")
                        context_score = sum([trend_flip, macd_alignment, rsi_alignment]) / 3.0

                        if confidence < 80 or context_score < 0.75:
                            print(
                                f"✋ Reverse bloccato: conf {confidence:.0f}%, contesto {context_score*100:.0f}% | "
                                "eseguo CLOSE conservativo"
                            )
                            action_to_execute = "CLOSE"
                        else:
                            action_to_execute = "CLOSE_COOLDOWN"

                    if action_to_execute == "CLOSE_COOLDOWN":
                        print(f"🔒 Chiudo {symbol} e imposto cooldown per evitare reverse immediato")
                        if execute_close_position(symbol):
                            now_ts = time.time()
                            reverse_cooldown_tracker[sym_id] = now
                            try:
                                ensure_parent_dir(COOLDOWN_FILE)
                                cooldowns = load_json(COOLDOWN_FILE, default={})
                                cooldowns[sym_id] = now_ts
                                cooldowns[f"{sym_id}_long"] = now_ts
                                cooldowns[f"{sym_id}_short"] = now_ts
                                save_json(COOLDOWN_FILE, cooldowns)
                            except Exception:
                                pass
                    elif action_to_execute == "REVERSE":
                        print(f"🔄 Eseguo REVERSE per {symbol} con size {recovery_size_pct*100:.1f}%")
                        if execute_reverse(symbol, side_dir, recovery_size_pct):
                            reverse_cooldown_tracker[sym_id] = now
                    elif action_to_execute == "CLOSE":
                        print(f"🔒 Eseguo CLOSE per {symbol}")
                        execute_close_position(symbol)
                    else:
                        print(f"✋ HOLD - Mantengo posizione {symbol}")
                else:
                    print(f"⚠️ Analisi AI fallita per {symbol} - Mantengo posizione")

                continue

            if roi <= AI_REVIEW_THRESHOLD:
                print(f"🔍 AI REVIEW: {symbol} {side_dir.upper()} ROI={roi*100:.2f}% - Chiedo consiglio AI...")

                position_data = {
                    "side": side_dir,
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "roi_pct": roi,
                    "size": size,
                    "pnl_dollars": pnl_dollars,
                    "leverage": leverage,
                    "wallet_balance": wallet_balance,
                }

                analysis = request_reverse_analysis(symbol, position_data)
                if analysis:
                    action = (analysis.get("action") or "HOLD").upper()
                    rationale = analysis.get("rationale", "No rationale")
                    confidence = to_float(analysis.get("confidence"), 0.0)

                    print(f"📊 AI RACCOMANDA: {action}")
                    print(f"   Rationale: {rationale}")

                    save_ai_decision({
                        "symbol": sym_id,
                        "action": action,
                        "rationale": rationale,
                        "analysis_summary": f"AI REVIEW | ROI: {roi*100:.2f}% | Confidence: {confidence:.0f}%",
                        "roi_pct": roi * 100,
                        "leverage": leverage,
                        "size_pct": 0,
                    })
                else:
                    print(f"⚠️ Analisi AI fallita per {symbol}")

                continue

            if roi <= WARNING_THRESHOLD:
                print(f"⚠️ WARNING: {symbol} {side_dir.upper()} ROI={roi*100:.2f}% - Perdita moderata")

    except Exception as e:
        print(f"⚠️ Smart Reverse system error: {e}")

# =========================================================
# API ENDPOINTS
# =========================================================
@app.get("/get_wallet_balance")
def get_balance():
    if not exchange:
        return {"equity": 0, "available": 0}
    try:
        bal = exchange.fetch_balance(params={"type": "swap"})
        u = bal.get("USDT", {}) or {}
        return {"equity": to_float(u.get("total"), 0.0), "available": to_float(u.get("free"), 0.0)}
    except Exception:
        return {"equity": 0, "available": 0}

@app.get("/get_open_positions")
def get_positions():
    if not exchange:
        return {"active": [], "details": []}
    try:
        raw = exchange.fetch_positions(None, params={"category": "linear"})
        active = []
        details = []

        for p in raw:
            contracts = to_float(p.get("contracts"), 0.0)
            if contracts <= 0:
                continue

            sym_ccxt = p.get("symbol", "")
            sym_id = bybit_symbol_id(sym_ccxt)
            entry_price = to_float(p.get("entryPrice"), 0.0)
            mark_price = to_float(p.get("markPrice"), entry_price)
            leverage = max(1.0, to_float(p.get("leverage"), 1.0))
            side_dir = normalize_position_side(p.get("side", "")) or "long"

            pnl_pct = 0.0
            if entry_price > 0:
                if side_dir == "short":
                    pnl_pct = ((entry_price - mark_price) / entry_price) * leverage * 100.0
                else:
                    pnl_pct = ((mark_price - entry_price) / entry_price) * leverage * 100.0

            details.append({
                "symbol": sym_id,
                "side": side_dir,
                "size": contracts,
                "entry_price": entry_price,
                "mark_price": mark_price,
                "pnl": to_float(p.get("unrealizedPnl"), 0.0),
                "pnl_pct": round(pnl_pct, 2),
                "leverage": leverage,
                "positionIdx": get_position_idx_from_position(p),
            })
            active.append(sym_id)

        return {"active": active, "details": details}
    except Exception:
        return {"active": [], "details": []}

@app.get("/get_history")
def get_hist():
    return load_json(HISTORY_FILE, default=[])

@app.get("/get_closed_positions")
def get_closed():
    if not exchange:
        return []
    try:
        res = exchange.private_get_v5_position_closed_pnl({"category": "linear", "limit": 20})
        if res and res.get("retCode") == 0:
            items = (res.get("result", {}) or {}).get("list", []) or []
            clean = []
            for i in items:
                ts = int(to_float(i.get("updatedTime"), 0))
                clean.append({
                    "datetime": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M"),
                    "symbol": (i.get("symbol") or "").upper(),
                    "side": (i.get("side") or "").lower(),
                    "price": to_float(i.get("avgExitPrice"), 0.0),
                    "closedPnl": to_float(i.get("closedPnl"), 0.0),
                })
            return clean
        return []
    except Exception:
        return []

@app.post("/open_position")
def open_position(order: OrderRequest):
    if not exchange:
        return {"status": "error", "msg": "No Exchange"}

    try:
        # order.symbol può essere id (BTCUSDT) o symbol CCXT (BTC/USDT:USDT)
        raw_sym = str(order.symbol).strip()
        sym_id = bybit_symbol_id(raw_sym)
        sym_ccxt = ccxt_symbol_from_id(exchange, sym_id) or raw_sym

        # Decide side richiesta
        is_long_request = ("buy" in order.side.lower()) or ("long" in order.side.lower())
        requested_dir = "long" if is_long_request else "short"
        requested_side = side_to_order_side(requested_dir)  # buy/sell
        symbol_key = sym_id

        # Check existing position
        try:
            positions = exchange.fetch_positions([sym_ccxt], params={"category": "linear"})
            for p in positions:
                contracts = to_float(p.get("contracts"), 0.0)
                if contracts > 0:
                    existing_dir = normalize_position_side(p.get("side", "")) or "long"
                    if existing_dir == requested_dir:
                        print(f"⚠️ SKIP: già esiste posizione {existing_dir.upper()} su {sym_ccxt}")
                        return {
                            "status": "skipped",
                            "msg": f"Posizione {existing_dir} già aperta su {sym_ccxt}",
                            "existing_side": existing_dir,
                        }
                    else:
                        # Reverse diretto non consentito: chiudiamo e imponiamo cooldown
                        print(f"⏳ REVERSE BLOCCATO: {existing_dir} aperta, rifiuto {requested_dir} su {sym_ccxt}")
                        try:
                            ensure_parent_dir(COOLDOWN_FILE)
                            cooldowns = load_json(COOLDOWN_FILE, default={})
                            now_ts = time.time()
                            cooldowns[symbol_key] = now_ts
                            cooldowns[f"{symbol_key}_{existing_dir}"] = now_ts
                            save_json(COOLDOWN_FILE, cooldowns)
                        except Exception:
                            pass
                        return {
                            "status": "reverse_blocked",
                            "msg": f"Reverse diretto non consentito su {sym_ccxt}. Chiudi prima la posizione esistente.",
                            "existing_side": existing_dir,
                        }
        except Exception as e:
            print(f"⚠️ Errore check posizioni esistenti: {e}")

        # Cooldown check
        try:
            ensure_parent_dir(COOLDOWN_FILE)
            cooldowns = load_json(COOLDOWN_FILE, default={})
            cooldown_key = f"{symbol_key}_{requested_dir}"  # BTCUSDT_long
            last_close_time = to_float(cooldowns.get(cooldown_key), 0.0)
            elapsed = time.time() - last_close_time
            cooldown_window = max(COOLDOWN_MINUTES, REVERSE_COOLDOWN_MINUTES)

            if elapsed < (cooldown_window * 60):
                minutes_left = cooldown_window - (elapsed / 60)
                print(f"⏳ COOLDOWN: {sym_ccxt} {requested_dir} - ancora {minutes_left:.1f} minuti")
                return {
                    "status": "cooldown",
                    "msg": f"Cooldown attivo per {sym_ccxt} {requested_dir}",
                    "minutes_left": round(minutes_left, 1),
                }
        except Exception as e:
            print(f"⚠️ Errore check cooldown: {e}")

        # set leverage
        try:
            exchange.set_leverage(int(order.leverage), sym_ccxt, params={"category": "linear"})
        except Exception as e:
            print(f"⚠️ set_leverage fallito (ccxt): {e}")

        bal = exchange.fetch_balance(params={"type": "swap"})
        free_usdt = to_float((bal.get("USDT", {}) or {}).get("free", 0.0), 0.0)
        cost = max(free_usdt * float(order.size_pct), 10.0)
        price = to_float(exchange.fetch_ticker(sym_ccxt).get("last"), 0.0)
        if price <= 0:
            return {"status": "error", "msg": "Invalid price"}

        risk_data = get_market_risk_data(sym_id)
        atr_value = risk_data.get("atr")

        target_market = exchange.market(sym_ccxt)
        info = target_market.get("info", {}) or {}
        lot_filter = info.get("lotSizeFilter", {}) or {}
        qty_step = to_float(lot_filter.get("qtyStep") or (target_market.get("limits", {}).get("amount", {}) or {}).get("min"), 0.001)
        min_qty = to_float(lot_filter.get("minOrderQty") or qty_step, qty_step)

        qty_raw = (cost * float(order.leverage)) / price
        d_qty = Decimal(str(qty_raw))
        d_step = Decimal(str(qty_step))
        steps = (d_qty / d_step).to_integral_value(rounding=ROUND_DOWN)
        final_qty_d = steps * d_step
        if final_qty_d < Decimal(str(min_qty)):
            final_qty_d = Decimal(str(min_qty))
        final_qty = float("{:f}".format(final_qty_d.normalize()))

        if atr_value:
            sl_price = price - (atr_value * 1.2) if requested_dir == "long" else price + (atr_value * 1.2)
        else:
            sl_pct = float(order.sl_pct) if float(order.sl_pct) > 0 else DEFAULT_INITIAL_SL_PCT
            sl_price = price * (1 - sl_pct) if requested_dir == "long" else price * (1 + sl_pct)
        sl_str = exchange.price_to_precision(sym_ccxt, sl_price)

        pos_idx = direction_to_position_idx(requested_dir)

        log_suffix = f" idx={pos_idx}" if use_position_idx() else ""
        order_type = "limit" if ENTRY_ORDER_TYPE == "limit" else "market"
        print(f"🚀 ORDER {sym_ccxt}: type={order_type} side={requested_side} qty={final_qty} SL={sl_str}{log_suffix}")

        params = {"category": "linear", "stopLoss": sl_str}
        if use_position_idx():
            params["positionIdx"] = pos_idx
        params = strip_position_idx(params)

        try:
            params = strip_position_idx(params)
            res = exchange.create_order(sym_ccxt, order_type, requested_side, final_qty, price if order_type == "limit" else None, params)
        except Exception as e:
            err_msg = str(e)
            if use_position_idx() and "position idx not match position mode" in err_msg.lower():
                disable_position_idx("Bybit position mode mismatch")
                params.pop("positionIdx", None)
                params = strip_position_idx(params)
                res = exchange.create_order(sym_ccxt, order_type, requested_side, final_qty, price if order_type == "limit" else None, params)
            else:
                raise
        position_risk_meta[sym_id] = {
            "entry_price": price,
            "initial_sl": sl_price,
            "breakeven_reached": False,
        }
        return {"status": "executed", "id": res.get("id")}

    except Exception as e:
        print(f"❌ Order Error: {e}")
        return {"status": "error", "msg": str(e)}

@app.post("/close_position")
def close_position(req: CloseRequest):
    # se vuoi abilitarlo manualmente, puoi chiamare execute_close_position(req.symbol)
    return {"status": "manual_only"}

@app.post("/manage_active_positions")
def manage():
    check_recent_closes_and_save_cooldown()
    check_and_update_trailing_stops()
    check_smart_reverse()
    return {"status": "ok"}
