from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
import ccxt.async_support as ccxt
import numpy as np
import logging
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FibonacciLevels(BaseModel):
    swing_low: float
    swing_high: float
    level_236: float
    level_382: float
    level_500: float
    level_618: float
    level_786: float

class AnalysisRequest(BaseModel):
    symbol: str
    interval: str

app = FastAPI(title="Fibonacci & Cyclical Agent", version="1.0.0")

def calculate_fibonacci_levels(df: pd.DataFrame) -> Optional[FibonacciLevels]:
    try:
        swing_low_price = df['low'].min()
        swing_high_price = df['high'].max()
        price_range = swing_high_price - swing_low_price
        if price_range == 0: return None
        
        levels = {
            "swing_low": swing_low_price,
            "swing_high": swing_high_price,
            "level_236": swing_high_price - price_range * 0.236,
            "level_382": swing_high_price - price_range * 0.382,
            "level_500": swing_high_price - price_range * 0.5,
            "level_618": swing_high_price - price_range * 0.618,
            "level_786": swing_high_price - price_range * 0.786,
        }
        return FibonacciLevels(**levels)
    except Exception as e:
        logger.error(f"Errore calcolo Fibonacci: {e}")
        return None

@app.get("/")
async def read_root():
    return {"status": "Fibonacci & Cyclical Agent is running"}

@app.post("/analyze_fibonacci")
async def analyze_fibonacci(request: AnalysisRequest):
    logger.info(f"Richiesta Fibonacci per {request.symbol} su {request.interval}")
    exchange = ccxt.binance()
    try:
        ohlcv = await exchange.fetch_ohlcv(request.symbol, timeframe=request.interval, limit=200)
        if len(ohlcv) < 20:
            raise HTTPException(status_code=404, detail="Dati insufficienti per l'analisi.")
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        fib_levels = calculate_fibonacci_levels(df)
        
        if not fib_levels:
            raise HTTPException(status_code=500, detail="Impossibile calcolare i livelli di Fibonacci.")

        return {"fibonacci_levels": fib_levels, "last_close": df.iloc[-1]['close']}
    finally:
        await exchange.close()
