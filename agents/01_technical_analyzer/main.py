import pandas as pd
import pandas_ta as ta
import ccxt
import logging
import numpy as np  # Importiamo numpy per i calcoli di Gann
from typing import List, Dict, Any

# --- CONFIGURAZIONE LOGGING DEFINITIVA ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("--- CODICE VERSIONE FINALE + GANN/FIBO CARICATO ---")

from ta.trend import ADXIndicator, EMAIndicator
from ta.momentum import RSIIndicator, WilliamsRIndicator

def fetch_ohlcv(symbol: str, interval: str, limit: int = 100) -> list:
    logger.info(f"Recupero dati per {symbol}...")
    exchange = ccxt.binance()
    try:
        # Aumentiamo il limite per avere più storico per Fibo/Gann
        return exchange.fetch_ohlcv(symbol, timeframe=interval, limit=max(limit, 200))
    except Exception as e:
        logger.error(f"ERRORE CCXT per {symbol}: {e}", exc_info=True)
        raise

def create_dataframe(ohlcv: list) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    if df.empty:
        raise ValueError("DataFrame vuoto ricevuto da CCXT.")
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)
    return df

# --- NUOVA FUNZIONE: CALCOLO FIBONACCI ---
def calculate_fibonacci_levels(df: pd.DataFrame) -> Dict[str, float]:
    """Calcola i livelli di ritracciamento di Fibonacci."""
    try:
        high_price = df['high'].max()
        low_price = df['low'].min()
        price_range = high_price - low_price

        return {
            "fibo_0.0": high_price,
            "fibo_23.6": high_price - (price_range * 0.236),
            "fibo_38.2": high_price - (price_range * 0.382),
            "fibo_50.0": high_price - (price_range * 0.5),
            "fibo_61.8": high_price - (price_range * 0.618),
            "fibo_78.6": high_price - (price_range * 0.786),
            "fibo_100.0": low_price,
        }
    except Exception as e:
        logger.error(f"Errore nel calcolo di Fibonacci: {e}")
        return {} # Ritorna un dizionario vuoto in caso di errore

# --- NUOVA FUNZIONE: CALCOLO GANN (SQUARE OF 9) ---
def calculate_gann_levels(latest_price: float) -> Dict[str, float]:
    """Calcola i livelli di supporto/resistenza con la Gann Square of 9."""
    try:
        base_sqrt = np.sqrt(latest_price)
        
        # Livelli di resistenza
        r1_sqrt = base_sqrt + 0.25 # Angolo di 90 gradi
        r2_sqrt = base_sqrt + 0.50 # Angolo di 180 gradi
        
        # Livelli di supporto
        s1_sqrt = base_sqrt - 0.25
        s2_sqrt = base_sqrt - 0.50
        
        return {
            "gann_r1": r1_sqrt ** 2,
            "gann_r2": r2_sqrt ** 2,
            "gann_s1": s1_sqrt ** 2,
            "gann_s2": s2_sqrt ** 2,
        }
    except Exception as e:
        logger.error(f"Errore nel calcolo di Gann: {e}")
        return {} # Ritorna un dizionario vuoto in caso di errore

def run_analysis(symbol: str, interval: str, indicator_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    logger.info(f"--- INIZIO ANALISI AVANZATA PER {symbol} ---")
    try:
        ohlcv = fetch_ohlcv(symbol, interval)
        df = create_dataframe(ohlcv)
        results = {}

        for config in indicator_configs:
            name = config.get("name")
            length = config.get("length", 14)
            logger.info(f"Calcolo in corso: {name}({length if name not in ['Fibonacci', 'Gann'] else 'N/A'})")
            
            try:
                # --- BLOCCO INDICATORI ESISTENTI ---
                if name == "RSI": results['rsi'] = RSIIndicator(df['close'], length).rsi().iloc[-1]
                elif name == "EMA": results[f'ema_{length}'] = EMAIndicator(df['close'], length).ema_indicator().iloc[-1]
                elif name == "ADX": results['adx'] = ADXIndicator(df['high'], df['low'], df['close'], length).adx().iloc[-1]
                elif name == "WilliamsR": results['williams_r'] = WilliamsRIndicator(df['high'], df['low'], df['close'], length).williams_r().iloc[-1]
                
                # --- NUOVE ANALISI ---
                elif name == "Fibonacci":
                    results.update(calculate_fibonacci_levels(df))
                elif name == "Gann":
                    latest_price = df['close'].iloc[-1]
                    results.update(calculate_gann_levels(latest_price))
                    
                logger.info(f"-> {name} calcolato con successo.")
            except Exception as e:
                logger.error(f"!! CRASH nel calcolo di {name} per {symbol}: {e}", exc_info=True)
                results[name.lower()] = None

        if len(df) > 1:
            results["latest_price"] = df.iloc[-1]['close']
        
        logger.info(f"--- FINE ANALISI PER {symbol} ---")
        return results

    except Exception as e:
        logger.critical(f"!!! CRASH FATALE nell'analisi di {symbol}: {e}", exc_info=True)
        # In un'API reale, questo dovrebbe essere gestito da un middleware
        # Qui lo rilanciamo per farlo apparire nel log di FastAPI/Uvicorn
        raise
