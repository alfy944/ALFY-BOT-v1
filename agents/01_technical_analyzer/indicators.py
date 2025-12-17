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

        # Multi-timeframe 1h per conferma trend
        df_1h = self.fetch_ohlcv(ticker, "1h", limit=200)
        trend_1h = None
        if not df_1h.empty and len(df_1h) >= 50:
            df_1h["ema_50"] = self.calculate_ema(df_1h["close"], 50)
            last_1h = df_1h.iloc[-1]
            trend_1h = "BULLISH" if last_1h["close"] > last_1h["ema_50"] else "BEARISH"

        df["ema_20"] = self.calculate_ema(df["close"], 20)
        df["ema_50"] = self.calculate_ema(df["close"], 50)
        df["ema_200"] = self.calculate_ema(df["close"], 200)
        macd_line, macd_sig, macd_diff = self.calculate_macd(df["close"])
        df["macd_line"] = macd_line
        df["macd_signal"] = macd_sig
        df["macd_hist"] = macd_diff
        df["macd_hist_prev"] = df["macd_hist"].shift(1)
        df["rsi_7"] = self.calculate_rsi(df["close"], 7)
        df["rsi_14"] = self.calculate_rsi(df["close"], 14)
        df["atr_14"] = self.calculate_atr(df["high"], df["low"], df["close"], 14)

        if len(df) < 3:
            return {}

        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        pp = self.calculate_pivot_points(last["high"], last["low"], last["close"])

        swing_high_raw = df["high"].iloc[-20:-1].max()
        swing_low_raw = df["low"].iloc[-20:-1].min()
        swing_high = float(swing_high_raw) if pd.notna(swing_high_raw) else None
        swing_low = float(swing_low_raw) if pd.notna(swing_low_raw) else None

        vol_window = df["volume"].rolling(window=20).mean()
        avg_volume = vol_window.iloc[-2] if len(vol_window) >= 2 else last["volume"]
        volume_ratio = (last["volume"] / avg_volume) if avg_volume else 0
        volume_spike = pd.notna(avg_volume) and last["volume"] > (avg_volume * 1.5)

        trend = "BULLISH" if last["close"] > last["ema_50"] else "BEARISH"
        macd_trend = "POSITIVE" if last["macd_line"] > last["macd_signal"] else "NEGATIVE"
        trend_15m = trend

        atr_value = last["atr_14"]
        if pd.isna(atr_value) or atr_value <= 0:
            fallback_range = (df["high"] - df["low"]).rolling(window=14).mean().iloc[-1]
            if not pd.isna(fallback_range) and fallback_range > 0:
                atr_value = fallback_range
            else:
                atr_value = abs(last["close"]) * 0.001  # piccolo epsilon per evitare 0
        distance_from_ema50 = abs(last["close"] - last["ema_50"])
        volatility_ratio = (atr_value / last["close"]) if last["close"] else 0
        volatility = "high" if volatility_ratio > 0.02 else "low" if volatility_ratio < 0.01 else "normal"

        # Regime detection rafforzato per bloccare il range intraday
        ema20 = last["ema_20"]
        ema50 = last["ema_50"]
        ema200 = last["ema_200"]
        atr_pct = (atr_value / last["close"] * 100) if last["close"] else 0
        if abs(ema20 - ema50) / last["close"] < 0.003 and atr_pct < 0.35:
            regime = "range"
        elif ema20 > ema50 > ema200:
            regime = "trend_bull"
        elif ema20 < ema50 < ema200:
            regime = "trend_bear"
        elif (trend == "BULLISH" and macd_trend == "NEGATIVE") or (trend == "BEARISH" and macd_trend == "POSITIVE"):
            regime = "transition"
        else:
            regime = "transition"

        # Momentum exit conditions (per-bar, candle close driven)
        rsi_below_50 = last["rsi_14"] < 50
        rsi_above_50 = last["rsi_14"] > 50
        macd_hist_falling = (last["macd_hist"] < prev["macd_hist"]) and (prev["macd_hist"] < prev2["macd_hist"])
        macd_hist_rising = (last["macd_hist"] > prev["macd_hist"]) and (prev["macd_hist"] > prev2["macd_hist"])
        close_below_ema20 = last["close"] < last["ema_20"]
        close_above_ema20 = last["close"] > last["ema_20"]
        high_20 = df["high"].iloc[-20:].max()
        low_20 = df["low"].iloc[-20:].min()

        long_exit_votes = sum([bool(rsi_below_50), bool(macd_hist_falling), bool(close_below_ema20)])
        short_exit_votes = sum([bool(rsi_above_50), bool(macd_hist_rising), bool(close_above_ema20)])

        breakout_long = False
        breakout_short = False
        if len(df) >= 10:
            breakout_long = last["close"] > df["high"].iloc[-10:].max()
            breakout_short = last["close"] < df["low"].iloc[-10:].min()

        return {
            "symbol": ticker,
            "price": last["close"],
            "trend": trend,
            "trend_15m": trend_15m,
            "trend_1h": trend_1h,
            "regime": regime,
            "volatility": volatility,
            "rsi": round(last["rsi_14"], 2),
            "rsi_7": round(last["rsi_7"], 2),
            "macd": macd_trend,
            "macd_hist": round(last["macd_hist"], 6),
            "macd_hist_prev": round(prev["macd_hist"], 6),
            "support": round(last["close"] - (2 * atr_value), 2),
            "resistance": round(last["close"] + (2 * atr_value), 2),
            "breakout": {
                "long": bool(breakout_long),
                "short": bool(breakout_short),
            },
            "high_20": round(high_20, 4) if pd.notna(high_20) else None,
            "low_20": round(low_20, 4) if pd.notna(low_20) else None,
            "structure_break": {
                "long": bool(swing_high and last["close"] > swing_high),
                "short": bool(swing_low and last["close"] < swing_low),
                "swing_high": round(swing_high, 4) if swing_high else None,
                "swing_low": round(swing_low, 4) if swing_low else None,
            },
            "volume_spike": bool(volume_spike),
            "momentum_exit": {
                "long": bool(long_exit_votes >= 2),
                "short": bool(short_exit_votes >= 2),
                "votes": {
                    "long": long_exit_votes,
                    "short": short_exit_votes,
                    "rsi_below_50": bool(rsi_below_50),
                    "rsi_above_50": bool(rsi_above_50),
                    "macd_hist_falling": bool(macd_hist_falling),
                    "macd_hist_rising": bool(macd_hist_rising),
                    "close_below_ema20": bool(close_below_ema20),
                    "close_above_ema20": bool(close_above_ema20),
                },
            },
            "details": {
                "ema_20": round(last["ema_20"], 2),
                "ema_50": round(last["ema_50"], 2),
                "ema_200": round(last["ema_200"], 2),
                "rsi_7": round(last["rsi_7"], 2),
                "atr": round(atr_value, 2),
                "pivot_pp": round(pp["pp"], 2),
                "volume_avg_20": round(avg_volume, 2) if pd.notna(avg_volume) else None,
                "volume_ratio": round(volume_ratio, 2) if volume_ratio else 0,
            }
        }
