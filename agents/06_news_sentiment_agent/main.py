import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time

app = FastAPI(title="News Sentiment Agent")

API_KEY = os.getenv("CRYPTOPANIC_API_KEY")
BASE_URL = "https://cryptopanic.com/api/v1/posts/"

### --- INIZIO NUOVA LOGICA DI CACHING --- ###
CACHE_DURATION_SECONDS = 3600  # 1 ora
news_cache = {} # Cache per salvare i risultati
### --- FINE NUOVA LOGICA DI CACHING --- ###

class SentimentRequest(BaseModel):
    symbol: str

class SentimentResponse(BaseModel):
    sentiment_score: float
    summary: str

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/analyze_sentiment", response_model=SentimentResponse)
async def analyze_sentiment(request: SentimentRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="CryptoPanic API key non configurata.")

    currency_code = request.symbol.replace("USDT", "")
    current_time = time.time()

    ### --- INIZIO CONTROLLO CACHE --- ###
    # Controlla se abbiamo dati in cache e se non sono scaduti
    if currency_code in news_cache and (current_time - news_cache[currency_code]['timestamp'] < CACHE_DURATION_SECONDS):
        print(f"[{currency_code}] Servito dalla cache. Dati freschi.")
        return news_cache[currency_code]['data']
    ### --- FINE CONTROLLO CACHE --- ###

    print(f"[{currency_code}] Cache scaduta o non esistente. Contatto l'API di CryptoPanic...")
    params = {
        "auth_token": API_KEY,
        "currencies": currency_code,
        "public": "true"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()
        
        data = response.json()

        if not data.get('results'):
            # Anche se non ci sono notizie, mettiamo in cache il risultato per non chiedere di nuovo a vuoto
            result = SentimentResponse(sentiment_score=0.0, summary="Nessuna notizia recente trovata per la valuta.")
            news_cache[currency_code] = {'timestamp': current_time, 'data': result}
            return result

        total_votes = 0
        sentiment_accumulator = 0
        for news in data['results']:
            votes = news.get('votes', {})
            bullish = int(votes.get('bullish', 0))
            bearish = int(votes.get('bearish', 0))
            sentiment_accumulator += (bullish - bearish)
            total_votes += (bullish + bearish)
        
        sentiment_score = (sentiment_accumulator / total_votes) if total_votes > 0 else 0.0
        
        summary = f"Sentiment basato su {len(data['results'])} notizie. Punteggio: {sentiment_score:.2f}"
        result = SentimentResponse(sentiment_score=sentiment_score, summary=summary)
        
        ### --- INIZIO AGGIORNAMENTO CACHE --- ###
        # Salva i nuovi dati e il timestamp nella cache
        news_cache[currency_code] = {'timestamp': current_time, 'data': result}
        print(f"[{currency_code}] Cache aggiornata con successo.")
        ### --- FINE AGGIORNAMENTO CACHE --- ###
        
        return result

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Errore API CryptoPanic: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
