from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
import pandas_ta as ta
import ccxt.async_support as ccxt
import logging
from typing import Dict, List, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AnalysisRequest(BaseModel):
    symbol: str
    intervals: List[str]

app = FastAPI(title="Technical Analyzer Agent", version="1.0.0")

async def get_technical_analysis(symbol: str, intervals: List[str]) -> Dict:
    exchange = ccxt.binance()
    limit = 200
    analysis_results = {}

    try:
        for interval in intervals:
            logger.info(f"Recupero dati per {symbol} con intervallo {interval}...")
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
            if not ohlcv:
                logger.warning(f"Nessun dato ohlcv per {symbol} con intervallo {interval}")
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            
            last_row = df.iloc[-1]
            analysis_results[interval] = {
                'rsi': last_row.get('RSI_14'),
                'macd': last_row.get('MACD_12_26_9'),
                'last_close': last_row.get('close')
            }
        return analysis_results
    finally:
        await exchange.close()

@app.get("/")
async def read_root():
    return {"status": "Technical Analyzer Agent is running"}

@app.post("/analyze")
async def analyze_symbol(request: AnalysisRequest):
    logger.info(f"Ricevuta richiesta di analisi per {request.symbol}")
    analysis = await get_technical_analysis(request.symbol, request.intervals)
    return {"symbol": request.symbol, "analysis": analysis}
