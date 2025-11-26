"""Technical Analyzer Agent v2.1"""

import os
import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Any
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pybit.unified_trading import HTTP

app = FastAPI(title="Technical Analyzer Agent", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"
session = HTTP(testnet=TESTNET, api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"))

class AnalysisRequest(BaseModel):
    symbol: str
    timeframes: List[str] = ["15", "60", "240"]

class AnalysisResponse(BaseModel):
    symbol: str
    data: Dict[str, Any]
    timestamp: str

def get_kline_data(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    try:
        response = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
        if response['retCode'] == 0 and response['result']['list']:
            df = pd.DataFrame(response['result']['list'], columns=['time', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df = df.iloc[::-1].reset_index(drop=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
    except Exception as e:
        print(f"[ERROR] get_kline_data {symbol} {interval}: {e}")
    return pd.DataFrame()

def interpret_rsi(rsi_val, prev_rsi):
    if rsi_val is None or pd.isna(rsi_val):
        return {"value": None, "signal": "NO_DATA", "zone": "UNKNOWN"}
    rsi, prev = float(rsi_val), float(prev_rsi) if prev_rsi and not pd.isna(prev_rsi) else float(rsi_val)
    if rsi <= 25: zone, signal = "EXTREMELY_OVERSOLD", "STRONG_BUY"
    elif rsi <= 30: zone, signal = "OVERSOLD", "BUY"
    elif rsi >= 75: zone, signal = "EXTREMELY_OVERBOUGHT", "STRONG_SELL"
    elif rsi >= 70: zone, signal = "OVERBOUGHT", "SELL"
    else: zone, signal = "NEUTRAL", "NEUTRAL"
    return {"value": round(rsi, 2), "previous": round(prev, 2), "zone": zone, "signal": signal, "momentum": "RISING" if rsi > prev else "FALLING" if rsi < prev else "FLAT"}

def interpret_macd(line, sig, hist, prev_line, prev_sig):
    if any(pd.isna(x) for x in [line, sig, hist]):
        return {"line": None, "signal_line": None, "histogram": None, "cross": "NONE", "trend": "NEUTRAL"}
    line, sig, hist = float(line), float(sig), float(hist)
    prev_line = float(prev_line) if not pd.isna(prev_line) else line
    prev_sig = float(prev_sig) if not pd.isna(prev_sig) else sig
    cross = "BULLISH_CROSS" if prev_line <= prev_sig and line > sig else "BEARISH_CROSS" if prev_line >= prev_sig and line < sig else "NONE"
    trend = "BULLISH" if hist > 0 else "BEARISH" if hist < 0 else "NEUTRAL"
    return {"line": round(line, 6), "signal_line": round(sig, 6), "histogram": round(hist, 6), "cross": cross, "trend": trend}

def interpret_bollinger(close, upper, lower, middle):
    if any(pd.isna(x) or x is None for x in [close, upper, lower, middle]):
        return {"upper": None, "middle": None, "lower": None, "position": "MIDDLE", "signal": "NEUTRAL"}
    close, upper, lower, middle = float(close), float(upper), float(lower), float(middle)
    width_pct = ((upper - lower) / middle * 100) if middle > 0 else 0
    if close >= upper * 0.995: position, signal = "AT_UPPER", "OVERBOUGHT"
    elif close <= lower * 1.005: position, signal = "AT_LOWER", "OVERSOLD"
    elif close > middle: position, signal = "ABOVE_MIDDLE", "NEUTRAL_BULLISH"
    else: position, signal = "BELOW_MIDDLE", "NEUTRAL_BEARISH"
    return {"upper": round(upper, 2), "middle": round(middle, 2), "lower": round(lower, 2), "width_pct": round(width_pct, 2), "position": position, "signal": signal}

def determine_trend(close, sma50, sma200):
    if pd.isna(sma50) or pd.isna(sma200) or pd.isna(close):
        return {"sma_50": None, "sma_200": None, "trend": "UNKNOWN", "strength": "UNKNOWN"}
    close, sma50, sma200 = float(close), float(sma50), float(sma200)
    if close > sma200 and close > sma50:
        trend, strength = "BULLISH", "STRONG" if sma50 > sma200 else "MODERATE"
    elif close < sma200 and close < sma50:
        trend, strength = "BEARISH", "STRONG" if sma50 < sma200 else "MODERATE"
    else:
        trend, strength = "MIXED", "WEAK"
    return {"sma_50": round(sma50, 2), "sma_200": round(sma200, 2), "trend": trend, "strength": strength}

def generate_overall_signal(rsi_sig, macd_trend, bb_sig, trend):
    bull, bear = 0, 0
    if rsi_sig == "STRONG_BUY": bull += 3
    elif rsi_sig == "BUY": bull += 2
    elif rsi_sig == "STRONG_SELL": bear += 3
    elif rsi_sig == "SELL": bear += 2
    if macd_trend == "BULLISH": bull += 2
    elif macd_trend == "BEARISH": bear += 2
    if bb_sig == "OVERSOLD": bull += 1
    elif bb_sig == "OVERBOUGHT": bear += 1
    if trend == "BULLISH": bull += 1
    elif trend == "BEARISH": bear += 1
    total = bull + bear
    if total == 0: return {"bias": "NEUTRAL", "strength": 0, "signal": "HOLD", "bullish_score": 0, "bearish_score": 0}
    if bull > bear:
        return {"bias": "BULLISH", "strength": int((bull / (total + 2)) * 100), "signal": "BUY" if bull >= 4 else "LEAN_LONG", "bullish_score": bull, "bearish_score": bear}
    elif bear > bull:
        return {"bias": "BEARISH", "strength": int((bear / (total + 2)) * 100), "signal": "SELL" if bear >= 4 else "LEAN_SHORT", "bullish_score": bull, "bearish_score": bear}
    return {"bias": "NEUTRAL", "strength": 0, "signal": "HOLD", "bullish_score": bull, "bearish_score": bear}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "technical-analyzer-agent", "version": "2.1.0"}

@app.post("/analyze_multi_tf", response_model=AnalysisResponse)
def analyze_multi_tf(req: AnalysisRequest):
    results = {}
    for tf in req.timeframes:
        df = get_kline_data(req.symbol, tf)
        if df.empty or len(df) < 200:
            continue
        try:
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.sma(length=50, append=True)
            df.ta.sma(length=200, append=True)
            df.ta.atr(length=14, append=True)
            df['volume_sma'] = df['volume'].rolling(window=20).mean()
        except Exception as e:
            print(f"[ERROR] indicators {req.symbol} {tf}: {e}")
            continue
        curr, closed, prev = df.iloc[-1], df.iloc[-2], df.iloc[-3]
        current_price = float(curr['close'])
        rsi_data = interpret_rsi(closed.get('RSI_14'), prev.get('RSI_14'))
        macd_data = interpret_macd(closed.get('MACD_12_26_9'), closed.get('MACDs_12_26_9'), closed.get('MACDh_12_26_9'), prev.get('MACD_12_26_9'), prev.get('MACDs_12_26_9'))
        bb_data = interpret_bollinger(closed['close'], closed.get('BBU_20_2.0'), closed.get('BBL_20_2.0'), closed.get('BBM_20_2.0'))
        trend_data = determine_trend(closed['close'], closed.get('SMA_50'), closed.get('SMA_200'))
        atr_val = closed.get('ATRr_14')
        atr = round(float(atr_val), 4) if atr_val and not pd.isna(atr_val) else None
        vol = float(closed['volume']) if not pd.isna(closed['volume']) else 0
        vol_sma = float(closed['volume_sma']) if not pd.isna(closed.get('volume_sma')) else vol
        vol_ratio = round(vol / vol_sma, 2) if vol_sma > 0 else 1.0
        overall = generate_overall_signal(rsi_data.get("signal", "NEUTRAL"), macd_data.get("trend", "NEUTRAL"), bb_data.get("signal", "NEUTRAL"), trend_data.get("trend", "NEUTRAL"))
        results[tf] = {
            "close": current_price, "price": current_price,
            "rsi": rsi_data["value"], "RSI": rsi_data["value"], "rsi_detail": rsi_data,
            "macd": {"histogram": macd_data["histogram"], "hist": macd_data["histogram"], "line": macd_data["line"], "signal": macd_data["signal_line"], "cross": macd_data["cross"], "trend": macd_data["trend"]},
            "MACD": {"histogram": macd_data["histogram"], "hist": macd_data["histogram"], "MACD_hist": macd_data["histogram"]},
            "bollinger": bb_data, "bb": bb_data,
            "trend": trend_data["trend"], "trend_strength": trend_data["strength"], "sma_50": trend_data["sma_50"], "sma_200": trend_data["sma_200"],
            "atr": atr, "atr_14": atr,
            "volume": vol, "volume_sma": vol_sma, "volume_ratio": vol_ratio, "volume_signal": "HIGH" if vol_ratio > 1.5 else "LOW" if vol_ratio < 0.5 else "NORMAL",
            "overall": overall, "bias": overall["bias"], "signal": overall["signal"]
        }
    return AnalysisResponse(symbol=req.symbol, data=results, timestamp=datetime.now().isoformat())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
