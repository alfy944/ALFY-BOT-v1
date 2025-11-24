import os
import requests
from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

app = FastAPI(title="Mitragliere Dashboard Pro")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

POSITION_AGENT = "http://position-manager-agent:8000"
MASTER_AI_AGENT = "http://master-ai-agent:8000"

def get_wallet_data():
    try:
        return requests.get(f"{POSITION_AGENT}/get_wallet_balance", timeout=3).json()
    except: return {"equity": 0, "available": 0, "pnl": 0, "error": "Conn Error"}

def get_positions_data():
    try:
        return requests.get(f"{POSITION_AGENT}/get_open_positions", timeout=3).json().get("details", [])
    except: return []

def get_ai_config():
    try:
        return requests.get(f"{MASTER_AI_AGENT}/config", timeout=3).json()
    except: return {"mode": "calm", "risk_scale": 10, "max_leverage": 3}

def set_ai_config(data):
    try:
        requests.post(f"{MASTER_AI_AGENT}/config", json=data, timeout=3)
        return True
    except: return False

def get_equity_history(period="all"):
    try:
        return requests.get(f"{POSITION_AGENT}/get_history", params={"period": period}, timeout=3).json()
    except: return []

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/ui/balance", response_class=HTMLResponse)
async def ui_balance(request: Request):
    return templates.TemplateResponse("partials/balance_panel.html", {"request": request, "wallet": get_wallet_data()})

@app.get("/ui/open-positions", response_class=HTMLResponse)
async def ui_open_positions(request: Request):
    return templates.TemplateResponse("partials/open_positions_table.html", {"request": request, "positions": get_positions_data()})

@app.get("/ui/config", response_class=HTMLResponse)
async def ui_config_get(request: Request):
    return templates.TemplateResponse("partials/config_form.html", {"request": request, "config": get_ai_config(), "saved": False})

@app.post("/ui/config", response_class=HTMLResponse)
async def ui_config_post(request: Request, mode: str = Form(...), risk_scale: int = Form(...), max_leverage: int = Form(...)):
    new_conf = {"mode": mode, "risk_scale": risk_scale, "max_leverage": max_leverage}
    set_ai_config(new_conf)
    # Restituisce il form con il flag 'saved=True' per mostrare il messaggio
    return templates.TemplateResponse("partials/config_form.html", {"request": request, "config": new_conf, "saved": True})

@app.get("/ui/chart", response_class=HTMLResponse)
async def ui_chart(request: Request, period: str = Query("all")):
    data = get_equity_history(period)
    # Prepara i dati per Chart.js
    labels = [d['date'].split(" ")[1] if period == "day" else d['date'] for d in data]
    values = [d['equity'] for d in data]
    
    return templates.TemplateResponse("partials/equity_chart.html", {
        "request": request, "labels": labels, "values": values
    })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8501)
