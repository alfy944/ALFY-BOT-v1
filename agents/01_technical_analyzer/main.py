import pandas as pd
import pandas_ta as ta
import ccxt
import logging
from typing import List, Dict, Any

# --- CONFIGURAZIONE LOGGING DEFINITIVA ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("--- CODICE VERSIONE FINALE CARICATO ---")

from ta.trend import ADXIndicator, EMAIndicator
from ta.momentum import RSIIndicator, WilliamsRIndicator

def fetch_ohlcv(symbol: str, interval: str, limit: int = 100) -> list:
    logger.info(f"Recupero dati per {symbol}...")
    exchange = ccxt.binance()
    try:
        return exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
    except Exception as e:
        logger.error(f"ERRORE CCXT per {symbol}: {e}", exc_info=True)
        raise

def create_dataframe(ohlcv: list) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    if df.empty:
        raise ValueError("DataFrame vuoto ricevuto da CCXT.")
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    # Assicuriamoci che i tipi di dati siano corretti per i calcoli
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)
    return df

def run_analysis(symbol: str, interval: str, indicator_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    logger.info(f"--- INIZIO ANALISI PER {symbol} ---")
    try:
        ohlcv = fetch_ohlcv(symbol, interval)
        df = create_dataframe(ohlcv)
        results = {}

        for config in indicator_configs:
            name = config.get("name")
            length = config.get("length", 14)
            logger.info(f"Calcolo in corso: {name}({length})")
            try:
                if name == "RSI" and 'close' in df:
                    results['rsi'] = RSIIndicator(close=df['close'], window=length).rsi().iloc[-1]
                elif name == "EMA" and 'close' in df:
                    results[f'ema_{length}'] = EMAIndicator(close=df['close'], window=length).ema_indicator().iloc[-1]
                elif name == "ADX" and all(k in df for k in ['high', 'low', 'close']):
                    results['adx'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=length).adx().iloc[-1]
                elif name == "WilliamsR" and all(k in df for k in ['high', 'low', 'close']):
                    results['williams_r'] = WilliamsRIndicator(high=df['high'], low=df['low'], close=df['close'], lbp=length).williams_r().iloc[-1]
                logger.info(f"-> {name} calcolato con successo.")
            except Exception as e:
                logger.error(f"!! CRASH nel calcolo di {name} per {symbol}: {e}", exc_info=True)
                results[name] = None  # Inserisci None se il calcolo fallisce

        if len(df) > 1:
            last_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]
            pivot = (prev_candle['high'] + prev_candle['low'] + prev_candle['close']) / 3
            results.update({
                "pivot_point": pivot,
                "latest_price": last_candle['close']
            })
        else:
            results.update({"pivot_point": None, "latest_price": df.iloc[-1]['close'] if not df.empty else None})

        logger.info(f"--- FINE ANALISI PER {symbol} ---")
        return results

    except Exception as e:
        logger.critical(f"!!! CRASH FATALE nell'analisi di {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
