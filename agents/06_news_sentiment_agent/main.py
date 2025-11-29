from fastapi import FastAPI
import random

app = FastAPI()

@app.get("/global_sentiment")
def sentiment():
    # Restituisce un valore Fear & Greed simulato/realistico
    return {
        "score": 25,
        "label": "Fear",
        "sentiment_score": -0.5
    }

@app.get("/health")
def health(): return {"status": "ok"}
