# agents/02_news_sentiment/main.py

import requests
from transformers import pipeline
import os

# Inizializziamo il modello di sentiment analysis una sola volta.
# La prima volta che esegui questo codice, scaricherà il modello (può richiedere tempo e spazio).
# Usiamo un modello più piccolo e veloce, ottimo per il nostro scopo.
print("Caricamento del modello di sentiment analysis...")
sentiment_pipeline = pipeline('sentiment-analysis', model="distilbert-base-uncased-finetuned-sst-2-english")
print("Modello caricato.")

def get_crypto_news(api_key: str):
    """Recupera le notizie da CryptoPanic."""
    if not api_key or api_key == "YOUR_CRYPTO_PANIC_API_KEY":
        print("ERRORE: Chiave API di CryptoPanic non valida.")
        return [] # Restituisce una lista vuota se la chiave non è impostata

    url = f"https://cryptopanic.com/api/v1/posts/?auth_token={api_key}&public=true"
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Solleva un errore per risposte http non riuscite (4xx o 5xx)
        data = response.json()
        # Estraiamo solo i titoli delle notizie
        titles = [post['title'] for post in data['results']]
        return titles
    except requests.exceptions.RequestException as e:
        print(f"Errore durante la chiamata a CryptoPanic: {e}")
        return []

def analyze_news_sentiment(news_titles: list):
    """Analizza il sentiment di una lista di titoli di notizie."""
    if not news_titles:
        return {
            "average_sentiment_score": 0,
            "sentiment_label": "NEUTRAL",
            "article_count": 0,
            "analysis_details": []
        }

    sentiments = sentiment_pipeline(news_titles)
    
    # Calcoliamo un punteggio medio. Convertiamo 'POSITIVE' in 1 e 'NEGATIVE' in -1.
    score = 0
    for i, sentiment in enumerate(sentiments):
        # Aggiungiamo il titolo originale al risultato per chiarezza
        sentiment['article_title'] = news_titles[i]
        if sentiment['label'] == 'POSITIVE':
            score += sentiment['score']
        else:
            score -= sentiment['score']
    
    average_score = score / len(news_titles)

    if average_score > 0.1:
        label = "POSITIVE"
    elif average_score < -0.1:
        label = "NEGATIVE"
    else:
        label = "NEUTRAL"

    return {
        "average_sentiment_score": round(average_score, 3),
        "sentiment_label": label,
        "article_count": len(news_titles),
        "analysis_details": sentiments
    }

def run_full_news_analysis(api_key: str):
    """Funzione principale che orchestra il recupero e l'analisi delle notizie."""
    print("Recupero delle notizie in corso...")
    news_titles = get_crypto_news(api_key)
    
    if not news_titles:
        print("Nessuna notizia trovata o errore API.")
        # Restituisce comunque una struttura dati valida
        return analyze_news_sentiment([])

    print(f"Trovate {len(news_titles)} notizie. Analisi del sentiment in corso...")
    analysis_result = analyze_news_sentiment(news_titles)
    print("Analisi completata.")
    
    return analysis_result
