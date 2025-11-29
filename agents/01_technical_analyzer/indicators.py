import pandas as pd
import ta
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from pybit.unified_trading import HTTP

INTERVAL_TO_BYBIT = {
    "1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"
}

class CryptoTechnicalAnalysisBybit:
    def __init__(self):
        self.session = HTTP()

    def fetch_ohlcv(self, coin: str, interval: str, limit: int = 200) -> pd.DataFrame:
        if interval not in INTERVAL_TO_BYBIT: interval = "15m"
        bybit_interval = INTERVAL_TO_BYBIT[interval]
        
        symbol = coin.replace("-", "").upper()
        if "USDT" not in symbol: symbol += "USDT"

        try:
            resp = self.session.get_kline(category="linear", symbol=symbol, interval=bybit_interval, limit=limit)
            if resp['retCode'] != 0: raise Exception(resp['retMsg'])
            
            raw_data = resp['result']['list']
            df = pd.DataFrame(raw_data, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
            
            for col in ['open', 'high', 'low', 'close', 'vol']:
                df[col] = df[col].astype(float)
            
            df['timestamp'] = pd.to_datetime(pd.to_numeric(df['ts']), unit='ms', utc=True)
            df.rename(columns={'vol': 'volume'}, inplace=True)
            df = df.iloc[::-1].reset_index(drop=True)
            return df
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            return pd.DataFrame()

    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series:
        return ta.trend.EMAIndicator(data, window=period).ema_indicator()

    def calculate_macd(self, data: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        macd = ta.trend.MACD(data)
        return macd.macd(), macd.macd_signal(), macd.macd_diff()

    def calculate_rsi(self, data: pd.Series, period: int) -> pd.Series:
        return ta.momentum.RSIIndicator(data, window=period).rsi()

    def calculate_atr(self, high, low, close, period):
        return ta.volatility.AverageTrueRange(high, low, close, window=period).average_true_range()

    def calculate_pivot_points(self, high, low, close):
        pp = (high + low + close) / 3.0
        return {
            "pp": pp, 
            "s1": (2 * pp) - high, 
            "s2": pp - (high - low), 
            "r1": (2 * pp) - low, 
            "r2": pp + (high - low)
        }

    def get_complete_analysis(self, ticker: str) -> Dict:
        df = self.fetch_ohlcv(ticker, "15m", limit=200)
        if df.empty: return {}

        df["ema_20"] = self.calculate_ema(df["close"], 20)
        df["ema_50"] = self.calculate_ema(df["close"], 50)
        macd_line, macd_sig, macd_diff = self.calculate_macd(df["close"])
        df["macd_line"] = macd_line
        df["macd_signal"] = macd_sig
        df["rsi_7"] = self.calculate_rsi(df["close"], 7)
        df["rsi_14"] = self.calculate_rsi(df["close"], 14)
        df["atr_14"] = self.calculate_atr(df["high"], df["low"], df["close"], 14)
        
        last = df.iloc[-1]
        pp = self.calculate_pivot_points(last["high"], last["low"], last["close"])

        trend = "BULLISH" if last["close"] > last["ema_50"] else "BEARISH"
        macd_trend = "POSITIVE" if last["macd_line"] > last["macd_signal"] else "NEGATIVE"

        return {
            "symbol": ticker,
            "price": last["close"],
            "trend": trend,
            "rsi": round(last["rsi_14"], 2),
            "macd": macd_trend,
            "support": round(last["close"] - (2 * last["atr_14"]), 2),
            "resistance": round(last["close"] + (2 * last["atr_14"]), 2),
            "details": {
                "ema_20": round(last["ema_20"], 2),
                "ema_50": round(last["ema_50"], 2),
                "rsi_7": round(last["rsi_7"], 2),
                "atr": round(last["atr_14"], 2),
                "pivot_pp": round(pp["pp"], 2)
            }
        }
