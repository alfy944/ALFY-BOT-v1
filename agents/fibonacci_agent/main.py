"""Fibonacci Retracement Agent v2.1"""

import os
import pandas as pd
from typing import Dict, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pybit.unified_trading import HTTP

app = FastAPI(title="Fibonacci Agent", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
session = HTTP(testnet=TESTNET, api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

FIB_LEVELS = {"0.000": 0.0, "0.236": 0.236, "0.382": 0.382, "0.500": 0.5, "0.618": 0.618, "0.786": 0.786, "1.000": 1.0, "1.272": 1.272, "1.618": 1.618}

class FibonacciRequest(BaseModel):
    crypto_symbol: str
    interval: str = "D"
    lookback: int = 100

def get_bybit_data(symbol: str, interval: str = "D", limit: int = 200) -> pd.DataFrame:
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
    return {"status": "ok", "service": "fibonacci-agent", "version": "2.1.0"}

@app.post("/analyze_fibonacci")
async def analyze_fibonacci(request: FibonacciRequest):
    df = get_bybit_data(request.crypto_symbol, request.interval, request.lookback)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {request.crypto_symbol}")
    if len(df) < 20:
        raise HTTPException(status_code=400, detail=f"Insufficient data: {len(df)} candles")
    high_idx, swing_high = df['high'].idxmax(), float(df['high'].max())
    low_idx, swing_low = df['low'].idxmin(), float(df['low'].min())
    current_price = float(df['close'].iloc[-1])
    swing = swing_high - swing_low
    if swing == 0:
        return {"symbol": request.crypto_symbol, "current_price": current_price, "trend": "sideways", "levels": {}, "nearest_support": current_price, "nearest_resistance": current_price, "in_golden_pocket": False}
    trend = "UPTREND" if high_idx > low_idx else "DOWNTREND"
    levels = {}
    for name, ratio in FIB_LEVELS.items():
        if trend == "UPTREND":
            levels[f"level_{name}"] = round(swing_high - (swing * ratio), 2)
        else:
            levels[f"level_{name}"] = round(swing_low + (swing * ratio), 2)
    supports = [(n, p) for n, p in levels.items() if p < current_price]
    resistances = [(n, p) for n, p in levels.items() if p > current_price]
    supports.sort(key=lambda x: x[1], reverse=True)
    resistances.sort(key=lambda x: x[1])
    nearest_sup = supports[0] if supports else (None, swing_low)
    nearest_res = resistances[0] if resistances else (None, swing_high)
    fib_618, fib_500 = levels.get("level_0.618", 0), levels.get("level_0.500", 0)
    in_gp = (fib_618 <= current_price <= fib_500) if trend == "UPTREND" else (fib_500 <= current_price <= fib_618)
    return {
        "symbol": request.crypto_symbol, "current_price": current_price,
        "trend": trend.lower() + "_bias", "levels": levels, "fib_levels": levels,
        "nearest_support": nearest_sup[1], "nearest_resistance": nearest_res[1],
        "support_detail": {"level_name": nearest_sup[0], "price": nearest_sup[1], "distance_pct": round((current_price - nearest_sup[1]) / current_price * 100, 2)} if nearest_sup[0] else None,
        "resistance_detail": {"level_name": nearest_res[0], "price": nearest_res[1], "distance_pct": round((nearest_res[1] - current_price) / current_price * 100, 2)} if nearest_res[0] else None,
        "in_golden_pocket": bool(in_gp), "swing_high": round(swing_high, 2), "swing_low": round(swing_low, 2),
        "analyzed_at": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
