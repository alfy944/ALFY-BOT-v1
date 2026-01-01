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

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        cumulative_pv = (typical_price * df["volume"]).cumsum()
        cumulative_volume = df["volume"].cumsum()
        return cumulative_pv / cumulative_volume

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
        df_1m = self.fetch_ohlcv(ticker, "1m", limit=200)
        df_5m = self.fetch_ohlcv(ticker, "5m", limit=200)
        if df.empty or df_1m.empty or df_5m.empty:
            return {}

        df["ema_20"] = self.calculate_ema(df["close"], 20)
        df["ema_50"] = self.calculate_ema(df["close"], 50)
        macd_line, macd_sig, macd_diff = self.calculate_macd(df["close"])
        df["macd_line"] = macd_line
        df["macd_signal"] = macd_sig
        df["macd_hist"] = macd_diff
        df["rsi_7"] = self.calculate_rsi(df["close"], 7)
        df["rsi_14"] = self.calculate_rsi(df["close"], 14)
        df["atr_14"] = self.calculate_atr(df["high"], df["low"], df["close"], 14)

        df_1m["ema_9"] = self.calculate_ema(df_1m["close"], 9)
        df_1m["ema_21"] = self.calculate_ema(df_1m["close"], 21)
        df_1m["ema_50"] = self.calculate_ema(df_1m["close"], 50)
        df_1m["rsi_14"] = self.calculate_rsi(df_1m["close"], 14)
        df_1m["atr_14"] = self.calculate_atr(df_1m["high"], df_1m["low"], df_1m["close"], 14)
        df_1m["vwap"] = self.calculate_vwap(df_1m)

        df_5m["ema_9"] = self.calculate_ema(df_5m["close"], 9)
        df_5m["ema_21"] = self.calculate_ema(df_5m["close"], 21)

        if len(df) < 3 or len(df_1m) < 3 or len(df_5m) < 3:
            return {}

        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        last_1m = df_1m.iloc[-1]
        prev_1m = df_1m.iloc[-2]
        last_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2]

        pp = self.calculate_pivot_points(last["high"], last["low"], last["close"])

        trend = "BULLISH" if last["close"] > last["ema_50"] else "BEARISH"
        macd_trend = "POSITIVE" if last["macd_line"] > last["macd_signal"] else "NEGATIVE"

        # Momentum exit conditions (per-bar, candle close driven)
        rsi_below_50 = last["rsi_14"] < 50
        rsi_above_50 = last["rsi_14"] > 50
        macd_hist_falling = (last["macd_hist"] < prev["macd_hist"]) and (prev["macd_hist"] < prev2["macd_hist"])
        macd_hist_rising = (last["macd_hist"] > prev["macd_hist"]) and (prev["macd_hist"] > prev2["macd_hist"])
        close_below_ema20 = last["close"] < last["ema_20"]
        close_above_ema20 = last["close"] > last["ema_20"]

        long_exit_votes = int(sum([rsi_below_50, macd_hist_falling, close_below_ema20]))
        short_exit_votes = int(sum([rsi_above_50, macd_hist_rising, close_above_ema20]))

        ema_spread = (last_5m["ema_9"] - last_5m["ema_21"]) / last_5m["ema_21"]
        ema_spread_abs = abs(ema_spread)
        ema_slope_up = last_5m["ema_9"] > prev_5m["ema_9"]
        ema_slope_down = last_5m["ema_9"] < prev_5m["ema_9"]
        vwap_1m = last_1m["vwap"]
        ema50_1m = last_1m["ema_50"]
        price_above_mean = last_1m["close"] > vwap_1m
        price_below_mean = last_1m["close"] < vwap_1m
        mean_cross = (last_1m["close"] - vwap_1m) * (prev_1m["close"] - vwap_1m) <= 0

        trend_long = (last_5m["ema_9"] > last_5m["ema_21"]) and ema_slope_up and price_above_mean
        trend_short = (last_5m["ema_9"] < last_5m["ema_21"]) and ema_slope_down and price_below_mean
        range_mode = (ema_spread_abs < 0.0015) and mean_cross

        pullback_zone_long = last_1m["low"] <= min(last_1m["ema_9"], last_1m["ema_21"], vwap_1m)
        pullback_zone_short = last_1m["high"] >= max(last_1m["ema_9"], last_1m["ema_21"], vwap_1m)
        candle_reject_long = (last_1m["close"] > last_1m["open"]) and (last_1m["close"] > prev_1m["high"])
        candle_reject_short = (last_1m["close"] < last_1m["open"]) and (last_1m["close"] < prev_1m["low"])
        rsi_rising = last_1m["rsi_14"] > prev_1m["rsi_14"]
        rsi_falling = last_1m["rsi_14"] < prev_1m["rsi_14"]

        trend_scalp_long = trend_long and pullback_zone_long and candle_reject_long and (last_1m["rsi_14"] > 45) and rsi_rising
        trend_scalp_short = trend_short and pullback_zone_short and candle_reject_short and (last_1m["rsi_14"] < 55) and rsi_falling

        extended_below = last_1m["close"] < (vwap_1m - (0.5 * last_1m["atr_14"]))
        extended_above = last_1m["close"] > (vwap_1m + (0.5 * last_1m["atr_14"]))
        reclaim_vwap_long = (last_1m["close"] > vwap_1m) and (prev_1m["close"] <= vwap_1m)
        reclaim_vwap_short = (last_1m["close"] < vwap_1m) and (prev_1m["close"] >= vwap_1m)
        higher_low = last_1m["low"] > prev_1m["low"]
        lower_high = last_1m["high"] < prev_1m["high"]

        reversal_long = range_mode and extended_below and reclaim_vwap_long and higher_low and (last_1m["rsi_14"] < 35) and rsi_rising
        reversal_short = range_mode and extended_above and reclaim_vwap_short and lower_high and (last_1m["rsi_14"] > 65) and rsi_falling

        atr_1m = float(last_1m["atr_14"])
        trend_sl = atr_1m * 1.0
        trend_tp1 = atr_1m * 1.0
        trend_tp2 = atr_1m * 1.5
        reversal_sl = atr_1m * 1.4
        reversal_tp = atr_1m * 1.0

        return {
            "symbol": ticker,
            "price": float(last["close"]),
            "trend": trend,
            "rsi": float(round(last["rsi_14"], 2)),
            "rsi_7": float(round(last["rsi_7"], 2)),
            "macd": macd_trend,
            "macd_hist": float(round(last["macd_hist"], 6)),
            "support": float(round(last["close"] - (2 * last["atr_14"]), 2)),
            "resistance": float(round(last["close"] + (2 * last["atr_14"]), 2)),
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
                "ema_20": float(round(last["ema_20"], 2)),
                "ema_50": float(round(last["ema_50"], 2)),
                "rsi_7": float(round(last["rsi_7"], 2)),
                "atr": float(round(last["atr_14"], 2)),
                "pivot_pp": float(round(pp["pp"], 2))
            },
            "scalp_setup": {
                "timeframes": {
                    "1m": {
                        "ema_9": float(round(last_1m["ema_9"], 2)),
                        "ema_21": float(round(last_1m["ema_21"], 2)),
                        "ema_50": float(round(last_1m["ema_50"], 2)),
                        "vwap": float(round(vwap_1m, 2)),
                        "rsi_14": float(round(last_1m["rsi_14"], 2)),
                        "atr_14": float(round(last_1m["atr_14"], 6))
                    },
                    "5m": {
                        "ema_9": float(round(last_5m["ema_9"], 2)),
                        "ema_21": float(round(last_5m["ema_21"], 2)),
                        "ema_spread": float(round(ema_spread, 6))
                    }
                },
                "regime": {
                    "trend_long": bool(trend_long),
                    "trend_short": bool(trend_short),
                    "range": bool(range_mode)
                },
                "trend_scalp": {
                    "long": bool(trend_scalp_long),
                    "short": bool(trend_scalp_short),
                    "pullback_zone_long": bool(pullback_zone_long),
                    "pullback_zone_short": bool(pullback_zone_short),
                    "rsi_rising": bool(rsi_rising),
                    "rsi_falling": bool(rsi_falling)
                },
                "reversal_scalp": {
                    "long": bool(reversal_long),
                    "short": bool(reversal_short),
                    "extended_below": bool(extended_below),
                    "extended_above": bool(extended_above),
                    "reclaim_vwap_long": bool(reclaim_vwap_long),
                    "reclaim_vwap_short": bool(reclaim_vwap_short)
                },
                "risk_management": {
                    "trend": {
                        "sl_atr": float(round(trend_sl, 6)),
                        "tp1_atr": float(round(trend_tp1, 6)),
                        "tp2_atr": float(round(trend_tp2, 6))
                    },
                    "reversal": {
                        "sl_atr": float(round(reversal_sl, 6)),
                        "tp_atr": float(round(reversal_tp, 6))
                    },
                    "break_even_r": 0.7,
                    "time_stop_bars": 8,
                    "cooldown_after_losses": {
                        "losses": 2,
                        "cooldown_minutes": 60
                    }
                }
            }
        }
