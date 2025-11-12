# agents/02_news_sentiment/server.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Importiamo la logica principale
from .main import run_full_news_analysis

app = FastAPI(
    title="News Sentiment Agent",
    description="Un agente che recupera notizie crypto e ne analizza il sentiment.",
    version="1.0.0",
)

# Definiamo il modello di input: ci aspettiamo un JSON con una chiave api_key
class NewsInput(BaseModel):
    cryptopanic_api_key: str

@app.post("/analyze_news/")
async def get_sentiment(input_data: NewsInput):
    """
    Esegue l'analisi del sentiment sulle ultime notizie crypto.
    Richiede una chiave API valida per CryptoPanic.
    """
    if not input_data.cryptopanic_api_key or input_data.cryptopanic_api_key == "YOUR_CRYPTO_PANIC_API_KEY":
        raise HTTPException(status_code=400, detail="Chiave API di CryptoPanic non fornita o non valida.")

    analysis_result = run_full_news_analysis(api_key=input_data.cryptopanic_api_key)
    
    return analysis_result

@app.get("/")
def health_check():
    return {"status": "News Sentiment Agent is running"}