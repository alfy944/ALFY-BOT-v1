import pandas as pd
import ta
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from pybit.unified_trading import HTTP

INTERVAL_TO_BYBIT = {
    "1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"
}

DEFAULT_RANGE_CONFIG = {
    "adx_soft_threshold": 20,
}

class CryptoTechnicalAnalysisBybit:
    def __init__(self):
        self.session = HTTP()
        self.mean_reversion_state: Dict[str, Dict[str, Any]] = {}

    def _interval_seconds(self, interval: str) -> int:
        if interval not in INTERVAL_TO_BYBIT:
            return 0
        bybit_val = INTERVAL_TO_BYBIT[interval]
        if bybit_val == "D":
            return 86400
        try:
            return int(bybit_val) * 60
        except Exception:
            return 0

    def _drop_incomplete_candle(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        if df.empty:
            return df
        interval_seconds = self._interval_seconds(interval)
        if interval_seconds <= 0:
            return df
        last_ts = df.iloc[-1]["timestamp"]
        if pd.isna(last_ts):
            return df
        now = datetime.now(timezone.utc)
        close_time = last_ts + pd.Timedelta(seconds=interval_seconds)
        if now < close_time:
            return df.iloc[:-1].reset_index(drop=True)
        return df

    def _sanitize_for_json(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_for_json(v) for v in obj]
        if isinstance(obj, tuple):
            return [self._sanitize_for_json(v) for v in obj]
        if isinstance(obj, float):
            if pd.isna(obj) or obj == float("inf") or obj == float("-inf"):
                return None
            return obj
        return obj

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

    def fetch_ticker(self, coin: str) -> Dict:
        symbol = coin.replace("-", "").upper()
        if "USDT" not in symbol:
            symbol += "USDT"
        try:
            resp = self.session.get_tickers(category="linear", symbol=symbol)
            if resp["retCode"] != 0:
                raise Exception(resp["retMsg"])
            items = resp.get("result", {}).get("list", []) or []
            return items[0] if items else {}
        except Exception as e:
            print(f"Error fetching ticker {symbol}: {e}")
            return {}

    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series:
        return ta.trend.EMAIndicator(data, window=period).ema_indicator()

    def calculate_macd(self, data: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        macd = ta.trend.MACD(data)
        return macd.macd(), macd.macd_signal(), macd.macd_diff()

    def calculate_rsi(self, data: pd.Series, period: int) -> pd.Series:
        return ta.momentum.RSIIndicator(data, window=period).rsi()

    def calculate_bollinger(self, data: pd.Series, window: int = 20, dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        bb = ta.volatility.BollingerBands(data, window=window, window_dev=dev)
        return bb.bollinger_mavg(), bb.bollinger_hband(), bb.bollinger_lband()

    def calculate_atr(self, high, low, close, period):
        return ta.volatility.AverageTrueRange(high, low, close, window=period).average_true_range()

    def calculate_adx(self, high, low, close, period):
        return ta.trend.ADXIndicator(high, low, close, window=period).adx()

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
        adx_1h = None
        df = self.fetch_ohlcv(ticker, "5m", limit=200)
        if df.empty: return {}

        # Multi-timeframe for scalping (1m -> 5m -> 15m)
        df_1m = self.fetch_ohlcv(ticker, "1m", limit=200)
        trend_1m = None
        last_high_1m = None
        last_low_1m = None
        if not df_1m.empty and len(df_1m) >= 50:
            df_1m["ema_50"] = self.calculate_ema(df_1m["close"], 50)
            last_1m = df_1m.iloc[-1]
            trend_1m = "BULLISH" if last_1m["close"] > last_1m["ema_50"] else "BEARISH"
            last_high_1m = float(last_1m["high"])
            last_low_1m = float(last_1m["low"])

        df_15m = self.fetch_ohlcv(ticker, "15m", limit=200)
        trend_15m = None
        if not df_15m.empty and len(df_15m) >= 50:
            df_15m["ema_50"] = self.calculate_ema(df_15m["close"], 50)
            last_15m = df_15m.iloc[-1]
            trend_15m = "BULLISH" if last_15m["close"] > last_15m["ema_50"] else "BEARISH"

        try:
            df_1h = self.fetch_ohlcv(ticker, "1h", limit=200)
            if not df_1h.empty and len(df_1h) >= 20:
                df_1h["adx_14"] = self.calculate_adx(df_1h["high"], df_1h["low"], df_1h["close"], 14)
                adx_1h_val = df_1h["adx_14"].iloc[-1]
                if pd.notna(adx_1h_val):
                    adx_1h = float(adx_1h_val)
        except Exception:
            adx_1h = None

        df["ema_20"] = self.calculate_ema(df["close"], 20)
        df["ema_50"] = self.calculate_ema(df["close"], 50)
        df["ema_200"] = self.calculate_ema(df["close"], 200)
        macd_line, macd_sig, macd_diff = self.calculate_macd(df["close"])
        df["macd_line"] = macd_line
        df["macd_signal"] = macd_sig
        df["macd_hist"] = macd_diff
        df["macd_hist_prev"] = df["macd_hist"].shift(1)
        df["macd_hist_prev2"] = df["macd_hist"].shift(2)
        df["rsi_7"] = self.calculate_rsi(df["close"], 7)
        df["rsi_14"] = self.calculate_rsi(df["close"], 14)
        df["atr_14"] = self.calculate_atr(df["high"], df["low"], df["close"], 14)
        bb_mid, bb_upper, bb_lower = self.calculate_bollinger(df["close"], 20, 2.0)
        df["bb_mid"] = bb_mid
        df["bb_upper"] = bb_upper
        df["bb_lower"] = bb_lower

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

        vol_window = df["volume"].rolling(window=20, min_periods=5).mean()
        avg_volume = vol_window.iloc[-2] if len(vol_window) >= 2 else last["volume"]
        if avg_volume is not None and avg_volume > 0:
            volume_ratio = last["volume"] / avg_volume
        else:
            volume_ratio = None
        volume_spike = pd.notna(avg_volume) and avg_volume > 0 and last["volume"] > (avg_volume * 1.5)

        trend_5m = "BULLISH" if last["close"] > last["ema_50"] else "BEARISH"
        macd_trend = "POSITIVE" if last["macd_line"] > last["macd_signal"] else "NEGATIVE"

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

        atr_pct = volatility_ratio
        bb_mid_val = float(last["bb_mid"]) if pd.notna(last["bb_mid"]) else None
        bb_upper_val = float(last["bb_upper"]) if pd.notna(last["bb_upper"]) else None
        bb_lower_val = float(last["bb_lower"]) if pd.notna(last["bb_lower"]) else None
        rsi_14_val = float(last["rsi_14"]) if pd.notna(last["rsi_14"]) else None

        adx_soft_ok = adx_1h is not None and adx_1h < DEFAULT_RANGE_CONFIG["adx_soft_threshold"]
        range_checks = {
            "adx_ok": adx_1h is not None and adx_1h < DEFAULT_RANGE_CONFIG["adx_hard_threshold"],
            "ema_slope_ok": ema50_1h_slope is not None and abs(ema50_1h_slope) < DEFAULT_RANGE_CONFIG["ema_slope_threshold"],
            "ema_dist_ok": ema50_1h_dist is not None and ema50_1h_dist < DEFAULT_RANGE_CONFIG["ema_dist_threshold"],
            "atr_pct_ok": atr_pct is not None and atr_pct < DEFAULT_RANGE_CONFIG["atr_pct_threshold"],
        }
        range_checks = {k: bool(v) for k, v in range_checks.items()}
        range_score = sum(1 for v in range_checks.values() if v)
        range_active = bool(range_checks["adx_ok"]) and range_score >= DEFAULT_RANGE_CONFIG["min_checks"]
        range_block_reason = [k for k, v in range_checks.items() if not v]
        range_block_reason_labels = []
        for reason in range_block_reason:
            if reason == "adx_ok":
                range_block_reason_labels.append("adx_high")
            elif reason == "ema_slope_ok":
                range_block_reason_labels.append("ema_slope_high")
            elif reason == "ema_dist_ok":
                range_block_reason_labels.append("ema_dist_high")
            elif reason == "atr_pct_ok":
                range_block_reason_labels.append("atr_pct_high")
            else:
                range_block_reason_labels.append(reason)

        long_rejection = False
        short_rejection = False
        long_reentry = False
        short_reentry = False
        if len(df) >= 2 and bb_lower_val is not None and bb_upper_val is not None:
            prev = df.iloc[-2]
            long_reentry = prev["close"] <= prev["bb_lower"] and last["close"] >= bb_lower_val
            short_reentry = prev["close"] >= prev["bb_upper"] and last["close"] <= bb_upper_val
            long_rejection = last["low"] <= bb_lower_val and last["close"] >= bb_lower_val
            short_rejection = last["high"] >= bb_upper_val and last["close"] <= bb_upper_val

        # Regime detection rafforzato per bloccare il range intraday
        ema20 = last["ema_20"]
        ema50 = last["ema_50"]
        ema200 = last["ema_200"]
        atr_pct = (atr_value / last["close"] * 100) if last["close"] else 0
        adx_soft_ok = adx_1h is not None and adx_1h < DEFAULT_RANGE_CONFIG["adx_soft_threshold"]
        if abs(ema20 - ema50) / last["close"] < 0.003 and atr_pct < 0.35 and (adx_soft_ok or adx_1h is None):
            regime = "range"
        elif ema20 > ema50 > ema200:
            regime = "trend_bull"
        elif ema20 < ema50 < ema200:
            regime = "trend_bear"
        elif (trend_5m == "BULLISH" and macd_trend == "NEGATIVE") or (trend_5m == "BEARISH" and macd_trend == "POSITIVE"):
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

        last_high_5m = float(last["high"])
        last_low_5m = float(last["low"])

        ticker_data = self.fetch_ticker(ticker)
        bid = float(ticker_data.get("bid1Price") or 0)
        ask = float(ticker_data.get("ask1Price") or 0)
        mid = (bid + ask) / 2 if bid and ask else last["close"]
        spread_pct = ((ask - bid) / mid) if bid and ask and mid else 0

        breakout_long = False
        breakout_short = False
        if len(df) >= 10:
            breakout_long = last["close"] > df["high"].iloc[-10:].max()
            breakout_short = last["close"] < df["low"].iloc[-10:].min()

        breakout_event = pd.Series([False] * len(df))
        if bb_upper is not None and bb_lower is not None:
            atr_pct_series = df["atr_14"] / df["close"]
            breakout_band = (df["close"] > bb_upper) | (df["close"] < bb_lower)
            breakout_vol = atr_pct_series > DEFAULT_RANGE_CONFIG["breakout_atr_pct_threshold"]
            rolling_high = df["high"].rolling(window=20).max()
            rolling_low = df["low"].rolling(window=20).min()
            breakout_donchian = (df["close"] > rolling_high) | (df["close"] < rolling_low)
            breakout_event = breakout_band & breakout_vol & breakout_donchian

        breakout_guard_recent = False
        guard_lookback = DEFAULT_RANGE_CONFIG["breakout_guard_lookback"]
        if len(df) >= 1:
            breakout_guard_recent = bool(breakout_event.rolling(window=guard_lookback, min_periods=1).max().iloc[-1])

        setup_long = bool(
            bb_lower_val is not None
            and rsi_14_val is not None
            and last["low"] <= bb_lower_val
            and rsi_14_val <= DEFAULT_RANGE_CONFIG["rsi_setup_long"]
        )
        setup_short = bool(
            bb_upper_val is not None
            and rsi_14_val is not None
            and last["high"] >= bb_upper_val
            and rsi_14_val >= DEFAULT_RANGE_CONFIG["rsi_setup_short"]
        )

        symbol_key = ticker.replace("-", "").upper()
        state = self.mean_reversion_state.get(symbol_key, {})
        setup_side = state.get("setup_side")
        setup_ts = state.get("setup_ts")
        setup_ttl = DEFAULT_RANGE_CONFIG["setup_ttl_bars"]
        entry_interval_sec = self._interval_seconds("5m")

        setup_age_bars = 0
        if setup_ts and entry_interval_sec > 0:
            setup_age_bars = int((last["timestamp"] - setup_ts).total_seconds() / entry_interval_sec)
            if setup_age_bars >= setup_ttl:
                setup_side = None
                setup_ts = None
                setup_age_bars = 0

        if breakout_guard_recent or not range_active:
            setup_side = None
            setup_ts = None

        if setup_long:
            setup_side = "long"
            setup_ts = last["timestamp"]
        elif setup_short:
            setup_side = "short"
            setup_ts = last["timestamp"]

        trigger_long = bool(
            setup_side == "long"
            and (long_reentry or long_rejection)
            and rsi_14_val is not None
            and rsi_14_val >= DEFAULT_RANGE_CONFIG["rsi_trigger_long"]
        )
        trigger_short = bool(
            setup_side == "short"
            and (short_reentry or short_rejection)
            and rsi_14_val is not None
            and rsi_14_val <= DEFAULT_RANGE_CONFIG["rsi_trigger_short"]
        )

        if trigger_long or trigger_short:
            setup_side = None
            setup_ts = None

        self.mean_reversion_state[symbol_key] = {
            "setup_side": setup_side,
            "setup_ts": setup_ts,
        }

        mean_reversion_signals = {
            "range_active": range_active,
            "setup_long": setup_long,
            "setup_short": setup_short,
            "long_signal": bool(range_active and trigger_long),
            "short_signal": bool(range_active and trigger_short),
            "long_rejection": bool(long_rejection),
            "short_rejection": bool(short_rejection),
            "long_reentry": bool(long_reentry),
            "short_reentry": bool(short_reentry),
            "breakout_guard": bool(breakout_guard_recent),
            "breakout_guard_lookback": guard_lookback,
            "setup_pending": setup_side is not None,
            "setup_side": setup_side,
            "setup_ttl_bars": setup_ttl,
            "setup_age_bars": setup_age_bars,
            "mr_candidate_long": bool(range_active and not breakout_guard_recent and trigger_long),
            "mr_candidate_short": bool(range_active and not breakout_guard_recent and trigger_short),
            "candle_close_ts": int(last["timestamp"].timestamp() * 1000),
            "range_checks": range_checks,
            "range_block_reason": range_block_reason_labels,
            "adx_soft_ok": bool(adx_soft_ok),
            "volume_curr": round(float(last["volume"]), 6) if pd.notna(last["volume"]) else None,
            "volume_avg": round(float(avg_volume), 6) if pd.notna(avg_volume) else None,
        }

        payload = {
            "symbol": ticker,
            "price": last["close"],
            "trend": trend_5m,
            "trend_1m": trend_1m,
            "trend_5m": trend_5m,
            "trend_15m": trend_15m,
            "regime": regime,
            "volatility": volatility,
            "rsi": round(last["rsi_14"], 2),
            "rsi_7": round(last["rsi_7"], 2),
            "macd": macd_trend,
            "macd_hist": round(last["macd_hist"], 6),
            "macd_hist_prev": round(prev["macd_hist"], 6),
            "macd_hist_prev2": round(prev2["macd_hist"], 6),
            "support": round(last["close"] - (2 * atr_value), 2),
            "resistance": round(last["close"] + (2 * atr_value), 2),
            "breakout": {
                "long": bool(breakout_long),
                "short": bool(breakout_short),
            },
            "last_high_1m": last_high_1m,
            "last_low_1m": last_low_1m,
            "last_high_5m": last_high_5m,
            "last_low_5m": last_low_5m,
            "high_20": round(high_20, 4) if pd.notna(high_20) else None,
            "low_20": round(low_20, 4) if pd.notna(low_20) else None,
            "spread_pct": round(spread_pct, 6),
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
                "adx_1h": round(adx_1h, 2) if adx_1h is not None else None,
                "pivot_pp": round(pp["pp"], 2),
                "volume_avg_20": round(avg_volume, 2) if pd.notna(avg_volume) else None,
                "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
                "bb_mid": round(bb_mid_val, 6) if bb_mid_val is not None else None,
                "bb_upper": round(bb_upper_val, 6) if bb_upper_val is not None else None,
                "bb_lower": round(bb_lower_val, 6) if bb_lower_val is not None else None,
                "rsi_14": round(rsi_14_val, 2) if rsi_14_val is not None else None,
                "adx_1h": round(adx_1h, 2) if adx_1h is not None else None,
                "ema50_1h": round(ema50_1h, 6) if ema50_1h is not None else None,
                "ema50_1h_slope": round(ema50_1h_slope, 6) if ema50_1h_slope is not None else None,
                "price_to_ema50_1h_pct": round(ema50_1h_dist, 6) if ema50_1h_dist is not None else None,
                "atr_pct": round(atr_pct, 6) if atr_pct is not None else None,
                "volume_curr": round(float(last["volume"]), 6) if pd.notna(last["volume"]) else None,
            }
        }
        return self._sanitize_for_json(payload)

    def backtest_mean_reversion(
        self,
        symbol: str,
        limit: int = 2000,
        entry_interval: str = "5m",
        regime_interval: str = "1h",
        sl_atr_mult: float = 1.0,
        max_bars: int = 10,
        fee_pct: float = 0.0006,
        slippage_pct: float = 0.0002,
        train_split: float = 0.7,
        hard_stop_pct: float = 0.03,
    ) -> Dict:
        df_entry = self.fetch_ohlcv(symbol, entry_interval, limit=limit)
        df_regime = self.fetch_ohlcv(symbol, regime_interval, limit=max(200, int(limit / 12)))
        if df_entry.empty or df_regime.empty:
            return {"error": "Insufficient data"}

        df_entry["rsi_14"] = self.calculate_rsi(df_entry["close"], 14)
        df_entry["atr_14"] = self.calculate_atr(df_entry["high"], df_entry["low"], df_entry["close"], 14)
        bb_mid, bb_upper, bb_lower = self.calculate_bollinger(df_entry["close"], 20, 2.0)
        df_entry["bb_mid"] = bb_mid
        df_entry["bb_upper"] = bb_upper
        df_entry["bb_lower"] = bb_lower
        df_entry["atr_pct"] = df_entry["atr_14"] / df_entry["close"]

        df_regime["ema_50"] = self.calculate_ema(df_regime["close"], 50)
        df_regime["adx_14"] = self.calculate_adx(df_regime["high"], df_regime["low"], df_regime["close"], 14)
        df_regime["ema_50_slope"] = df_regime["ema_50"].pct_change()
        df_regime["ema_50_dist"] = (df_regime["close"] - df_regime["ema_50"]).abs() / df_regime["close"]

        df = pd.merge_asof(
            df_entry.sort_values("timestamp"),
            df_regime[["timestamp", "ema_50", "adx_14", "ema_50_slope", "ema_50_dist"]].sort_values("timestamp"),
            on="timestamp",
            direction="backward",
        )

        trades = []
        in_trade = None
        equity = 1.0
        equity_curve = [equity]
        setup_side = None
        setup_index = None

        total_fee_pct = fee_pct * 2
        for i in range(1, len(df)):
            row = df.iloc[i]
            if pd.isna(row["atr_14"]) or pd.isna(row["bb_mid"]) or pd.isna(row["rsi_14"]):
                continue

            range_checks = {
                "adx_ok": pd.notna(row["adx_14"]) and row["adx_14"] < DEFAULT_RANGE_CONFIG["adx_threshold"],
                "ema_slope_ok": pd.notna(row["ema_50_slope"]) and abs(row["ema_50_slope"]) < DEFAULT_RANGE_CONFIG["ema_slope_threshold"],
                "ema_dist_ok": pd.notna(row["ema_50_dist"]) and row["ema_50_dist"] < DEFAULT_RANGE_CONFIG["ema_dist_threshold"],
                "atr_pct_ok": row["atr_14"] / row["close"] < DEFAULT_RANGE_CONFIG["atr_pct_threshold"],
            }
            range_score = sum(1 for v in range_checks.values() if v)
            range_active = bool(range_checks["adx_ok"]) and range_score >= DEFAULT_RANGE_CONFIG["min_checks"]

            if in_trade:
                side = in_trade["side"]
                entry_price = in_trade["entry_price"]
                stop = in_trade["stop"]
                tp = in_trade["tp"]
                entry_idx = in_trade["entry_idx"]
                exit_reason = None
                exit_price = None

                if not range_active:
                    exit_reason = "regime_change"
                    exit_price = row["close"]
                elif i - entry_idx >= max_bars:
                    exit_reason = "timeout"
                    exit_price = row["close"]
                else:
                    if side == "long":
                        if row["low"] <= stop:
                            exit_reason = "stop"
                            exit_price = stop
                        elif row["high"] >= tp:
                            exit_reason = "tp"
                            exit_price = tp
                    else:
                        if row["high"] >= stop:
                            exit_reason = "stop"
                            exit_price = stop
                        elif row["low"] <= tp:
                            exit_reason = "tp"
                            exit_price = tp

                if exit_reason:
                    slippage = slippage_pct if side == "long" else -slippage_pct
                    exit_price = exit_price * (1 - slippage) if side == "long" else exit_price * (1 + slippage)
                    pnl = (exit_price - entry_price) / entry_price if side == "long" else (entry_price - exit_price) / entry_price
                    pnl -= total_fee_pct
                    equity *= 1 + pnl
                    equity_curve.append(equity)
                    trades.append({
                        "side": side,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl_pct": pnl,
                        "bars": i - entry_idx,
                        "exit_reason": exit_reason,
                    })
                    in_trade = None

                continue

            if not range_active:
                setup_side = None
                setup_index = None
                continue

            prev_row = df.iloc[i - 1]
            setup_long = row["low"] <= row["bb_lower"] and row["rsi_14"] <= DEFAULT_RANGE_CONFIG["rsi_setup_long"]
            setup_short = row["high"] >= row["bb_upper"] and row["rsi_14"] >= DEFAULT_RANGE_CONFIG["rsi_setup_short"]
            long_reentry = prev_row["close"] <= prev_row["bb_lower"] and row["close"] >= row["bb_lower"]
            short_reentry = prev_row["close"] >= prev_row["bb_upper"] and row["close"] <= row["bb_upper"]
            long_rejection = row["low"] <= row["bb_lower"] and row["close"] >= row["bb_lower"]
            short_rejection = row["high"] >= row["bb_upper"] and row["close"] <= row["bb_upper"]

            breakout_band = (row["close"] > row["bb_upper"]) or (row["close"] < row["bb_lower"])
            breakout_vol = row["atr_pct"] > DEFAULT_RANGE_CONFIG["breakout_atr_pct_threshold"]
            rolling_high = df["high"].iloc[max(0, i - 20):i + 1].max()
            rolling_low = df["low"].iloc[max(0, i - 20):i + 1].min()
            breakout_donchian = (row["close"] > rolling_high) or (row["close"] < rolling_low)
            breakout_event = breakout_band and breakout_vol and breakout_donchian
            guard_lookback = DEFAULT_RANGE_CONFIG["breakout_guard_lookback"]
            if guard_lookback > 1:
                recent_window = df.iloc[max(0, i - guard_lookback + 1): i + 1]
                breakout_recent = (
                    (recent_window["close"] > recent_window["bb_upper"])
                    | (recent_window["close"] < recent_window["bb_lower"])
                ) & (recent_window["atr_pct"] > DEFAULT_RANGE_CONFIG["breakout_atr_pct_threshold"])
                breakout_recent = breakout_recent.any()
            else:
                breakout_recent = breakout_event

            if breakout_recent:
                setup_side = None
                setup_index = None
                continue

            if setup_index is not None and (i - setup_index) >= DEFAULT_RANGE_CONFIG["setup_ttl_bars"]:
                setup_side = None
                setup_index = None

            if setup_long:
                setup_side = "long"
                setup_index = i
            elif setup_short:
                setup_side = "short"
                setup_index = i

            trigger_long = (
                setup_side == "long"
                and (long_reentry or long_rejection)
                and row["rsi_14"] >= DEFAULT_RANGE_CONFIG["rsi_trigger_long"]
            )
            trigger_short = (
                setup_side == "short"
                and (short_reentry or short_rejection)
                and row["rsi_14"] <= DEFAULT_RANGE_CONFIG["rsi_trigger_short"]
            )

            if trigger_long or trigger_short:
                side = "long" if trigger_long else "short"
                entry_slippage = slippage_pct if side == "long" else -slippage_pct
                entry_price = row["close"] * (1 + entry_slippage) if side == "long" else row["close"] * (1 - entry_slippage)
                atr_val = row["atr_14"]
                sl_distance = atr_val * sl_atr_mult
                if hard_stop_pct > 0:
                    sl_distance = min(sl_distance, entry_price * hard_stop_pct)
                stop = entry_price - sl_distance if side == "long" else entry_price + sl_distance
                tp = row["bb_mid"]
                if pd.isna(tp):
                    continue
                in_trade = {
                    "side": side,
                    "entry_price": entry_price,
                    "stop": stop,
                    "tp": tp,
                    "entry_idx": i,
                }
                setup_side = None
                setup_index = None

        def summarize(trade_slice: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not trade_slice:
                return {
                    "trades": 0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "expectancy": 0.0,
                    "max_drawdown": 0.0,
                    "max_consecutive_losses": 0,
                    "avg_bars": 0.0,
                    "median_bars": 0.0,
                }
            wins = [t for t in trade_slice if t["pnl_pct"] > 0]
            losses = [t for t in trade_slice if t["pnl_pct"] <= 0]
            total_win = sum(t["pnl_pct"] for t in wins)
            total_loss = abs(sum(t["pnl_pct"] for t in losses))
            profit_factor = total_win / total_loss if total_loss > 0 else 0.0
            expectancy = sum(t["pnl_pct"] for t in trade_slice) / len(trade_slice)
            bars = [t["bars"] for t in trade_slice]
            bars_sorted = sorted(bars)
            median_bars = bars_sorted[len(bars_sorted) // 2] if bars_sorted else 0.0

            max_consec_losses = 0
            current_losses = 0
            for t in trade_slice:
                if t["pnl_pct"] <= 0:
                    current_losses += 1
                    max_consec_losses = max(max_consec_losses, current_losses)
                else:
                    current_losses = 0

            return {
                "trades": len(trade_slice),
                "win_rate": len(wins) / len(trade_slice),
                "profit_factor": profit_factor,
                "expectancy": expectancy,
                "max_consecutive_losses": max_consec_losses,
                "avg_bars": sum(bars) / len(bars),
                "median_bars": median_bars,
            }

        split_idx = int(len(trades) * train_split)
        train_trades = trades[:split_idx]
        test_trades = trades[split_idx:]
        equity_series = pd.Series(equity_curve)
        rolling_max = equity_series.cummax()
        drawdown = ((equity_series - rolling_max) / rolling_max).min() if not equity_series.empty else 0.0

        payload = {
            "symbol": symbol,
            "params": {
                "entry_interval": entry_interval,
                "regime_interval": regime_interval,
                "sl_atr_mult": sl_atr_mult,
                "max_bars": max_bars,
                "fee_pct": fee_pct,
                "slippage_pct": slippage_pct,
                "train_split": train_split,
                "hard_stop_pct": hard_stop_pct,
            },
            "performance": {
                "train": summarize(train_trades),
                "test": summarize(test_trades),
                "overall": summarize(trades),
                "max_drawdown": drawdown,
            },
            "trades_sample": trades[-10:],
        }
        return self._sanitize_for_json(payload)
