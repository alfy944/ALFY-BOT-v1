import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from textblob import TextBlob
import logging

# Configurazione del logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- LA RIGA MANCANTE CHE HA CAUSATO TUTTO ---
# Creiamo l'istanza dell'applicazione FastAPI
app = FastAPI()
# --------------------------------------------

# Modello Pydantic per validare i dati in input
class SentimentRequest(BaseModel):
    symbols: List[str]

# Funzione per recuperare la chiave API in modo sicuro
def get_api_key():
    api_key = os.getenv("CRYPTOPANIC_API_KEY")
    if not api_key:
        logger.error("La variabile d'ambiente CRYPTOPANIC_API_KEY non è stata trovata.")
        raise ValueError("Manca la variabile d'ambiente CRYPTOPANIC_API_KEY")
    return api_key

@app.post("/get_sentiment")
async def get_sentiment(request_data: SentimentRequest):
    """
    Riceve una lista di simboli (es. ["BTC", "ETH"]), contatta l'API di CryptoPanic,
    e calcola il sentiment medio delle notizie recenti.
    """
    try:
        api_key = get_api_key()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    sentiments = {}
    for symbol in request_data.symbols:
        logger.info(f"Recupero notizie per il simbolo: {symbol}")
        
        # Costruisci l'URL per l'API di CryptoPanic
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={api_key}&currencies={symbol}&public=true"
        
        try:
            response = requests.get(url)
            response.raise_for_status()  # Lancia un errore per status HTTP 4xx/5xx
            data = response.json()

            if not data['results']:
                logger.warning(f"Nessuna notizia trovata per {symbol}")
                sentiments[symbol] = {"average_sentiment": 0, "news_count": 0}
                continue

            total_polarity = 0
            news_count = len(data['results'])

            for post in data['results']:
                # Usa TextBlob per analizzare il titolo della notizia
                analysis = TextBlob(post['title'])
                total_polarity += analysis.sentiment.polarity
            
            # Calcola il sentiment medio (da -1 a 1)
            average_sentiment = total_polarity / news_count if news_count > 0 else 0
            sentiments[symbol] = {"average_sentiment": average_sentiment, "news_count": news_count}
            logger.info(f"Sentiment per {symbol}: {average_sentiment:.2f} basato su {news_count} notizie.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Errore nella chiamata API a CryptoPanic per {symbol}: {e}")
            # Non bloccare tutto se un simbolo fallisce, ma segnalalo
            sentiments[symbol] = {"error": f"Errore API: {e}"}
        except Exception as e:
            logger.error(f"Errore inaspettato durante l'analisi di {symbol}: {e}")
            sentiments[symbol] = {"error": f"Errore interno: {e}"}
            
    return sentiments

@app.get("/")
def read_root():
    return {"message": "News Sentiment Agent è attivo e funzionante!"}
