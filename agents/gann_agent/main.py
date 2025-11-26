"""Gann Fan Agent v2.1"""

import os
import pandas as pd
from typing import Dict, Any
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pybit.unified_trading import HTTP

app = FastAPI(title="Gann Agent", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
session = HTTP(testnet=TESTNET, api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

GANN_ANGLES = {"4x1": 4.0, "3x1": 3.0, "2x1": 2.0, "1x1": 1.0, "1x2": 0.5, "1x3": 0.333, "1x4": 0.25}

class GannRequest(BaseModel):
    symbol: str
    interval: str = "D"
    lookback: int = 150

def get_bybit_data(symbol: str, interval: str = "D", limit: int = 150) -> pd.DataFrame:
    try:
        response = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
        if response['retCode'] == 0 and response['result']['list']:
            df = pd.DataFrame(response['result']['list'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df.iloc[::-1].reset_index(drop=True)
    except Exception as e:
        print(f"[ERROR] get_bybit_data {symbol}: {e}")
    return pd.DataFrame()

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "gann-agent", "version": "2.1.0"}

@app.post("/analyze_gann")
def analyze_gann(request: GannRequest):
    df = get_bybit_data(request.symbol, request.interval, request.lookback)
    if df.empty or len(df) < 20:
        return {"symbol": request.symbol, "error": "Insufficient data", "angles": {}}
    idx_max, high_val = df['high'].idxmax(), float(df['high'].max())
    idx_min, low_val = df['low'].idxmin(), float(df['low'].min())
    current_price = float(df['close'].iloc[-1])
    current_idx = len(df) - 1
    if idx_min < idx_max:
        anchor_price, anchor_idx, target_price, mode = low_val, idx_min, high_val, "FAN_UP"
    else:
        anchor_price, anchor_idx, target_price, mode = high_val, idx_max, low_val, "FAN_DOWN"
    bars_between = max(1, abs(idx_max - idx_min))
    unit = abs(target_price - anchor_price) / bars_between
    elapsed = current_idx - anchor_idx
    angles = {}
    for name, ratio in GANN_ANGLES.items():
        if mode == "FAN_UP":
            angles[name] = round(anchor_price + (unit * ratio * elapsed), 2)
        else:
            angles[name] = round(anchor_price - (unit * ratio * elapsed), 2)
    sorted_lvls = sorted(angles.items(), key=lambda x: x[1])
    support, resistance = ("Floor", 0.0), ("Ceiling", float('inf'))
    for i in range(len(sorted_lvls) - 1):
        if sorted_lvls[i][1] <= current_price <= sorted_lvls[i+1][1]:
            support, resistance = sorted_lvls[i], sorted_lvls[i+1]
            break
    if current_price > sorted_lvls[-1][1]:
        support = sorted_lvls[-1]
    if current_price < sorted_lvls[0][1]:
        resistance = sorted_lvls[0]
    lvl_1x1 = angles.get("1x1", current_price)
    if mode == "FAN_UP":
        trend_status = "STRONG_UPTREND" if current_price > lvl_1x1 * 1.02 else "WEAK_CORRECTION"
    else:
        trend_status = "STRONG_DOWNTREND" if current_price < lvl_1x1 * 0.98 else "WEAK_REVERSAL"
    return {
        "symbol": request.symbol, "current_price": current_price, "anchor_mode": mode, "trend_status": trend_status,
        "angles": angles, "level_1x1": round(lvl_1x1, 2),
        "support_level": round(support[1], 2), "support_angle": support[0],
        "resistance_level": round(resistance[1], 2) if resistance[1] != float('inf') else None, "resistance_angle": resistance[0],
        "swing_high": round(high_val, 2), "swing_low": round(low_val, 2),
        "analyzed_at": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
