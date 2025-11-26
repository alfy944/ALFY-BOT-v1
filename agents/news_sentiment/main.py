"""
News & Sentiment Agent v2.1 (PRODUCTION OPTIMIZED)
==================================================
OTTIMIZZAZIONI:
1. Cache in memoria con TTL 15 minuti
2. Batch fetching: UNA chiamata API per TUTTE le crypto
3. Endpoint /refresh_all per pre-caricare la cache
"""

import os
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="News Sentiment Agent (Optimized)", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

API_KEY = os.getenv("COINGECKO_API_KEY")
BASE_URL = "https://api.coingecko.com/api/v3"
CACHE_TTL_SECONDS = int(os.getenv("SENTIMENT_CACHE_TTL", "900"))

SYMBOL_TO_ID = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "BNBUSDT": "binancecoin", "SOLUSDT": "solana",
    "XRPUSDT": "ripple", "ADAUSDT": "cardano", "DOGEUSDT": "dogecoin", "AVAXUSDT": "avalanche-2",
    "LINKUSDT": "chainlink", "MATICUSDT": "matic-network", "LTCUSDT": "litecoin", "DOTUSDT": "polkadot"
}
COINGECKO_IDS = list(SYMBOL_TO_ID.values())
ID_TO_SYMBOL = {v: k for k, v in SYMBOL_TO_ID.items()}

class SentimentCache:
    def __init__(self, ttl: int = 900):
        self.ttl = ttl
        self.data: Dict[str, Dict] = {}
        self.last_update: Optional[datetime] = None
        self.lock = asyncio.Lock()
    
    def is_valid(self) -> bool:
        if not self.last_update: return False
        return (datetime.now() - self.last_update).total_seconds() < self.ttl
    
    def get(self, symbol: str) -> Optional[Dict]:
        return self.data.get(symbol.upper()) if self.is_valid() else None
    
    async def update(self, data: Dict[str, Dict]):
        async with self.lock:
            self.data = data
            self.last_update = datetime.now()
    
    def get_status(self) -> Dict:
        age = int((datetime.now() - self.last_update).total_seconds()) if self.last_update else -1
        return {"valid": self.is_valid(), "age_seconds": age, "ttl_seconds": self.ttl, "symbols_cached": len(self.data)}

sentiment_cache = SentimentCache(ttl=CACHE_TTL_SECONDS)

def calculate_sentiment_score(price_change: float) -> float:
    return round(max(-1, min(1, price_change / 20)), 3)

def get_sentiment_label(score: float) -> str:
    if score >= 0.4: return "STRONG_BULLISH"
    if score >= 0.2: return "BULLISH"
    if score <= -0.4: return "STRONG_BEARISH"
    if score <= -0.2: return "BEARISH"
    return "NEUTRAL"

async def fetch_batch_market_data() -> Dict[str, Dict]:
    results = {}
    ids_string = ",".join(COINGECKO_IDS)
    url = f"{BASE_URL}/coins/markets"
    params = {"vs_currency": "usd", "ids": ids_string, "order": "market_cap_desc", "per_page": 250, "page": 1, "sparkline": "false", "price_change_percentage": "24h,7d"}
    headers = {"x-cg-demo-api-key": API_KEY} if API_KEY else {}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            if response.status_code == 429:
                print("[WARN] CoinGecko rate limit!")
                return {}
            response.raise_for_status()
            data = response.json()
        for coin in data:
            coin_id = coin.get("id", "")
            symbol = ID_TO_SYMBOL.get(coin_id)
            if not symbol: continue
            price_change_24h = float(coin.get("price_change_percentage_24h", 0) or 0)
            sentiment_score = calculate_sentiment_score(price_change_24h)
            results[symbol] = {
                "symbol": symbol, "coin_id": coin_id, "sentiment_score": sentiment_score,
                "sentiment_label": get_sentiment_label(sentiment_score),
                "price_change_24h": round(price_change_24h, 2),
                "price_change_7d": round(float(coin.get("price_change_percentage_7d_in_currency", 0) or 0), 2),
                "current_price": float(coin.get("current_price", 0) or 0),
                "market_cap_rank": coin.get("market_cap_rank", 0),
                "community_sentiment": 50.0, "source": "coingecko_batch",
                "fetched_at": datetime.now().isoformat()
            }
        print(f"[INFO] Batch fetch: {len(results)} coins")
        return results
    except Exception as e:
        print(f"[ERROR] fetch_batch: {e}")
        return {}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "news-sentiment-agent", "version": "2.1.0", "cache": sentiment_cache.get_status()}

@app.post("/refresh_all")
async def refresh_all_sentiment():
    print("[INFO] Refreshing all sentiment data...")
    data = await fetch_batch_market_data()
    if data:
        await sentiment_cache.update(data)
        return {"status": "refreshed", "symbols_updated": len(data), "cache": sentiment_cache.get_status()}
    return {"status": "error", "message": "Failed to fetch", "cache": sentiment_cache.get_status()}

@app.get("/analyze_market_data/{symbol}")
async def analyze_market_data(symbol: str):
    symbol_upper = symbol.upper()
    cached = sentiment_cache.get(symbol_upper)
    if cached:
        return {**cached, "from_cache": True, "cache_age_seconds": sentiment_cache.get_status()["age_seconds"]}
    print(f"[INFO] Cache miss for {symbol_upper}")
    data = await fetch_batch_market_data()
    if data:
        await sentiment_cache.update(data)
        cached = sentiment_cache.get(symbol_upper)
        if cached: return {**cached, "from_cache": False}
    return {"symbol": symbol_upper, "sentiment_score": 0.0, "sentiment_label": "NEUTRAL", "price_change_24h": 0.0, "source": "fallback"}

@app.get("/all_sentiment")
async def get_all_sentiment():
    if not sentiment_cache.is_valid():
        data = await fetch_batch_market_data()
        if data: await sentiment_cache.update(data)
    return {"data": sentiment_cache.data if sentiment_cache.is_valid() else {}, "cache": sentiment_cache.get_status()}

@app.on_event("startup")
async def startup():
    print(f"[STARTUP] Cache TTL: {CACHE_TTL_SECONDS}s, Symbols: {len(SYMBOL_TO_ID)}")
    data = await fetch_batch_market_data()
    if data:
        await sentiment_cache.update(data)
        print(f"[STARTUP] Cache populated: {len(data)} symbols")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
