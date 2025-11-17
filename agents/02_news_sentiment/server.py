from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from main import get_cryptopanic_sentiment

class SentimentRequest(BaseModel):
    # CryptoPanic funziona meglio con i simboli delle valute (es. BTC, ETH)
    currencies: List[str]

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "News Sentiment Agent (CryptoPanic Edition) è attivo."}

@app.post("/analyze-sentiment")
def analyze_sentiment_endpoint(request: SentimentRequest):
    if not request.currencies:
        raise HTTPException(status_code=400, detail="La lista 'currencies' non può essere vuota.")
        
    result = get_cryptopanic_sentiment(currencies=request.currencies)
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
        
    return result