import pandas as pd
import ta
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from pybit.unified_trading import HTTP

INTERVAL_TO_BYBIT = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"
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
        df_3m = self.fetch_ohlcv(ticker, "3m", limit=200)
        df_5m = self.fetch_ohlcv(ticker, "5m", limit=200)
        if df.empty or df_1m.empty or df_3m.empty or df_5m.empty:
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
        df_1m["atr_14"] = self.calculate_atr(df_1m["high"], df_1m["low"], df_1m["close"], 14)
        df_1m["vwap"] = self.calculate_vwap(df_1m)
        macd_1m, macd_1m_sig, macd_1m_diff = self.calculate_macd(df_1m["close"])
        df_1m["macd_line"] = macd_1m
        df_1m["macd_signal"] = macd_1m_sig
        df_1m["macd_hist"] = macd_1m_diff

        macd_3m, macd_3m_sig, macd_3m_diff = self.calculate_macd(df_3m["close"])
        df_3m["macd_line"] = macd_3m
        df_3m["macd_signal"] = macd_3m_sig
        df_3m["macd_hist"] = macd_3m_diff

        df_5m["ema_9"] = self.calculate_ema(df_5m["close"], 9)
        df_5m["ema_21"] = self.calculate_ema(df_5m["close"], 21)

        if len(df) < 3 or len(df_1m) < 3 or len(df_3m) < 3 or len(df_5m) < 3:
            return {}

        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        last_1m = df_1m.iloc[-1]
        prev_1m = df_1m.iloc[-2]
        last_3m = df_3m.iloc[-1]
        prev_3m = df_3m.iloc[-2]
        last_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2]

        pp = self.calculate_pivot_points(last["high"], last["low"], last["close"])

        trend = "BULLISH" if last["close"] > last["ema_50"] else "BEARISH"
        macd_trend = "POSITIVE" if last["macd_line"] > last["macd_signal"] else "NEGATIVE"

        # Momentum exit conditions (per-bar, candle close driven)
        macd_hist_falling = (last["macd_hist"] < prev["macd_hist"]) and (prev["macd_hist"] < prev2["macd_hist"])
        macd_hist_rising = (last["macd_hist"] > prev["macd_hist"]) and (prev["macd_hist"] > prev2["macd_hist"])
        close_below_ema20 = last["close"] < last["ema_20"]
        close_above_ema20 = last["close"] > last["ema_20"]

        long_exit_votes = int(sum([macd_hist_falling, close_below_ema20]))
        short_exit_votes = int(sum([macd_hist_rising, close_above_ema20]))

        ema_spread = (last_5m["ema_9"] - last_5m["ema_21"]) / last_5m["ema_21"]
        ema_dist_1m = (last_1m["ema_9"] - last_1m["ema_21"]) / last_1m["ema_21"]
        ema_dist_5m = ema_spread
        atr_pct_1m = last_1m["atr_14"] / last_1m["close"]
        trend_5m = "BULLISH" if last_5m["ema_9"] > last_5m["ema_21"] else "BEARISH"
        vwap_1m = last_1m["vwap"]
        ema50_1m = last_1m["ema_50"]
        macd_hist_1m = last_1m["macd_hist"]
        macd_hist_3m = last_3m["macd_hist"]
        macd_hist_1m_prev = prev_1m["macd_hist"]
        candle_long_ok = last_1m["close"] > last_1m["open"]
        candle_short_ok = last_1m["close"] < last_1m["open"]
        macd_hist_improving_long = macd_hist_1m > macd_hist_1m_prev
        macd_hist_improving_short = macd_hist_1m < macd_hist_1m_prev

        trend_long = trend_5m == "BULLISH" and ema_dist_5m >= 0.0008
        trend_short = trend_5m == "BEARISH" and ema_dist_5m <= -0.0008

        if abs(ema_dist_1m) >= 0.0020:
            mode = "EXTREME"
        elif trend_long:
            mode = "TREND_LONG"
        elif trend_short:
            mode = "TREND_SHORT"
        else:
            mode = "REVERSAL"

        trend_scalp_long = (
            mode == "TREND_LONG"
            and ema_dist_1m > 0
            and atr_pct_1m >= 0.0009
            and macd_hist_1m > 0
            and macd_hist_improving_long
            and candle_long_ok
        )
        trend_scalp_short = (
            mode == "TREND_SHORT"
            and ema_dist_1m < 0
            and atr_pct_1m >= 0.0009
            and macd_hist_1m < 0
            and macd_hist_improving_short
            and candle_short_ok
        )

        reversal_long = (
            mode == "REVERSAL"
            and ema_dist_1m < -0.0012
            and atr_pct_1m >= 0.0011
            and macd_hist_1m > 0
            and macd_hist_improving_long
            and candle_long_ok
        )
        reversal_short = (
            mode == "REVERSAL"
            and ema_dist_1m > 0.0012
            and atr_pct_1m >= 0.0011
            and macd_hist_1m < 0
            and macd_hist_improving_short
            and candle_short_ok
        )
        extreme_reversal_long = (
            mode == "EXTREME"
            and ema_dist_1m < -0.0020
            and atr_pct_1m >= 0.0012
            and macd_hist_1m > 0
            and macd_hist_improving_long
            and candle_long_ok
        )
        extreme_reversal_short = (
            mode == "EXTREME"
            and ema_dist_1m > 0.0020
            and atr_pct_1m >= 0.0012
            and macd_hist_1m < 0
            and macd_hist_improving_short
            and candle_short_ok
        )

        atr_1m = float(last_1m["atr_14"])
        trend_sl = atr_1m * 1.0
        trend_tp1 = atr_1m * 1.0
        trend_tp2 = atr_1m * 1.8
        reversal_sl = atr_1m * 1.4
        reversal_tp = atr_1m * 1.0
        extreme_reversal_sl = atr_1m * 1.4
        extreme_reversal_tp = atr_1m * 0.8

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
                "decision_timeframe": "1m",
                "timeframes": {
                    "1m": {
                        "trend": "BULLISH" if last_1m["ema_9"] > last_1m["ema_21"] else "BEARISH",
                        "ema_9": float(round(last_1m["ema_9"], 2)),
                        "ema_21": float(round(last_1m["ema_21"], 2)),
                        "ema_50": float(round(last_1m["ema_50"], 2)),
                        "ema_dist": float(round(ema_dist_1m, 6)),
                        "vwap": float(round(vwap_1m, 2)),
                        "atr_14": float(round(last_1m["atr_14"], 6)),
                        "atr_pct": float(round(atr_pct_1m, 4)),
                        "macd_hist": float(round(last_1m["macd_hist"], 6)),
                        "volume": float(round(last_1m["volume"], 6))
                    },
                    "3m": {
                        "macd_hist": float(round(last_3m["macd_hist"], 6)),
                        "volume": float(round(last_3m["volume"], 6))
                    },
                    "5m": {
                        "trend": trend_5m,
                        "ema_9": float(round(last_5m["ema_9"], 2)),
                        "ema_21": float(round(last_5m["ema_21"], 2)),
                        "ema_spread": float(round(ema_spread, 6)),
                        "ema_dist": float(round(ema_dist_5m, 6))
                    }
                },
                "regime": {
                    "mode": mode,
                    "trend_long": bool(mode == "TREND_LONG"),
                    "trend_short": bool(mode == "TREND_SHORT"),
                    "reversal": bool(mode == "REVERSAL"),
                    "extreme": bool(mode == "EXTREME")
                },
                "trend_scalp": {
                    "long": bool(trend_scalp_long),
                    "short": bool(trend_scalp_short),
                    "ema_dist_1m": float(round(ema_dist_1m, 6)),
                    "atr_pct_1m": float(round(atr_pct_1m, 6)),
                    "macd_hist_1m": float(round(macd_hist_1m, 6))
                },
                "reversal_scalp": {
                    "long": bool(reversal_long),
                    "short": bool(reversal_short),
                    "ema_dist_1m": float(round(ema_dist_1m, 6)),
                    "atr_pct_1m": float(round(atr_pct_1m, 6)),
                    "macd_hist_1m": float(round(macd_hist_1m, 6)),
                    "macd_hist_3m": float(round(macd_hist_3m, 6))
                },
                "extreme_reversal_scalp": {
                    "long": bool(extreme_reversal_long),
                    "short": bool(extreme_reversal_short),
                    "ema_dist_1m": float(round(ema_dist_1m, 6)),
                    "atr_pct_1m": float(round(atr_pct_1m, 6)),
                    "macd_hist_1m": float(round(macd_hist_1m, 6)),
                    "macd_hist_3m": float(round(macd_hist_3m, 6))
                },
                "risk_management": {
                    "trend": {
                        "sl_atr": float(round(trend_sl, 6)),
                        "tp1_atr": float(round(trend_tp1, 6)),
                        "tp2_atr": float(round(trend_tp2, 6)),
                        "tp1_partial_pct": 0.6
                    },
                    "reversal": {
                        "sl_atr": float(round(reversal_sl, 6)),
                        "tp_atr": float(round(reversal_tp, 6)),
                        "tp_target": "0.8r_to_1.0r"
                    },
                    "extreme_reversal": {
                        "sl_atr": float(round(extreme_reversal_sl, 6)),
                        "tp_atr": float(round(extreme_reversal_tp, 6)),
                        "tp_target": "0.8r_to_1.0r"
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
