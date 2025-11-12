import pandas as pd
import numpy as np
from scipy.stats import linregress

def calculate_rsi(data, window=14):
    """Calcola l'Relative Strength Index (RSI)."""
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(data, window=20, num_std_dev=2):
    """Calcola le Bande di Bollinger."""
    rolling_mean = data['close'].rolling(window=window).mean()
    rolling_std = data['close'].rolling(window=window).std()
    upper_band = rolling_mean + (rolling_std * num_std_dev)
    lower_band = rolling_mean - (rolling_std * num_std_dev)
    return upper_band, lower_band

def calculate_macd(data, slow_window=26, fast_window=12, signal_window=9):
    """Calcola il Moving Average Convergence Divergence (MACD)."""
    ema_slow = data['close'].ewm(span=slow_window, adjust=False).mean()
    ema_fast = data['close'].ewm(span=fast_window, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal_line

def calculate_trend_strength(data):
    """Calcola la forza del trend usando la pendenza della regressione lineare."""
    x = np.arange(len(data))
    y = data['close'].values
    slope, _, _, _, _ = linregress(x, y)
    return slope * 1000  # Moltiplicato per un fattore per renderlo più leggibile

def analyze(market_data: pd.DataFrame):
    """
    Funzione principale che esegue l'analisi tecnica completa.
    
    Args:
        market_data (pd.DataFrame): DataFrame con colonne ['timestamp', 'open', 'high', 'low', 'close', 'volume'].
                                    Deve essere ordinato per timestamp.
    
    Returns:
        dict: Un dizionario contenente i valori degli ultimi indicatori calcolati.
    """
    if not isinstance(market_data, pd.DataFrame) or 'close' not in market_data.columns:
        raise ValueError("L'input deve essere un DataFrame di pandas con la colonna 'close'.")

    # Assicuriamoci che i dati siano ordinati
    market_data = market_data.sort_values('timestamp').reset_index(drop=True)

    # Calcolo indicatori
    rsi = calculate_rsi(market_data)
    upper_band, lower_band = calculate_bollinger_bands(market_data)
    macd, signal_line = calculate_macd(market_data)
    trend_strength = calculate_trend_strength(market_data)
    
    # Prendiamo solo l'ultimo valore calcolato per ogni indicatore
    latest_indicators = {
        "rsi": rsi.iloc[-1],
        "bollinger_upper": upper_band.iloc[-1],
        "bollinger_lower": lower_band.iloc[-1],
        "macd": macd.iloc[-1],
        "macd_signal": signal_line.iloc[-1],
        "trend_strength": trend_strength,
        "latest_price": market_data['close'].iloc[-1]
    }
    
    return latest_indicators

if __name__ == '__main__':
    # Esempio di utilizzo:
    # In un caso reale, caricheremmo i dati da un file o da un'API.
    print("Esecuzione di un test di esempio per l'analista tecnico...")
    
    # Creiamo dati fittizi per il test
    timestamps = pd.to_datetime(pd.date_range(start='2023-01-01', periods=100, freq='h'))
    close_prices = 50000 + np.random.randn(100).cumsum() * 50
    
    dummy_data = pd.DataFrame({
        'timestamp': timestamps,
        'open': close_prices - 10,
        'high': close_prices + 20,
        'low': close_prices - 20,
        'close': close_prices,
        'volume': np.random.rand(100) * 10
    })

    analysis_result = analyze(dummy_data)
    
    print("\nRisultato dell'analisi (ultimi valori):")
    import json
    print(json.dumps(analysis_result, indent=2))