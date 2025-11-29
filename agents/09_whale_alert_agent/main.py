import os, httpx, time
from fastapi import FastAPI

app = FastAPI()
KEY = os.getenv("WHALE_ALERT_API_KEY")

@app.get("/get_alerts")
async def whales():
    if not KEY: return {"summary": "No Key"}
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                "https://api.whale-alert.io/v1/transactions",
                params={"api_key": KEY, "min_value": 10000000, "start": int(time.time())-3600, "limit": 5}
            )
            txs = r.json().get("transactions", [])
            summary = ", ".join([f"{t['symbol']} ${t['amount_usd']//1000000}M" for t in txs if t['symbol'] in ['BTC','ETH','SOL']])
            return {"summary": summary if summary else "Quiet"}
    except: return {"summary": "API Error"}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
