from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from textblob import TextBlob
import requests
import logging
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NewsRequest(BaseModel):
    symbol: str

app = FastAPI()

@app.get("/")
async def read_root():
    return {"status": "News Sentiment Agent is running"}

def get_crypto_news(symbol: str) -> List[Dict[str, Any]]:
    base_symbol = symbol.split('/')[0]
    url = f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories={base_symbol.upper()}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return [{"title": article["title"], "url": article["url"]} for article in data.get("Data", [])[:10]]
    except requests.exceptions.RequestException as e:
        logger.error(f"Errore API CryptoCompare: {e}")
        return []

def analyze_sentiment(text: str) -> float:
    return TextBlob(text).sentiment.polarity

@app.post("/analyze")
def analyze_news_sentiment(request: NewsRequest):
    logger.info(f"Ricevuta richiesta di analisi sentiment per {request.symbol}")
    articles = get_crypto_news(request.symbol)
    if not articles:
        return {"symbol": request.symbol, "average_sentiment_polarity": 0.0, "news_count": 0}

    total_polarity = sum(analyze_sentiment(article.get("title", "")) for article in articles)
    average_polarity = total_polarity / len(articles)
    
    return {
        "symbol": request.symbol,
        "average_sentiment_polarity": average_polarity,
        "news_count": len(articles),
    }
